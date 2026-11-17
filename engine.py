"""Engine: reads any DInput / generic HID gamepad through SDL and feeds a virtual Xbox 360 (XInput)
pad created with ViGEmBus. Also contains the mapping wizard and the driver installer."""
import os

os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
os.environ["SDL_HIDAPI_JOYSTICK"] = "0"   # raw DInput view of the pad, not SDL's own remapping
os.environ["SDL_VIDEODRIVER"] = "dummy"   # no window; only needed so SDL pumps joystick events
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import copy, ctypes, importlib.util, shutil, subprocess, sys, threading, time, traceback
import pygame
import storage
import hidhide

# Xbox 360 pads (including our own virtual one) are already XInput: never offer them as a source.
EXCLUDE_VIDPID = {"045E:028E"}

# (key, prompt, kind)   kind: btn = button/hat, trig = button or axis, stick = axis
STEPS = [
    ("A", "Press A (bottom face button)", "btn"),
    ("B", "Press B (right face button)", "btn"),
    ("X", "Press X (left face button)", "btn"),
    ("Y", "Press Y (top face button)", "btn"),
    ("LB", "Press the left bumper (LB / L1)", "btn"),
    ("RB", "Press the right bumper (RB / R1)", "btn"),
    ("BACK", "Press Back / Select / View", "btn"),
    ("START", "Press Start / Menu", "btn"),
    ("GUIDE", "Press Home / Guide (Skip if none)", "btn"),
    ("LS", "Click the LEFT stick in (L3)", "btn"),
    ("RS", "Click the RIGHT stick in (R3)", "btn"),
    ("DUP", "Press D-pad UP", "btn"),
    ("DDOWN", "Press D-pad DOWN", "btn"),
    ("DLEFT", "Press D-pad LEFT", "btn"),
    ("DRIGHT", "Press D-pad RIGHT", "btn"),
    ("LT", "Squeeze the LEFT trigger (LT / L2) fully", "trig"),
    ("RT", "Squeeze the RIGHT trigger (RT / R2) fully", "trig"),
    ("LX", "Push the LEFT stick fully RIGHT and hold", "stick"),
    ("LY", "Push the LEFT stick fully UP and hold", "stick"),
    ("RX", "Push the RIGHT stick fully RIGHT and hold", "stick"),
    ("RY", "Push the RIGHT stick fully UP and hold", "stick"),
]


class Cancelled(Exception):
    pass


class WizardError(Exception):
    pass


def guid_vidpid(g):
    """USB vendor:product from an SDL GUID string, or '' when the GUID does not carry one."""
    try:
        if len(g) == 32 and g[12:16] == "0000":
            vid = int(g[10:12] + g[8:10], 16)
            pid = int(g[18:20] + g[16:18], 16)
            if vid:
                return f"{vid:04X}:{pid:04X}"
    except ValueError:
        pass
    return ""


# ---- reading bindings --------------------------------------------------------

def read_snapshot(j):
    return (
        [j.get_axis(a) for a in range(j.get_numaxes())],
        [j.get_button(b) for b in range(j.get_numbuttons())],
        [j.get_hat(h) for h in range(j.get_numhats())],
    )


def is_active(b, snap):
    if not b:
        return False
    ax, bt, ht = snap
    t, i = b["type"], b["index"]
    try:
        if t == "button":
            return bool(bt[i])
        if t == "hat":
            return tuple(ht[i]) == tuple(b["value"])
        if t == "axis_btn":
            return (ax[i] - b["rest"]) * b.get("dir", 1) > 0.5
        if t == "axis":
            return abs(ax[i] - b["rest"]) > 0.5
    except IndexError:
        pass
    return False


def trigger_value(b, snap):
    """0..1 for a trigger bound to a button/hat (digital) or an axis (analog)."""
    if not b:
        return 0.0
    if b["type"] in ("button", "hat", "axis_btn"):
        return 1.0 if is_active(b, snap) else 0.0
    try:
        v = snap[0][b["index"]]
    except IndexError:
        return 0.0
    span = b["full"] - b["rest"]
    if abs(span) < 1e-3:
        return 0.0
    return max(0.0, min(1.0, (v - b["rest"]) / span))


