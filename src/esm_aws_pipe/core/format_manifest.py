"""Creates processing manifest from raw ESM exports
and handles any intermediate pre-processing

"""

from typing import Optional, Union
from pathlib import Path

import pandas as pd
import numpy as np

from esm_aws_pipe.core.provenance import ProcessMetadata
from esm_aws_pipe.utils import Clock

REQ_ESM_EXPORT_COLS = {"Image ID", "File Location"}


def format_manifest(
    esm_export_path: Path,
    save_dir: Optional[Path] = None,
    default_dest_dir: Optional[Union[Path, str]] = None,
    save_manifest: bool = True,
    group_id_prefix: str = "JDI",
    testing: bool = False,
    metadata_tracker: Optional[ProcessMetadata] = None,
) -> tuple[pd.DataFrame, Optional[ProcessMetadata]]:
    """Format manifest from raw ESM export

    Parameters
    ----------
        esm_export_path : Path
            Path to the CSV file containing the raw ESM export metadata

        save_dir : Path
            Path to the directory where the manifest will be saved to

        default_dest_dir : Optional[Path | str], default=None
            Optionally specify a default destination directory for images
            to be used whenever

    Returns
    -------
        manifest : DataFrame
            The processing manifest

    """
    clock = Clock()
    clock.start()

    if not esm_export_path.exists():
        raise FileNotFoundError(f"No ESM export file found at {esm_export_path}")

    if esm_export_path.suffix != ".csv":
        raise ValueError(f"Expected a CSV file, not {esm_export_path.suffix}")

    esm_export = pd.read_csv(esm_export_path)
    print(f"--- Identified {len(esm_export)} images to exported from ESM ---")

    # ESM exports data with extra comma at end, creating a false column
    esm_export = esm_export.dropna(axis=1)

    current_headers = set(esm_export.columns)
    missing_reqs = REQ_ESM_EXPORT_COLS.difference(current_headers)
    if any(missing_reqs):
        raise ValueError(
            f"Missing required headers: {missing_reqs}\n\nMust re-export data from ESM with this option selected"
        )

    manifest = esm_export.assign(dest_dir="")  # placeholder column NOTE might move

    # validate Aperio locations and extract filenames
    manifest = manifest.assign(
        valid_location=manifest["File Location"].apply(lambda x: Path(x).exists()),
        filename=manifest["File Location"].apply(lambda x: Path(x).name),
    )
    manifest = manifest.assign(
        group=manifest["filename"].apply(
            lambda x: (
                x.split(" ")[0]
                if x.split(" ")[0].startswith(group_id_prefix)
                else np.nan
            )
        )
    )

    dropped: list[str] = []

    def validate_aperio_location(m: pd.DataFrame) -> pd.DataFrame:
        n_valid_locations = m[m["valid_location"] == True]["valid_location"].count()
        print(f"--- {n_valid_locations} image(s) with valid Aperio location(s) ---")
        if n_valid_locations != len(m):
            dropped = m[m["valid_location"] == False]["filename"].to_list()
            print(
                f"\nWARNING: Dropping the following image(s) due to invalid Aperio location(s):"
            )
            for i, image in enumerate(dropped, 1):
                print(f"\t{i}) {image}")

            m = m[m["valid_location"] == True]

        return m

    # will always fail in testing given false paths
    # ignore filtering if so
    if not testing:
        # check for valid Aperio locations (e.g., WSIs moved, renamed, or deleted)

        manifest = validate_aperio_location(manifest)

    # check for missing JDI identification
    missing_jdi = manifest[manifest["group"].isna()]
    if not missing_jdi.empty:
        print(
            f"\nWARNING: The following images are missing a {group_id_prefix} number:"
        )
        for i, image in enumerate(missing_jdi["File Location"].to_list(), 1):
            print(f"\t{i}) {image}")

        solution_text = f"\t*These images will not be removed from the manifest; however, the the {group_id_prefix} number must be manually input into the manifest in the `group` column. Images with persistently missing {group_id_prefix} numbers during uploading will be skipped silently later"
        print(solution_text.expandtabs(2))

    endtime = clock.end()

    # save manifest
    if save_manifest:
        if not isinstance(save_dir, Path):
            raise TypeError(
                f"Unexpected `save_dir` type: {type(save_dir)}. Must supply Path"
            )
        if not save_dir.is_dir():
            raise FileExistsError(
                f"Must supply path to a directory, not {save_dir.name}"
            )

        save_path = save_dir / "esm_to_aws_manifest.csv"
        manifest.to_csv(save_path, index=False)

        if isinstance(metadata_tracker, ProcessMetadata):
            metadata_tracker.add_manifest_metadata(
                path=save_path,
            )

        print(f"Saved manifest to {save_path}")

    # add to running metadata tracker if provided
    if isinstance(metadata_tracker, ProcessMetadata):
        metadata_tracker.add_esm_export_metadata(
            path=esm_export_path,
            identified_exports=len(esm_export),
            dropped_images=dropped,
            missing_group_id_count=len(missing_jdi),
            missing_group_id_filenames=missing_jdi["File Location"].to_list(),
        )

        metadata_tracker.add_manifest_metadata(
            created_in=endtime,
            total_wsis=len(manifest),
            total_groups=manifest["group"].nunique(),
        )

    return manifest, metadata_tracker
