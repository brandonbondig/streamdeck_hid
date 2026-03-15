from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from .config import ROOT_PAGE, ButtonSpec, DirectoryTarget, PageSpec, build_directory_pages, build_pages, directory_page_id
from .deck import describe_layout, find_mini_deck, format_open_error
from .dependencies import TransportError
from .hid import HIDScriptError, HIDScriptRunner
from .rendering import print_help, redraw_all_keys, update_key
from .scripts import load_hid_scripts
from .settings import Settings, load_settings
from .usb import discover_usb_roots


class StreamDeckMiniApp:
    def __init__(self, settings: Settings | None = None, root_page_id: str = ROOT_PAGE):
        self.settings = load_settings() if settings is None else settings
        self.state_lock = threading.RLock()
        self.usb_roots: tuple[Path, ...] = ()
        self.hid_scripts: list[Any] = []
        self.base_pages: dict[str, PageSpec] = {}
        self.base_directory_targets: dict[str, DirectoryTarget] = {}
        self.directory_targets: dict[str, DirectoryTarget] = {}
        self.running_script_path: Path | None = None
        self.hid_runner = HIDScriptRunner(self.settings.hid_device)
        self.pages: dict[str, PageSpec] = {}
        self.root_page_id = root_page_id
        self.current_page_id = root_page_id
        self.page_stack: list[str] = []
        self.stop_event = threading.Event()
        self.deck: Any | None = None
        self.refresh_sources(force=True)
        self.validate_pages()

    def run(self) -> int:
        try:
            self.deck = find_mini_deck()
        except RuntimeError as exc:
            print(exc)
            return 1

        if not self.open_deck():
            return 1

        try:
            print(f"Connected to {self.deck.deck_type()} ({describe_layout(self.deck)})")
            print(f"Serial: {self.get_serial_number()}")
            print(f"HID device: {self.settings.hid_device}")
            print(f"HID script directory: {self.settings.script_dir}")
            print(self.usb_status_text())
            print(f"Indexed {len(self.hid_scripts)} local HID script(s)")
            print_help(self.current_page)

            next_refresh_at = time.monotonic() + self.settings.source_refresh_seconds
            while not self.stop_event.wait(0.25):
                if time.monotonic() < next_refresh_at:
                    continue

                if self.refresh_sources():
                    print(self.usb_status_text())
                    print(f"Indexed {len(self.hid_scripts)} local HID script(s)")
                    self.redraw_current_page()

                next_refresh_at = time.monotonic() + self.settings.source_refresh_seconds
        except KeyboardInterrupt:
            print("\nStopping.")
        finally:
            self.close_deck()

        return 0

    def open_deck(self) -> bool:
        assert self.deck is not None

        try:
            self.deck.open()
        except TransportError as exc:
            print(format_open_error(self.deck, exc))
            return False

        self.deck.reset()
        self.deck.set_brightness(50)
        redraw_all_keys(self.deck, self.current_page)
        self.deck.set_key_callback(self.on_key_change)
        return True

    def close_deck(self) -> None:
        if self.deck is not None and self.deck.is_open():
            self.deck.reset()
            self.deck.close()

    def get_serial_number(self) -> str:
        assert self.deck is not None

        try:
            return self.deck.get_serial_number()
        except Exception:
            return "unknown"

    @property
    def current_page(self) -> PageSpec:
        with self.state_lock:
            return self.pages[self.current_page_id]

    def usb_status_text(self) -> str:
        with self.state_lock:
            if not self.usb_roots:
                return "USB source: not connected"

            names = ", ".join(path.name or str(path) for path in self.usb_roots)
            return f"USB sources: {names}"

    def validate_pages(self) -> None:
        with self.state_lock:
            if self.root_page_id not in self.pages:
                raise ValueError(f"Unknown root page: {self.root_page_id}")

            for page in self.pages.values():
                for button in page.buttons:
                    if (
                        button.action in {"page", "replace_page"}
                        and button.target_page not in self.pages
                        and button.target_page not in self.directory_targets
                    ):
                        raise ValueError(f"Button {button.label!r} points to unknown page {button.target_page!r}")
                    if button.action == "script" and button.script_path is None:
                        raise ValueError(f"Button {button.label!r} is missing a script path.")

    def ensure_page_loaded(self, page_id: str) -> bool:
        with self.state_lock:
            if page_id in self.pages:
                return True

            target = self.directory_targets.get(page_id)

        if target is None:
            return False

        self.load_directory_target(target)

        with self.state_lock:
            return page_id in self.pages

    def load_directory_target(self, target: DirectoryTarget) -> None:
        new_pages, new_targets = build_directory_pages(
            target.source,
            self.settings.script_extensions,
            target.relative_path,
        )

        with self.state_lock:
            self.pages.update(new_pages)
            self.directory_targets.update(new_targets)

    def on_key_change(self, deck: Any, key: int, state: bool) -> None:
        with self.state_lock:
            page = self.pages.get(self.current_page_id)
            if page is None or key >= len(page.buttons):
                return

            spec = page.buttons[key]

        update_key(deck, key, spec, pressed=state)

        if state:
            print(f"Key {key} pressed")
            return

        print(f"Key {key} released")
        self.run_action(spec)

    def run_action(self, spec: ButtonSpec) -> None:
        assert self.deck is not None

        if spec.action == "brightness" and spec.value is not None:
            self.deck.set_brightness(spec.value)
            print(f"Set brightness to {spec.value}%")
        elif spec.action == "clear":
            self.deck.reset()
            redraw_all_keys(self.deck, self.current_page)
            print("Cleared and redrew all keys.")
        elif spec.action == "page" and spec.target_page is not None:
            self.open_page(spec.target_page)
        elif spec.action == "replace_page" and spec.target_page is not None:
            self.replace_page(spec.target_page)
        elif spec.action == "back":
            self.go_back()
        elif spec.action == "home":
            self.go_home()
        elif spec.action == "script" and spec.script_path is not None:
            self.run_hid_script(spec)
        elif spec.action == "refresh":
            self.manual_refresh()
        elif spec.action == "exit":
            print("Exit requested from the Stream Deck.")
            self.stop_event.set()
        elif spec.action == "noop":
            pass

    def redraw_current_page(self) -> None:
        assert self.deck is not None
        if not self.ensure_page_loaded(self.current_page_id):
            return

        page = self.current_page
        redraw_all_keys(self.deck, page)
        print_help(page)

    def open_page(self, page_id: str) -> None:
        assert self.deck is not None

        if not self.ensure_page_loaded(page_id):
            return

        with self.state_lock:
            if page_id not in self.pages or page_id == self.current_page_id:
                return

            self.page_stack.append(self.current_page_id)
            self.current_page_id = page_id
            title = self.pages[self.current_page_id].title

        print(f"Opened page: {title}")
        self.redraw_current_page()

    def replace_page(self, page_id: str) -> None:
        assert self.deck is not None

        if not self.ensure_page_loaded(page_id):
            return

        with self.state_lock:
            if page_id not in self.pages or page_id == self.current_page_id:
                return

            self.current_page_id = page_id
            title = self.pages[self.current_page_id].title

        print(f"Opened page: {title}")
        self.redraw_current_page()

    def go_back(self) -> None:
        with self.state_lock:
            if not self.page_stack:
                print("Already on the top page.")
                return

            self.current_page_id = self.page_stack.pop()
            title = self.pages[self.current_page_id].title

        print(f"Returned to page: {title}")
        self.redraw_current_page()

    def go_home(self) -> None:
        with self.state_lock:
            if self.current_page_id == self.root_page_id and not self.page_stack:
                return

            self.current_page_id = self.root_page_id
            self.page_stack.clear()
            title = self.pages[self.current_page_id].title

        print(f"Returned to page: {title}")
        self.redraw_current_page()

    def run_hid_script(self, spec: ButtonSpec) -> None:
        assert spec.script_path is not None

        with self.state_lock:
            if self.running_script_path is not None:
                print(f"Script already running: {self.running_script_path.name}")
                return

            self.running_script_path = spec.script_path

        print(f"Running HID script: {spec.script_path.name}")
        thread = threading.Thread(
            target=self.execute_hid_script,
            args=(spec.script_path,),
            daemon=True,
        )
        thread.start()

    def execute_hid_script(self, script_path: Path) -> None:
        try:
            self.hid_runner.run_script_file(script_path)
            print(f"Finished HID script: {script_path.name}")
        except HIDScriptError as exc:
            print(f"HID script failed: {exc}")
        except Exception as exc:
            print(f"Unexpected HID script error for {script_path.name}: {exc}")
        finally:
            with self.state_lock:
                if self.running_script_path == script_path:
                    self.running_script_path = None

    def manual_refresh(self) -> None:
        changed = self.refresh_sources(force=True)
        print("Sources refreshed.")
        print(self.usb_status_text())
        print(f"Indexed {len(self.hid_scripts)} local HID script(s)")

        if changed and self.deck is not None and self.deck.is_open():
            self.redraw_current_page()

    def refresh_sources(self, force: bool = False) -> bool:
        with self.state_lock:
            previous_usb_roots = self.usb_roots
            current_directory_target = self.directory_targets.get(self.current_page_id)
            restore_targets = [
                target
                for target in [self.directory_targets.get(page_id) for page_id in [self.current_page_id, *self.page_stack]]
                if target is not None
            ]

        new_usb_roots = tuple(discover_usb_roots(self.settings))
        new_hid_scripts = load_hid_scripts(self.settings.script_dir, self.settings.script_extensions)
        new_pages, new_directory_targets = build_pages(
            self.settings.script_dir,
            self.settings.script_extensions,
            usb_roots=list(new_usb_roots),
        )

        with self.state_lock:
            changed = (
                force
                or new_usb_roots != self.usb_roots
                or new_hid_scripts != self.hid_scripts
                or new_pages != self.base_pages
                or new_directory_targets != self.base_directory_targets
            )

            if not changed:
                return False

            self.usb_roots = new_usb_roots
            self.hid_scripts = new_hid_scripts
            self.base_pages = dict(new_pages)
            self.base_directory_targets = dict(new_directory_targets)
            self.pages = dict(new_pages)
            self.directory_targets = dict(new_directory_targets)

        if previous_usb_roots == new_usb_roots:
            for target in dict.fromkeys(restore_targets):
                self.load_directory_target(target)

        with self.state_lock:
            if self.current_page_id not in self.pages:
                if current_directory_target is not None:
                    fallback_page_id = directory_page_id(
                        current_directory_target.source.id,
                        current_directory_target.relative_path,
                        0,
                    )
                    if fallback_page_id in self.pages:
                        self.current_page_id = fallback_page_id
                        self.page_stack = [page_id for page_id in self.page_stack if page_id in self.pages]
                    else:
                        self.current_page_id = self.root_page_id
                        self.page_stack.clear()
                else:
                    self.current_page_id = self.root_page_id
                    self.page_stack.clear()
            else:
                self.page_stack = [page_id for page_id in self.page_stack if page_id in self.pages]

        self.validate_pages()
        return True


def main() -> int:
    return StreamDeckMiniApp().run()
