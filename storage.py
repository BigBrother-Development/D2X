"""Paths, mapping files, settings and the start-with-Windows registry entry."""
import json, os, re, shutil, sys, winreg

APP_NAME = "D2X - DInput to XInput"
FROZEN = getattr(sys, "frozen", False)
BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
DATA_DIR = os.path.join(_APPDATA, "D2X")
_OLD_DATA_DIR = os.path.join(_APPDATA, "DInput2XInput")  # name used before the D2X rename
MAPPINGS_DIR = os.path.join(DATA_DIR, "mappings")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LOG_FILE = os.path.join(DATA_DIR, "d2x.log")

DEFAULT_SETTINGS = {"mapping": None, "device": None, "minimize_to_tray": False, "seeded": False}


def ensure_dirs():
    if not os.path.isdir(DATA_DIR) and os.path.isdir(_OLD_DATA_DIR):  # keep mappings from older versions
        try:
            os.rename(_OLD_DATA_DIR, DATA_DIR)
        except OSError:
            pass
    os.makedirs(MAPPINGS_DIR, exist_ok=True)


def load_settings():
    ensure_dirs()
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s.update(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    if not s["seeded"]:  # first run: copy the mappings that ship with the app
        seed = os.path.join(BUNDLE, "mappings")
        if os.path.isdir(seed):
            for fn in os.listdir(seed):
                dst = os.path.join(MAPPINGS_DIR, fn)
                if fn.endswith(".json") and not os.path.exists(dst):
                    shutil.copy(os.path.join(seed, fn), dst)
        s["seeded"] = True
        names = list_mappings()
        if s["mapping"] is None and names:
            s["mapping"] = names[0]
        save_settings(s)
    return s


def save_settings(s):
    ensure_dirs()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


# ---- mappings -------------------------------------------------------------

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name):
    name = _BAD.sub("", name).strip().rstrip(".")
    return name


def mapping_path(name):
    return os.path.join(MAPPINGS_DIR, safe_name(name) + ".json")


def list_mappings():
    ensure_dirs()
    return sorted(fn[:-5] for fn in os.listdir(MAPPINGS_DIR) if fn.endswith(".json"))


def load_mapping(name):
    with open(mapping_path(name), encoding="utf-8") as f:
        m = json.load(f)
    m.setdefault("name", name)
    m.setdefault("bindings", {})
    m.setdefault("rest", [])
    return m


def save_mapping(name, data):
    ensure_dirs()
    data = dict(data, name=name)
    with open(mapping_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def delete_mapping(name):
    try:
        os.remove(mapping_path(name))
    except FileNotFoundError:
        pass


# ---- start with Windows (per-user Run key, no admin needed) ----------------

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "D2X"
OLD_RUN_NAME = "DInput2XInput"  # name used before the D2X rename


def _run_value_exists(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, name)
        return True
    except FileNotFoundError:
        return False


def startup_enabled():
    return _run_value_exists(RUN_NAME) or _run_value_exists(OLD_RUN_NAME)


def set_startup(on):
    if on:
        if FROZEN:
            cmd = f'"{sys.executable}"'
        else:
            cmd = f'"{sys.executable}" "{os.path.abspath(os.path.join(BUNDLE, "app.py"))}"'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, cmd + " --autostart")
    for name in (RUN_NAME, OLD_RUN_NAME):
        if (not on or name == OLD_RUN_NAME) and _run_value_exists(name):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
