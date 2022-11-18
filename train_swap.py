from DGDataset import DGDataset
import network
import torch
from torch.utils.data import DataLoader
import torch.nn as nn
import numpy as np
import argparse
from torch.optim import Adam
from torch.optim import lr_scheduler

parser = argparse.ArgumentParser()
parser.add_argument("--n_epochs", type=int, default=200, help="number of epochs of training")
parser.add_argument("--batch_size", type=int, default=256, help="size of the batches")
parser.add_argument("--lr", type=float, default=0.001, help="adam: learning rate")
parser.add_argument("--latent_dim", type=int, default=64, help="dimensionality of the latent space")
parser.add_argument("--img_size", type=int, default=32, help="size of each image dimension")
parser.add_argument("--target", type=str, default="syn", help="target domain")
parser.add_argument("--baseline", type=bool, default=False, help="baseline method")
parser.add_argument("--final_cls", type=str, default="latent", help="final classifier method")
opt = parser.parse_args()
print(opt)

Digits_DG = ["mnist", "mnist_m", "svhn", "syn"]
Digits_DG.remove(opt.target)
train_set = Digits_DG
train_loader = DataLoader(dataset=DGDataset(dataroots=train_set, mode="train"),
                          batch_size=opt.batch_size, shuffle=True, drop_last=True)
val_loader = DataLoader(dataset=DGDataset(dataroots=train_set, mode="val"),
                          batch_size=opt.batch_size, shuffle=True, drop_last=True)
test_loader = DataLoader(dataset=DGDataset([opt.target], mode="test"),
                          batch_size=opt.batch_size, shuffle=True, drop_last=True)

cuda = True if torch.cuda.is_available() else False
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
backbone = network.MLP_Swap([3 * opt.img_size ** 2, 512, opt.latent_dim * 4, opt.latent_dim]).to(device)
cls_classifier = network.cls_classifier(opt.latent_dim).to(device)
domain_classifier = None if opt.baseline else network.domain_classifier(opt.latent_dim, 3).to(device)
final_classifier = network.cls_classifier(opt.latent_dim).to(device) if opt.final_cls == "same" \
    else network.cls_classifier(opt.latent_dim * 2).to(device)

optimizer = Adam(backbone.parameters(), lr=opt.lr)
optimizer_cls = Adam(cls_classifier.parameters(), lr=opt.lr)
optimizer_final = Adam(final_classifier.parameters(), lr=opt.lr)
scheduler = lr_scheduler.StepLR(optimizer, step_size=100, gamma=0.1)
scheduler_cls = lr_scheduler.StepLR(optimizer_cls, step_size=100, gamma=0.1)
scheduler_final = lr_scheduler.StepLR(optimizer_final, step_size=50, gamma=0.1)
if domain_classifier is not None:
    optimizer_domain = Adam(domain_classifier.parameters(), lr=opt.lr)
    scheduler_domain = lr_scheduler.StepLR(optimizer_domain, step_size=100, gamma=0.1)
criterion = nn.CrossEntropyLoss()

def val_accuracy(final=False):
    total = 0
    correct = 0
    for it, (batch, domain) in enumerate(val_loader):
        x = batch[0].to(device)
        x = x.reshape(opt.batch_size, -1)
        y = batch[1].to(device)
        # feature = feature[:, :opt.latent_dim]
        if final == True:
            if opt.final_cls == "same":
                feature, _ = backbone(x, mode="test")
            else:
                _, feature = backbone(x, mode="test")
            scores = final_classifier(feature)
        else:
            feature, _ = backbone(x, mode="test")
            scores = cls_classifier(feature)
        _, pred = scores.max(dim=1)
        correct += torch.sum(pred.eq(y)).item()
        total += x.shape[0]
    return correct / total


def test_accuracy(final=False):
    total = 0
    correct = 0
    for it, (batch, domain) in enumerate(test_loader):
        x = batch[0].to(device)
        x = x.reshape(opt.batch_size, -1)
        y = batch[1].to(device)
        if final == True:
            if opt.final_cls == "same":
                feature, _ = backbone(x, mode="test")
            else:
                _, feature = backbone(x, mode="test")
            scores = final_classifier(feature)
        else:
            feature, _ = backbone(x, mode="test")
            scores = cls_classifier(feature)
        _, pred = scores.max(dim=1)
        correct += torch.sum(pred.eq(y)).item()
        total += x.shape[0]
    return correct / total

val_accs = []
test_accs = []
for epoch in range(opt.n_epochs):
    for it, (batch, domain) in enumerate(train_loader):
        x = batch[0]
        x = x.reshape(opt.batch_size, -1)
        y = batch[1]
        if cuda:
            x = x.cuda()
            y = y.cuda()
            domain = domain.cuda()
            tmp = torch.clone(domain)
            domain[:opt.batch_size // 2] = domain[opt.batch_size // 2:]
            domain[opt.batch_size // 2:] = tmp[:opt.batch_size // 2]

        # feature, _ = backbone(x)
        if domain_classifier is not None:
            feature, _ = backbone(x)
            scores_cls = cls_classifier(feature)
            loss_cls = criterion(scores_cls, y)
            scores_domain = domain_classifier(feature)
            loss_domain = criterion(scores_domain, domain)
            loss = loss_cls + 0.5 * loss_domain
        else:
            feature, _ = backbone(x, mode="baseline")
            scores = cls_classifier(feature)
            loss_cls = criterion(scores, y)
            loss = loss_cls
        optimizer.zero_grad()
        optimizer_cls.zero_grad()
        if domain_classifier is not None:
            optimizer_domain.zero_grad()
        loss.backward()
        optimizer.step()
        optimizer_cls.step()
        if domain_classifier is not None:
            optimizer_domain.step()
    scheduler.step()
    scheduler_cls.step()
    if domain_classifier is not None:
        scheduler_domain.step()
    val_acc = val_accuracy()
    test_acc = test_accuracy()
    if epoch > opt.n_epochs // 2:
        val_accs.append(val_acc)
        test_accs.append(test_acc)
    print("epoch : %d || loss : %f || val_acc : %f || test_acc : %f" % (epoch, loss, val_acc, test_acc))

print("Best val_acc : %f and its test_acc : %f" % (max(val_accs), test_accs[val_accs.index(max(val_accs))]))
print("Best test_acc : %f" % max(test_accs))

if opt.final_cls == "latent":
    val_accs = []
    test_accs = []
    for epoch in range(opt.n_epochs // 2):
        for it, (batch, domain) in enumerate(train_loader):
            x = batch[0]
            x = x.reshape(opt.batch_size, -1)
            y = batch[1]
            if cuda:
                x = x.cuda()
                y = y.cuda()
            if opt.final_cls == "same":
                feature, _ = backbone(x)
            else:
                _, feature = backbone(x)
            scores = final_classifier(feature)
            loss_cls = criterion(scores, y)
            loss = loss_cls
            optimizer_final.zero_grad()
            loss.backward()
            optimizer_final.step()
        scheduler_final.step()
        val_acc = val_accuracy(final=True)
        test_acc = test_accuracy(final=True)
        val_accs.append(val_acc)
        test_accs.append(test_acc)
        print("epoch : %d || loss : %f || val_acc : %f || test_acc : %f" % (epoch, loss, val_acc, test_acc))

    print("Best val_acc : %f and its test_acc : %f" % (max(val_accs), test_accs[val_accs.index(max(val_accs))]))
    print("Best test_acc : %f" % max(test_accs))

