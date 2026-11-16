"""8BitDo Ultimate 2 (Bluetooth, DInput) -> virtual Xbox 360 (XInput) bridge.

Usage (script or the packaged EXE):
  bridge            # run the bridge (default); installs the ViGEmBus driver if missing
  bridge map        # (re)do the guided button mapping; "map all" redoes every step
  bridge run        # same as no argument
  bridge startup on|off|status   # start automatically when you log in to Windows
While running: press S to toggle start-with-Windows, Q to quit.
Requires: ViGEmBus driver (installed automatically), pip install pygame vgamepad
"""
import ctypes, json, msvcrt, os, shutil, subprocess, sys, time, winreg

os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
os.environ["SDL_HIDAPI_JOYSTICK"] = "0"  # raw DInput view of the pad
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

FROZEN = getattr(sys, "frozen", False)
# user-editable files live next to the EXE (or script); a default mapping is bundled inside
HERE = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
BUNDLE = getattr(sys, "_MEIPASS", HERE)
MAP_FILE = os.path.join(HERE, "mapping.json")
if not os.path.exists(MAP_FILE) and os.path.exists(os.path.join(BUNDLE, "mapping.json")):
    shutil.copy(os.path.join(BUNDLE, "mapping.json"), MAP_FILE)
VID_PID_MARK = ("c82d0000", "1260")  # 2DC8:6012 inside SDL GUID

# (key, prompt, kind)  kind: btn = button/hat, stick = axis w/ direction, trig = axis, 0..1
STEPS = [
    ("A", "Press A", "btn"), ("B", "Press B", "btn"),
    ("X", "Press X", "btn"), ("Y", "Press Y", "btn"),
    ("LB", "Press left bumper (LB)", "btn"), ("RB", "Press right bumper (RB)", "btn"),
    ("BACK", "Press Back/Select/View", "btn"), ("START", "Press Start/Menu", "btn"),
    ("GUIDE", "Press Home/Guide (or press ENTER on keyboard to skip)", "btn?"),
    ("LS", "Click LEFT stick in", "btn"), ("RS", "Click RIGHT stick in", "btn"),
    ("DUP", "Press D-pad UP", "btn"), ("DDOWN", "Press D-pad DOWN", "btn"),
    ("DLEFT", "Press D-pad LEFT", "btn"), ("DRIGHT", "Press D-pad RIGHT", "btn"),
    ("LT", "Squeeze LEFT trigger (LT) fully", "trig"), ("RT", "Squeeze RIGHT trigger (RT) fully", "trig"),
    ("LX", "Push LEFT stick fully RIGHT and hold", "stick"),
    ("LY", "Push LEFT stick fully UP and hold", "stick"),
    ("RX", "Push RIGHT stick fully RIGHT and hold", "stick"),
    ("RY", "Push RIGHT stick fully UP and hold", "stick"),
    # extra buttons XInput has no slot for; assigned via EXTRA_ASSIGN below
    ("L4", "Press back button L4 (or press ENTER on keyboard to skip)", "btn?"),
    ("R4", "Press back button R4 (or press ENTER on keyboard to skip)", "btn?"),
    ("PL", "Press back button PL (or press ENTER on keyboard to skip)", "btn?"),
    ("PR", "Press back button PR (or press ENTER on keyboard to skip)", "btn?"),
]

# Extra button -> Xbox button it should act as. Edit freely, e.g. {"L4": "X", "R4": "Y"}.
# Valid targets: A B X Y LB RB BACK START GUIDE LS RS DUP DDOWN DLEFT DRIGHT
EXTRA_ASSIGN = {}


def find_pad():
    pygame.joystick.quit(); pygame.joystick.init()
    for i in range(pygame.joystick.get_count()):
        j = pygame.joystick.Joystick(i)
        g = j.get_guid()
        if all(m in g for m in VID_PID_MARK):
            j.init(); return j
    return None


def snapshot(j):
    pygame.event.pump()
    return (
        [j.get_axis(a) for a in range(j.get_numaxes())],
        [j.get_button(b) for b in range(j.get_numbuttons())],
        [j.get_hat(h) for h in range(j.get_numhats())],
    )


def wait_idle(j, rest):
    while True:
        ax, bt, ht = snapshot(j)
        if (not any(bt) and all(h == (0, 0) for h in ht)
                and all(abs(a - r) < 0.2 for a, r in zip(ax, rest))):
            return
        time.sleep(0.03)


