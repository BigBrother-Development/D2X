# 8BitDo XInput Bridge

Makes an 8BitDo Ultimate 2 Wireless connected over Bluetooth appear to Windows as a virtual Xbox 360 (XInput) controller, so games that only support XInput (for example WoW) accept it.

In Bluetooth mode the pad is a generic DInput gamepad (USB ID 2DC8:6012, 6 axes, 24 buttons, 1 hat). The bridge reads it with SDL (pygame) and feeds a virtual Xbox 360 pad created through the ViGEmBus driver (vgamepad).

## Use

1. Pair the pad over Bluetooth.
2. Run `8BitDo-XInput-Bridge.exe` and leave the window open while you play.
   - First run on a PC without ViGEmBus: it offers to install the bundled driver (one administrator prompt) and relaunches.
   - First run without a mapping: it walks you through pressing each control.
3. Keys while running: `S` toggles start-with-Windows, `Q` quits.

Commands:

```
8BitDo-XInput-Bridge.exe              run the bridge
8BitDo-XInput-Bridge.exe map          redo only missing mapping steps ("map all" redoes everything)
8BitDo-XInput-Bridge.exe startup on   start at login (also: off, status)
```

`mapping.json` lives next to the EXE and can be edited or deleted to remap.

## Build

```
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\build.ps1
```

Or run from source: `.\.venv\Scripts\python.exe bridge.py`.

`tools/probe.py` prints raw axes, buttons and hat of the pad; `tools/xcheck.py` lists which XInput slots are occupied (`watch` argument prints live values).

## Known limits

- Triggers: over Bluetooth this pad reports LT and RT as plain buttons (8 and 9), so they are fully on or fully off. Analog triggers need the 2.4G dongle or USB, where the pad is already XInput and this bridge is not needed.
- Back buttons (L4, R4, PL, PR) are recorded in `mapping.json` but do nothing: an Xbox 360 pad has no spare buttons. `EXTRA_ASSIGN` in `bridge.py` can make each act as a standard button.
- The pad is matched by USB ID 2DC8:6012. Other 8BitDo models or modes need `VID_PID_MARK` changed and a new mapping.
- ViGEmBus is end-of-life upstream. The bundled installer is version 1.17.333, taken from the vgamepad package.
- Tested only on Windows 10. Windows 11 is untested.
- The real DInput pad stays visible to games alongside the virtual one. If a game double-reads it, hide it with HidHide.
