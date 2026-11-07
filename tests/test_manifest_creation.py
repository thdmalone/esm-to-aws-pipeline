import pytest

from esm_aws_pipe.core.format_manifest import format_manifest

from pandas import DataFrame


def test_format_manifest(tmp_path):
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

    manifest, _ = format_manifest(
        esm_export_path=export_path,
        save_manifest=False,
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
