"""Shared helpers for the M0 spikes. Throwaway; not imported by bullpit/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bullpit.config import Settings, get_settings

OUTPUT_DIR = Path(__file__).parent / "output"


def settings() -> Settings:
    return get_settings()


def save_json(name: str, data: Any) -> Path:
    """Write raw output as JSON to scripts/spikes/output/<name>.json (git-ignored)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"  -> saved {path}")
    return path


def section(title: str) -> None:
    print(f"\n=== {title} ===")
