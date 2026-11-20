import pytest

from esm_aws_pipe.core.format_manifest import format_manifest
from esm_aws_pipe.core.project import init_project, ProcessMetadata

from pandas import DataFrame


def test_metadata_collection(tmp_path):
    batch_id = "test_batch"
    images = [1, 2, 3, 4]
    esm_export_data = {
        "Specimen Acc#": [batch_id for _ in range(len(images))],
        "Image ID": images,
        "File Location": [
            "//path/to/GRP-1 slide.svs",
            "//path/to/GRP-2 slide.svs",
            "//path/to/GRP-3 slide.svs",
            "//path/to/GRP-4 slide.svs",
        ],
    }
    proj = init_project(tmp_path / "proj")
    export_esm_to = proj.batches_dir / f"{batch_id}.csv"

    DataFrame(esm_export_data).to_csv(export_esm_to, index=False)

    run = proj.init_run(batch_id)
    md = run.get_metadata()

    _, metadata = format_manifest(
        esm_export_path=run.esm_export,
        manifest_path=run.manifest,
        metadata_tracker=md,
        group_id_prefix="GRP",
        testing=True,
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