def detect(j, rest, kind, timeout=None):
    """Return a binding dict for the first input that activates, or None on timeout."""
    t0 = time.time()
    while timeout is None or time.time() - t0 < timeout:
        if kind == "btn?":
            while msvcrt.kbhit():
                if msvcrt.getwch() in (chr(13), chr(10)):
                    return None
        ax, bt, ht = snapshot(j)
        if kind != "stick":  # buttons/hat count for btn, btn? and trig (triggers may be digital)
            for i, v in enumerate(bt):
                if v: return {"type": "button", "index": i}
            for h, v in enumerate(ht):
                if v != (0, 0):
                    return {"type": "hat", "index": h, "value": list(v)}
        # axes: pick the biggest deviation > 0.5
        best, bi = 0.0, None
        for i, (a, r) in enumerate(zip(ax, rest)):
            if abs(a - r) > best: best, bi = abs(a - r), i
        if bi is not None and best > 0.5 and kind in ("trig", "stick"):
            time.sleep(0.4 if kind == "stick" else 0.5)  # let it reach full travel
            ax, _, _ = snapshot(j)
            full = ax[bi]
            return {"type": "axis", "index": bi, "rest": rest[bi], "full": full}
        if kind in ("btn", "btn?") and best > 0.5:
            # some pads put triggers on axes; allow as button
            return {"type": "axis_btn", "index": bi, "rest": rest[bi], "full": ax[bi]}
        time.sleep(0.01)
    return None


def do_map():
    pygame.init()
    j = find_pad()
    if not j:
        sys.exit("8BitDo pad (2DC8:6012) not found. Connect it over Bluetooth and wake it.")
    print(f"Found: {j.get_name()}  axes={j.get_numaxes()} buttons={j.get_numbuttons()} hats={j.get_numhats()}")
    print("Leave all sticks/triggers untouched for a moment...")
    time.sleep(1.5)
    rest = snapshot(j)[0]
    mapping = {"rest": rest}
    if os.path.exists(MAP_FILE) and "all" not in sys.argv:
        mapping = json.load(open(MAP_FILE))
        mapping["rest"] = rest
        print("Resuming: keeping", [k for k in mapping if k != "rest"])
    for key, prompt, kind in STEPS:
        if key in mapping:
            continue
        wait_idle(j, rest)
        print(f"\n-> {prompt}", flush=True)
        while msvcrt.kbhit(): msvcrt.getwch()  # drop stray keypresses
        b = detect(j, rest, kind)
        if b is None:
            print("   skipped")
            mapping[key] = None
            with open(MAP_FILE, "w") as f:
                json.dump(mapping, f, indent=2)
            continue
        mapping[key] = b
        print("   got", b, flush=True)
        with open(MAP_FILE, "w") as f:
            json.dump(mapping, f, indent=2)
    with open(MAP_FILE, "w") as f:
        json.dump(mapping, f, indent=2)
    print(f"\nSaved {MAP_FILE}. Now run:  python bridge.py run")


def active(j, b, snap):
    ax, bt, ht = snap
    t = b["type"]
    if t == "button": return bool(bt[b["index"]])
    if t == "hat": return tuple(ht[b["index"]]) == tuple(b["value"])
    if t == "axis_btn": return abs(ax[b["index"]] - b["rest"]) > 0.5
    if t == "axis": return abs(ax[b["index"]] - b["rest"]) > 0.5
    return False


def axis_val(b, snap, kind):
    if not b: return 0.0
    if b["type"] in ("button", "hat"):  # digital trigger
        return 1.0 if active(None, b, snap) else 0.0
    v = snap[0][b["index"]]
    r, full = b["rest"], b["full"]
    span = full - r
    if abs(span) < 1e-3: return 0.0
    n = (v - r) / span  # 0..1 toward the recorded direction
    if kind == "trig":
        return max(0.0, min(1.0, n))
    return max(-1.0, min(1.0, n * (1 if span > 0 else 1)))  # signed along recorded direction


def stick_val(b, snap):
    """Signed -1..1 where +1 is the direction recorded in mapping (right / up)."""
    if not b: return 0.0
    v = snap[0][b["index"]]
    r, full = b["rest"], b["full"]
    span = full - r
    if abs(span) < 1e-3: return 0.0
    n = (v - r) / span
    n = max(-1.0, min(1.0, n))
    return n


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"  # per-user, no admin needed
RUN_NAME = "8BitDoXInputBridge"


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except FileNotFoundError:
        return False


def set_startup(on):
    if on:
        exe = f'"{sys.executable}"' if FROZEN else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, exe + " --autostart")
    elif startup_enabled():
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_NAME)


def do_startup():
    arg = sys.argv[2].lower() if len(sys.argv) > 2 else "status"
    if arg in ("on", "off"):
        set_startup(arg == "on")
    print("Start with Windows:", "ON" if startup_enabled() else "OFF")


def install_driver():
    """Run the ViGEmBus MSI that ships inside vgamepad, elevated. Returns True on success."""
    msi = os.path.join(BUNDLE, "vgamepad", "win", "vigem", "install", "x64", "ViGEmBusSetup_x64.msi")
    if not os.path.exists(msi):
        import importlib.util  # running as a plain script: find the package without importing it
        pkg = importlib.util.find_spec("vgamepad").submodule_search_locations[0]
        msi = os.path.join(pkg, "win", "vigem", "install", "x64", "ViGEmBusSetup_x64.msi")
    # copy out of the temp bundle so msiexec can read it
    tmp = os.path.join(os.environ.get("TEMP", HERE), "ViGEmBusSetup_x64.msi")
    shutil.copy(msi, tmp)
    print("Windows will ask for administrator permission to install the driver...")
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "msiexec.exe", f'/i "{tmp}" /passive /norestart', None, 1)
    if rc <= 32:
        print("Driver install was cancelled or could not start.")
        return False
    time.sleep(3)  # ShellExecute does not wait; poll for the bus service instead
    for _ in range(90):
        r = subprocess.run(["sc", "query", "ViGEmBus"], capture_output=True, text=True)
        if "RUNNING" in r.stdout:
            return True
        time.sleep(1)
    return False


