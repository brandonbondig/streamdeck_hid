from __future__ import annotations

from pathlib import Path

from .settings import Settings


def discover_usb_roots(settings: Settings) -> list[Path]:
    if settings.usb_mount_root is None or not settings.usb_mount_root.is_dir():
        return []

    mount_root = settings.usb_mount_root.resolve()
    if mount_root.name.lower() == "volumes":
        return direct_mount_dirs(mount_root)

    candidates = find_mount_candidates(mount_root, settings.usb_scan_depth)
    return dedupe_paths(candidates)


def find_mount_candidates(root: Path, max_depth: int) -> list[Path]:
    if max_depth <= 0 or not root.is_dir():
        return []

    candidates: list[Path] = []

    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.is_symlink():
            continue

        if not child.is_dir():
            continue

        child_entries = list(iter_directory(child))
        child_files = [entry for entry in child_entries if entry.is_file()]
        child_dirs = [entry for entry in child_entries if entry.is_dir()]

        if child_files or not child_dirs or max_depth == 1:
            candidates.append(child.resolve())
            continue

        nested_candidates = find_mount_candidates(child, max_depth - 1)
        if nested_candidates:
            candidates.extend(nested_candidates)

    return candidates


def dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []

    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue

        seen.add(resolved)
        result.append(resolved)

    return result


def direct_mount_dirs(root: Path) -> list[Path]:
    result: list[Path] = []

    for path in sorted(iter_directory(root), key=lambda item: item.name.lower()):
        if path.is_symlink():
            continue

        if path.is_dir():
            result.append(path.resolve())

    return result


def iter_directory(path: Path):
    try:
        yield from path.iterdir()
    except OSError:
        return
