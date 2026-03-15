from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = ".env"
DEFAULT_SCRIPT_DIR = "./hid_scripts"
DEFAULT_HID_DEVICE = "/dev/hidg0"
DEFAULT_SCRIPT_EXTENSIONS = (".txt", ".hid", ".ducky")
DEFAULT_SOURCE_REFRESH_SECONDS = 2.0
DEFAULT_USB_SCAN_DEPTH = 2


@dataclass(frozen=True)
class Settings:
    env_file: Path | None
    script_dir: Path
    hid_device: Path
    script_extensions: tuple[str, ...]
    source_refresh_seconds: float
    usb_mount_root: Path | None
    usb_scan_depth: int


def load_settings() -> Settings:
    env_file = load_default_env_file()
    base_dir = env_file.parent if env_file is not None else PROJECT_ROOT
    script_dir = resolve_setting_path(os.environ.get("STREAMDECK_SCRIPT_DIR", DEFAULT_SCRIPT_DIR), base_dir)
    hid_device = resolve_setting_path(os.environ.get("STREAMDECK_HID_DEVICE", DEFAULT_HID_DEVICE), base_dir)
    script_extensions = parse_script_extensions(os.environ.get("STREAMDECK_SCRIPT_EXTENSIONS"))
    source_refresh_seconds = parse_positive_float(
        os.environ.get("STREAMDECK_SOURCE_REFRESH_SECONDS"),
        DEFAULT_SOURCE_REFRESH_SECONDS,
    )
    usb_mount_root = parse_optional_path(os.environ.get("STREAMDECK_USB_MOUNT_ROOT"), base_dir)
    usb_scan_depth = parse_positive_int(
        os.environ.get("STREAMDECK_USB_SCAN_DEPTH"),
        DEFAULT_USB_SCAN_DEPTH,
    )

    return Settings(
        env_file=env_file,
        script_dir=script_dir,
        hid_device=hid_device,
        script_extensions=script_extensions,
        source_refresh_seconds=source_refresh_seconds,
        usb_mount_root=usb_mount_root,
        usb_scan_depth=usb_scan_depth,
    )


def load_default_env_file() -> Path | None:
    env_value = os.environ.get("STREAMDECK_ENV_FILE", DEFAULT_ENV_FILE).strip()
    if not env_value:
        return None

    env_path = resolve_env_file_path(env_value)
    if env_path is None:
        return None

    load_env_file(env_path)
    return env_path


def load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        cleaned_value = strip_matching_quotes(value.strip())
        os.environ.setdefault(key, cleaned_value)


def strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    return value


def parse_script_extensions(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_SCRIPT_EXTENSIONS

    extensions = []
    for raw_item in value.split(","):
        item = raw_item.strip().lower()
        if not item:
            continue

        if not item.startswith("."):
            item = f".{item}"

        extensions.append(item)

    return tuple(extensions or DEFAULT_SCRIPT_EXTENSIONS)


def parse_optional_path(value: str | None, base_dir: Path) -> Path | None:
    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    return resolve_path_value(cleaned, base_dir)


def resolve_setting_path(value: str, base_dir: Path) -> Path:
    return resolve_path_value(value, base_dir)


def resolve_path_value(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path

    return path.resolve()


def resolve_env_file_path(value: str) -> Path | None:
    env_path = Path(value).expanduser()
    candidates = [env_path]

    if not env_path.is_absolute():
        candidates.append(PROJECT_ROOT / env_path)

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved

    return None


def parse_positive_float(value: str | None, default: float) -> float:
    if value is None:
        return default

    cleaned = value.strip()
    if not cleaned:
        return default

    try:
        parsed = float(cleaned)
    except ValueError:
        return default

    return parsed if parsed > 0 else default


def parse_positive_int(value: str | None, default: int) -> int:
    if value is None:
        return default

    cleaned = value.strip()
    if not cleaned:
        return default

    try:
        parsed = int(cleaned)
    except ValueError:
        return default

    return parsed if parsed > 0 else default
