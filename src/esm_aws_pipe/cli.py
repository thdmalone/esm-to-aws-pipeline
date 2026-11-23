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

        project_path : Path
            Path to the current project

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

    proj = load_project(project_path)
    run = proj.load_run(batch_id)
    metadata = run.get_metadata()
    cfg = proj.load_config()

    s3b = cfg.get("bucket", s3_bucket)
    s3bl = cfg.get("bucket_location", s3_bucket_location)
    s3ar = cfg.get("region", aws_region)
    awp = cfg.get("aws_profile_name", aws_profile)

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

    validate_identity_and_s3_access(profile=awp)

    metadata = upload_groups(
        compressed_groups=valid_compressions,
        bucket=s3b,
        key=s3bl,
        metadata_tracker=metadata,
        aws_region=s3ar,
        aws_config_profile=awp,
    )

    metadata.export()

    if export_links:
        links = export_sharelinks(run.shareable_links, metadata)
        typer.echo(f"View AWS shareable links at {links}")


# --------------- Single Run / Breakpoint Commands ---------------


@app.command("run")
def process_completely(
    project_path: Annotated[Path, typer.Option(..., "--project-path", "--p")],
    *,
    batch_id: Annotated[
        Optional[str], typer.Option("--batch_id", "--batch", "--b")
    ] = None,
    process_all: Annotated[bool, typer.Option("--process-all", "--all")] = False,
    group_prefix: Annotated[
        Optional[str], typer.Option("--group-prefix", "--gp")
    ] = None,
    review_missing_groups: Annotated[
        bool, typer.Option(f"--review-missing-group", "--rmg")
    ] = False,
    compression_type: Annotated[
        Optional[str], typer.Option("--compress", "--c")
    ] = None,
    remove_ungrouped: Annotated[
        bool, typer.Option("--remove-ungrouped", "--rm")
    ] = False,
    aws_profile: Annotated[Optional[str], typer.Option("--aws-profile", "--ap")] = None,
    s3_bucket: Annotated[Optional[str], typer.Option("--bucket", "--b")] = None,
    s3_bucket_location: Annotated[Optional[str], typer.Option("--key", "--k")] = None,
    aws_region: Annotated[Optional[str], typer.Option("--region", "--r")] = None,
    export_links: Annotated[bool, typer.Option("--export-links")] = True,
):
    """Run all steps

    Parameters
    ----------
        project_path : Path
            Path to the current project

        batch_id : Optional[str], default=None
            The research ID associated with this batch (e.g., Rxx-xxxx). Required if
            `process_all=False`

        process_all : bool, defualt=False
            If true, will process all batches detected in the batches directory

        group_prefix : Optional[str], default=None
            Prefix of image filenames indicating the grouping it belongs to.
            Overrides whatever is specified in `config.yml`

        review_missing_groups : bool, default=True
            If True, will allow the user the remediate the manifest for WSIs with
            missing group IDs prior to compression

        compression_type : Optional[str], default="zip"
            Specify how groups are compressed. Refer to
            https://docs.python.org/3/library/shutil.html#shutil.make_archive
            for more information on compression formats. Overrides whatever is
            specified in `config.yml`

        remove_ungrouped : bool, default=False
            Specify where to remove images without a group ID in the `group`
            column of the manifest. Images without a group id are grouped under
            "ungrouped" by default. Overrides whatever is specified in `config.yml`

        aws_profile : Optional[str], default=None
            Specify a properly configured AWS profile according to `~/.aws/config`.
            Overrides whatever is specified in `config.yml`

        s3_bucket : Optional[str], default=None
            Name of the target S3 bucket. Overrides whatever is specified in `config.yml`

        s3_bucket_location : Optional[str], default=None
            Path-like location of the specific location within the bucket to upload to.
            Overrides whatever is specified in `config.yml`

        aws_region : Optional[str], default=None

        export_links : bool, default=True
            If true, extracts presigned url data from the metadata and saves it to a CSV
            for easier access.


    """
    proj = load_project(project_path)
    cfg = proj.load_config()

    # load config variables
    gp = cfg.get(f"esm_group_prefix", group_prefix)
    rmg = cfg.get("review_missing_groups", review_missing_groups)
    ct = cfg.get(f"compression_type", compression_type)
    ru = cfg.get(f"remove_ungrouped", remove_ungrouped)
    s3b = cfg.get("bucket", s3_bucket)
    s3bl = cfg.get("bucket_location", s3_bucket_location)
    s3ar = cfg.get("region", aws_region)
    awp = cfg.get("aws_profile_name", aws_profile)

    if s3b is None or s3bl is None:
        raise ValueError(
            f"Must specify an s3 bucket and bucket location (prefix): bucket={s3b} | prefix={s3bl}"
        )
    validate_identity_and_s3_access(profile=awp)

    # start pipeline
    processing_queue = [f for f in proj.batches_dir.iterdir() if f.suffix == ".csv"]
    if not any(processing_queue):
        raise FileNotFoundError(f"No batches detected in {proj.batches_dir}.")

    multiple_batches = len(processing_queue) > 1

    if multiple_batches:
        if process_all:
            typer.echo(f"\nIdentified {len(processing_queue)} batches to process")
        elif not isinstance(batch_id, str):
            raise ValueError(
                f"Multiple batches identified and {process_all=}. Must specify a `batch_id` to run. (Got {batch_id=})"
            )
        elif isinstance(batch_id, str):
            processing_queue = [proj.batches_dir / batch_id]

    for batch in processing_queue:
        typer.echo(f"\n\n\t\t----- Processing {batch} -----")
        run = proj.init_run(batch.stem)
        metadata = run.get_metadata()

        manifest, metadata = format_manifest(
            esm_export_path=run.esm_export,
            manifest_path=run.manifest,
            metadata_tracker=metadata,
            group_id_prefix=gp,
        )

        if metadata.missing_groups and review_missing_groups:
            typer.echo(
                f"\nPlease review the manifest and remediate before compression:\n\n{run.manifest.resolve()}\n\n"
            )

            proceed = typer.confirm(f"Ready to proceed?")
            if not proceed:
                typer.echo(f"Terminating processing")
                return
        else:
            typer.echo(f"Finished generating the processing manifest")

        _, metadata = compress(
            run.manifest,
            run.groups_dir,
            metadata,
            remove_ungrouped=ru,
            compression_type=ct,
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
            aws_config_profile=awp,
        )

        metadata.export()

        if export_links:
            links = export_sharelinks(run.shareable_links, metadata)
            typer.echo(f"View AWS shareable links at {links}")
