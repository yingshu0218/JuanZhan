import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    converter_token: str

    @classmethod
    def from_env(cls):
        return cls(Path(os.getenv("JUANZHAN_DATA_DIR", ".local/archive")).resolve(),
                   os.getenv("CONVERTER_SERVICE_TOKEN", ""))

    @property
    def database(self):
        return self.data_dir / "database" / "archive.sqlite3"

    def prepare_archive(self):
        for directory in ("database", "managed", "derived"):
            (self.data_dir / directory).mkdir(parents=True, exist_ok=True)
