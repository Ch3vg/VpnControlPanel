from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    directory = path.parent
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    os.chmod(tmp_path, mode)
    os.replace(tmp_path, path)
