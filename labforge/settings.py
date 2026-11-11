"""Runtime settings, all overridable with LABFORGE_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass
class Settings:
    home: Path = field(default_factory=lambda: Path(os.environ.get("LABFORGE_HOME", Path.home() / ".labforge")))
    extra_catalog: Path | None = field(
        default_factory=lambda: Path(p) if (p := os.environ.get("LABFORGE_CATALOG_DIR")) else None
    )
    max_ttl_minutes: int = field(default_factory=lambda: _env_int("LABFORGE_MAX_TTL_MINUTES", 8 * 60))
    max_active_labs: int = field(default_factory=lambda: _env_int("LABFORGE_MAX_ACTIVE_LABS", 10))
    reap_interval: int = field(default_factory=lambda: _env_int("LABFORGE_REAP_INTERVAL_SECONDS", 10))
    link_pool: str = field(default_factory=lambda: os.environ.get("LABFORGE_LINK_POOL", "172.30.0.0/16"))
    mgmt_pool: str = field(default_factory=lambda: os.environ.get("LABFORGE_MGMT_POOL", "172.29.0.0/16"))

    @property
    def db_path(self) -> Path:
        return self.home / "labforge.db"

    @property
    def user_catalog(self) -> Path:
        return self.home / "catalog"


settings = Settings()
