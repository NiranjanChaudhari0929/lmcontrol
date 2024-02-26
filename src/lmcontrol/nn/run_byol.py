import argparse
import glob

import lightning as L
from lightning.pytorch.loggers import CSVLogger
from lightning.pytorch.callbacks.early_stopping import EarlyStopping
import numpy as np
import torch
from torch.utils.data import DataLoader

from ..utils import get_logger
from .dataset import get_lightly_dataset, get_transforms
from .byol import get_transform as BYOLTransform, BYOL


def get_npzs(timepoints, hts):
    ret = list()
    for tp in timepoints:
        for ht in hts:
            ret.extend(glob.glob(f"S{tp}/*HT{ht}/*.npz"))
    return ret


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", type=str, help="the experiment name")
    parser.add_argument("-c", "--checkpoint", type=str, help="checkpoint file to pick up from", default=None)
    parser.add_argument("-e", "--epochs", type=int, help="the number of epochs to run for", default=10)
    parser.add_argument("-d", "--debug", action='store_true', help="run with a small dataset", default=False)

    args = parser.parse_args(argv)

    logger = get_logger('info')


    if args.debug:
        train_files = get_npzs(["14", "4"], ["1"])
        val_files = get_npzs(["10"], ["5"])
    else:
        train_files = get_npzs(["4", "14"], ["1", "2", "3", "4", "6", "7", "8", "9", "11", "12"])
        val_files = get_npzs(["10"], ["5", "10"])

    train_tfm = BYOLTransform()
    val_tfm = BYOLTransform(
            transform1=get_transforms('rotate', 'crop', 'hflip', 'vflip', 'float', 'rgb'),
            transform2=get_transforms('crop', 'float', 'rgb'),
            )

    logger.info(f"Loading training data: {len(train_files)} files")
    train_dataset = get_lightly_dataset(train_files, transform=train_tfm, logger=logger)
    logger.info(f"Loading validation data: {len(val_files)} files")
    val_dataset = get_lightly_dataset(val_files, transform=val_tfm, logger=logger)

    model = BYOL()

    train_dl = DataLoader(
        train_dataset,
        batch_size=256,
        shuffle=True,
        drop_last=True,
        num_workers=3,
    )

    val_dl = DataLoader(
        val_dataset,
        batch_size=256,
        shuffle=False,
        drop_last=True,
        num_workers=3,
    )

    accelerator = "gpu" if torch.cuda.is_available() else "cpu"

    trainer = L.Trainer(max_epochs=args.epochs, devices=1, accelerator=accelerator,
                        logger=CSVLogger(".", name=args.experiment),
                        callbacks=[EarlyStopping(monitor=model.val_metric, min_delta=0.001, patience=3, mode="min")])

    trainer.fit(model=model, train_dataloaders=train_dl, val_dataloaders=val_dl)

def predict(argv=None):

    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=str, help="path to the model checkpoint file to use for inference")
    parser.add_argument("output_npz", type=str, help="the path to save the embeddings to. Saved in NPZ format")
    parser.add_argument("-d", "--debug", action='store_true', help="run with a small dataset", default=False)
    parser.add_argument("-p", "--pred-only", action='store_true', default=False,
                        help="only save predictions, otherwise save original image data and labels in output_npz")

    args = parser.parse_args(argv)

    logger = get_logger('info')

    if args.debug:
        test_files = sorted(glob.glob(f"S4/*HT*1/*.npz"))
    else:
        test_files = sorted(glob.glob(f"S*/*HT*/*.npz"))

    transform = get_transforms('crop', 'float', 'rgb')
    logger.info(f"Loading training data: {len(test_files)} files")
    test_dataset = get_lightly_dataset(test_files, transform=transform, logger=logger, return_labels=True)

    test_dl = DataLoader(test_dataset, batch_size=512, shuffle=False, drop_last=False, num_workers=3)

    model = BYOL.load_from_checkpoint(args.checkpoint)
    accelerator = "gpu" if torch.cuda.is_available() else "cpu"
    trainer = L.Trainer(devices=1, accelerator=accelerator)

    logger.info("Running predictions witih Lightning")
    predictions = trainer.predict(model, test_dl)
    predictions = torch.cat(predictions).numpy()

    out_data = dict(predictions=predictions)

    if not args.pred_only:
        dset = test_dataset.dataset
        out_data['images'] = np.asarray(torch.squeeze(dset.data))
        for i, k in enumerate(dset.label_types):
            out_data[k + "_classes"] = dset.label_classes[i]
            out_data[k + "_labels"] = np.asarray(dset.labels[:, i])

    np.savez(args.output_npz, **out_data)


if __name__ == '__main__':
    main()
