from pathlib import Path
from dataclasses import dataclass
from shutil import move

from esm_aws_pipe.utils import ensure_dir, read_yaml
from esm_aws_pipe.core.provenance import ProcessMetadata, load_metadata

from esm_aws_pipe.core.config import ProjectConfig


@dataclass
class ProcessingRun:
    root: Path

    @property
    def batch_id(self) -> str:
        return self.root.name

    @property
    def project(self) -> Path:
        return self.root.parent

    @property
    def groups_dir(self) -> Path:
        return self.root / "groups"

    @property
    def esm_export(self) -> Path:
        return self.root / "esm_export.csv"

    @property
    def manifest(self) -> Path:
        return self.root / "esm_to_aws_manifest.csv"

    @property
    def metadata_file(self) -> Path:
        return self.root / "process_metadata.json"

    @property
    def shareable_links(self) -> Path:
        return self.root / "sharelinks.csv"

    def get_metadata(self) -> ProcessMetadata:
        """Create metadata object, or load an existing one"""
        # NOTE log load/creation decision
        if self.metadata_file.exists():
            return load_metadata(self.metadata_file)

        return ProcessMetadata(batch_id=self.batch_id, save_path=self.metadata_file)


@dataclass
class Project:
    root: Path

    @property
    def batches_dir(self) -> Path:
        return self.root / "batches"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def config(self) -> Path:
        return self.root / "config.yml"

    def init_run(self, batch_id: str) -> ProcessingRun:
        run_path = self.runs_dir / batch_id
        if run_path.exists():
            raise FileExistsError(f"A run already exists for this batch: {batch_id}")

        # create new subdir for the run then move the ESM export
        ensure_dir(run_path)
        new_run = ProcessingRun(run_path)
        ensure_dir(new_run.groups_dir)

        move(self.batches_dir / f"{batch_id}.csv", new_run.esm_export)

        return new_run

    def load_run(self, batch_id: str) -> ProcessingRun:
        run_path = self.runs_dir / batch_id
        if not run_path.exists():
            raise FileNotFoundError(
                f"This batch has not been processed before. Run `manifest` for this batch first."
            )

        # NOTE additional structural validation
        return ProcessingRun(run_path)

    def load_config(self) -> ProjectConfig:
        cfg = read_yaml(self.config)
        return ProjectConfig(**cfg)


def init_project(root: Path) -> Project:
    """Define a new project"""

    proj = Project(root)

    ensure_dir(proj.batches_dir)
    ensure_dir(proj.runs_dir)

    default_cfg = ProjectConfig()
    default_cfg.export(proj.config)

    return proj


def load_project(root: Path) -> Project:
    if not root.exists():
        raise FileExistsError(f"Path does not exist")

    if not root.is_dir():
        raise ValueError(f"Expected a path to a directory")

    # validate structure
    for dirname in ("batches", "runs"):
        dir = root / dirname
        if not dir.exists() and not dir.is_dir():
            raise FileExistsError(
                f"Invalid project strucutre: Missing the {dirname} directory"
            )

    if not (root / "config.yml").exists():
        raise FileNotFoundError(f"Invalid project strucutre: Missing config file")

    return Project(root)