def stick_value(b, snap):
    """-1..1, where +1 is the direction recorded in the mapping (right / up)."""
    if not b or b["type"] != "axis":
        return 0.0
    try:
        v = snap[0][b["index"]]
    except IndexError:
        return 0.0
    span = b["full"] - b["rest"]
    if abs(span) < 1e-3:
        return 0.0
    return max(-1.0, min(1.0, (v - b["rest"]) / span))


# ---- driver ----------------------------------------------------------------

def _vgamepad_dir():
    p = os.path.join(storage.BUNDLE, "vgamepad")
    if os.path.isdir(p):
        return p
    return importlib.util.find_spec("vgamepad").submodule_search_locations[0]


def install_driver():
    """Run the ViGEmBus MSI shipped inside vgamepad (elevated). Blocks until the service runs."""
    msi = os.path.join(_vgamepad_dir(), "win", "vigem", "install", "x64", "ViGEmBusSetup_x64.msi")
    tmp = os.path.join(os.environ.get("TEMP", storage.DATA_DIR), "ViGEmBusSetup_x64.msi")
    shutil.copy(msi, tmp)  # msiexec cannot read from PyInstaller's temp bundle reliably
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "msiexec.exe", f'/i "{tmp}" /passive /norestart', None, 1)
    if rc <= 32:
        return False
    time.sleep(3)
    for _ in range(90):
        r = subprocess.run(["sc", "query", "ViGEmBus"], capture_output=True, text=True,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
        if "RUNNING" in r.stdout:
            return True
        time.sleep(1)
    return False


# ---- engine ----------------------------------------------------------------

class Engine(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="engine")
        self._lock = threading.Lock()
        self.quit_evt = threading.Event()
        self._rescan = threading.Event()
        self._skip = threading.Event()
        self._cancel = threading.Event()
        self._retry_driver = threading.Event()
        self._wiz_req = None
        self.mapping = None
        self.device_pref = None
        self.vg = None
        self.pad = None
        self.hide_enabled = False
        self.hider = hidhide.Hider()
        self._hide_next = 0.0
        self._hid_dirty = True   # first pass also cleans up after a crashed earlier run
        self._st = {
            "driver": "starting", "driver_msg": "",
            "devices": [], "active_name": "", "hide": "off", "hide_msg": "",
            "mode": "bridge", "prompt": "", "step": 0, "steps": len(STEPS), "wizard_result": None,
        }

    # -- public API (called from the GUI thread) --
    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._st)

    def set_mapping(self, m):
        with self._lock:
            self.mapping = m
        self._rescan.set()

    def set_device(self, guid):
        with self._lock:
            self.device_pref = guid or None
        self._rescan.set()

    def rescan(self):
        self._rescan.set()

    def set_hide(self, on):
        """Hide the real controller from other programs (needs the HidHide driver)."""
        with self._lock:
            self.hide_enabled = bool(on)
        self._hide_next = 0.0

    def retry_driver(self):
        self._retry_driver.set()

    def start_wizard(self, name, guid=None):
        with self._lock:
            if self._wiz_req or self._st["mode"] == "mapping":
                return False
            self._wiz_req = (name, guid)
            self._st.update(mode="mapping", wizard_result=None, step=0, prompt="Starting...")
        self._skip.clear()
        self._cancel.clear()
        return True

    def skip_step(self):
        self._skip.set()

    def cancel_wizard(self):
        self._cancel.set()

    def stop(self):
        self.quit_evt.set()

    # -- internals --
    def _set(self, **kw):
        with self._lock:
            self._st.update(kw)

    def _try_driver(self):
        for k in [k for k in sys.modules if k == "vgamepad" or k.startswith("vgamepad.")]:
            del sys.modules[k]
        try:
            import vgamepad as vg
            self.vg = vg
            self.pad = vg.VX360Gamepad()
            self._set(driver="ok", driver_msg="")
        except RuntimeError as e:
            if "BUS_NOT_FOUND" in str(e):
                self._set(driver="missing", driver_msg="ViGEmBus driver is not installed")
            else:
                self._set(driver="error", driver_msg=str(e))
        except Exception as e:  # DLL missing, etc.
            self._set(driver="error", driver_msg=f"{type(e).__name__}: {e}")

    def _release(self):
        if self.pad is not None:
            try:
                self.pad.reset()
                self.pad.update()
            except Exception:
                pass

    def _scan(self):
        devs = []
        for i in range(pygame.joystick.get_count()):
            j = pygame.joystick.Joystick(i)
            g = j.get_guid()
            vp = guid_vidpid(g)
            if vp in EXCLUDE_VIDPID:
                continue
            devs.append({"index": i, "guid": g, "name": j.get_name(), "vidpid": vp})
        return devs

    def _pick(self, devices):
        with self._lock:
            m, pref = self.mapping, self.device_pref
        if m is None:
            return None
        if pref:
            return next((d for d in devices if d["guid"] == pref), None)
        vp = m.get("vidpid", "")
        if vp:
            return next((d for d in devices if d["vidpid"] == vp), None)
        return devices[0] if devices else None

    def run(self):
        try:
            self._main()
        except Exception:
            storage.ensure_dirs()
            with open(storage.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "engine crashed\n" + traceback.format_exc() + "\n")
            self._set(driver="error", driver_msg="Engine crashed, see the log file")
        finally:
            self._release()
            self.pad = None
            self.hider.unhide()

    def _main(self):
        pygame.display.init()
        pygame.joystick.init()
        held = None
        next_scan = 0.0
        next_drv = 0.0
        while not self.quit_evt.is_set():
            now = time.time()
            if self._retry_driver.is_set():
                self._retry_driver.clear()
                next_drv = 0.0
            if self.pad is None and now >= next_drv:
                self._try_driver()
                next_drv = now + 3.0

            added = False
            for ev in pygame.event.get():
                if ev.type == pygame.JOYDEVICEREMOVED and held and ev.instance_id == held["iid"]:
                    held = None
                    self._release()
                    self._set(active_name="")
                    next_scan = 0.0
                elif ev.type == pygame.JOYDEVICEADDED:
                    added = True

            req, self._wiz_req = self._wiz_req, None
            if req:
                self._release()
                self._run_wizard(req[0], req[1], held)
                held = None
                self._rescan.set()

            force = self._rescan.is_set()
            if force or added or now >= next_scan:
                self._rescan.clear()
                if held is None or force:
                    pygame.joystick.quit()
                    pygame.joystick.init()
                    held = None
                devices = self._scan()
                self._set(devices=devices)
                next_scan = now + (1.5 if held is None else 4.0)
                target = self._pick(devices)
                if target is None:
                    if held:
                        held = None
                        self._release()
                    self._set(active_name="")
                elif held is None or held["guid"] != target["guid"]:
                    j = pygame.joystick.Joystick(target["index"])
                    held = {"j": j, "guid": target["guid"], "iid": j.get_instance_id(), "name": target["name"],
                            "vidpid": target["vidpid"]}
                    self._set(active_name=target["name"])

            self._sync_hide(held, now)

            with self._lock:
                m = self.mapping
            if held and m and self.pad is not None:
                try:
                    snap = read_snapshot(held["j"])
                except pygame.error:
                    held = None
                    self._release()
                    self._set(active_name="")
                    continue
                self._apply(snap, m)
                time.sleep(0.004)
            else:
                time.sleep(0.05)

    def _sync_hide(self, held, now):
        if now < self._hide_next:
            return
        self._hide_next = now + 3.0
        with self._lock:
            on = self.hide_enabled
        if not on:
            if self._hid_dirty and self.hider.unhide():
                self._hid_dirty = False
            self._set(hide="off", hide_msg="")
        elif not hidhide.is_installed():
            self._set(hide="missing", hide_msg="")
        elif not held:
            self._set(hide="waiting", hide_msg="")
        else:
            ok, msg = self.hider.hide(held["vidpid"])
            self._hid_dirty = True
            self._set(hide="ok" if ok else "error", hide_msg=msg)

    def _apply(self, snap, m):
        vg = self.vg
        B = vg.XUSB_BUTTON
        bind = m.get("bindings", {})
        pad = self.pad
        table = {
            "A": B.XUSB_GAMEPAD_A, "B": B.XUSB_GAMEPAD_B, "X": B.XUSB_GAMEPAD_X, "Y": B.XUSB_GAMEPAD_Y,
            "LB": B.XUSB_GAMEPAD_LEFT_SHOULDER, "RB": B.XUSB_GAMEPAD_RIGHT_SHOULDER,
            "BACK": B.XUSB_GAMEPAD_BACK, "START": B.XUSB_GAMEPAD_START, "GUIDE": B.XUSB_GAMEPAD_GUIDE,
            "LS": B.XUSB_GAMEPAD_LEFT_THUMB, "RS": B.XUSB_GAMEPAD_RIGHT_THUMB,
            "DUP": B.XUSB_GAMEPAD_DPAD_UP, "DDOWN": B.XUSB_GAMEPAD_DPAD_DOWN,
            "DLEFT": B.XUSB_GAMEPAD_DPAD_LEFT, "DRIGHT": B.XUSB_GAMEPAD_DPAD_RIGHT,
        }
        for k, xb in table.items():
            if is_active(bind.get(k), snap):
                pad.press_button(xb)
            else:
                pad.release_button(xb)
        pad.left_trigger_float(trigger_value(bind.get("LT"), snap))
        pad.right_trigger_float(trigger_value(bind.get("RT"), snap))
        pad.left_joystick_float(stick_value(bind.get("LX"), snap), stick_value(bind.get("LY"), snap))
        pad.right_joystick_float(stick_value(bind.get("RX"), snap), stick_value(bind.get("RY"), snap))
        pad.update()

    # -- mapping wizard (runs on the engine thread) --
    def _pump(self, iid):
        if self.quit_evt.is_set() or self._cancel.is_set():
            raise Cancelled()
        for ev in pygame.event.get():
            if ev.type == pygame.JOYDEVICEREMOVED and ev.instance_id == iid:
                raise WizardError("The controller disconnected")

    def _sleep(self, secs, iid):
        end = time.time() + secs
        while time.time() < end:
            self._pump(iid)
            time.sleep(0.02)

    def _wait_idle(self, j, rest, iid):
        while True:
            self._pump(iid)
            ax, bt, ht = read_snapshot(j)
            if (not any(bt) and all(tuple(h) == (0, 0) for h in ht)
                    and all(abs(a - r) < 0.2 for a, r in zip(ax, rest))):
                return
            time.sleep(0.03)

    def _detect(self, j, rest, kind, iid):
        """First input that fires for this step as a binding dict; None if the user pressed Skip."""
        while True:
            self._pump(iid)
            if self._skip.is_set():
                self._skip.clear()
                return None
            ax, bt, ht = read_snapshot(j)
            if kind != "stick":
                for i, v in enumerate(bt):
                    if v:
                        return {"type": "button", "index": i}
                for h, v in enumerate(ht):
                    if tuple(v) != (0, 0):
                        return {"type": "hat", "index": h, "value": list(v)}
            best, bi = 0.0, None
            for i, (a, r) in enumerate(zip(ax, rest)):
                if abs(a - r) > best:
                    best, bi = abs(a - r), i
            if bi is not None and best > 0.5:
                if kind in ("trig", "stick"):
                    self._sleep(0.5, iid)  # let it reach full travel
                    full = read_snapshot(j)[0][bi]
                    return {"type": "axis", "index": bi, "rest": rest[bi], "full": full}
                # D-pad or buttons reported as an axis
                return {"type": "axis_btn", "index": bi, "rest": rest[bi],
                        "dir": 1 if ax[bi] > rest[bi] else -1}
            time.sleep(0.01)

    def _run_wizard(self, name, guid, held):
        try:
            devs = self.snapshot()["devices"]
            d = None
            if guid:
                d = next((x for x in devs if x["guid"] == guid), None)
            if d is None and held:
                d = next((x for x in devs if x["guid"] == held["guid"]), None)
            if d is None and devs:
                d = devs[0]
            if d is None:
                raise WizardError("No controller found. Connect it, wake it, then try again.")
            j = pygame.joystick.Joystick(d["index"])
            iid = j.get_instance_id()
            self._set(prompt="Leave all sticks and triggers untouched...", step=0)
            self._sleep(1.5, iid)
            rest = [a for a in read_snapshot(j)[0]]
            bindings = {}
            for n, (key, prompt, kind) in enumerate(STEPS):
                self._set(step=n, prompt=prompt)
                self._wait_idle(j, rest, iid)
                self._skip.clear()
                bindings[key] = self._detect(j, rest, kind, iid)
            storage.save_mapping(name, {
                "vidpid": d["vidpid"], "device_name": d["name"], "rest": rest, "bindings": bindings,
            })
            self._set(wizard_result={"status": "saved", "name": name})
        except Cancelled:
            self._set(wizard_result={"status": "cancelled"})
        except WizardError as e:
            self._set(wizard_result={"status": "error", "message": str(e)})
        except Exception as e:
            self._set(wizard_result={"status": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            self._set(mode="bridge", prompt="")
