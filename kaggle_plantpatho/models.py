from typing import Optional, Union

import torch
import torchmetrics
import torchvision
from pytorch_lightning import LightningModule
from torch import nn, Tensor
from torch.nn import functional as F


class LitResnet(nn.Module):

    def __init__(self, arch: str, pretrained: bool = True, num_classes: int = 6):
        super().__init__()
        self.arch = arch
        self.num_classes = num_classes
        self.model = torchvision.models.__dict__[arch](pretrained=pretrained)
        num_features = self.model.fc.in_features
        self.model.fc = nn.Linear(num_features, num_classes)

    def forward(self, x):
        return self.model(x)


class LitPlantPathology(LightningModule):
    """
    This model is meant and tested to be used together with `PlantPathologySimpleDataset`
    """

    def __init__(
        self,
        model: Union[nn.Module, str] = "ResNet50",
        lr: float = 1e-4,
        augmentations: Optional[nn.Module] = None,
    ):
        super().__init__()
        if isinstance(model, str):
            model = LitResnet(arch=model)
        self.model = model
        self.arch = model.arch
        self.num_classes = model.num_classes
        self.train_accuracy = torchmetrics.Accuracy()
        self.train_precision = torchmetrics.Precision(**self._metrics_extra_args)
        self.train_f1_score = torchmetrics.F1(**self._metrics_extra_args)
        self.val_accuracy = torchmetrics.Accuracy()
        self.val_precision = torchmetrics.Precision(**self._metrics_extra_args)
        self.val_f1_score = torchmetrics.F1(**self._metrics_extra_args)
        self.learning_rate = lr
        self.aug = augmentations

    @property
    def _metrics_extra_args(self):
        return dict()

    def forward(self, x: Tensor) -> Tensor:
        return F.softmax(self.model(x))

    def compute_loss(self, y_hat: Tensor, y: Tensor):
        return F.cross_entropy(y_hat, y)

    def training_step(self, batch, batch_idx):
        x, y = batch
        if self.aug:
            x = self.aug(x)  # => batched augmentations
        y_hat = self(x)
        loss = self.compute_loss(y_hat, y)
        self.log("train_loss", loss, prog_bar=False)
        self.log("train_acc", self.train_accuracy(y_hat, y), prog_bar=False)
        self.log("train_prec", self.train_precision(y_hat, y), prog_bar=False)
        self.log("train_f1", self.train_f1_score(y_hat, y), prog_bar=True)
        return loss

    def validation_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = self.compute_loss(y_hat, y)
        self.log("valid_loss", loss, prog_bar=False)
        self.log("valid_acc", self.val_accuracy(y_hat, y), prog_bar=True)
        self.log("valid_prec", self.val_precision(y_hat, y), prog_bar=True)
        self.log("valid_f1", self.val_f1_score(y_hat, y), prog_bar=True)

    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=self.learning_rate)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, self.trainer.max_epochs, 0)
        return [optimizer], [scheduler]


class MultiPlantPathology(LitPlantPathology):
    """
    This model is meant and tested to be used together with `PlantPathologyDataset`
    """

    @property
    def _metrics_extra_args(self):
        return dict(num_classes=self.num_classes, average='weighted')

    def forward(self, x: Tensor) -> Tensor:
        return torch.sigmoid(self.model(x))

    def compute_loss(self, y_hat: Tensor, y: Tensor):
        return F.binary_cross_entropy_with_logits(y_hat, y.to(y_hat.dtype))
