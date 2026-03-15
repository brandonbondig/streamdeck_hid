# Stream Deck Mini HID Browser

This project turns a 3x2 Elgato Stream Deck Mini into a simple browser for HID payload scripts.

Scripts can come from:

- a local folder on the Raspberry Pi
- mounted USB volumes

When a script button is pressed, the Pi reads the text file and writes keyboard reports to the configured HID gadget device, usually `/dev/hidg0`.

## What It Does

- Mirrors folders from `STREAMDECK_SCRIPT_DIR` on the Stream Deck
- Shows an optional `USB` button when mounted volumes are found under `STREAMDECK_USB_MOUNT_ROOT`
- Lets the user pick a mounted USB drive, then browse its folders
- Uses yellow buttons for folders
- Uses blue buttons for scripts coming from USB
- Uses `REFRESH` to rescan local and USB sources
- Uses `BACK` inside folder pages and `MORE` when a page has too many items
- Loads folders lazily so startup does not hang on large or messy USB drives

## Requirements

- Elgato Stream Deck Mini with a 3x2 layout
- Python environment with the `streamdeck` package installed
- Raspberry Pi configured as a USB HID gadget that exposes `/dev/hidg0`

Optional:

- `pillow` for nicer key rendering

Important runtime notes:

- The official Elgato Stream Deck app must not be using the device at the same time.
- On macOS, if the HID backend is missing, install `hidapi` with `brew install hidapi`.

## Setup

Install dependencies in the Python environment you will actually use to run the app:

```bash
pip install streamdeck pillow
```

Create a `.env` based on `.env.example`:

```env
STREAMDECK_SCRIPT_DIR=./hid_scripts
STREAMDECK_HID_DEVICE=/dev/hidg0
STREAMDECK_SCRIPT_EXTENSIONS=.txt,.hid,.ducky
STREAMDECK_SOURCE_REFRESH_SECONDS=2
STREAMDECK_USB_MOUNT_ROOT=/media/pi
STREAMDECK_USB_SCAN_DEPTH=2
```

Environment variables:

- `STREAMDECK_SCRIPT_DIR`: local root folder for scripts and folders
- `STREAMDECK_HID_DEVICE`: HID gadget device to write keyboard reports to
- `STREAMDECK_SCRIPT_EXTENSIONS`: allowed script extensions
- `STREAMDECK_SOURCE_REFRESH_SECONDS`: how often the app rescans sources
- `STREAMDECK_USB_MOUNT_ROOT`: mount root that contains USB volumes, for example `/Volumes` on macOS or `/media/pi` on Raspberry Pi OS
- `STREAMDECK_USB_SCAN_DEPTH`: how deep to search for mount candidates when the mount root is not a flat directory like `/Volumes`
- `STREAMDECK_ENV_FILE`: optional path to a different env file; defaults to `.env`

## Folder Layout

Example local structure:

```text
hid_scripts/
  scripts/
    hello_pi.txt
    windows_login.txt
  admin/
    reboot_host.txt
```

Example with USB volumes:

```text
hid_scripts/
  scripts/

/media/pi/
  USB_ONE/
    payloads/
      login.txt
  USB_TWO/
    tools/
      launcher.txt
```

Behavior on the deck:

- Local folders and scripts appear on the root page
- A `USB` button appears only when at least one mounted volume is found
- Opening `USB` shows one button per mounted drive
- Opening a drive mirrors that drive's folders

Unreadable files, hidden system folders, and symlink loops are skipped.

## Running

Start the app with:

```bash
python main.py
```

The app targets a Stream Deck Mini specifically. If a different model is connected, it will reject it.

## HID Script Files

Scripts must be UTF-8 text files using one of these extensions:

- `.txt`
- `.hid`
- `.ducky`

Optional metadata at the top of a file:

```text
# label: HELLO
# description: Type hello from pi
# color: 30,140,210
```

- `label`: short button label
- `description`: help text printed to the terminal
- `color`: `R,G,B` or `#RRGGBB`

Example:

```text
# label: HELLO
# description: Type "hello from pi" and press Enter
# color: 30,140,210
STRING hello from pi
ENTER
```

## Supported Commands

```text
REM comment
DELAY 500
DEFAULT_DELAY 100
STRING hello world
STRINGLN hello world
KEY ENTER
ENTER
TAB
ESC
SPACE
DELETE
UP
DOWN
LEFT
RIGHT
CTRL ALT DELETE
GUI r
CTRL SHIFT ESC
```

Notes:

- `STRING` types plain text using a US keyboard layout
- `STRINGLN` types text and presses Enter
- Combo lines support modifiers plus one non-modifier key
- Supported modifiers include `CTRL`, `SHIFT`, `ALT`, `GUI`, `WIN`, `CMD`, `META`, and right-side variants such as `RALT`
- Lines starting with `REM` are ignored
- Lines starting with `#` are treated as comments by the executor

## Troubleshooting

- `The streamdeck package is not available in this Python interpreter`
  Use the same interpreter where you installed `streamdeck`.
- `Missing macOS library: libhidapi.dylib`
  Install it with `brew install hidapi`.
- `Detected ... but could not open it`
  Quit the Elgato Stream Deck app or any other software that already owns the device.
- `Could not open HID gadget device /dev/hidg0`
  The Raspberry Pi USB gadget setup is not ready, or the device path is wrong.
