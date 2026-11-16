import ctypes, time, sys

class GP(ctypes.Structure):
    _fields_ = [("buttons", ctypes.c_ushort), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]
class ST(ctypes.Structure):
    _fields_ = [("pkt", ctypes.c_ulong), ("gp", GP)]

x = ctypes.WinDLL("xinput1_4.dll")
connected = [i for i in range(4) if x.XInputGetState(i, ctypes.byref(ST())) == 0]
print("XInput slots connected:", connected)
if connected and "watch" in sys.argv:
    s = ST(); last = None; end = time.time() + 12
    print("Press things for 12s...")
    while time.time() < end:
        x.XInputGetState(connected[0], ctypes.byref(s)); g = s.gp
        cur = (hex(g.buttons), g.lt, g.rt, g.lx, g.ly, g.rx, g.ry)
        if cur != last: print(cur, flush=True); last = cur
        time.sleep(0.02)
