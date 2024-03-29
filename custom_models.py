import torch
import torch.nn as nn
import torch.nn.init as init
import torch.nn.functional as F
from torchvision import models

class AvgPool(nn.Module):
    def forward(self, x):
        return torch.nn.functional.avg_pool2d(x, (x.size(2), x.size(3)))

class ResNet(nn.Module):
    def __init__(self, num_classes, net_cls=models.resnet50, pretrained=False):
        super(ResNet, self).__init__()
        self.net = net_cls(pretrained=pretrained)
        self.net.avgpool = AvgPool()
        
        self.fc = nn.Sequential(
            nn.Linear(self.net.fc.in_features+1, 512),
            nn.Dropout(0.3),
            nn.Linear(512, 128),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes)
        )
        self.net.fc = nn.Dropout(0.0)
        
    def fresh_params(self):
        return self.net.fc.parameters()
    
    def forward(self, x, O): #0, 1, 2, 3 -> (0, 3, 1, 2)
        out = torch.transpose(x, 1, 3) #0, 3, 2, 1
        out = torch.transpose(out, 2, 3) #0, 3, 1, 2
        out = self.net(out)
        out = out.view(out.size(0), -1)
        out = torch.cat([out, O], 1)
        return self.fc(out)
    
class DenseNet201(nn.Module):
    def __init__(self, num_classes, freeze=True):
        super(DenseNet201, self).__init__()
        
        net = models.densenet201(pretrained=True)
        num_ftrs = net.classifier.in_features
        
        self.features = nn.Sequential(*list(net.children())[:-1])
        
        self.classifier = nn.Sequential(
            nn.Linear(num_ftrs, 512),
            nn.Dropout(0.3),
            nn.Linear(512, 128),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes)
        )
    
    def fresh_params(self):
        return self.net.classifier.parameters()
    
    def forward(self, x, O): #0, 1, 2, 3 -> (0, 3, 1, 2)
        out = torch.transpose(x, 1, 3) #0, 3, 2, 1
        out = torch.transpose(out, 2, 3) #0, 3, 1, 2
    
        f = self.features(out)
        f = F.relu(f, inplace=True)
        f = F.avg_pool2d(f, (f.size(2), f.size(3))).view(f.size(0), -1)
        y = self.classifier(f)
        return y