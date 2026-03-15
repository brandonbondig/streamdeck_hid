from __future__ import annotations

import sys
from typing import Any

from .dependencies import DeviceManager, ProbeError


def describe_layout(deck: Any) -> str:
    rows, columns = deck.key_layout()
    return f"{columns}x{rows}"


def format_probe_error(exc: Exception) -> str:
    message_lines = [
        "Could not initialize the Stream Deck HID backend.",
        f"Python interpreter: {sys.executable}",
    ]

    details = str(exc)
    if "libhidapi.dylib" in details:
        message_lines.extend(
            [
                "Missing macOS library: libhidapi.dylib",
                "Install it with: brew install hidapi",
                "Then run this script again.",
            ]
        )
    else:
        message_lines.append(f"Backend error: {details}")

    return "\n".join(message_lines)


def format_open_error(deck: Any, exc: Exception) -> str:
    message_lines = [
        f"Detected {deck.deck_type()} ({describe_layout(deck)}), but could not open it.",
        "Another app likely already has exclusive access to the device.",
        "Quit the Elgato Stream Deck app or any other Stream Deck tool, then unplug and replug the deck and run this script again.",
        f"Backend error: {exc}",
    ]
    return "\n".join(message_lines)


def find_mini_deck() -> Any:
    try:
        decks = DeviceManager().enumerate()
    except ProbeError as exc:
        raise RuntimeError(format_probe_error(exc)) from exc

    if not decks:
        raise RuntimeError("No Stream Deck device found.")

    for deck in decks:
        if deck.key_layout() == (2, 3) and deck.key_count() == 6:
            return deck

    found = ", ".join(f"{deck.deck_type()} ({describe_layout(deck)})" for deck in decks)
    raise RuntimeError(f"Found Stream Deck devices, but none matched a 3x2 layout: {found}")