def load_vgamepad():
    """Import vgamepad; if the ViGEmBus driver is missing, offer to install it and relaunch."""
    try:
        import vgamepad as vg
        return vg
    except RuntimeError as e:
        if "BUS_NOT_FOUND" not in str(e):
            raise
    print("The ViGEmBus driver (virtual Xbox controller) is not installed on this PC.")
    if input("Install it now? [Y/n] ").strip().lower() in ("", "y", "yes"):
        if install_driver():
            print("Driver installed. Restarting...")
            args = [sys.executable] + ([] if FROZEN else [os.path.abspath(__file__)]) + sys.argv[1:]
            subprocess.Popen(args, creationflags=0x00000010)  # CREATE_NEW_CONSOLE
            sys.exit(0)
        print("Driver did not start. A reboot may be needed, then run this again.")
    sys.exit(1)


def do_run():
    vg = load_vgamepad()
    B = vg.XUSB_BUTTON
    if not os.path.exists(MAP_FILE):
        print("No button mapping yet - starting the guided mapping first.")
        do_map()
        if not os.path.exists(MAP_FILE):
            return
    m = json.load(open(MAP_FILE))
    btn_map = {
        "A": B.XUSB_GAMEPAD_A, "B": B.XUSB_GAMEPAD_B, "X": B.XUSB_GAMEPAD_X, "Y": B.XUSB_GAMEPAD_Y,
        "LB": B.XUSB_GAMEPAD_LEFT_SHOULDER, "RB": B.XUSB_GAMEPAD_RIGHT_SHOULDER,
        "BACK": B.XUSB_GAMEPAD_BACK, "START": B.XUSB_GAMEPAD_START, "GUIDE": B.XUSB_GAMEPAD_GUIDE,
        "LS": B.XUSB_GAMEPAD_LEFT_THUMB, "RS": B.XUSB_GAMEPAD_RIGHT_THUMB,
        "DUP": B.XUSB_GAMEPAD_DPAD_UP, "DDOWN": B.XUSB_GAMEPAD_DPAD_DOWN,
        "DLEFT": B.XUSB_GAMEPAD_DPAD_LEFT, "DRIGHT": B.XUSB_GAMEPAD_DPAD_RIGHT,
    }
    pygame.init()
    pad = vg.VX360Gamepad()
    print("Virtual Xbox 360 controller created. Leave this window open.")
    print(f"Keys: S = toggle start-with-Windows (now {'ON' if startup_enabled() else 'OFF'}), Q = quit")
    j = None
    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch().lower()
            if ch == "q":
                return
            if ch == "s":
                set_startup(not startup_enabled())
                print("Start with Windows:", "ON" if startup_enabled() else "OFF", flush=True)
        if j is None:
            j = find_pad()
            if j is None:
                time.sleep(1.0); continue
            print("Physical pad connected:", j.get_name(), flush=True)
        try:
            snap = snapshot(j)
        except pygame.error:
            j = None; pad.reset(); pad.update(); continue
        for k, xb in btn_map.items():
            on = False
            b = m.get(k)
            if b and active(j, b, snap): on = True
            for extra, target in EXTRA_ASSIGN.items():
                eb = m.get(extra)
                if target == k and eb and active(j, eb, snap): on = True
            if on: pad.press_button(xb)
            else: pad.release_button(xb)
        pad.left_trigger_float(axis_val(m.get("LT"), snap, "trig"))
        pad.right_trigger_float(axis_val(m.get("RT"), snap, "trig"))
        pad.left_joystick_float(stick_val(m.get("LX"), snap), stick_val(m.get("LY"), snap))
        pad.right_joystick_float(stick_val(m.get("RX"), snap), stick_val(m.get("RY"), snap))
        pad.update()
        if not pygame.joystick.get_count():
            j = None
        time.sleep(0.004)


if __name__ == "__main__":
    if "--autostart" in sys.argv:  # launched by Windows at login: minimise the console window
        sys.argv.remove("--autostart")
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    try:
        {"map": do_map, "run": do_run, "startup": do_startup}[cmd]()
    except KeyError:
        print(__doc__)
    except KeyboardInterrupt:
        pass
    except SystemExit as e:
        if e.code not in (None, 0) and FROZEN:
            print(e.code if isinstance(e.code, str) else "")
            input("Press ENTER to close...")
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        if FROZEN: input("Press ENTER to close...")
