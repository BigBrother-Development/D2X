# D2X: DInput to XInput

Makes a generic DInput gamepad (Bluetooth or USB) look like an Xbox 360 (XInput) controller to Windows, so games that only support XInput accept it. Windows only.

> **Heads up: this project was created with AI (Claude).** It was written for one specific controller, the **8BitDo Ultimate 2 Wireless over Bluetooth (DInput mode)**, and that is the only controller it has been tested with. It should work with any Bluetooth or USB controller that Windows exposes as a generic DInput gamepad, but that is unverified. **Not tested on Windows 11** (developed and tested on Windows 10). Expect rough edges and please report them.

## How it works

The program reads the real controller through SDL (pygame) and feeds a virtual Xbox 360 pad created with the [ViGEmBus](https://github.com/nefarius/ViGEmBus) driver (via [vgamepad](https://github.com/yannbouteiller/vgamepad)). A small window lets you pick the controller and a mapping, create new mappings, and set start-with-Windows and minimize-to-tray. Games see a normal XInput controller.

## Install

You need Windows 10 (Windows 11 is untested) and a controller already paired or plugged in.

**Option A: prebuilt EXE.** Download `D2X.exe` from the [Releases page](../../releases) and run it. No Python needed.

**Option B: build it yourself.** Needs Python 3.10 or newer and PowerShell:

```
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\build.ps1
```

Output: `dist\D2X.exe`. To run from source instead: `.\.venv\Scripts\python.exe app.py`.

### The ViGEmBus driver

The virtual pad needs the ViGEmBus driver. The EXE bundles the installer (version 1.17.333, taken from the vgamepad package). If the driver is missing, the window shows an **Install driver** button; it runs the bundled installer and asks for administrator permission once. If the driver is already installed, nothing extra is needed.

ViGEmBus is end-of-life upstream. It still works, but it is no longer updated.

## Use

1. Connect the controller (Bluetooth pairing or USB). If it is a Bluetooth pad that sleeps, press a button to wake it.
2. Run `D2X.exe` and leave it running while you play.
3. The window shows **Converting: <controller name>** when it is working. Start your game; it should see an Xbox 360 controller.

Window options:

- **Controller:** `Auto` matches the connected controller to the selected mapping by its USB vendor:product ID. Pick a specific controller to override that. **Refresh** rescans.
- **Mapping:** the mapping to use. Buttons: **New mapping...**, **Delete**, **Open folder**.
- **Start with Windows:** adds a per-user startup entry (no admin needed). It starts hidden in the tray, or minimized if the tray option is off.
- **Minimize to tray:** minimize and the close button hide the window to the system tray. Right-click the tray icon for Show and Exit.

## Creating a mapping for your controller

Each controller reports its buttons differently, so a mapping tells the program which physical control is which Xbox control. If your controller has no mapping yet:

1. Connect the controller and open the program.
2. Select your controller in the controller dropdown (leave `Auto` if only one is connected).
3. Click **New mapping...** and type a name, for example `Brand Model`.
4. Follow the prompts. Press or move each control when asked: A, B, X, Y, LB, RB, Back, Start, Guide, stick clicks, D-pad, triggers, then both sticks.
   - For the stick steps, push the stick fully in the direction asked and hold it.
   - If your controller has no such control, or you do not want to map it, click **Skip this control** to move on.
   - **Cancel** abandons the wizard without saving.
5. The mapping is saved and selected. Test it in a game or in Windows' game controller settings.

Notes on triggers: if your pad reports its triggers as an analog axis, you get analog triggers. Some pads, including the 8BitDo Ultimate 2 over Bluetooth, report them as plain buttons, so they are fully on or off. That is a limit of what the pad sends, not something the program can change.

### Mapping files

Mappings are plain JSON files, one per controller, in `%APPDATA%\D2X\mappings` (the **Open folder** button opens it). The files in this repository's [`mappings`](mappings) folder are copied there on first run. Structure:

```
{ "name": "...", "vidpid": "2DC8:6012", "rest": [axis rest values],
  "bindings": { "A": {"type": "button", "index": 0},
                "DUP": {"type": "hat", "index": 0, "value": [0, 1]},
                "LT": {"type": "button", "index": 8},
                "LX": {"type": "axis", "index": 0, "rest": -0.008, "full": 1.0}, ... } }
```

`vidpid` is the controller's USB vendor:product ID, used by `Auto` to pick the right mapping.

## Contributing your mapping

If you made a mapping for a controller and it works, please open a pull request so it ships by default and others do not have to redo it.

1. Fork this repository.
2. Copy your mapping file from `%APPDATA%\D2X\mappings` into the repository's `mappings` folder. Name it after the controller, for example `Brand Model.json`.
3. Check that `vidpid` is set and that `name` matches the file name.
4. Open a pull request. In the description, say which controller it is, how it connects (Bluetooth, USB, 2.4G dongle), which controller mode it was in (for example DInput), your Windows version, and which games you tried. Mention any controls you skipped.

Bug fixes and other improvements are welcome too.

## Tools

`tools\probe.py` prints a controller's raw axes, buttons and hat. `tools\xcheck.py` lists occupied XInput slots (`watch` prints live values). `app.py --screenshot out.png` saves a picture of the window and exits. Logs are written to `%APPDATA%\D2X\d2x.log`.

## Known limits

- Xbox 360 style pads are hidden from the list: they are already XInput, and the virtual pad itself is one.
- An Xbox 360 pad has 10 buttons plus the D-pad and Guide, so extra buttons (back paddles and similar) cannot be passed on.
- On some pads the triggers are reported as plain buttons, so they are fully on or off (see above).
- The real DInput pad stays visible to games next to the virtual one. If a game double-reads it, hide it with [HidHide](https://github.com/nefarius/HidHide).
- Windows 11 is untested.
- Only the 8BitDo Ultimate 2 over Bluetooth has been tested.

## License

[MIT](LICENSE)
