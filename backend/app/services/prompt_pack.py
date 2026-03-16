from __future__ import annotations

from pathlib import Path
import re
from threading import Lock
from typing import Any

from ..config import get_settings

PROMPT_FILES = ("role.md", "policy.md", "user.md", "data_availability.md", "output.md")
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")

_CACHE_LOCK = Lock()
_FILE_CACHE: dict[Path, tuple[float, str]] = {}


def build_system_prompt_from_pack(locale: str, context: dict[str, Any]) -> str:
    base_dir = _resolve_base_dir()
    locale_dir = _resolve_locale_dir(base_dir, locale)
    rendered_parts: list[str] = []
    for filename in PROMPT_FILES:
        file_path = locale_dir / filename
        text = _load_markdown(file_path)
        rendered = _render_template(text, context)
        rendered_parts.append(f"## {filename}\n{rendered.strip()}")
    return "\n\n".join(rendered_parts).strip()


def validate_prompt_pack_files() -> None:
    base_dir = _resolve_base_dir()
    for locale_dir_name in ("zh", "en"):
        locale_dir = base_dir / locale_dir_name
        if not locale_dir.exists():
            raise RuntimeError(f"Prompt locale directory missing: {locale_dir}")
        for filename in PROMPT_FILES:
            file_path = locale_dir / filename
            if not file_path.exists():
                raise RuntimeError(f"Prompt file missing: {file_path}")


def _resolve_locale_dir(base_dir: Path, locale: str) -> Path:
    settings = get_settings()
    locale_key = "zh" if locale.lower().startswith("zh") else "en"
    candidate = base_dir / locale_key
    if candidate.exists():
        return candidate
    fallback = (settings.prompt_locale_fallback or "en").strip().lower() or "en"
    return base_dir / fallback


def _resolve_base_dir() -> Path:
    configured = Path(get_settings().prompts_dir)
    if configured.is_absolute():
        return configured
    backend_root = Path(__file__).resolve().parents[2]
    candidate = backend_root / configured
    if candidate.exists():
        return candidate
    return configured


def _load_markdown(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Prompt file missing: {path}")
    mtime = path.stat().st_mtime
    with _CACHE_LOCK:
        cached = _FILE_CACHE.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
    text = path.read_text(encoding="utf-8")
    with _CACHE_LOCK:
        _FILE_CACHE[path] = (mtime, text)
    return text


def _render_template(template: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = _lookup_dotted(context, key)
        if value is None:
            return ""
        if isinstance(value, list):
            if not value:
                return "[]"
            return ", ".join(str(item) for item in value)
        return str(value)

    return PLACEHOLDER_PATTERN.sub(replace, template)


def _lookup_dotted(context: dict[str, Any], dotted_key: str) -> Any:
    current: Any = context
    for part in dotted_key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None
    return current
