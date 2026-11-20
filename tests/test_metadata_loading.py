from pathlib import Path

from esm_aws_pipe.core.provenance import ProcessMetadata, load_metadata


def test_metadata_loading(tmp_path):
    path = tmp_path / "process_metadata.json"
    mdo = ProcessMetadata("PYTEST-01", path)

    esm_metadata = {f"eem{n}": f"eem{n}" for n in range(1, 4)}
    manifest_metadata = {f"mm{n}": f"mm{n}" for n in range(1, 4)}
    compression_metadata = {f"cm{n}": f"cm{n}" for n in range(1, 4)}

    mdo.add_esm_export_metadata(**esm_metadata)
    mdo.add_manifest_metadata(**manifest_metadata)
    mdo.add_compression_metadata(**compression_metadata)
    mdo.export()

    loaded_mdo = load_metadata(path)

    assert (
        loaded_mdo.esm_export_metadata == esm_metadata
    ), f"Error loading ESM export metadata"
    assert (
        loaded_mdo.manifest_metadata == manifest_metadata
    ), f"Error loading manfiest metadata"
    assert (
        loaded_mdo.compression_metadata == compression_metadata
    ), f"Error loading compression metadata"
