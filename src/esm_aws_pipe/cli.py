import os
from pathlib import Path
from typing import Annotated, Optional

import typer

from esm_aws_pipe.core.project import init_project, load_project
from esm_aws_pipe.core.format_manifest import format_manifest
from esm_aws_pipe.core.compression import compress
from esm_aws_pipe.core.s3 import (
    upload_groups,
    export_sharelinks,
    validate_identity_and_s3_access,
)
from esm_aws_pipe.core.provenance import ProcessMetadata, load_metadata
from esm_aws_pipe.utils import ensure_dir

app = typer.Typer(add_completion=False)


@app.command("new")
def create_project(project_path: Annotated[Path, typer.Option(..., "--path", "--p")]):
    """Start a new project

    Parameters
    ----------
        project_path : Path
            Path to a directory for this project; directory is created if it doesn't exist

    """
    ensure_dir(project_path)
    init_project(project_path)

    typer.echo(f"Successfully created a new project at {project_path}")


# --------------- Modular Commands ---------------
@app.command("manifest")
def create_manifest(
    project_path: Annotated[Path, typer.Option(..., "--project-path", "--p")],
    batch_id: Annotated[str, typer.Option(..., "--batch_id", "--batch", "--b")],
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
    proj = load_project(project_path)

    # validate batch existence
    esm_export = proj.batches_dir / f"{batch_id}.csv"
    if not esm_export.exists():
        raise FileExistsError(
            f"Batch {batch_id} not found in the batches directory. Was this exported from ESM?"
        )

    # create a new run for this batch
    run = proj.init_run(batch_id)  # NOTE esm_export patch is changed/standardized here
    metadata = run.get_metadata()

    _, metadata = format_manifest(
        esm_export_path=run.esm_export,
        manifest_path=run.manifest,
        metadata_tracker=metadata,
        group_id_prefix=group_prefix,
    )

    if metadata.missing_groups:
        typer.echo(
            f"\nPlease review the manifest and remediate before compression:\n\n{run.manifest.resolve()}\n\n"
        )
        # NOTE group prefix is only checked for manifest creation
        # manually remediated group ids are not validated - the only
        # thing checked moving forward is whether the group column
        # contains a value (relative to the initial marker for a missing
        # group, specifically)

    metadata.export()


@app.command("compress")
def copy_and_compress(
    project_path: Annotated[Path, typer.Option(..., "--project-path", "--p")],
    batch_id: Annotated[str, typer.Option(..., "--batch_id", "--batch", "--b")],
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
    proj = load_project(project_path)
    run = proj.load_run(batch_id)

    metadata = run.get_metadata()

    _, metadata = compress(
        run.manifest,
        run.groups_dir,
        metadata,
        remove_ungrouped=remove_ungrouped,
        compression_type=compression_type,
    )

    metadata.export()


@app.command("upload")
def upload_to_s3(
    project_path: Annotated[Path, typer.Option(..., "--project-path", "--p")],
    batch_id: Annotated[str, typer.Option(..., "--batch_id", "--batch", "--b")],
    aws_profile: Annotated[Optional[str], typer.Option("--aws-profile", "--ap")] = None,
    s3_bucket: Annotated[Optional[str], typer.Option("--bucket", "--b")] = None,
    s3_bucket_location: Annotated[Optional[str], typer.Option("--key", "--k")] = None,
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
    validate_identity_and_s3_access(profile=aws_profile)

    proj = load_project(project_path)
    run = proj.load_run(batch_id)
    metadata = run.get_metadata()
    cfg = proj.load_config()

    s3b = cfg.get("bucket", s3_bucket)
    s3bl = cfg.get("bucket_location", s3_bucket_location)
    s3ar = cfg.get("region", aws_region)

    if s3b is None or s3bl is None:
        raise ValueError(
            f"Must specify an s3 bucket and bucket location (prefix): bucket={s3b} | prefix={s3bl}"
        )

    # check for zipped files
    valid_compressions = list(run.groups_dir.glob("*.zip"))

    if not any(valid_compressions):
        raise FileNotFoundError(
            f"No compressed groups identified in this directory: {run.groups_dir}\n\nHave images been compressed? Review metadata file for zipped file locations: {run.metadata_file}"
        )

    metadata = upload_groups(
        compressed_groups=valid_compressions,
        bucket=s3b,
        key=s3bl,
        metadata_tracker=metadata,
        aws_region=s3ar,
        aws_config_profile=aws_profile,
    )

    metadata.export()

    if export_links:
        links = export_sharelinks(run.shareable_links, metadata)
        typer.echo(f"View AWS shareable links at {links}")


# --------------- Single Run / Breakpoint Commands ---------------


@app.command("from_esm")
def process_batch_esm(
    esm_export_file: Annotated[Path, typer.Option(..., "--esm_export", "--in", "--i")],
    batch_id: Annotated[str, typer.Option(..., "--batch_id", "--batch", "--b")] = "",
    infer_batch_id: Annotated[bool, typer.Option("--infer_batch")] = False,
    group_prefix: Annotated[str, typer.Option("--gp")] = "JDI",
):
    """Start pipeline from an ESM export

    Compress groups of WSIs to ZIP and upload to AWS

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
    """Start pipeline from a manifest (step 2)

    Compress groups of WSIs to ZIP and upload to AWS

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


@app.command("mult_batches")
def process_multiple_batches():
    """Process all batches in a directory. Only ESM exports are supported.

    Compress groups of WSIs to ZIP and upload to AWS

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
