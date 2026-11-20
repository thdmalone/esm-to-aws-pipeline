import pytest

from esm_aws_pipe.core.format_manifest import format_manifest
from esm_aws_pipe.core.project import init_project

from pandas import DataFrame


def test_format_manifest(tmp_path):
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

    manifest, _ = format_manifest(
        esm_export_path=run.esm_export,
        manifest_path=run.manifest,
        metadata_tracker=md,
        group_id_prefix="GRP",
        testing=True,
    )

    groups = [f"GRP-{i}" for i in images]

    assert (
        manifest.loc[2, "group"] == "GRP-3"
    ), f"Failed group extraction:\n\tExtracted: {manifest['group'].to_list()} | Expected: {groups}"

    assert (
        manifest.loc[1, "filename"] == "GRP-2 slide.svs"
    ), f'Failed filename extraction:\n\tExtracted: {manifest["filename"].to_list()} | Expected: {[f"{i} slide.svs" for i in groups]}'
