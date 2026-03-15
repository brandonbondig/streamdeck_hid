from __future__ import annotations

import threading
import time
from pathlib import Path

MODIFIERS = {
    "CTRL": 0x01,
    "CONTROL": 0x01,
    "SHIFT": 0x02,
    "ALT": 0x04,
    "GUI": 0x08,
    "WIN": 0x08,
    "CMD": 0x08,
    "META": 0x08,
    "RCTRL": 0x10,
    "RSHIFT": 0x20,
    "RALT": 0x40,
    "RGUI": 0x80,
}

SPECIAL_KEYS = {
    "ENTER": 0x28,
    "RETURN": 0x28,
    "ESC": 0x29,
    "ESCAPE": 0x29,
    "BACKSPACE": 0x2A,
    "TAB": 0x2B,
    "SPACE": 0x2C,
    "MINUS": 0x2D,
    "EQUAL": 0x2E,
    "LEFTBRACE": 0x2F,
    "RIGHTBRACE": 0x30,
    "BACKSLASH": 0x31,
    "SEMICOLON": 0x33,
    "APOSTROPHE": 0x34,
    "GRAVE": 0x35,
    "COMMA": 0x36,
    "DOT": 0x37,
    "PERIOD": 0x37,
    "SLASH": 0x38,
    "CAPSLOCK": 0x39,
    "F1": 0x3A,
    "F2": 0x3B,
    "F3": 0x3C,
    "F4": 0x3D,
    "F5": 0x3E,
    "F6": 0x3F,
    "F7": 0x40,
    "F8": 0x41,
    "F9": 0x42,
    "F10": 0x43,
    "F11": 0x44,
    "F12": 0x45,
    "PRINTSCREEN": 0x46,
    "SCROLLLOCK": 0x47,
    "PAUSE": 0x48,
    "INSERT": 0x49,
    "HOME": 0x4A,
    "PAGEUP": 0x4B,
    "DELETE": 0x4C,
    "END": 0x4D,
    "PAGEDOWN": 0x4E,
    "RIGHT": 0x4F,
    "LEFT": 0x50,
    "DOWN": 0x51,
    "UP": 0x52,
}

SHIFT_CHARACTERS = {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "-",
    "+": "=",
    "{": "[",
    "}": "]",
    "|": "\\",
    ":": ";",
    '"': "'",
    "~": "`",
    "<": ",",
    ">": ".",
    "?": "/",
}

BASE_CHARACTER_CODES = {
    "-": 0x2D,
    "=": 0x2E,
    "[": 0x2F,
    "]": 0x30,
    "\\": 0x31,
    ";": 0x33,
    "'": 0x34,
    "`": 0x35,
    ",": 0x36,
    ".": 0x37,
    "/": 0x38,
    " ": 0x2C,
}


class HIDScriptError(RuntimeError):
    pass


class HIDScriptRunner:
    def __init__(self, device_path: Path, hold_seconds: float = 0.02):
        self.device_path = device_path
        self.hold_seconds = hold_seconds
        self.lock = threading.Lock()

    def run_script_file(self, path: Path) -> None:
        script_text = path.read_text(encoding="utf-8")

        try:
            with self.lock, self.device_path.open("wb", buffering=0) as hid_device:
                executor = HIDExecutor(hid_device, self.hold_seconds)
                executor.execute(script_text)
        except OSError as exc:
            raise HIDScriptError(f"Could not open HID gadget device {self.device_path}: {exc}") from exc


