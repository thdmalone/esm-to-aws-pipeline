from pathlib import Path
from typing import Union, Optional
import time

from boto3 import client
from botocore.exceptions import BotoCoreError, ClientError


def upload_file_to_s3(
    local_path: Path,
    bucket: str,
    bucket_location: str,
    *,
    region: Optional[str],
    max_retries: int = 3,
    retry_delay: float = 1.0,
):
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
                # note error
                raise RuntimeError(f"S3 upload failed for {local_path.name}") from exc
            # note retry attempt
            time.sleep(retry_delay * (2 ** (attempts - 1)))
