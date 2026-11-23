from typing import Union
from dataclasses import dataclass, field
from pathlib import Path

from esm_aws_pipe.utils import write_yaml, read_yaml


@dataclass(frozen=True)
class ProjectConfig:
    esm_group_prefix: str
    review_missing_groups: bool

    compression_type: str
    remove_ungrouped: bool

    aws_access_key_id: str
    aws_secret_access_key: str
    aws_profile_name: str
    bucket: str
    bucket_location: str
    region: str
    max_aws_upload_retries: int
    aws_upload_retry_delay: float

    export_sharelinks: bool

    def get(self, key: str, default):
        if default is not None:
            return default

        return self.__dict__[key]

    def to_dict(self):
        return {
            "manifest": {
                "esm_group_prefix": self.esm_group_prefix,
                "review_missing_groups": self.review_missing_groups,
            },
            "compression": {
                "compression_type": self.compression_type,
                "remove_ungrouped": self.remove_ungrouped,
            },
            "uploading": {
                "aws_access_key_id": self.aws_access_key_id,
                "aws_secret_access_key": self.aws_secret_access_key,
                "aws_profile_name": self.aws_profile_name,
                "bucket": self.bucket,
                "bucket_location": self.bucket_location,
                "region": self.region,
                "max_aws_upload_retries": self.max_aws_upload_retries,
                "aws_upload_retry_delay": self.aws_upload_retry_delay,
                "export_sharelinks": self.export_sharelinks,
            },
        }


DEFAULT_CFG = ProjectConfig(
    aws_access_key_id="",
    aws_secret_access_key="",
    aws_profile_name="",
    bucket="",
    bucket_location="",
    region="us-east-1",
    max_aws_upload_retries=3,
    aws_upload_retry_delay=1.0,
    esm_group_prefix="",
    compression_type="zip",
    remove_ungrouped=False,
    export_sharelinks=False,
    review_missing_groups=False,
)
