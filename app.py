"""DInput to XInput: graphical front end."""
import ctypes, os, queue, sys, threading, time, traceback

import engine as eng  # must be imported first: sets the SDL environment before pygame loads
import storage
from icon import make_icon

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from PIL import ImageTk

AUTO = "Auto (use the controller the mapping was made for)"


def dev_label(d):
    return f"{d['name']}  [{d['vidpid']}]" if d["vidpid"] else d["name"]


class App:
    def __init__(self, autostart=False, screenshot=None):
        self.settings = storage.load_settings()
        self.q = queue.Queue()
        self.tray = None
        self.wiz = None            # wizard dialog widgets
        self.wiz_handled = True
        self.dev_guids = []        # guid for each device entry (index + 1, 0 is Auto)
        self.screenshot = screenshot

        self.engine = eng.Engine()
        self._apply_mapping_to_engine(self.settings.get("mapping"))
        self.engine.set_device(self.settings.get("device"))
        self.engine.start()

        self.root = root = tk.Tk()
        root.title(storage.APP_NAME)
        root.resizable(False, False)
        self._icon_img = ImageTk.PhotoImage(make_icon(64))
        root.iconphoto(True, self._icon_img)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Unmap>", self.on_unmap)
        self._build()

        if autostart:
            if self.settings["minimize_to_tray"]:
                self.to_tray()
            else:
                root.iconify()
        root.after(150, self.poll)
        if screenshot:
            root.after(2500, self._shot)

    # ---- UI ----
    def _build(self):
        r = self.root
        f = ttk.Frame(r, padding=12)
        f.grid(sticky="nsew")

        st = ttk.LabelFrame(f, text="Status", padding=8)
        st.grid(row=0, column=0, sticky="ew")
        st.columnconfigure(1, weight=1)
        ttk.Label(st, text="Driver:").grid(row=0, column=0, sticky="w")
        self.lbl_driver = ttk.Label(st, text="Starting...")
        self.lbl_driver.grid(row=0, column=1, sticky="w", padx=6)
        self.btn_install = ttk.Button(st, text="Install driver", command=self.install_driver)
        ttk.Label(st, text="Controller:").grid(row=1, column=0, sticky="w")
        self.lbl_dev = ttk.Label(st, text="...", wraplength=330)
        self.lbl_dev.grid(row=1, column=1, columnspan=2, sticky="w", padx=6)

        cf = ttk.LabelFrame(f, text="Controller to convert", padding=8)
        cf.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        cf.columnconfigure(0, weight=1)
        self.cmb_dev = ttk.Combobox(cf, state="readonly", values=[AUTO], width=52)
        self.cmb_dev.current(0)
        self.cmb_dev.grid(row=0, column=0, sticky="ew")
        self.cmb_dev.bind("<<ComboboxSelected>>", self.on_device)
        ttk.Button(cf, text="Refresh", command=self.engine.rescan).grid(row=0, column=1, padx=(6, 0))

        mf = ttk.LabelFrame(f, text="Mapping", padding=8)
        mf.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        mf.columnconfigure(0, weight=1)
        self.cmb_map = ttk.Combobox(mf, state="readonly", width=52)
        self.cmb_map.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.cmb_map.bind("<<ComboboxSelected>>", self.on_mapping)
        ttk.Button(mf, text="New mapping...", command=self.new_mapping).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(mf, text="Delete", command=self.delete_mapping).grid(row=1, column=1, pady=(8, 0), padx=6)
        ttk.Button(mf, text="Open folder", command=lambda: os.startfile(storage.MAPPINGS_DIR)).grid(
            row=1, column=2, pady=(8, 0))
        self.refresh_mappings()

        self.var_startup = tk.BooleanVar(value=storage.startup_enabled())
        self.var_tray = tk.BooleanVar(value=bool(self.settings["minimize_to_tray"]))
        ttk.Checkbutton(f, text="Start with Windows", variable=self.var_startup,
                        command=self.on_startup).grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Checkbutton(f, text="Minimize to tray", variable=self.var_tray,
                        command=self.on_tray_opt).grid(row=4, column=0, sticky="w")
        ttk.Label(f, text="Keep this program running while you play.", foreground="#666666").grid(
            row=5, column=0, sticky="w", pady=(10, 0))

    def refresh_mappings(self, select=None):
        names = storage.list_mappings()
        self.cmb_map["values"] = names
        cur = select or self.settings.get("mapping")
        if cur in names:
            self.cmb_map.set(cur)
        else:
            self.cmb_map.set("")

    # ---- engine glue ----
    def _apply_mapping_to_engine(self, name):
        try:
            m = storage.load_mapping(name) if name else None
        except (OSError, ValueError):
            m = None
        self.engine.set_mapping(m)

    def on_mapping(self, _e=None):
        name = self.cmb_map.get()
        self.settings["mapping"] = name or None
        storage.save_settings(self.settings)
        self._apply_mapping_to_engine(name)

    def on_device(self, _e=None):
        i = self.cmb_dev.current()
        guid = self.dev_guids[i - 1] if 0 < i <= len(self.dev_guids) else None
        self.settings["device"] = guid
        storage.save_settings(self.settings)
        self.engine.set_device(guid)

    def selected_guid(self):
        i = self.cmb_dev.current()
        return self.dev_guids[i - 1] if 0 < i <= len(self.dev_guids) else None

    def delete_mapping(self):
        name = self.cmb_map.get()
        if not name:
            return
        if not messagebox.askyesno(storage.APP_NAME, f'Delete the mapping "{name}"?'):
            return
        storage.delete_mapping(name)
        self.settings["mapping"] = None
        storage.save_settings(self.settings)
        self.engine.set_mapping(None)
        self.refresh_mappings()

    def new_mapping(self):
        snap = self.engine.snapshot()
        if not snap["devices"]:
            messagebox.showinfo(storage.APP_NAME, "No controller detected. Connect it (Bluetooth or USB), "
                                "wake it by pressing a button, then press Refresh.")
            return
        name = simpledialog.askstring("New mapping", "Name for this controller (for example\n"
                                      "the controller's model):", parent=self.root)
        if not name:
            return
        name = storage.safe_name(name)
        if not name:
            messagebox.showwarning(storage.APP_NAME, "That name has no usable characters.")
            return
        if name in storage.list_mappings() and not messagebox.askyesno(
                storage.APP_NAME, f'A mapping named "{name}" already exists. Replace it?'):
            return
        if self.engine.start_wizard(name, self.selected_guid()):
            self.wiz_handled = False
            self.wiz_name = name
            self.open_wizard()

    def open_wizard(self):
        w = tk.Toplevel(self.root)
        w.title("New mapping: " + self.wiz_name)
        w.transient(self.root)
        w.resizable(False, False)
        w.protocol("WM_DELETE_WINDOW", self.engine.cancel_wizard)
        f = ttk.Frame(w, padding=16)
        f.grid()
        lbl_step = ttk.Label(f, text="")
        lbl_step.grid(row=0, column=0, columnspan=2, sticky="w")
        lbl_prompt = ttk.Label(f, text="", font=("Segoe UI", 13, "bold"), wraplength=380, justify="left")
        lbl_prompt.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 12))
        bar = ttk.Progressbar(f, length=380, maximum=len(eng.STEPS))
        bar.grid(row=2, column=0, columnspan=2)
        ttk.Button(f, text="Skip this control", command=self.engine.skip_step).grid(
            row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Button(f, text="Cancel", command=self.engine.cancel_wizard).grid(
            row=3, column=1, sticky="e", pady=(12, 0))
        f.columnconfigure(1, weight=1)
        self.wiz = {"win": w, "step": lbl_step, "prompt": lbl_prompt, "bar": bar}

    def close_wizard(self):
        if self.wiz:
            self.wiz["win"].destroy()
            self.wiz = None

    # ---- driver ----
    def install_driver(self):
        self.btn_install.state(["disabled"])

        def work():
            try:
                ok = eng.install_driver()
            except Exception:
                ok = False
            self.q.put("driver_ok" if ok else "driver_fail")
        threading.Thread(target=work, daemon=True).start()

    # ---- options ----
    def on_startup(self):
        try:
            storage.set_startup(self.var_startup.get())
        except OSError as e:
            messagebox.showerror(storage.APP_NAME, f"Could not change the startup setting:\n{e}")
        self.var_startup.set(storage.startup_enabled())

    def on_tray_opt(self):
        self.settings["minimize_to_tray"] = bool(self.var_tray.get())
        storage.save_settings(self.settings)

    # ---- tray ----
    def to_tray(self):
        if self.tray:
            return
        import pystray
        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda: self.q.put("show"), default=True),
            pystray.MenuItem("Exit", lambda: self.q.put("quit")),
        )
        self.tray = pystray.Icon("dinput2xinput", make_icon(64), storage.APP_NAME, menu)
        self.tray.run_detached()
        self.root.withdraw()

    def from_tray(self):
        if self.tray:
            self.tray.stop()
            self.tray = None
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def on_unmap(self, e):
        if e.widget is self.root and self.settings["minimize_to_tray"] and self.root.state() == "iconic":
            self.root.after(10, self.to_tray)

    def on_close(self):
        if self.settings["minimize_to_tray"]:
            self.to_tray()
        else:
            self.quit()

    def quit(self):
        self.engine.stop()
        self.engine.join(2)
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    # ---- polling ----
    def poll(self):
        try:
            self._poll()
        except Exception:
            self._log()
        self.root.after(150, self.poll)

    def _poll(self):
        while True:
            try:
                msg = self.q.get_nowait()
            except queue.Empty:
                break
            if msg == "show":
                self.from_tray()
            elif msg == "quit":
                self.quit()
                return
            elif msg == "driver_ok":
                self.engine.retry_driver()
            elif msg == "driver_fail":
                self.btn_install.state(["!disabled"])
                messagebox.showwarning(storage.APP_NAME, "The driver did not start. If you cancelled the "
                                       "administrator prompt, try again; otherwise a reboot may be needed.")

        s = self.engine.snapshot()

        drv = s["driver"]
        if drv == "ok":
            self.lbl_driver.config(text="Ready (virtual Xbox 360 controller active)", foreground="#1a7f37")
            self.btn_install.grid_remove()
        elif drv == "missing":
            self.lbl_driver.config(text="ViGEmBus driver is not installed", foreground="#b42318")
            self.btn_install.grid(row=0, column=2)
        elif drv == "error":
            self.lbl_driver.config(text=s["driver_msg"] or "Driver error", foreground="#b42318")
            self.btn_install.grid_remove()
        else:
            self.lbl_driver.config(text="Starting...", foreground="")

        if s["active_name"]:
            self.lbl_dev.config(text="Converting: " + s["active_name"], foreground="#1a7f37")
        elif not self.cmb_map.get():
            self.lbl_dev.config(text="Choose a mapping, or create one with New mapping...", foreground="")
        else:
            self.lbl_dev.config(text="Waiting for the controller (press a button to wake it)...", foreground="")

        guids = [d["guid"] for d in s["devices"]]
        if guids != self.dev_guids:
            self.dev_guids = guids
            self.cmb_dev["values"] = [AUTO] + [dev_label(d) for d in s["devices"]]
            pref = self.settings.get("device")
            self.cmb_dev.current(guids.index(pref) + 1 if pref in guids else 0)

        if s["mode"] == "mapping" and self.wiz:
            n = s["step"]
            self.wiz["step"].config(text=f"Step {min(n + 1, s['steps'])} of {s['steps']}")
            self.wiz["prompt"].config(text=s["prompt"])
            self.wiz["bar"]["value"] = n
        res = s["wizard_result"]
        if res and not self.wiz_handled and s["mode"] == "bridge":
            self.wiz_handled = True
            self.close_wizard()
            if res["status"] == "saved":
                self.settings["mapping"] = res["name"]
                storage.save_settings(self.settings)
                self.refresh_mappings(select=res["name"])
                self._apply_mapping_to_engine(res["name"])
                messagebox.showinfo(storage.APP_NAME, f'Mapping "{res["name"]}" saved and selected.')
            elif res["status"] == "error":
                messagebox.showerror(storage.APP_NAME, res["message"])

    def _log(self):
        storage.ensure_dirs()
        with open(storage.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")

    def _shot(self):
        from PIL import ImageGrab
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        ImageGrab.grab((x - 8, y - 40, x + self.root.winfo_width() + 8, y + self.root.winfo_height() + 8)).save(
            self.screenshot)
        self.quit()


def single_instance():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\DInput2XInputSingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    args = sys.argv[1:]
    shot = args[args.index("--screenshot") + 1] if "--screenshot" in args else None
    if not shot and not single_instance():
        ctypes.windll.user32.MessageBoxW(0, "DInput to XInput is already running (check the system tray).",
                                         storage.APP_NAME, 0x40)
        return
    try:
        app = App(autostart="--autostart" in args, screenshot=shot)
        app.root.mainloop()
    except Exception:
        storage.ensure_dirs()
        with open(storage.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
        ctypes.windll.user32.MessageBoxW(0, "The program crashed. Details were written to:\n" + storage.LOG_FILE,
                                         storage.APP_NAME, 0x10)


if __name__ == "__main__":
    main()
