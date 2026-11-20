from pathlib import Path

import boto3
import pytest

moto = pytest.importorskip("moto")
from esm_aws_pipe.core.s3 import upload_file_to_s3


@moto.mock_aws
def test_upload_file_to_s3(tmp_path: Path) -> None:
    bucket = "test-bucket"
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=bucket)

    file_path = tmp_path / "file.txt"
    file_path.write_text("content", encoding="utf-8")

    s3_path = upload_file_to_s3(file_path, bucket, "file.txt", error="raise")

    obj = client.get_object(Bucket=bucket, Key="file.txt")
    assert obj["Body"].read().decode("utf-8") == "content"
