from pandas import DataFrame

from esm_aws_pipe.core.compression import compress


def test_compression_saving(tmp_path):
    manifest_template = {
        "Specimen": ["test-01", "test-01", "test-01", "test-01"],
        "Image ID": [1, 2, 3, 4],
        "File Location": [
            "//path/to/GRP-1 slide.svs",
            "//path/to/GRP-2 slide.svs",
            "//path/to/GRP-3 slide.svs",
            "//path/to/GRP-4 slide.svs",
        ],
        "filename": [
            "GRP-1 slide.svs",
            "GRP-2 slide.svs",
            "GRP-3 slide.svs",
            "slide.svs",
        ],
        "group": [
            "GRP-1",
            "GRP-2",
            "GRP-3",
            "",
        ],
        "missing_group": [False, False, False, True],
    }

    manifest = DataFrame(manifest_template)

    zps, _ = compress(manifest=manifest, outdir=tmp_path, testing=True)

    target_zps = [str(tmp_path / gi) for gi in manifest_template["group"][:-1]]

    # test integrity check
    assert len(zps) == 4, f"Error saving zipped paths in `compress()`"
    assert len(target_zps) == 3, f"Error creating `target_zps` answer"

    # actual test
    assert all(i in zps for i in target_zps), f"Did not format zipped paths as expected"
