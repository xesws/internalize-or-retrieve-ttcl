# Run manifest builder (handbook §4.2): GPU model, commit sha, config hash,
# model role strings, paid-API token usage. One manifest.json per run under
# results/<run_id>/.
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def config_hash(config: dict[str, Any]) -> str:
    blob = json.dumps(config, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def gpu_name() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return "cpu-only-host"


def build_manifest(run_id: str, config: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "created_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "config_hash": config_hash(config),
        "gpu": gpu_name(),
        "seed": config.get("run", {}).get("seed"),
        "max_new_tokens": config.get("run", {}).get("max_new_tokens"),
        "models": config.get("models", {}),
        "paid_api_usage": {},   # filled by the Mac-side LLM client: per-model call/prompt/completion token sums
    }
    if extra:
        manifest.update(extra)
    return manifest


def write_manifest(run_dir: str | Path, manifest: dict[str, Any]) -> Path:
    path = Path(run_dir) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return path
