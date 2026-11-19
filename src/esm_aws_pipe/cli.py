from pathlib import Path
from typing import Annotated, Optional

import typer

from esm_aws_pipe.core.format_manifest import format_manifest
from esm_aws_pipe.core.compression import compress
from esm_aws_pipe.core.s3 import upload_groups, export_sharelinks
from esm_aws_pipe.core.provenance import ProcessMetadata, load_metadata
from esm_aws_pipe.utils import ensure_dir

app = typer.Typer(add_completion=False)


# --------------- Modular Commands ---------------
@app.command("manifest")
def create_manifest(
    esm_export_file: Annotated[Path, typer.Option(..., "--esm_export", "--in", "--i")],
    batch_id: Annotated[str, typer.Option("--batch_id", "--batch", "--b")] = "",
    infer_batch_id: Annotated[bool, typer.Option("--infer_batch")] = False,
    group_prefix: Annotated[str, typer.Option("--gp")] = "JDI",
):
    """Process the exported ESM CSV to prepare for compression and S3 uploading

    Parameters
    ----------

        esm_export_file : Path
            Path to the CSV export from eSlideManager containing Aperio
            File Location and Image ID information. The parent directory
            of this file is used for the output of all downstream tasks.

        batch_id : str
            The research ID associated with this batch (e.g., Rxx-xxxx)

        infer_batch : bool, default=False
            Can infer the batch ID from the name of the ESM export instead
            of explicitly providing it.

        group_prefix : str
            Prefix of image filenames indicating the grouping it belongs to


    """
    out_dir = esm_export_file.parent

    if infer_batch_id:
        batch_id = esm_export_file.stem

    metadata = ProcessMetadata(batch_id=batch_id, save_dir=out_dir)

    _, metadata = format_manifest(
        esm_export_path=esm_export_file,
        save_dir=out_dir,
        metadata_tracker=metadata,
        group_id_prefix=group_prefix,
    )

    if metadata.missing_groups:
        typer.echo(
            f"Images with missing group IDs detected. Please review the manifest and remediate:\n{out_dir.resolve() / 'esm_to_aws_manifest.csv'}\n\n"
        )

    metadata.export()


@app.command("compress")
def copy_and_compress(
    out_dir: Annotated[Path, typer.Option(..., "--out", "--o")],
    compression_type: Annotated[str, typer.Option("--compress", "--c")] = "zip",
    remove_ungrouped: Annotated[bool, typer.Option("--rm")] = False,
):
    """Copy WSIs then compress by groups to prepare for S3 upload

    Parameters
    ----------
        out_dir : Path
            Directory containing the ESM export and manifest

        remove_ungrouped : bool, default=False
            Specify where to remove images without a group ID in
            the `group` column of the manifest. Images without a
            group id are grouped under "ungrouped" by default.

        compression_type : str, default="zip"
            Specify how groups are compressed. Refer to
            https://docs.python.org/3/library/shutil.html#shutil.make_archive
            for more information on compression formats

    """

    metadata_path = out_dir / "process_metadata.json"
    metadata = load_metadata(metadata_path)

    manifest_path = out_dir / "esm_to_aws_manifest.csv"

    _, metadata = compress(
        manifest_path,
        out_dir,
        metadata,
        remove_ungrouped=remove_ungrouped,
        compression_type=compression_type,
    )

    metadata.export()


@app.command("upload")
def upload_to_s3(
    out_dir: Annotated[Path, typer.Option(..., "--out", "--o")],
    s3_bucket: Annotated[str, typer.Option(..., "--bucket", "--b")],
    s3_bucket_location: Annotated[str, typer.Option(..., "--key", "--k")],
    aws_region: Annotated[Optional[str], typer.Option("--region", "--r")] = None,
    export_links: Annotated[bool, typer.Option("--export-links")] = True,
):
    """Upload compressed files to S3 and generate an expirable, presigned share link
    for successful uploads.

    Parameters
    ----------
        out_dir : Path
            Directory containing the manifest and a "groups" subdirectory
            containing compressed WSI groups

        s3_bucket : str
            Name of the target S3 bucket

        s3_bucket_location : str
            Path-like location of the specific location within the bucket to
            upload to

        aws_region : str

        export_links : bool, default=True
            If true, extracts presigned url data from the metadata and saves it
            to a CSV for easier access.


    """
    metadata_path = out_dir / "process_metadata.json"
    metadata = load_metadata(metadata_path)

    # check for zipped files
    groups_dir = out_dir / "groups"

    if not groups_dir.exists():
        raise FileNotFoundError(
            f"Invalid directory: {groups_dir}.\n\nHave images been compressed?"
        )

    valid_compressions = list(groups_dir.glob("*.zip"))

    if not any(valid_compressions):
        raise FileNotFoundError(
            f"No compressed groups identified in this directory: {groups_dir}\n\nHave images been compressed? Review metadata file for zipped file locations: {metadata_path}"
        )

    metadata = upload_groups(
        compressed_groups=valid_compressions,
        bucket=s3_bucket,
        key=s3_bucket_location,
        metadata_tracker=metadata,
        aws_region=aws_region,
    )

    metadata.export()

    if export_sharelinks:
        links = export_sharelinks(out_dir, metadata)
        typer.echo(f"View AWS shareable links at {links}")


# --------------- Single Run / Breakpoint Commands ---------------


@app.command("from_esm")
def process_batch_esm(
    esm_export_file: Annotated[Path, typer.Option(..., "--esm_export", "--in", "--i")],
    batch_id: Annotated[str, typer.Option(..., "--batch_id", "--batch", "--b")] = "",
    infer_batch_id: Annotated[bool, typer.Option("--infer_batch")] = False,
    group_prefix: Annotated[str, typer.Option("--gp")] = "JDI",
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

        save_manifest : bool, default=True
            Export manifest to `out_dir` as "esm_to_aws_manifest.csv"

    """
    # TODO consider adding existence checks and overriding oversight
    out_dir = esm_export_file.parent

    if infer_batch_id:
        batch_id = esm_export_file.stem

    metadata = ProcessMetadata(batch_id=batch_id, save_dir=out_dir)

    manifest, metadata = format_manifest(
        esm_export_path=esm_export_file,
        save_dir=out_dir,
        metadata_tracker=metadata,
        group_id_prefix=group_prefix,
    )

    if metadata.missing_groups:
        typer.echo(
            f"Images with missing group IDs detected. Please review the manifest and remediate:\n{out_dir.resolve() / 'esm_to_aws_manifest.csv'}\n\n"
        )

        ready = typer.confirm("Ready to proceed?")
        if not ready:
            typer.echo(
                f"Terminating processing. Restart from ESM or continue directly from an existing manifest."
            )
            return

    zipped_paths, metadata = compress(
        manifest=manifest, outdir=out_dir, metadata_tracker=metadata
    )

    metadata.export()


@app.command("from_manifest")
def process_batch_manifest():
    """ """
