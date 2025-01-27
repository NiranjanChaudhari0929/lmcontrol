import sys

from torch.utils.data import DataLoader

from .dataset import LMDataset
from ..utils import get_logger


def get_loaders(args, inference=True, tfm=None, train_tfm=None, val_tfm=None, return_labels=True, logger=None):
    logger = logger or get_logger('warning')

    dset_kwargs = dict(n_samples=args.n_samples,
                       logger=logger,
                       return_labels=return_labels)

    for attr in ('label', ):
        if hasattr(args, attr):
            dset_kwargs[attr] = getattr(args, attr)

    dl_kwargs = dict(num_workers=0 if args.debug else 3, batch_size=args.batch_size,
                     multiprocessing_context='spawn', persistent_workers=True)

    if inference:
        logger.info(f"Loading inference data from {args.input}")
        dataset = LMDataset(args.input, transform=tfm, **dset_kwargs)
        if args.split_seed is not None:
            dataset.set_random_split(0.1, 0.1, seed=args.split_seed)
        loader = DataLoader(dataset, worker_init_fn=dataset.open, **dl_kwargs)
        return loader
    else:
        logger.info(f"Loading training data from {args.input}")
        train_dataset = LMDataset(args.input, transform=train_tfm, split='train', **dset_kwargs)

        logger.info(f"Loading validation data from {args.input}")
        val_dataset = LMDataset(args.input, transform=val_tfm, split='validation', **dset_kwargs)

        if args.debug:
            train_dataset.open()
            val_dataset.open()

        if args.split_seed is not None:
            train_dataset.set_random_split(0.1, 0.1, seed=args.split_seed)
            val_dataset.set_random_split(0.1, 0.1, seed=args.split_seed)

        train_loader = DataLoader(train_dataset, shuffle=True, worker_init_fn=train_dataset.open, **dl_kwargs)
        val_loader = DataLoader(val_dataset, shuffle=False, worker_init_fn=val_dataset.open, **dl_kwargs)

        return train_loader, val_loader
