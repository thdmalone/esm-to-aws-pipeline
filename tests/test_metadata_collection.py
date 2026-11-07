import pytest

from esm_aws_pipe.core.format_manifest import format_manifest
from esm_aws_pipe.core.provenance import ProcessMetadata

from pandas import DataFrame


def test_metadata_collection(tmp_path):
    images = [1, 2, 3, 4]
    esm_export_data = {
        "Image ID": images,
        "File Location": [
            "//path/to/GRP-1 slide.svs",
            "//path/to/GRP-2 slide.svs",
            "//path/to/GRP-3 slide.svs",
            "//path/to/GRP-4 slide.svs",
        ],
    }

    export_path = tmp_path / "manifest.csv"
    DataFrame(esm_export_data).to_csv(export_path, index=False)

    metadata_tracker = ProcessMetadata("test_batch", tmp_path)

    _, metadata = format_manifest(
        esm_export_path=export_path,
        save_manifest=False,
        group_id_prefix="GRP",
        testing=True,
        metadata_tracker=metadata_tracker,
    )

    assert isinstance(metadata, ProcessMetadata)
    assert isinstance(metadata._ctime, str), f"Failure updating the creation time"

    # validate content category existence
    manifest_metadata_keys = {"created_in", "total_wsis", "total_groups"}
    export_metadata_keys = {
        "path",
        "identified_exports",
        "dropped_images",
        "missing_group_id_count",
        "missing_group_id_filenames",
    }

    missing_mani_keys = manifest_metadata_keys.difference(
        set(metadata.manifest_metadata.keys())
    )
    missing_expo_keys = export_metadata_keys.difference(
        set(metadata.esm_export_metadata.keys())
    )

    assert not any(
        missing_mani_keys
    ), f"Failed collecting manifest metadata for {missing_mani_keys}"
    assert not any(
        missing_expo_keys
    ), f"Failed collecting export metadata for {missing_expo_keys}"

    # validate content value parsing
    assert (
        metadata.esm_export_metadata["missing_group_id_count"] == 0
    ), f"Identified {metadata.esm_export_metadata["missing_group_id_count"]} images without a group id in the filename"
