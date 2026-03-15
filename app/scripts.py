from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

Color = tuple[int, int, int]
DEFAULT_SCRIPT_COLOR: Color = (215, 95, 45)
DEFAULT_FOLDER_COLOR: Color = (235, 190, 45)
LABEL_LIMIT = 7
IGNORED_DIRECTORY_NAMES = {
    ".spotlight-v100",
    ".fseventsd",
    ".trashes",
    "system volume information",
}

METADATA_PREFIX = "#"


@dataclass(frozen=True)
class HidScript:
    name: str
    path: Path
    label: str
    color: Color
    description: str


@dataclass(frozen=True)
class HidFolder:
    name: str
    path: Path
    label: str
    color: Color
    description: str


HidEntry = HidScript | HidFolder


class ScriptLoadError(ValueError):
    pass


def load_hid_entries(directory: Path, extensions: tuple[str, ...]) -> list[HidEntry]:
    if not directory.exists() or not directory.is_dir():
        return []

    folders: list[HidFolder] = []
    scripts: list[HidScript] = []
    allowed_extensions = {extension.lower() for extension in extensions}

    for path in safe_iterdir(directory):
        if path.is_symlink():
            continue

        if path.is_dir():
            if should_ignore_directory(path):
                continue

            folders.append(build_hid_folder(path))
            continue

        if not path.is_file() or path.suffix.lower() not in allowed_extensions:
            continue

        script = try_build_hid_script(path)
        if script is not None:
            scripts.append(script)

    return [*folders, *scripts]


def load_hid_scripts(script_dir: Path, extensions: tuple[str, ...]) -> list[HidScript]:
    if not script_dir.exists() or not script_dir.is_dir():
        return []

    scripts: list[HidScript] = []
    allowed_extensions = {extension.lower() for extension in extensions}

    for path in walk_script_files(script_dir, allowed_extensions):
        script = try_build_hid_script(path)
        if script is not None:
            scripts.append(script)

    return scripts


def build_hid_folder(path: Path) -> HidFolder:
    return HidFolder(
        name=path.name,
        path=path.resolve(),
        label=normalize_label(path.name),
        color=DEFAULT_FOLDER_COLOR,
        description=f"Open folder {path.name}",
    )


def build_hid_script(path: Path) -> HidScript:
    metadata = read_metadata(path)
    label = normalize_label(metadata.get("label", path.stem))
    description = metadata.get("description", f"Run {path.stem}")
    color = parse_color(metadata.get("color"))

    return HidScript(
        name=path.stem,
        path=path.resolve(),
        label=label,
        color=color,
        description=description,
    )


def try_build_hid_script(path: Path) -> HidScript | None:
    try:
        return build_hid_script(path)
    except ScriptLoadError:
        return None


def read_metadata(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}

    try:
        contents = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ScriptLoadError(f"Script file is not valid UTF-8 text: {path}") from exc
    except OSError as exc:
        raise ScriptLoadError(f"Could not read script file: {path}") from exc

    for raw_line in contents.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if not line.startswith(METADATA_PREFIX):
            break

        content = line[len(METADATA_PREFIX):].strip()
        if ":" not in content:
            continue

        key, value = content.split(":", 1)
        normalized_key = key.strip().lower()
        if normalized_key in {"label", "description", "color"}:
            metadata[normalized_key] = value.strip()

    return metadata


def normalize_label(value: str) -> str:
    normalized = value.replace("_", " ").replace("-", " ").strip().upper()
    if not normalized:
        return "SCRIPT"

    if len(normalized) <= LABEL_LIMIT:
        return normalized

    tokens = [token for token in re.split(r"\s+", normalized) if token]
    if len(tokens) >= 2:
        compact = "".join(token[:3] for token in tokens[:2])
        if compact:
            return compact[:LABEL_LIMIT]

    compact = re.sub(r"[^A-Z0-9]", "", normalized)
    return (compact or "SCRIPT")[:LABEL_LIMIT]


def parse_color(value: str | None) -> Color:
    if not value:
        return DEFAULT_SCRIPT_COLOR

    stripped = value.strip()
    if stripped.startswith("#") and len(stripped) == 7:
        try:
            return (
                int(stripped[1:3], 16),
                int(stripped[3:5], 16),
                int(stripped[5:7], 16),
            )
        except ValueError:
            return DEFAULT_SCRIPT_COLOR

    parts = [part.strip() for part in stripped.split(",")]
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        red, green, blue = (max(0, min(255, int(part))) for part in parts)
        return red, green, blue

    return DEFAULT_SCRIPT_COLOR


def safe_iterdir(directory: Path) -> list[Path]:
    try:
        return sorted(directory.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return []


def should_ignore_directory(path: Path) -> bool:
    name = path.name.strip().lower()
    return name.startswith(".") or name in IGNORED_DIRECTORY_NAMES


def walk_script_files(
    root_dir: Path,
    allowed_extensions: set[str],
    visited: set[Path] | None = None,
) -> Iterable[Path]:
    if visited is None:
        visited = set()

    try:
        resolved_root = root_dir.resolve()
    except OSError:
        return

    if resolved_root in visited:
        return

    visited.add(resolved_root)

    for path in safe_iterdir(root_dir):
        if path.is_symlink():
            continue

        if path.is_dir():
            if should_ignore_directory(path):
                continue

            yield from walk_script_files(path, allowed_extensions, visited)
            continue

        if path.is_file() and path.suffix.lower() in allowed_extensions:
            yield path
