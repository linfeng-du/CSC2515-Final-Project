import torch
import torch.nn as nn


def mlp(sizes, activation=nn.ReLU):
    # Build a feedforward neural network.
    layers = []
    for j in range(len(sizes)-1):
        act = activation
        layers += [nn.Linear(sizes[j], sizes[j+1]), act()]
    return nn.Sequential(*layers)


def cls_classifier(sizes):
    # Build a feedforward neural network.
    layers = []
    layers += [nn.Linear(sizes, 10), nn.Softmax()]
    return nn.Sequential(*layers)


def domain_classifier(size, n_domains):
    # Build a feedforward neural network.
    layers = []
    layers += [nn.Linear(size, n_domains), nn.Softmax()]
    return nn.Sequential(*layers)


class MLP_Swap(nn.Module):
    def __init__(self, sizes):
        super(MLP_Swap, self).__init__()

        self.mlp1 = mlp(sizes[:-1])
        self.mlp2 = mlp(sizes[-2:])

    def forward(self, x, mode="train"):
        feature = self.mlp1(x)
        batch_szie = feature.shape[0]
        latent_dim = feature.shape[1]
        if mode == "train":
            feature_swaped = torch.clone(feature)
            feature_swaped[0:batch_szie//2, latent_dim//2:] = feature[batch_szie//2:, latent_dim//2:]
            feature_swaped[batch_szie//2:, latent_dim//2:] = feature[0:batch_szie//2, latent_dim//2:]
            return self.mlp2(feature_swaped), feature[:, 0:latent_dim//2]
        else:
            return self.mlp2(feature), feature[:, 0:latent_dim//2]
