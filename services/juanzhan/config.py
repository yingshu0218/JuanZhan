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

    source_mounts: tuple[tuple[str, str], ...] = ()
    backup_dir: Path | None = None
    public_url: str | None = None

    def __post_init__(self):
        if self.public_url:
            from urllib.parse import urlsplit
            value=urlsplit(self.public_url)
            if (len(self.public_url)>2048 or any(ord(c)<33 or ord(c)>126 for c in self.public_url)
                or value.username or value.password or value.query or value.fragment or value.path not in ('','/')
                or not value.hostname or '\\' in self.public_url
                or (value.scheme!='https' and not (value.scheme=='http' and value.hostname in ('127.0.0.1','localhost','::1')))):
                raise ValueError('JUANZHAN_PUBLIC_URL requires an HTTPS origin or loopback HTTP')
            value.port
            object.__setattr__(self,'public_url',self.public_url.rstrip('/'))

    @classmethod
    def from_env(cls):
        from .source_paths import parse_mounts
        source_mounts = parse_mounts(os.getenv("JUANZHAN_SOURCE_MOUNTS", "{}"))
        cookie_secure = os.getenv("JUANZHAN_COOKIE_SECURE", "true").lower()
        if cookie_secure not in ("true", "false"):
            raise ValueError("JUANZHAN_COOKIE_SECURE must be true or false")
        upload_max_bytes = int(os.getenv("JUANZHAN_UPLOAD_MAX_BYTES", str(64 * 1024 * 1024)))
        upload_timeout = float(os.getenv("JUANZHAN_UPLOAD_TIMEOUT_SECONDS", "60"))
        if not 1<=upload_max_bytes<=1024*1024*1024 or not 0<upload_timeout<=3600:
            raise ValueError("Invalid upload size or receive timeout")
        return cls(Path(os.getenv("JUANZHAN_DATA_DIR", ".local/archive")).resolve(),
                   os.getenv("CONVERTER_SERVICE_TOKEN", ""),
                   cookie_secure == "true",upload_max_bytes,upload_timeout,source_mounts,
                   Path(os.environ["JUANZHAN_BACKUP_DIR"]).resolve() if os.getenv("JUANZHAN_BACKUP_DIR") else None,
                   os.getenv('JUANZHAN_PUBLIC_URL') or None)

    @property
    def database(self):
        return self.data_dir / "database" / "archive.sqlite3"

    def prepare_archive(self):
        if (self.data_dir / "RESTORE_IN_PROGRESS").exists():
            raise RuntimeError("Incomplete restore; use a new destination and repeat verified recovery")
        for directory in ("database", "managed", "derived"):
            (self.data_dir / directory).mkdir(parents=True, exist_ok=True)
