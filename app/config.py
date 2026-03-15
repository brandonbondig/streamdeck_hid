from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

from .scripts import DEFAULT_FOLDER_COLOR, HidEntry, HidFolder, load_hid_entries

Color = tuple[int, int, int]
ButtonAction = Literal["brightness", "clear", "exit", "page", "replace_page", "back", "home", "noop", "script", "refresh"]
KEY_COUNT = 6
PAGE_PREFIX = "browser_"
ROOT_PAGE = f"{PAGE_PREFIX}root_0"
ROOT_TITLE = "Folders"
USB_INDEX_PAGE_PREFIX = f"{PAGE_PREFIX}usb_index_"
ROOT_SINGLE_PAGE_CAPACITY = 5
ROOT_PAGED_CAPACITY = 4
CHILD_SINGLE_PAGE_CAPACITY = 5
CHILD_PAGED_CAPACITY = 4
USB_SCRIPT_COLOR: Color = (55, 135, 235)


@dataclass(frozen=True)
class ButtonSpec:
    label: str
    color: Color
    action: ButtonAction
    description: str
    value: int | None = None
    target_page: str | None = None
    script_path: Path | None = None


@dataclass(frozen=True)
class PageSpec:
    id: str
    title: str
    buttons: tuple[ButtonSpec, ...]


@dataclass(frozen=True)
class SourceSpec:
    id: str
    title: str
    root_dir: Path
    root_button_label: str | None
    root_button_description: str | None = None
    root_button_color: Color = DEFAULT_FOLDER_COLOR
    script_button_color: Color | None = None


@dataclass(frozen=True)
class DirectoryTarget:
    source: SourceSpec
    relative_path: Path


EMPTY_BUTTON = ButtonSpec(
    label="",
    color=(24, 24, 24),
    action="noop",
    description="Unused",
)


def page_from_slots(id: str, title: str, buttons: list[ButtonSpec]) -> PageSpec:
    if len(buttons) != KEY_COUNT:
        raise ValueError(f"Page {id!r} must define exactly {KEY_COUNT} buttons.")

    return PageSpec(id=id, title=title, buttons=tuple(buttons))


def root_page_id(page_index: int) -> str:
    return f"{PAGE_PREFIX}root_{page_index}"


def usb_index_page_id(page_index: int) -> str:
    return f"{USB_INDEX_PAGE_PREFIX}{page_index}"


def directory_page_id(source_id: str, relative_path: Path, page_index: int) -> str:
    parts = [sanitize_path_part(part) for part in relative_path.parts if part not in {"", "."}]
    suffix = "__".join(parts) if parts else "root"
    return f"{PAGE_PREFIX}{source_id}__{suffix}_{page_index}"


def sanitize_path_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "dir"


def build_pages(
    script_dir: Path,
    extensions: tuple[str, ...],
    usb_roots: list[Path] | None = None,
) -> tuple[dict[str, PageSpec], dict[str, DirectoryTarget]]:
    local_source = SourceSpec(
        id="local",
        title=ROOT_TITLE,
        root_dir=script_dir.resolve(),
        root_button_label=None,
    )

    pages: dict[str, PageSpec] = {}
    directory_targets: dict[str, DirectoryTarget] = {}
    root_buttons = build_root_buttons(local_source, extensions, directory_targets)

    usb_sources = build_usb_sources(usb_roots or [])
    if usb_sources:
        root_buttons.append(
            ButtonSpec(
                label="USB",
                color=DEFAULT_FOLDER_COLOR,
                action="page",
                description="Choose a connected USB drive",
                target_page=usb_index_page_id(0),
            )
        )
        build_usb_index_pages(usb_sources, pages, directory_targets)

    build_root_pages(root_buttons, pages)
    return pages, directory_targets


def build_usb_sources(usb_roots: list[Path]) -> list[SourceSpec]:
    usb_sources: list[SourceSpec] = []

    for index, usb_root in enumerate(usb_roots):
        resolved_root = usb_root.resolve()
        usb_sources.append(
            SourceSpec(
                id=f"usb_{index}_{sanitize_path_part(resolved_root.name)}",
                title=resolved_root.name or f"USB {index + 1}",
                root_dir=resolved_root,
                root_button_label=normalize_button_label(resolved_root.name or f"USB {index + 1}"),
                root_button_description=f"Open USB drive {resolved_root.name or index + 1}",
                script_button_color=USB_SCRIPT_COLOR,
            )
        )

    return usb_sources


