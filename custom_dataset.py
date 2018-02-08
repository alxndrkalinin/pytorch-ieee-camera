import random
from io import BytesIO
import math

import skimage
from PIL import Image
import jpeg4py as jpeg
import cv2

from torch.utils.data import Dataset

from utils import *

class IEEECameraDataset(Dataset):
    def __init__(self, items, crop_size, verbose=False, training=True):
        self.training = training 
        self.items = items
        self.crop_size = crop_size
        self.verbose = verbose
        validation = not training
        self.transforms = VALIDATION_TRANSFORMS if validation else [[]]
    
    def __len__(self):
        return len(self.items)
    
    def __getitem__(self, idx):
        sample = process_item(self.items[idx], self.crop_size, self.verbose, training=self.training, transforms=self.transforms)
        if sample is None:
            print(self.items[idx])
        
        X, O, y = sample

        return X, O, y

RESOLUTIONS = {
    0: [[1520,2688]], # flips
    1: [[3264,2448]], # no flips
    2: [[2432,4320]], # flips
    3: [[3120,4160]], # flips
    4: [[4128,2322]], # no flips
    5: [[3264,2448]], # no flips
    6: [[3024,4032]], # flips
    7: [[1040,780],  # Motorola-Nexus-6 no flips
        [3088,4130], [3120,4160]], # Motorola-Nexus-6 flips
    8: [[4128,2322]], # no flips 
    9: [[6000,4000]], # no flips
}

ORIENTATION_FLIP_ALLOWED = [
    True,
    False,
    True,
    True,
    False,
    False,
    True,
    True,
    False,
    False
]

for class_id, resolutions in RESOLUTIONS.copy().items():
    resolutions.extend([resolution[::-1] for resolution in resolutions])
    RESOLUTIONS[class_id] = resolutions

MANIPULATIONS = ['jpg70', 'jpg90', 'gamma0.8', 'gamma1.2', 'bicubic0.5', 'bicubic0.8', 'bicubic1.5', 'bicubic2.0']

load_img_fast_jpg  = lambda img_path: jpeg.JPEG(img_path).decode()
load_img           = lambda img_path: np.array(Image.open(img_path))

def load_img_fast_jpg(img_path):
    try:
        x = jpeg.JPEG(img_path).decode()
        return x
    except:
        return load_img(img_path)

def random_manipulation(img, manipulation=None):

    if manipulation == None:
        manipulation = random.choice(MANIPULATIONS)

    if manipulation.startswith('jpg'):
        quality = int(manipulation[3:])
        out = BytesIO()
        im = Image.fromarray(img)
        im.save(out, format='jpeg', quality=quality)
        im_decoded = jpeg.JPEG(np.frombuffer(out.getvalue(), dtype=np.uint8)).decode()
        del out
        del im
    elif manipulation.startswith('gamma'):
        gamma = float(manipulation[5:])
        # alternatively use skimage.exposure.adjust_gamma
        # img = skimage.exposure.adjust_gamma(img, gamma)
        im_decoded = np.uint8(cv2.pow(img / 255., gamma)*255.)
    elif manipulation.startswith('bicubic'):
        scale = float(manipulation[7:])
        im_decoded = cv2.resize(img,(0,0), fx=scale, fy=scale, interpolation = cv2.INTER_CUBIC)
    else:
        assert False
    return im_decoded

