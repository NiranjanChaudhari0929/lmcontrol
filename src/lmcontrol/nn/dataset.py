import numpy as np
from lightly.data import LightlyDataset
import torch
from torch.utils.data import Dataset
import torchvision.transforms.v2 as T


from ..data_utils import load_npzs
from ..utils import get_logger


class GaussianNoise(T._transform.Transform):
    """Applies random Gaussian noise to a tensor.

    The intensity of the noise is dependent on the mean of the pixel values.
    See https://arxiv.org/pdf/2101.04909.pdf for more information.

    """
    def __init__(self, p=0.5, sigma=(6, 10)):
        super().__init__()
        self.p = p
        self.sigma = sigma

    def __call__(self, sample: torch.Tensor) -> torch.Tensor:
        if torch.rand(1)[0] < self.p:
            mu = sample.to(float).mean()
            snr = self.sigma
            if isinstance(self.sigma, tuple):
                snr = torch.randint(low=self.sigma[0], high=self.sigma[1], size=(1,))
            sigma = mu / snr
            noise = torch.normal(torch.zeros(sample.shape), sigma)
            if sample.dtype == torch.uint8:
                noise = noise.to(torch.uint8)
            return sample + noise
        return sample


class LMDataset(Dataset):

    def __init__(self, npzs, use_masks=False, return_labels=False, logger=None):
        """
        Args:
            npzs (array-like)       : A list or tuple of paths to NPZ files containing cropped images
        """
        logger = logger or get_logger('warning')
        masks, images, paths, metadata = load_npzs(npzs, logger)
        if use_masks:
            self.data = masks
        else:
            self.data = images
        self.data = torch.from_numpy(self.data)[:, None, :, :]
        self.paths = tuple(paths)
        self.transform = None

    def __getitem__(self, i):
        ret = self.data[i]
        if self.transform is not None:
            ret = self.transform(ret)
        return ret, -1

    def __len__(self):
        return len(self.data)

    @staticmethod
    def index_to_filename(dataset, i):
        return dataset.paths[i]


TRANSFORMS = {
        'blur': T.GaussianBlur(3, sigma=(0.01, 1.0)),
        'rotate': T.RandomRotation(180),
        'crop': T.CenterCrop((64, 64)),
        'hflip': T.RandomHorizontalFlip(0.5),
        'vflip': T.RandomVerticalFlip(0.5),
        'noise': GaussianNoise(sigma=(10, 12)),
        'rgb': T.Lambda(lambda x: x.repeat(3, 1, 1) if x.ndim == 3 else x.repeat(1, 3, 1, 1)),
        'float': T.Lambda(lambda x: x.to(torch.float32)),
}


def get_transforms(*transforms):
    """Return a transforms appropriate for Ambr light microscopy data

    The following transforms and their respective keys are:
        blur:       A Gaussian Blur
        rotate:     Random rotation of up to 180 degrees in either direction
        crop:       Center crop images to 64x64 pixels
        hflip:      Random horizontal rotation with probability of 0.5
        vflip:      Random vertical rotation with probability of 0.5
        noise:      Randomly apply noise with probability of 0.5. Noise magnitude
                    will be between 10-12 signal-to-noise ratio
        rgb:        Convert to RGB format i.e. 3 channels
        float:      Convert to torch.Float dtype

    Args:
        transforms: the list of transforms to get. Valid options are 'blur', 'rotate', 'crop',
                    'hflip', 'vflip', 'noise', 'rgb', 'float'.
    Returns:
        a single transform or a Compose object pipeline with transforms in the order they
        are given. If no transforms are specified, the identity transform will be returned
    """
    if len(transforms) == 0:
        return lambda x: x
    ret = list()
    for tfm in transforms:
        if tfm not in TRANSFORMS:
            raise ValueError(f"Unrecognozed transform: '{tfm}'")
        ret.append(TRANSFORMS[tfm])
    return ret[0] if len(ret) == 1 else T.Compose(ret)



def get_lightly_dataset(npzs, transform=None, **lmdset_kwargs):
    """Helper function for getting a LightlyDataset"""
    dataset = LMDataset(npzs, **lmdset_kwargs)
    return LightlyDataset.from_torch_dataset(dataset,
                                             transform=transform,
                                             index_to_filename=dataset.index_to_filename)