import shutil
from typing import Optional, Union, Literal
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from esm_aws_pipe.utils import Clock
from esm_aws_pipe.core.provenance import ProcessMetadata

REQUIRED_MANIFEST_HEADERS = {"Image ID", "File Location", "dest_dir"}


def load_and_validate_manifest(
    manifest: Union[Path, pd.DataFrame],
    root_destination_directory: Optional[Path] = None,
):
    """Loads manifest CSV data and validates file locations

    Parameters
    ----------
        manifest_path : Path or DataFrame
            Path to or Dataframe of the CSV file containing
            ESM exported metadata (Image ID, File Location,
            etc) and the destination dirs for all images to
            copy and upload into AWS

        root_destination_dir : Optional[Path], default=None
            Helpful if processing 2+ collections of whole
            slide image groupings (e.g., patient, tumor type,
            etc). Zipped folders pertaining to each group of
            WSIs are saved to this directory. If provided, the
            `dest_dir` column in the manifest can be relative,
            and only refer to the name of the parent folder for
            the group of WSIs; otherwise, `dest_dir` is expected
            to contain complete paths.


    """
    if isinstance(manifest, Path):
        if not manifest.exists():
            raise FileNotFoundError(f"No manifest file found at {manifest}")

        if manifest.suffix != ".csv":
            raise ValueError(f"Expected a CSV file, not {manifest.suffix}")

        manifest = pd.read_csv(manifest)

    print(f"--- Identified {len(manifest)} images to process ---")

    # validate required headers
    current_headers = set(manifest.columns)
    missing_reqs = REQUIRED_MANIFEST_HEADERS.difference(current_headers)
    if any(missing_reqs):
        raise ValueError(
            f"Missing the following required columns in the manifest: {missing_reqs}"
        )

    return manifest


def clean_manifest():
    """

    Perform the following cleanings task:
        1. Update destination dir to `save_dir`/<group>
            Images are temporarily moved here prior
            to compression
        2. Add group id to filenames if needed to finalize
           the destination path


    """


def compress(
    manifest: pd.DataFrame,
    outdir: Path,
    metadata_tracker: Optional[ProcessMetadata] = None,
    missing_group_behavior: Literal["ignore", "group"] = "group",
):
    """Temporarily move WSIs to a folder for compression

    Parameters
    ----------
        manifest : DataFrame
            Structurally validated manifest detailing
            images and associated metadata required for
            processing

        out_dir : Path
            Zipped files are saved here

        metadata_tracker : Optional[ProcessMetadata], default=None
            Object for tracking processing metadata

        missing_group_behavior : {"ignore", "group"}
            Defines how to handle WSIs without a group ID in the manifest
            * "ignore": images are skipped
            * "group": images are saved to a directory labelled "unknown_group"

    """
    clock = Clock()
    clock.start()

    # append filename to dst dir
    corrected_dst = (
        manifest["dest_dir"].astype(str) + "\\" + manifest["filename"].astype(str)
    )

    # reformat to derive src-dst path pairs
    src_dst = pd.concat([manifest["File Location"], corrected_dst], axis=1).set_axis(
        ["src", "dst"], axis=1
    )
    paired_paths = list(src_dst.itertuples(index=False, name=None))

    # move images from Aperio into a temporary directory that will be compressed
    for src, dst in tqdm(paired_paths, desc="Moving from Aperio"):
        source = Path(src)
        destination = Path(dst)

        destination.parent.mkdir(parents=True, exist_ok=True)

        shutil.copyfile(source, destination)

    shutil.make_archive(base_name="out", root_dir=outdir, format="zip")

    # move images back to Aperio
    for src, dst in paired_paths:
        source = Path(src)
        destination = Path(dst)

        shutil.move(destination, source)

    clock.end()


# copy into destination folder - shutil.copyfile()
# compress destination folder - shutil.make_archive()