def build_root_buttons(
    source: SourceSpec,
    extensions: tuple[str, ...],
    directory_targets: dict[str, DirectoryTarget],
) -> list[ButtonSpec]:
    entries = load_hid_entries(source.root_dir, extensions)
    return [button_for_entry(source, entry, directory_targets) for entry in entries]


def build_root_pages(buttons: list[ButtonSpec], pages: dict[str, PageSpec]) -> None:
    if not buttons:
        pages[root_page_id(0)] = build_empty_root_page()
        return

    if len(buttons) <= ROOT_SINGLE_PAGE_CAPACITY:
        chunks = [buttons]
    else:
        first_chunk = buttons[:3]
        remaining_chunks = [
            buttons[index:index + ROOT_PAGED_CAPACITY]
            for index in range(3, len(buttons), ROOT_PAGED_CAPACITY)
        ]
        chunks = [first_chunk, *remaining_chunks]

    for page_index, chunk in enumerate(chunks):
        page_buttons = [EMPTY_BUTTON] * KEY_COUNT
        for button_index, button in enumerate(chunk):
            page_buttons[button_index] = button

        apply_root_navigation_buttons(page_buttons, len(chunks), page_index)
        title = ROOT_TITLE if len(chunks) == 1 else f"{ROOT_TITLE} {page_index + 1}/{len(chunks)}"
        pages[root_page_id(page_index)] = page_from_slots(root_page_id(page_index), title, page_buttons)


def build_empty_root_page() -> PageSpec:
    buttons = [EMPTY_BUTTON] * KEY_COUNT
    buttons[0] = ButtonSpec(
        label="EMPTY",
        color=(70, 70, 70),
        action="noop",
        description="No folders or scripts found",
    )
    apply_root_navigation_buttons(buttons, total_pages=1, page_index=0)
    return page_from_slots(root_page_id(0), ROOT_TITLE, buttons)


def apply_root_navigation_buttons(buttons: list[ButtonSpec], total_pages: int, page_index: int) -> None:
    buttons[5] = ButtonSpec(
        label="REFRESH",
        color=(45, 150, 165),
        action="refresh",
        description="Rescan local and USB sources",
    )

    if total_pages > 1:
        buttons[4] = ButtonSpec(
            label="MORE",
            color=(85, 120, 175),
            action="replace_page",
            description="Open next root page",
            target_page=root_page_id((page_index + 1) % total_pages),
        )


def build_usb_index_pages(
    usb_sources: list[SourceSpec],
    pages: dict[str, PageSpec],
    directory_targets: dict[str, DirectoryTarget],
) -> None:
    buttons = [build_source_root_button(source, directory_targets) for source in usb_sources]
    page_capacity = CHILD_SINGLE_PAGE_CAPACITY if len(buttons) <= CHILD_SINGLE_PAGE_CAPACITY else CHILD_PAGED_CAPACITY
    chunks = [buttons[index:index + page_capacity] for index in range(0, len(buttons), page_capacity)]

    for page_index, chunk in enumerate(chunks):
        page_buttons = [EMPTY_BUTTON] * KEY_COUNT
        for button_index, button in enumerate(chunk):
            page_buttons[button_index] = button

        apply_usb_index_navigation_buttons(page_buttons, len(chunks), page_index)
        title = "USB" if len(chunks) == 1 else f"USB {page_index + 1}/{len(chunks)}"
        pages[usb_index_page_id(page_index)] = page_from_slots(usb_index_page_id(page_index), title, page_buttons)


def apply_usb_index_navigation_buttons(buttons: list[ButtonSpec], total_pages: int, page_index: int) -> None:
    buttons[5] = ButtonSpec(
        label="BACK",
        color=(110, 110, 110),
        action="back",
        description="Go back one folder",
    )

    if total_pages > 1:
        buttons[4] = ButtonSpec(
            label="MORE",
            color=(85, 120, 175),
            action="replace_page",
            description="Open next USB page",
            target_page=usb_index_page_id((page_index + 1) % total_pages),
        )


def build_directory_pages(
    source: SourceSpec,
    extensions: tuple[str, ...],
    relative_path: Path,
) -> tuple[dict[str, PageSpec], dict[str, DirectoryTarget]]:
    current_dir = source.root_dir / relative_path
    relative_path = current_dir.relative_to(source.root_dir)
    entries = load_hid_entries(current_dir, extensions)
    pages: dict[str, PageSpec] = {}
    directory_targets: dict[str, DirectoryTarget] = {}

    if not entries:
        page_id = directory_page_id(source.id, relative_path, 0)
        pages[page_id] = build_empty_directory_page(source, relative_path)
        directory_targets[page_id] = DirectoryTarget(source=source, relative_path=relative_path)
        return pages, directory_targets

    build_directory_pages_for_entries(source, relative_path, entries, pages, directory_targets)
    return pages, directory_targets


