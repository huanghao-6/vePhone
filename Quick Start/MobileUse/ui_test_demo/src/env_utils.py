from __future__ import annotations

from pathlib import Path
import os
from typing import Optional


def strip_wrapping_quotes(value: str) -> str:
    v = (value or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
        return v[1:-1]
    return v


def load_env_file(env_path: Path, *, override: bool = False) -> None:
    """Load KEY=VALUE lines from an env file into os.environ.

    - Ignores blank lines and comments (#...)
    - Strips wrapping quotes: KEY="value" -> value
    - By default does not override existing os.environ values
    """
    if not env_path.exists():
        return

    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = strip_wrapping_quotes(v.strip())
            if not k:
                continue
            if not override and k in os.environ:
                continue
            os.environ[k] = v
    except Exception:
        return


def load_env_from_root(root: Path, filename: str = ".env", *, override: bool = False) -> None:
    load_env_file(root / filename, override=override)


def env_bool(name: str, default: bool = False) -> bool:
    v: Optional[str] = os.environ.get(name)
    if v is None or str(v).strip() == "":
        return default
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return default