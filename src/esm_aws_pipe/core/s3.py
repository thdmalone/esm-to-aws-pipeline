from pathlib import Path
from typing import Optional, Literal
from time import sleep
from tqdm import tqdm
from datetime import datetime

from esm_aws_pipe.core.provenance import ProcessMetadata
from esm_aws_pipe.utils import DT_FORMAT

from boto3 import client
from botocore.exceptions import BotoCoreError, ClientError
from pandas import DataFrame


def upload_groups(
    compressed_groups: list[Path],
    bucket: str,
    key: str,
    metadata_tracker: ProcessMetadata,
    aws_region: Optional[str] = None,
    on_error: Literal["raise", "ignore"] = "ignore",
) -> ProcessMetadata:
    """Upload all compressed groups in a directory

    Parameters
    ----------
        compressed_groups : list[Path]
            Paths to compressed files

        bucket : str
            Name of the target S3 bucket to upload file to

        key : str
            Path-like location within bucket where file is
            being uploaded to

        metadata_tracker : ProcessMetadata

        on_error : {"raise", "ignore"}, default="ignore"
            Specifies error handling
            * `raise`: Uploading errors terminate the process
            * `ignore`: Uploading errors are logged as failures
            and process continues


    """

    def _parse_status(s: str):
        if "upload failed" in s:
            success = False
            s3_path = ""
        else:
            success = True
            s3_path = s

        return {"status": success, "s3_path": s3_path}

    progress = {}
    failed = 0
    for compression in tqdm(compressed_groups, desc="Uploading groups to S3"):
        # complete s3 path
        complete_key = key + f"/{compression.name}"

        status = upload_file_to_s3(
            local_path=compression,
            bucket=bucket,
            bucket_location=complete_key,
            error=on_error,
            region=aws_region,
        )

        payload = _parse_status(status)

        if payload["status"] is False:
            failed += 1
            presigned_package = {"url": "", "generated": ""}
        else:
            presigned_package = generate_share_link(
                bucket, complete_key, region=aws_region
            )

        payload.update(
            presigned_url=presigned_package,
        )
        progress[compression.name] = payload

    metadata_tracker.add_upload_metadata(
        processed=len(compressed_groups),
        failed_attempts=failed,
        progress_details=progress,
    )

    return metadata_tracker


def upload_file_to_s3(
    local_path: Path,
    bucket: str,
    bucket_location: str,
    *,
    error: str,
    region: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> str:
    """Upload file to S3 Bucket

    Parameters
    ----------
        local_path : Path
            Path to the file on local machine

        bucket : str
            Name of the target S3 bucket to upload file to

        bucket_location : str
            Location within bucket where file is being uploaded to

        region : Optional[str]
            AWS region of the target bucket

        max_retries : int, default=3
            Max upload attempts

        retry_delay : float, default=1.0
            Delay between failed upload attempts in seconds

    Returns
    -------
        status : str
            If `error="ignore"`, then the failed message is returned otherwise
            successful uploads return a path-like s3 location

    """
    cl = client("s3", region_name=region)
    attempts = 0
    while True:
        try:
            cl.upload_file(str(local_path), bucket, bucket_location)
            return f"s3://{bucket}/{bucket_location}"
        except (BotoCoreError, ClientError) as exc:
            attempts += 1
            if attempts > max_retries:
                msg = f"S3 upload failed for {local_path.name}"
                if error == "raise":
                    raise RuntimeError(msg) from exc
                return msg

            # note retry attempt
            sleep(retry_delay * (2 ** (attempts - 1)))


def generate_share_link(
    bucket: str,
    bucket_location: str,
    *,
    region: Optional[str] = None,
    expires_in: int = 604800,
) -> dict[str, str]:
    """AWS CLI presign command for generating a share link

    Parameters
    ----------
        bucket : str
            Name of the target S3 bucket to upload file to

        bucket_location : str
            Location within bucket where file is being uploaded to

        region : Optional[str]
            AWS region of the target bucket

        expires_in : int, default=604800
            Time in seconds until the shareable link expires.

    Returns
    -------
        presigned_url : str

        created_time : str
            timestamp for when url was generated

    """
    cl = client("s3", region_name=region)
    url = cl.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": bucket_location},
        expires_in=expires_in,
    )

    return {"url": url, "generated": datetime.now().strftime(DT_FORMAT)}


def export_sharelinks(out: Path, metadata: ProcessMetadata):
    """Extract valid presigned URLs from the metadata tracker and exports to CSV
    for easier viewing. Groups that failed to upload and do not have an S3 location
    are skipped.

    Returns
    -------
        export_path : Path
            CSV containing AWS sharelinks

    """
    # map group name to dict of status elements
    upload_details: dict[str, dict] = metadata.upload.get("progress_details")  # type: ignore

    if not isinstance(upload_details, dict):
        raise ValueError(f"Invalid or unsaved (progress) details")

    records = []
    for group, details in upload_details.items():
        psu = details.get("presigned_url")
        # might be redundant, might remove once validated
        if not isinstance(psu, dict):
            raise ValueError(
                f"Invalid presigned metadata save. Expected dict, got {type(psu)} ->\n\n{psu}"
            )

        # skip empty presigned links (i.e., failed uploads)
        if psu["url"] == "":
            continue

        records.append(
            {
                "group": group[:-4],
                "presigned_url": psu["url"],
                "created_on": psu["generated"],
            }
        )

    save_to = out / "sharelinks.csv"
    DataFrame(records).to_csv(save_to, index=False)
    return save_to
