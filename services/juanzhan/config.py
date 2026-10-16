import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    converter_token: str
    cookie_secure: bool = True

    @classmethod
    def from_env(cls):
        cookie_secure = os.getenv("JUANZHAN_COOKIE_SECURE", "true").lower()
        if cookie_secure not in ("true", "false"):
            raise ValueError("JUANZHAN_COOKIE_SECURE must be true or false")
        return cls(Path(os.getenv("JUANZHAN_DATA_DIR", ".local/archive")).resolve(),
                   os.getenv("CONVERTER_SERVICE_TOKEN", ""),
                   cookie_secure == "true")

    @property
    def database(self):
        return self.data_dir / "database" / "archive.sqlite3"

    def prepare_archive(self):
        for directory in ("database", "managed", "derived"):
            (self.data_dir / directory).mkdir(parents=True, exist_ok=True)
