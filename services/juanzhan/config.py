import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    converter_token: str
    cookie_secure: bool = True
    upload_max_bytes: int = 64 * 1024 * 1024
    upload_timeout_seconds: float = 60

    @classmethod
    def from_env(cls):
        cookie_secure = os.getenv("JUANZHAN_COOKIE_SECURE", "true").lower()
        if cookie_secure not in ("true", "false"):
            raise ValueError("JUANZHAN_COOKIE_SECURE must be true or false")
        upload_max_bytes = int(os.getenv("JUANZHAN_UPLOAD_MAX_BYTES", str(64 * 1024 * 1024)))
        upload_timeout = float(os.getenv("JUANZHAN_UPLOAD_TIMEOUT_SECONDS", "60"))
        if not 1<=upload_max_bytes<=1024*1024*1024 or not 0<upload_timeout<=3600:
            raise ValueError("Invalid upload size or receive timeout")
        return cls(Path(os.getenv("JUANZHAN_DATA_DIR", ".local/archive")).resolve(),
                   os.getenv("CONVERTER_SERVICE_TOKEN", ""),
                   cookie_secure == "true",upload_max_bytes,upload_timeout)

    @property
    def database(self):
        return self.data_dir / "database" / "archive.sqlite3"

    def prepare_archive(self):
        for directory in ("database", "managed", "derived"):
            (self.data_dir / directory).mkdir(parents=True, exist_ok=True)
