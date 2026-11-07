from datetime import datetime
import time
import json
from pathlib import Path
from typing import Any

DT_FORMAT = "%Y-%m-%d %H:%M:%S"


class Clock:
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.laps: list = []

    def start(self):
        self.start_time = time.time()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Start time in Los Angeles: {now}")

    def lap(self) -> str:
        if not self.start_time:
            raise AttributeError(f"Clock not started. Call `start()` first")

        current = time.time()

        # no prior laps, i.e., this is the first lap
        if len(self.laps) == 0:
            last = self.start_time
        else:
            last = self.laps[-1]

        time_since_last_lap = current - last
        self.laps.append(time_since_last_lap)

        time_readout = self.get_elapsed_time_readout(time_since_last_lap)

        print(f"Lap time: {time_readout}")
        return time_readout

    def end(self) -> str:
        self.end_time = time.time()

        if any(self.laps):
            last_stamp = self.laps[-1]
        else:
            last_stamp = self.start_time

        elapsed_time = self.end_time - last_stamp  # type: ignore
        self._print_elapsed_time(elapsed_time)
        return self.get_elapsed_time_readout(elapsed_time)

    def _format_elapsed_time(self, elapsed_time):
        hours, rem = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(rem, 60)
        return hours, minutes, seconds

    def _print_elapsed_time(self, elapsed_time):
        time_readout = self.get_elapsed_time_readout(elapsed_time)
        print(f"Elapsed time: {time_readout}")

    def get_elapsed_time_readout(self, elapsed_time) -> str:
        hours, minutes, seconds = self._format_elapsed_time(elapsed_time)
        time_readout = (
            f"{int(hours)} hours, {int(minutes)} minutes, {seconds:.2f} seconds"
        )

        if int(hours) == 0:
            time_readout = f"{int(minutes)} minutes, {seconds:.2f} seconds"
        if int(minutes) == 0:
            time_readout = f"{seconds:.2f} seconds"

        return time_readout


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def validate_extension(path: Path, extension: str):
    return path.with_suffix(extension)


class SetEncoder(json.JSONEncoder):
    def default(self, obj):  # type: ignore
        import numpy as np

        if isinstance(obj, Path):
            return str(obj)

        return json.JSONEncoder.default(self, obj)


def save_json(path: Path, data: dict):
    ensure_dir(path.parent)
    path = validate_extension(path, ".json")
    with open(path, "w") as fn:
        json.dump(data, fn, cls=SetEncoder)


def load_json(path: str) -> dict[str, Any]:
    assert path.endswith(".json"), f"Must specify a .json file, not {path}"
    with open(path, "r") as fn:
        return json.load(fn)
