from pathlib import Path

import typer

from esm_aws_pipe.core.format_manifest import format_manifest
from esm_aws_pipe.core.compression import load_and_validate_manifest, compress
from esm_aws_pipe.core.provenance import ProcessMetadata
from esm_aws_pipe.utils import ensure_dir

app = typer.Typer()


@app.command("process")
def process_batch(
    batch_id: str = typer.Option(..., "--batch_id"),
    esm_export_file: Path = typer.Option(..., "--esm_export_path"),
    out_dir: Path = typer.Option(..., "--out_path"),
    save_manifest: bool = typer.Option(True),
):
    """Compress groups of WSIs to ZIP and upload to AWS

    Parameters
    ----------
        batch_id : str
            The research ID associated with this batch
            (e.g., Rxx-xxxx)

        esm_export_file : Path
            Path to the CSV export from eSlideManager containing
            Aperio File Location and Image ID information.

        out_dir : Path
            Path to the output directory where zip files
            and processing metadata will be saved to

    """

    metadata = ProcessMetadata(batch_id=batch_id, save_dir=out_dir)

    ensure_dir(out_dir)

    manifest, metadata = format_manifest(
        esm_export_path=esm_export_file,
        save_dir=out_dir,
        group_id_prefix="JDI",
        save_manifest=save_manifest,
        metadata_tracker=metadata,
    )
