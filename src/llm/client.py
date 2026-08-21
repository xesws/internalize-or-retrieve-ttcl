"""Mac-side LLM client for hosted APIs (the ONLY place paid keys are used).

Role-based: gen / sys / judge / dev_aux resolve (base_url, key, model) from the
repo .env + configs/default.yaml. Every call retries up to 3 times (handbook
§4.2 — report after three failures, never silently degrade) and appends token
usage to a journal that run manifests aggregate (DeepSeek balance discipline).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_USAGE_PATH: Path | None = None

# GLM-5.3 caps temperature at 1.0; keep every role inside that bound.
MAX_TEMPERATURE = 1.0


class LLMError(RuntimeError):
    pass


def load_env(env_path: Path | str | None = None) -> dict[str, str]:
    """Minimal .env loader (KEY=VALUE lines, # comments)."""
    path = Path(env_path) if env_path else _REPO_ROOT / ".env"
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k in (
        "ZAI_API_KEY", "OPENAI_API_KEY", "HF_TOKEN") and v})
    return env


_ROLE_DEFAULTS = {
    # role: (model_env, base_url, api_key_env, default_model)
    "gen": ("GEN_MODEL", "https://api.z.ai/api/coding/paas/v4", "ZAI_API_KEY", "glm-5.3"),
    "sys": ("SYS_MODEL", "https://api.z.ai/api/coding/paas/v4", "ZAI_API_KEY", "glm-5.3"),
    "judge": ("JUDGE_MODEL", "https://api.deepseek.com", "OPENAI_API_KEY", "deepseek-v4-pro"),
    "dev_aux": ("DEV_AUX_MODEL", "https://api.deepseek.com", "OPENAI_API_KEY", "deepseek-v4-flash"),
}


def resolve_role(role: str, env: dict[str, str]) -> dict[str, str]:
    model_env, base_url, key_env, default_model = _ROLE_DEFAULTS[role]
    return {
        "model": env.get(model_env, default_model),
        "base_url": base_url.rstrip("/"),
        "api_key": env.get(key_env, ""),
    }


def set_usage_journal(path: Path | str | None) -> None:
    """Where per-call token usage is appended (results/<run_id>/llm_usage.jsonl)."""
    global _USAGE_PATH
    _USAGE_PATH = Path(path) if path else None


def _record_usage(role: str, model: str, usage: dict[str, Any], meta: dict[str, Any]) -> None:
    if _USAGE_PATH is None or not usage:
        return
    _USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _USAGE_PATH.open("a") as f:
        f.write(json.dumps({
            "ts": time.time(), "role": role, "model": model,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            **meta,
        }) + "\n")


def usage_summary() -> dict[str, dict[str, int]]:
    """Aggregate the journal: {model: {calls, prompt_tokens, completion_tokens, total_tokens}}."""
    if _USAGE_PATH is None or not _USAGE_PATH.exists():
        return {}
    out: dict[str, dict[str, int]] = {}
    for line in _USAGE_PATH.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        m = out.setdefault(r["model"], {"calls": 0, "prompt_tokens": 0,
                                        "completion_tokens": 0, "total_tokens": 0})
        m["calls"] += 1
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if r.get(k):
                m[k] += r[k]
    return out


def chat(
    messages: list[dict],
    role: str = "gen",
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    env: dict[str, str] | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    """One chat completion; returns assistant text. Raises LLMError after 3
    failed attempts (caller must surface, not swallow)."""
    cfg = resolve_role(role, load_env() if env is None else env)
    if not cfg["api_key"]:
        raise LLMError(f"missing API key for role={role} ({cfg['base_url']})")
    body = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "temperature": min(temperature, MAX_TEMPERATURE),
        "max_tokens": max_tokens,
        "stream": False,
    }).encode()

    last_err: Exception | None = None
    for attempt in range(1, 4):
        req = urllib.request.Request(
            cfg["base_url"] + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {cfg['api_key']}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode())
            text = data["choices"][0]["message"]["content"]
            if not text:
                raise LLMError("empty completion content")
            _record_usage(role, cfg["model"], data.get("usage", {}), meta or {})
            return text
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                KeyError, IndexError, json.JSONDecodeError, LLMError) as e:
            last_err = e
            time.sleep(2 * attempt)
    raise LLMError(f"role={role} model={cfg['model']} failed after 3 attempts: {last_err}")


def parse_json_block(text: str) -> Any:
    """Robustly pull the first balanced JSON object/array out of an LLM reply
    (strips code fences / prose wrappers)."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()
    candidates = [(i, ch) for i, ch in
                  ((s.find("{"), "{"), (s.find("["), "[")) if i != -1]
    if not candidates:
        raise LLMError(f"no JSON block found in reply head: {text[:120]!r}")
    start, opener = min(candidates)
    closer = {"{": "}", "[": "]"}[opener]
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return json.loads(s[start:i + 1])
    raise LLMError(f"no JSON block found in reply head: {text[:120]!r}")
