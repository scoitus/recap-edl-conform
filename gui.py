"""Simple double-clickable GUI for the EDL -> SubCap generator.

Pick the long EDL, the short EDL, and an output folder, then click Generate.
Launch it via the EDL SubCap.command shortcut (double-click in Finder) or with
`python3 gui.py`. Stdlib only (tkinter).
"""

import os
import sys
import threading
import traceback

import tkinter as tk
from tkinter import filedialog, ttk

from edl_parser import EDLParseError
from main import run

EDL_TYPES = [("EDL files", "*.edl"), ("All files", "*.*")]


class App:
    def __init__(self, root):
        self.root = root
        root.title("EDL → SubCap Generator")
        root.minsize(640, 440)

        self.long_var = tk.StringVar()
        self.short_var = tk.StringVar()
        self.out_var = tk.StringVar()

        pad = {"padx": 8, "pady": 6}
        frm = ttk.Frame(root, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        self._file_row(frm, 0, "Long sequence EDL:", self.long_var,
                       self._pick_long)
        self._file_row(frm, 1, "Short cutdown EDL:", self.short_var,
                       self._pick_short)
        self._dir_row(frm, 2, "Output folder:", self.out_var, self._pick_out)

        self.run_btn = ttk.Button(frm, text="Generate", command=self._go)
        self.run_btn.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)

        self.log = tk.Text(frm, height=14, wrap="word", state="disabled")
        self.log.grid(row=4, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(4, weight=1)

        scroll = ttk.Scrollbar(frm, command=self.log.yview)
        scroll.grid(row=4, column=3, sticky="ns")
        self.log.config(yscrollcommand=scroll.set)

        self._log("Select the two EDLs and an output folder, then click "
                  "Generate.\n23.98 fps NON-DROP exports with Source File "
                  "comments ON.\n")

    def _file_row(self, parent, r, label, var, cmd):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w",
                                           padx=8, pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=r, column=1, sticky="ew",
                                                 padx=8, pady=6)
        ttk.Button(parent, text="Browse…", command=cmd).grid(
            row=r, column=2, padx=8, pady=6)

    _dir_row = _file_row  # same layout; different picker command

    def _pick_long(self):
        p = filedialog.askopenfilename(title="Select the LONG sequence EDL",
                                       filetypes=EDL_TYPES)
        if p:
            self.long_var.set(p)
            if not self.out_var.get():
                self.out_var.set(os.path.join(os.path.dirname(p), "subcap_out"))

    def _pick_short(self):
        p = filedialog.askopenfilename(title="Select the SHORT cutdown EDL",
                                       filetypes=EDL_TYPES)
        if p:
            self.short_var.set(p)

    def _pick_out(self):
        p = filedialog.askdirectory(title="Select the output folder")
        if p:
            self.out_var.set(p)

    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.root.update_idletasks()

    def _go(self):
        long_p = self.long_var.get().strip()
        short_p = self.short_var.get().strip()
        out_d = self.out_var.get().strip()

        if not long_p or not short_p or not out_d:
            self._log("ERROR: please choose both EDLs and an output folder.")
            return
        for p, name in ((long_p, "Long EDL"), (short_p, "Short EDL")):
            if not os.path.isfile(p):
                self._log("ERROR: %s not found: %s" % (name, p))
                return

        self.run_btn.config(state="disabled")
        self._log("\n--- Generating ---")
        # Run off the UI thread so the window stays responsive.
        threading.Thread(target=self._worker,
                         args=(long_p, short_p, out_d), daemon=True).start()

    def _worker(self, long_p, short_p, out_d):
        def ui_log(msg):
            self.root.after(0, self._log, msg)
        try:
            result = run(long_p, short_p, out_d, log=ui_log)
            ui_log("\nDONE. Wrote 3 files to:\n  %s" % out_d)
            ui_log("Import %s into the long sequence in Avid."
                   % os.path.basename(result["subcap"]))
        except EDLParseError as e:
            ui_log("\nABORT: %s" % e)
        except Exception:  # surface any unexpected error in the log
            ui_log("\nUNEXPECTED ERROR:\n" + traceback.format_exc())
        finally:
            self.root.after(0, lambda: self.run_btn.config(state="normal"))


def main():
    # Ensure imports resolve when launched from elsewhere (e.g. Finder).
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
