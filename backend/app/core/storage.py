"""File store for the case workspace. Local folder now; the same four methods map to Azure Blob Storage later."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol


class FileStore(Protocol):
    def put(self, key: str, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def path(self, key: str) -> Path: ...


def safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()äöüÄÖÜß]", "_", name).strip(" .") or "file"
    return name[:120]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalFileStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValueError("key leaves the store")
        return p

    def put(self, key: str, data: bytes) -> str:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)
        return key

    def get(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self.path(key).exists()

    def delete_prefix(self, prefix: str) -> None:
        import shutil
        p = self.path(prefix)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()