class HIDExecutor:
    def __init__(self, hid_device, hold_seconds: float):
        self.hid_device = hid_device
        self.hold_seconds = hold_seconds

    def execute(self, script_text: str) -> None:
        default_delay_ms = 0

        for line_number, raw_line in enumerate(script_text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            upper_line = line.upper()
            if upper_line.startswith("REM "):
                continue

            command, _, remainder = line.partition(" ")
            upper_command = command.upper()

            if upper_command in {"DEFAULT_DELAY", "DEFAULTDELAY"}:
                default_delay_ms = parse_delay_ms(remainder, line_number)
                continue

            if upper_command == "DELAY":
                self.delay(parse_delay_ms(remainder, line_number))
                continue

            if upper_command == "STRING":
                self.type_text(remainder)
                self.apply_default_delay(default_delay_ms)
                continue

            if upper_command == "STRINGLN":
                self.type_text(remainder)
                self.tap_key(0, SPECIAL_KEYS["ENTER"])
                self.apply_default_delay(default_delay_ms)
                continue

            if upper_command == "KEY":
                if not remainder.strip():
                    raise HIDScriptError(f"Line {line_number}: KEY requires a key name or character.")

                modifiers, keycode = resolve_token(remainder.strip())
                self.tap_key(modifiers, keycode)
                self.apply_default_delay(default_delay_ms)
                continue

            modifiers, keycode = resolve_combo(line, line_number)
            self.tap_key(modifiers, keycode)
            self.apply_default_delay(default_delay_ms)

    def type_text(self, text: str) -> None:
        for character in text:
            modifiers, keycode = resolve_character(character)
            self.tap_key(modifiers, keycode)

    def tap_key(self, modifiers: int, keycode: int) -> None:
        self.write_report(modifiers, keycode)
        time.sleep(self.hold_seconds)
        self.write_report(0, 0)
        time.sleep(self.hold_seconds)

    def write_report(self, modifiers: int, keycode: int) -> None:
        report = bytes([modifiers, 0, keycode, 0, 0, 0, 0, 0])
        self.hid_device.write(report)
        self.hid_device.flush()

    def delay(self, milliseconds: int) -> None:
        time.sleep(milliseconds / 1000)

    def apply_default_delay(self, default_delay_ms: int) -> None:
        if default_delay_ms > 0:
            self.delay(default_delay_ms)


def parse_delay_ms(value: str, line_number: int) -> int:
    cleaned_value = value.strip()
    if not cleaned_value or not cleaned_value.isdigit():
        raise HIDScriptError(f"Line {line_number}: delay value must be an integer number of milliseconds.")

    return int(cleaned_value)


def resolve_combo(line: str, line_number: int) -> tuple[int, int]:
    modifiers = 0
    keycode: int | None = None

    for token in line.split():
        upper_token = token.upper()
        if upper_token in MODIFIERS:
            modifiers |= MODIFIERS[upper_token]
            continue

        if keycode is not None:
            raise HIDScriptError(f"Line {line_number}: only one non-modifier key is supported per combo.")

        _, keycode = resolve_token(token)

    if keycode is None:
        raise HIDScriptError(f"Line {line_number}: combo must include a non-modifier key.")

    return modifiers, keycode


def resolve_token(token: str) -> tuple[int, int]:
    stripped_token = token.strip()
    if not stripped_token:
        raise HIDScriptError("Empty key token.")

    upper_token = stripped_token.upper()
    if upper_token in SPECIAL_KEYS:
        return 0, SPECIAL_KEYS[upper_token]

    if len(stripped_token) == 1:
        return resolve_character(stripped_token)

    if len(upper_token) == 1:
        return resolve_character(upper_token)

    raise HIDScriptError(f"Unsupported key token: {token}")


def resolve_character(character: str) -> tuple[int, int]:
    if len(character) != 1:
        raise HIDScriptError(f"Unsupported character token: {character}")

    if "a" <= character <= "z":
        return 0, 0x04 + (ord(character) - ord("a"))

    if "A" <= character <= "Z":
        return MODIFIERS["SHIFT"], 0x04 + (ord(character) - ord("A"))

    if "1" <= character <= "9":
        return 0, 0x1E + (ord(character) - ord("1"))

    if character == "0":
        return 0, 0x27

    if character in BASE_CHARACTER_CODES:
        return 0, BASE_CHARACTER_CODES[character]

    if character in SHIFT_CHARACTERS:
        _, base_keycode = resolve_character(SHIFT_CHARACTERS[character])
        return MODIFIERS["SHIFT"], base_keycode

    raise HIDScriptError(f"Unsupported character: {character!r}")