def build_directory_pages_for_entries(
    source: SourceSpec,
    relative_path: Path,
    entries: list[HidEntry],
    pages: dict[str, PageSpec],
    directory_targets: dict[str, DirectoryTarget],
) -> None:
    page_capacity = CHILD_SINGLE_PAGE_CAPACITY if len(entries) <= CHILD_SINGLE_PAGE_CAPACITY else CHILD_PAGED_CAPACITY
    chunks = [entries[index:index + page_capacity] for index in range(0, len(entries), page_capacity)]

    for page_index, chunk in enumerate(chunks):
        buttons = [EMPTY_BUTTON] * KEY_COUNT
        for button_index, entry in enumerate(chunk):
            buttons[button_index] = button_for_entry(source, entry, directory_targets)

        apply_directory_navigation_buttons(source, buttons, relative_path, len(chunks), page_index)
        page_id = directory_page_id(source.id, relative_path, page_index)
        pages[page_id] = page_from_slots(
            page_id,
            title_for_directory(source, relative_path, len(chunks), page_index),
            buttons,
        )
        directory_targets[page_id] = DirectoryTarget(source=source, relative_path=relative_path)


def build_empty_directory_page(source: SourceSpec, relative_path: Path) -> PageSpec:
    buttons = [EMPTY_BUTTON] * KEY_COUNT
    buttons[0] = ButtonSpec(
        label="EMPTY",
        color=(70, 70, 70),
        action="noop",
        description="Folder is empty",
    )
    apply_directory_navigation_buttons(source, buttons, relative_path, total_pages=1, page_index=0)
    return page_from_slots(
        directory_page_id(source.id, relative_path, 0),
        title_for_directory(source, relative_path, total_pages=1, page_index=0),
        buttons,
    )


def apply_directory_navigation_buttons(
    source: SourceSpec,
    buttons: list[ButtonSpec],
    relative_path: Path,
    total_pages: int,
    page_index: int,
) -> None:
    buttons[5] = ButtonSpec(
        label="BACK",
        color=(110, 110, 110),
        action="back",
        description="Go back one folder",
    )

    if total_pages > 1:
        buttons[4] = ButtonSpec(
            label="MORE",
            color=(85, 120, 175),
            action="replace_page",
            description="Open next folder page",
            target_page=directory_page_id(source.id, relative_path, (page_index + 1) % total_pages),
        )


def build_source_root_button(source: SourceSpec, directory_targets: dict[str, DirectoryTarget]) -> ButtonSpec:
    assert source.root_button_label is not None
    target_page = directory_page_id(source.id, Path("."), 0)
    directory_targets[target_page] = DirectoryTarget(source=source, relative_path=Path("."))
    return ButtonSpec(
        label=source.root_button_label,
        color=source.root_button_color,
        action="page",
        description=source.root_button_description or f"Open {source.title}",
        target_page=target_page,
    )


def button_for_entry(
    source: SourceSpec,
    entry: HidEntry,
    directory_targets: dict[str, DirectoryTarget],
) -> ButtonSpec:
    if isinstance(entry, HidFolder):
        relative_path = entry.path.relative_to(source.root_dir)
        target_page = directory_page_id(source.id, relative_path, 0)
        directory_targets[target_page] = DirectoryTarget(source=source, relative_path=relative_path)
        return ButtonSpec(
            label=entry.label,
            color=entry.color,
            action="page",
            description=entry.description,
            target_page=target_page,
        )

    color = source.script_button_color if source.script_button_color is not None else entry.color
    return ButtonSpec(
        label=entry.label,
        color=color,
        action="script",
        description=entry.description,
        script_path=entry.path,
    )


def title_for_directory(source: SourceSpec, relative_path: Path, total_pages: int, page_index: int) -> str:
    folder_name = source.title if not relative_path.parts else relative_path.name
    if total_pages == 1:
        return folder_name

    return f"{folder_name} {page_index + 1}/{total_pages}"


def normalize_button_label(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", " ", value).strip().upper()
    if not normalized:
        return "USB"

    if len(normalized) <= 7:
        return normalized

    tokens = normalized.split()
    if len(tokens) >= 2:
        compact = "".join(token[:3] for token in tokens[:2])
        if compact:
            return compact[:7]

    return normalized.replace(" ", "")[:7]
