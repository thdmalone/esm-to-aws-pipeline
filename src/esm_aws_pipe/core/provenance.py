from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

from esm_aws_pipe.utils import DT_FORMAT, save_json


@dataclass
class ProcessMetadata:
    batch_id: str
    save_dir: Path
    esm_export: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)
    _ctime = None

    def __post_init__(self):
        if not self.save_dir.is_dir():
            raise ValueError(
                f"Must provide path to a directory, not {self.save_dir.name}"
            )
        self._ctime = datetime.now().strftime(DT_FORMAT)

    # @property
    # def save_dir(self) -> Path:
    #     return Path(self._save_dir)

    @property
    def manifest_metadata(self) -> dict:
        return self.manifest

    @property
    def esm_export_metadata(self) -> dict:
        return self.esm_export

    def add_esm_export_metadata(self, **metadata):
        self.esm_export.update(**metadata)

    def add_manifest_metadata(self, **metadata):
        self.manifest.update(**metadata)

    def to_dict(self) -> dict:
        return {
            "created": self._ctime,
            "batch_id": self.batch_id,
            "esm_export_meta": self.esm_export,
            "manifest_meta": self.manifest,
        }

    def export(self):
        save_to = self.save_dir / "process_metadata.json"
        save_json(save_to, self.to_dict())
        print(f"\nSaved run metadata to {save_to}")
