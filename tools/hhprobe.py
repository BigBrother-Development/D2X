"""Probe the HidHide control device: prints active flag, whitelist, blacklist (read-only)."""
import ctypes, ctypes.wintypes as w

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateFileW.restype = w.HANDLE
k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
k32.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, w.LPVOID, w.DWORD, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID]
k32.CloseHandle.argtypes = [w.HANDLE]

def ctl(n):  # CTL_CODE(32769, n, METHOD_BUFFERED, FILE_READ_DATA)
    return (32769 << 16) | (1 << 14) | (n << 2) | 0

path = r"\\.\HidHide"
h = k32.CreateFileW(path, 0x80000000, 7, None, 3, 0x80, None)
if h in (None, ctypes.c_void_p(-1).value):
    raise SystemExit("open failed, error %d" % ctypes.get_last_error())

def get(n, size=8192):
    buf = ctypes.create_string_buffer(size); ret = w.DWORD(0)
    ok = k32.DeviceIoControl(h, ctl(n), None, 0, buf, size, ctypes.byref(ret), None)
    if not ok:
        return None, ctypes.get_last_error()
    return buf.raw[:ret.value], 0

raw, err = get(2052); print("active:", raw, err)
for name, n in (("whitelist", 2048), ("blacklist", 2050)):
    raw, err = get(n)
    items = [] if raw is None else [s for s in raw.decode("utf-16-le").split("\0") if s]
    print(name, err, items)
k32.CloseHandle(h)
