from typing import Union
from dataclasses import dataclass
from pathlib import Path

from esm_aws_pipe.utils import write_yaml, read_yaml


@dataclass(frozen=True)
class ProjectConfig:
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_profile_name: str = ""
    bucket: str = ""
    bucket_location: str = ""
    region: str = "us-east-1"
    max_aws_upload_retries: int = 3
    aws_upload_retry_delay: float = 1.0

    def get(self, key: str, default):
        return self.__dict__.get(key, default)

    def to_dict(self):
        return self.__dict__.copy()

    def export(self, save_path: Path):
        write_yaml(save_path, self.to_dict())
