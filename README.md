# DInput to XInput

Makes a generic DInput gamepad (Bluetooth or USB) look like an Xbox 360 (XInput) controller to Windows, so games that only support XInput accept it. Windows only.

The program reads the real controller through SDL (pygame) and feeds a virtual Xbox 360 pad created with the ViGEmBus driver (via vgamepad). A small window lets you pick the controller and a mapping, create new mappings, and set start-with-Windows and minimize-to-tray.

Tested only with the 8BitDo Ultimate 2 Wireless over Bluetooth (DInput mode) on Windows 10. Other controllers should work if Windows exposes them as a generic gamepad, but that is unverified.

## Use

1. Connect the controller (Bluetooth pairing or USB).
2. Run `DInput-to-XInput.exe` and leave it running while you play.
3. Pick a mapping in the dropdown, or press **New mapping...**, name it, and press each control when asked. **Skip this control** leaves a control unmapped.
4. Options: **Start with Windows** (per-user startup entry, no admin needed) and **Minimize to tray** (minimize and the close button hide the window to the tray; right-click the tray icon for Exit).

If the ViGEmBus driver is missing, the window shows an **Install driver** button. It runs the installer that ships inside the program and asks for administrator permission once.

## Mappings

One JSON file per controller in `%APPDATA%\DInput2XInput\mappings` (the **Open folder** button opens it). The mappings in this repo's `mappings` folder are copied there on first run, for example `8BitDo Ultimate 2`. Structure:

```
{ "name": "...", "vidpid": "2DC8:6012", "rest": [axis rest values],
  "bindings": { "A": {"type": "button", "index": 0},
                "DUP": {"type": "hat", "index": 0, "value": [0, 1]},
                "LT": {"type": "button", "index": 8},
                "LX": {"type": "axis", "index": 0, "rest": -0.008, "full": 1.0}, ... } }
```

A trigger bound to an `axis` gives analog values; bound to a `button` it is fully on or off.

With the controller dropdown on Auto, a mapping is used with the connected controller that has the same USB vendor:product ID. Pick a specific controller to override that.

## Build

```
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\build.ps1
```

Output: `dist\DInput-to-XInput.exe`. To run from source: `.\.venv\Scripts\python.exe app.py`. `app.py --screenshot out.png` saves a picture of the window and exits.

`tools\probe.py` prints a controller's raw axes, buttons and hat; `tools\xcheck.py` lists occupied XInput slots (`watch` prints live values).

## Known limits

- Xbox 360 style pads are hidden from the list: they are already XInput, and the virtual pad itself is one.
- An Xbox 360 pad has 10 buttons plus the D-pad and Guide, so extra buttons (back paddles and similar) cannot be passed on.
- On some pads, such as the 8BitDo Ultimate 2 over Bluetooth, the triggers are reported as plain buttons, so they are fully on or off. Pads that report an analog axis get analog triggers.
- ViGEmBus is end-of-life upstream. The bundled installer is version 1.17.333, taken from the vgamepad package.
- The real DInput pad stays visible to games next to the virtual one. If a game double-reads it, hide it with HidHide.
- Windows 11 is untested.
