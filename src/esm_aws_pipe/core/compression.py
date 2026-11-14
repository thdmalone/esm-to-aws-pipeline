from shutil import make_archive, rmtree, copyfile
from typing import Optional, Union, Literal
from pathlib import Path

from pandas import DataFrame, read_csv
from tqdm import tqdm

from esm_aws_pipe.utils import Clock
from esm_aws_pipe.core.provenance import ProcessMetadata

REQUIRED_MANIFEST_HEADERS = {"Image ID", "File Location"}


def load_and_validate_manifest(
    manifest: Union[Path, DataFrame],
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

        manifest = read_csv(manifest)

    print(f"--- Identified {len(manifest)} images to process ---")

    # validate required headers
    current_headers = set(manifest.columns)
    missing_reqs = REQUIRED_MANIFEST_HEADERS.difference(current_headers)
    if any(missing_reqs):
        raise ValueError(
            f"Missing the following required columns in the manifest: {missing_reqs}"
        )

    return manifest


def compress(
    manifest: DataFrame,
    outdir: Path,
    metadata_tracker: Optional[ProcessMetadata] = None,
    missing_group_behavior: Literal["ignore", "group"] = "group",
    testing: bool = False,
) -> Union[ProcessMetadata, None]:
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
    from subprocess import run

    def _update_group(m: DataFrame, d: bool) -> DataFrame:
        # WSIs that are still missing a group IDs
        missing_group = m[m["group"].isna() == True]

        # tracking variables
        dropped = 0
        no_group = []

        if any(missing_group):
            n_missing = len(missing_group)
            print(
                f"WARNING: {n_missing} WSIs that are still missing a group ID | drop_ungrouped = {d}"
            )
            no_group = missing_group["File Location"].to_list()
            for i in no_group:
                print(f"* {i}")

            if d:
                dropped = n_missing
                m = m[m["group"].isna() == False]
            else:
                m.loc[missing_group.index, "group"] = "ungrouped"

        if isinstance(metadata_tracker, ProcessMetadata):
            metadata_tracker.add_compression_metadata(
                drop_ungrouped_images=d,
                n_images_dropped=dropped,
                missing_group=no_group,
            )

        return m

    def _copy_files(paths: list[tuple[str, str]]):
        for src, dst in paths:
            source = Path(src)
            destination = Path(dst)

            destination.parent.mkdir(parents=True, exist_ok=True)

            copyfile(source, destination)

    def _delete_copies(dir: Path):
        """Delete folders of copied images"""
        try:
            # this should work if folders are local
            rmtree(dir)
        except Exception:  # specify actual exception
            # shutil.rmtree doesnt seem to work when removing
            # dirs in CHLA sharepoint so this force deletes
            run(["cmd", "/c", "rmdir", "/s", "/q", dest_dir])

    clock = Clock()
    clock.start()

    drop = True if missing_group_behavior == "ignore" else False
    cleaned_manifest = _update_group(manifest, drop)

    # format destination paths
    cleaned_manifest = cleaned_manifest.assign(
        dst_dir=f"{str(outdir)}\\"
        + cleaned_manifest["group"].astype(str)
        + "\\"
        + cleaned_manifest["filename"].astype(str)
    )

    # move images from Aperio into a temporary directory that will be compressed
    zipped_paths = []
    for group_id, group_df in tqdm(
        list(cleaned_manifest.groupby("group")), desc="Compressing groups"
    ):
        dest_dir = outdir / str(group_id)
        paired_paths = list(
            group_df[["File Location", "dst_dir"]].itertuples(index=False, name=None)
        )
        if not testing:
            _copy_files(paired_paths)

        zipped_path = make_archive(
            base_name=dest_dir, root_dir=dest_dir, format="zip"  # type: ignore
        )
        zipped_paths.append(zipped_path)

        # manually format target zip path to check existence
        zip_manual = outdir / f"{group_id}.zip"
        if zip_manual.exists():
            _delete_copies(dest_dir)
        else:
            # log warning of unexpected compression
            pass

    endtime = clock.end()

    if isinstance(metadata_tracker, ProcessMetadata):
        metadata_tracker.add_compression_metadata(
            elapsed_time=endtime,
            missing_group_behavior=missing_group_behavior,
            zipped_paths=zipped_paths,
        )

    return metadata_tracker


if __name__ == "__main__":
    mani = read_csv(
        r"C:\Users\thmalone\OneDrive - Childrens Hospital Los Angeles\Personal Research\Acute Projects\PLM AWS Upload\cli-test\esm_to_aws_manifest.csv"
    )
    od = Path(
        r"C:\Users\thmalone\OneDrive - Childrens Hospital Los Angeles\Personal Research\Acute Projects\PLM AWS Upload\cli-test"
    )
    mdt = ProcessMetadata("cli-test", od)

    compress(manifest=mani, outdir=od, metadata_tracker=mdt)
