from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Union

from numpy import isin

from esm_aws_pipe.utils import DT_FORMAT, save_json, load_json


@dataclass
class ProcessMetadata:
    batch_id: str
    save_dir: Path
    esm_export: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)
    compression: dict = field(default_factory=dict)
    _ctime = None
    _missing_groups: bool = False

    def __post_init__(self):
        if not self.save_dir.is_dir():
            raise ValueError(
                f"Must provide path to a directory, not {self.save_dir.name}"
            )
        self._ctime = datetime.now().strftime(DT_FORMAT)

        if self.batch_id == "":
            raise ValueError(
                f"Empty batch ID detected: {self.batch_id=}\nCheck the provided CLI value or inference setting."
            )

    # @property
    # def save_dir(self) -> Path:
    #     return Path(self._save_dir)

    @property
    def missing_groups(self) -> bool:
        return self._missing_groups

    @property
    def manifest_metadata(self) -> dict:
        return self.manifest

    @property
    def esm_export_metadata(self) -> dict:
        return self.esm_export

    @property
    def compression_metadata(self) -> dict:
        return self.compression

    def add_esm_export_metadata(self, **metadata):
        self.esm_export.update(**metadata)

    def add_manifest_metadata(self, **metadata):
        self.manifest.update(**metadata)

    def add_compression_metadata(self, **metadata):
        self.compression.update(**metadata)

    def to_dict(self) -> dict:
        return {
            "created": self._ctime,
            "batch_id": self.batch_id,
            "esm_export_meta": self.esm_export,
            "manifest_meta": self.manifest,
            "compression_meta": self.compression,
        }

    def export(self):
        save_to = self.save_dir / "process_metadata.json"
        save_json(save_to, self.to_dict())
        print(f"\nSaved run metadata to {save_to.resolve()}")


def load_metadata(path: Union[str, Path]) -> ProcessMetadata:
    """Load previously saved metadata"""
    metadata_path = Path(path) if isinstance(path, str) else path
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"No metadata found at this location {metadata_path.resolve()}\n\nPlease check the path or run `create_manifest` first."
        )

    metadata = load_json(metadata_path)

    # validate required keys
    req_keys = {"batch_id", "created"}
    missing_req_keys = req_keys.difference(set(metadata.keys()))

    if any(missing_req_keys):
        raise ValueError(
            f"Incorrectly formatted metadata. Missing the following required keys: {missing_req_keys}."
        )

    metadata_obj = ProcessMetadata(
        batch_id=metadata.pop("batch_id"), save_dir=metadata_path.parent
    )

    func_map = {
        "esm_export_meta": metadata_obj.add_esm_export_metadata,
        "manifest_meta": metadata_obj.add_manifest_metadata,
        "compression_meta": metadata_obj.add_compression_metadata,
    }

    # override ctime
    metadata_obj._ctime = metadata.pop("created")

    for key, func in func_map.items():
        if key in metadata.keys():
            func(**metadata[f"{key}"])

    return metadata_obj