def get_crop(img, crop_size, random_crop=False):
    #print(img.shape)
    center_x, center_y = img.shape[1] // 2, img.shape[0] // 2
    half_crop = crop_size // 2
    pad_x = max(0, crop_size - img.shape[1])
    pad_y = max(0, crop_size - img.shape[0])
    if (pad_x > 0) or (pad_y > 0):
        img = np.pad(img, ((pad_y//2, pad_y - pad_y//2), (pad_x//2, pad_x - pad_x//2), (0,0)), mode='wrap')
        center_x, center_y = img.shape[1] // 2, img.shape[0] // 2
    if random_crop:
        freedom_x, freedom_y = img.shape[1] - crop_size, img.shape[0] - crop_size
        if freedom_x > 0:
            center_x += np.random.randint(math.ceil(-freedom_x/2.0), freedom_x - math.floor(freedom_x/2.0) )
        if freedom_y > 0:
            center_y += np.random.randint(math.ceil(-freedom_y/2.0), freedom_y - math.floor(freedom_y/2.0) )

    return img[center_y - half_crop : center_y + crop_size - half_crop, center_x - half_crop : center_x + crop_size - half_crop]

def process_item(item, crop_size, verbose, training, transforms=[[]]):
    class_name = item.split('/')[-2]
    class_idx = get_class(class_name)

    validation = not training 

    img = load_img_fast_jpg(item)
    
    shape = list(img.shape[:2])
#    if(training and (img.shape[0]<1 or img.shape[1]<1 or img.shape[2]<1)):
#        print('Loaded: {}'.format(item))

    # discard images that do not have right resolution
    #if shape not in RESOLUTIONS[class_idx]:
    #    return None

    # some images may not be downloaded correctly and are B/W, discard those
    if img.ndim != 3:
        print('BROKEN: {}'.format(item))
        return None

    if len(transforms) == 1:
        _img = img
    else:
        _img = np.copy(img)

        img_s         = [ ]
        manipulated_s = [ ]
        class_idx_s   = [ ]

    for transform in transforms:

        force_manipulation = 'manipulation' in transform

        if ('orientation' in transform) and (ORIENTATION_FLIP_ALLOWED[class_idx] is False):
            continue

        force_orientation  = ('orientation'  in transform) and ORIENTATION_FLIP_ALLOWED[class_idx]

        # some images are landscape, others are portrait, so augment training by randomly changing orientation
        if ((np.random.rand() < 0.5) and training and ORIENTATION_FLIP_ALLOWED[class_idx]) or force_orientation:
            img = np.rot90(_img, 1, (0,1))
            # is it rot90(..3..), rot90(..1..) or both? 
            # for phones with landscape mode pics could be taken upside down too, although less likely
            # most of the test images that are flipped are 1
            # however,eg. img_4d7be4c_unalt looks 3
            # and img_4df3673_manip img_6a31fd7_unalt looks 2!
        else:
            img = _img

#        rot_size= img.shape
#        if(training and (img.shape[0]<1 or img.shape[1]<1 or img.shape[2]<1)):
#            print('Rotated: {}, {}'.format(item, rot_size))
            
        img = get_crop(img, crop_size * 2, random_crop=True if training else False) 
        # * 2 bc may need to scale by 0.5x and still get a 512px crop
        
#        cr_size = img.shape
#        if(training and (img.shape[0]<1 or img.shape[1]<1 or img.shape[2]<1)):
#            print('Rotated: {}, {}'.format(item, rot_size))
#            print('Cropped: {}, {}'.format(item, cr_size))

        if verbose:
            print("om: ", img.shape, item)

        manipulated = 0.
        if ((np.random.rand() < 0.5) and training) or force_manipulation:
            img = random_manipulation(img)
            manipulated = 1.
            if verbose:
                print("am: ", img.shape, item)
        
#        man_size = img.shape
#        if(training and (img.shape[0]<1 or img.shape[1]<1 or img.shape[2]<1)):
#            print('Rotated: {}, {}'.format(item, rot_size))
#            print('Cropped: {}, {}'.format(item, cr_size))
#            print('Manipulated: {}, {}'.format(item, man_size))

        img = get_crop(img, crop_size, random_crop=True if training else False)
        if verbose:
            print("ac: ", img.shape, item)
            
#        if(training and (img.shape[0]<1 or img.shape[1]<1 or img.shape[2]<1)):
#            print('Rotated: {}, {}'.format(item, rot_size))
#            print('Cropped: {}, {}'.format(item, cr_size))
#            print('Manipulated: {}, {}'.format(item, man_size))
#            print('Cropped 2: {},{}'.format(item, img.shape))

        img = preprocess_image(img)# TODO:
        if verbose:
            print("ap: ", img.shape, item)
        
        if len(transforms) > 1:
            img_s.append(img)    
            manipulated_s.append(manipulated)
            class_idx_s.append(class_idx)
    
    if len(transforms) == 1:
        return img, np.array([manipulated], dtype=np.float32), class_idx
    else:
        return img_s, manipulated_s, class_idx_s

VALIDATION_TRANSFORMS = [ [], ['orientation'], ['manipulation'], ['orientation','manipulation']]

def preprocess_image(img):
    return img.astype(np.float32)

'''
def preprocess_image(img):
    
    if args.kernel_filter: TODO:
        # see slide 13
        # http://www.lirmm.fr/~chaumont/publications/WIFS-2016_TUAMA_COMBY_CHAUMONT_Camera_Model_Identification_With_CNN_slides.pdf
        kernel_filter = 1/12. * np.array([\
            [-1,  2,  -2,  2, -1],  \
            [ 2, -6,   8, -6,  2],  \
            [-2,  8, -12,  8, -2],  \
            [ 2, -6,   8, -6,  2],  \
            [-1,  2,  -2,  2, -1]]) 

        return cv2.filter2D(img.astype(np.float32),-1,kernel_filter)
        # kernel filter already puts mean ~0 and roughly scales between [-1..1]
        # no need to preprocess_input further
    else:
        # find `preprocess_input` function specific to the classifier
        classifier_to_module = { 
            'NASNetLarge'       : 'nasnet',
            'NASNetMobile'      : 'nasnet',
            'DenseNet40'        : 'densenet',
            'DenseNet121'       : 'densenet',
            'DenseNet161'       : 'densenet',
            'DenseNet201'       : 'densenet',
            'InceptionResNetV2' : 'inception_resnet_v2',
            'InceptionV3'       : 'inception_v3',
            'MobileNet'         : 'mobilenet',
            'ResNet50'          : 'resnet50',
            'VGG16'             : 'vgg16',
            'VGG19'             : 'vgg19',
            'Xception'          : 'xception',

        }

        if args.classifier in classifier_to_module:
            classifier_module_name = classifier_to_module[args.classifier]
        else:
            classifier_module_name = 'xception'

        preprocess_input_function = getattr(globals()[classifier_module_name], 'preprocess_input')
        return preprocess_input_function(img.astype(np.float32))
'''