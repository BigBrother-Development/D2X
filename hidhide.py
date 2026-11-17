"""Hides the real DInput controller from other programs using the HidHide driver
(https://github.com/nefarius/HidHide, MIT). Games then see only the virtual Xbox 360 pad.

D2X adds the controller to HidHide's blacklist while it runs and removes it again when it exits. Its own
exe is added to HidHide's application whitelist so D2X can keep reading the real pad (this entry stays).
The "session blacklist" described on HidHide's master branch is not in the released driver (1.5.230),
so the normal blacklist is used and the entries are recorded in a state file for crash recovery.
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import re
import subprocess
import sys
import time

DEVICE_PATH = r"\\.\HidHide"
INSTALLER_NAME = "HidHide_1.5.230_x64.exe"


def _ctl(func):  # CTL_CODE(32769, func, METHOD_BUFFERED, FILE_READ_DATA)
    return (32769 << 16) | (1 << 14) | (func << 2)


IOCTL_GET_WHITELIST = _ctl(2048)
IOCTL_SET_WHITELIST = _ctl(2049)
IOCTL_GET_ACTIVE = _ctl(2052)
IOCTL_SET_ACTIVE = _ctl(2053)
IOCTL_GET_BLACKLIST = _ctl(2050)
IOCTL_SET_BLACKLIST = _ctl(2051)

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = w.HANDLE
_k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
_k32.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, w.LPVOID, w.DWORD, w.LPVOID, w.DWORD,
                                 ctypes.POINTER(w.DWORD), w.LPVOID]
_k32.CloseHandle.argtypes = [w.HANDLE]
_k32.QueryDosDeviceW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
_INVALID = ctypes.c_void_p(-1).value


class HidHideError(Exception):
    pass


class _Handle:
    """The driver allows one open handle at a time, so keep it short-lived."""

    def __enter__(self):
        err = 0
        for _ in range(10):
            h = _k32.CreateFileW(DEVICE_PATH, 0x80000000, 7, None, 3, 0x80, None)  # GENERIC_READ, share all
            if h not in (None, _INVALID):
                self.h = h
                return self
            err = ctypes.get_last_error()
            if err != 32:  # not a sharing violation
                break
            time.sleep(0.1)
        raise HidHideError("cannot open the HidHide control device (error %d)" % err)

    def __exit__(self, *a):
        _k32.CloseHandle(self.h)

    def ioctl(self, code, data=b"", out_size=0):
        inbuf = ctypes.create_string_buffer(data, len(data)) if data else None
        outbuf = ctypes.create_string_buffer(out_size) if out_size else None
        ret = w.DWORD(0)
        if not _k32.DeviceIoControl(self.h, code, inbuf, len(data), outbuf, out_size, ctypes.byref(ret), None):
            raise HidHideError("HidHide request failed (error %d)" % ctypes.get_last_error())
        return outbuf.raw[:ret.value] if outbuf else b""


def _multisz(items):
    return ("\0".join(items) + "\0\0").encode("utf-16-le") if items else "\0\0".encode("utf-16-le")


def _parse_multisz(raw):
    return [s for s in raw.decode("utf-16-le").split("\0") if s]


def _get_list(h, code):
    # first call with a small buffer to learn the size, then read the whole list
    size = 4096
    for _ in range(4):
        try:
            return _parse_multisz(h.ioctl(code, out_size=size))
        except HidHideError:
            size *= 4
    raise HidHideError("could not read the HidHide list")


def is_installed():
    try:
        with _Handle():
            return True
    except HidHideError:
        return False


def dos_device_path(path):
    """C:\\dir\\a.exe -> \\Device\\HarddiskVolume3\\dir\\a.exe (the form HidHide's whitelist uses)."""
    path = os.path.abspath(path)
    drive, rest = os.path.splitdrive(path)
    buf = ctypes.create_unicode_buffer(1024)
    if not _k32.QueryDosDeviceW(drive, buf, 1024):
        raise HidHideError("cannot resolve drive " + drive)
    return buf.value + rest


# ---- finding the controller's device instance IDs --------------------------

class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]


class _DevInfo(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("ClassGuid", _GUID), ("DevInst", w.DWORD), ("Reserved", ctypes.c_void_p)]


_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
_setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, w.LPCWSTR, w.HWND, w.DWORD]
_setupapi.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, w.DWORD, ctypes.POINTER(_DevInfo)]
_setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_DevInfo), w.LPWSTR, w.DWORD,
                                                  ctypes.POINTER(w.DWORD)]
_setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_DevInfo), w.DWORD,
                                                        ctypes.POINTER(w.DWORD), ctypes.c_void_p, w.DWORD,
                                                        ctypes.POINTER(w.DWORD)]
_setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]


def instance_ids(vidpid):
    """Device instance IDs of the connected HID / USB nodes of a controller ('2DC8:6012').

    Bluetooth LE pads report the vendor ID with a source prefix (VID&122DC8), USB pads as VID_2DC8."""
    vid, _, pid = vidpid.upper().partition(":")
    if len(vid) != 4 or len(pid) != 4:
        return []
    pat = re.compile(r"VID[_&](?:[0-9A-F]{2})?%s[_&]?PID[_&]%s" % (vid, pid), re.I)
    DIGCF_PRESENT, DIGCF_ALLCLASSES = 0x2, 0x4
    hdev = _setupapi.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if hdev in (None, _INVALID):
        return []
    found = []
    try:
        info = _DevInfo()
        info.cbSize = ctypes.sizeof(_DevInfo)
        i = 0
        while _setupapi.SetupDiEnumDeviceInfo(hdev, i, ctypes.byref(info)):
            i += 1
            buf = ctypes.create_unicode_buffer(512)
            if not _setupapi.SetupDiGetDeviceInstanceIdW(hdev, ctypes.byref(info), buf, 512, None):
                continue
            iid = buf.value
            if not pat.search(iid):
                continue
            if iid.upper().startswith(("HID\\", "USB\\")):  # the Bluetooth parent nodes are left alone
                found.append(iid)
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return found


# ---- hiding ----------------------------------------------------------------

class Hider:
    """hide(vidpid) / unhide(). Safe to call repeatedly; hide() returns (ok, message)."""

    def __init__(self):
        self._applied = None
        self._state_file = None

    def _state_path(self):
        import storage
        return os.path.join(storage.DATA_DIR, "hidhide_state.json")

    def _save(self, ids, active_before):
        import storage
        storage.ensure_dirs()
        with open(self._state_path(), "w", encoding="utf-8") as f:
            json.dump({"ids": ids, "active_before": active_before}, f)

    def _load(self):
        try:
            with open(self._state_path(), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"ids": [], "active_before": None}

    def hide(self, vidpid):
        ids = sorted(instance_ids(vidpid))
        if ids == self._applied:
            return True, ""
        try:
            with _Handle() as h:
                exe = dos_device_path(sys.executable)
                wl = _get_list(h, IOCTL_GET_WHITELIST)
                if exe.lower() not in (x.lower() for x in wl):
                    h.ioctl(IOCTL_SET_WHITELIST, _multisz(wl + [exe]))
                state = self._load()
                active_before = state["active_before"]
                if h.ioctl(IOCTL_GET_ACTIVE, out_size=1) == b"\x00":
                    if active_before is None:
                        active_before = False
                    h.ioctl(IOCTL_SET_ACTIVE, b"\x01")
                old = {x.lower() for x in state["ids"]}
                bl = [x for x in _get_list(h, IOCTL_GET_BLACKLIST) if x.lower() not in old]
                self._save(ids, active_before)  # record first, so a crash can still be undone
                h.ioctl(IOCTL_SET_BLACKLIST, _multisz(bl + ids))
        except HidHideError as e:
            return False, str(e)
        self._applied = ids
        return True, ""

    def unhide(self):
        """Remove what hide() added. Also cleans up after a crashed earlier run."""
        state = self._load()
        if not state["ids"] and state["active_before"] is None:
            self._applied = None
            return True
        try:
            with _Handle() as h:
                mine = {x.lower() for x in state["ids"]}
                bl = [x for x in _get_list(h, IOCTL_GET_BLACKLIST) if x.lower() not in mine]
                h.ioctl(IOCTL_SET_BLACKLIST, _multisz(bl))
                if state["active_before"] is False and not bl:
                    h.ioctl(IOCTL_SET_ACTIVE, b"\x00")
        except HidHideError:
            return False
        try:
            os.remove(self._state_path())
        except OSError:
            pass
        self._applied = None
        return True


# ---- installer ---------------------------------------------------------------

def installer_path():
    import storage
    return os.path.join(storage.BUNDLE, "vendor", INSTALLER_NAME)


def install():
    """Run the bundled HidHide installer (elevated) and wait for the control device. Returns True on success.
    HidHide may ask for a restart; the driver then only becomes available after it."""
    import storage
    src = installer_path()
    tmp = os.path.join(os.environ.get("TEMP", storage.DATA_DIR), INSTALLER_NAME)
    with open(src, "rb") as f, open(tmp, "wb") as g:
        g.write(f.read())
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", tmp, None, None, 1)
    if rc <= 32:
        return False
    for _ in range(300):  # up to 5 minutes for the user to click through the installer
        time.sleep(1)
        if is_installed():
            return True
    return False
