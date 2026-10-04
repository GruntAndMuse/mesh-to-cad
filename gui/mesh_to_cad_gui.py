#!/usr/bin/env python3
"""
mesh-to-cad GUI — drag, drop, done.

WHAT THIS IS:
    A graphical front end for the mesh-to-cad pipeline, for people the
    command line scares. Drop STL files on the window, press RUN, get
    plain-English results. Every error says what happened AND what to do.

WHAT THIS IS NOT:
    A reimplementation of the pipeline. All real work is done by the
    mesh-to-cad CLI, invoked as a subprocess. This GUI is a thin,
    friendly shell around it. If the CLI changes, the GUI follows.

PRIVACY (GruntAndMuse principle — non-negotiable):
    This GUI makes ZERO network calls. Ever. The only network touchpoint
    in the whole tool is the CLI's `mesh-to-cad update` subcommand, which
    runs only when you press the "Check for updates" button. You can
    verify: grep this file for urllib, requests, socket, http — you will
    find nothing.

USAGE:
    python3 gui/mesh_to_cad_gui.py
    (or run the bundled mesh-to-cad-gui executable)
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Drag-and-drop support (optional, degrades gracefully)
# ---------------------------------------------------------------------------
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    TkinterDnD = None
    DND_FILES = None
    _DND_AVAILABLE = False

# ---------------------------------------------------------------------------
# Locate the CLI. Source mode: ../mesh-to-cad run with this Python.
# Frozen (PyInstaller): a sibling mesh-to-cad executable next to the GUI exe.
# ---------------------------------------------------------------------------
_GUI_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _GUI_DIR.parent
_CLI_SCRIPT = _PROJECT_DIR / "mesh-to-cad"

ACCEPTED_EXTENSIONS = {".stl", ".ply", ".obj", ".3mf"}
APP_TITLE = "mesh-to-cad"

# ---------------------------------------------------------------------------
# Visual identity (style only — no behavior lives here).
# mesh-to-cad has its OWN look: dark slate header bar, warm stone
# neutrals, one teal accent. Deliberately NOT med-tracker's blue/green —
# Dennis: "polished, not matching." tkinter can't do rounded corners, so
# cards are flat white frames on the warm-gray window with generous
# padding; colors, spacing, and hierarchy carry the design, and
# pixel-perfect rounding is skipped on purpose.
# ---------------------------------------------------------------------------
C_BG = "#f5f5f4"          # warm light-gray app background (stone-100)
C_CARD = "#ffffff"        # section cards
C_HEADER_BG = "#1e293b"   # dark slate header bar (slate-800)
C_HEADER_FG = "#f8fafc"   # header text (slate-50)
C_HEADER_MUTED = "#94a3b8"  # header secondary text (slate-400)
C_PRIMARY = "#0d9488"     # teal accent — primary actions (teal-600)
C_PRIMARY_DARK = "#0f766e"  # primary pressed/hover (teal-700)
C_PRIMARY_DISABLED = "#99f6e4"  # primary disabled (teal-200)
C_SUCCESS = "#15803d"     # success green (green-700)
C_TEXT = "#292524"        # headings (stone-800)
C_BODY = "#57534e"        # body text (stone-600)
C_MUTED = "#a8a29e"       # muted / helper text (stone-400)
C_GRAY_BTN = "#e7e5e4"    # secondary buttons (stone-200)
C_GRAY_BTN_DARK = "#d6d3d1"  # secondary hover (stone-300)
C_ERROR = "#b91c1c"       # error red (red-700)
C_WARN = "#b45309"        # warning amber (amber-700)
C_DROP_BG = "#ccfbf1"     # drop zone tint (teal-100)
C_DROP_HOVER = "#99f6e4"  # drop zone on drag-over (teal-200)
C_DROP_FG = "#0f766e"     # drop zone text/border (teal-700)
C_BORDER = "#e7e5e4"      # hairlines (stone-200)


def _find_cli():
    """Return (argv_prefix, is_exe). argv_prefix goes before CLI args."""
    if getattr(sys, "frozen", False):
        exe_name = "mesh-to-cad.exe" if os.name == "nt" else "mesh-to-cad"
        cand = Path(sys.executable).resolve().parent / exe_name
        if cand.exists():
            return [str(cand)], True
    if _CLI_SCRIPT.exists():
        return [sys.executable, str(_CLI_SCRIPT)], False
    return None, False


def _cli_version(argv_prefix):
    try:
        p = subprocess.run(argv_prefix + ["--version"], capture_output=True,
                           text=True, timeout=20)
        return p.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# Days after the build date before the GUI shows the age banner.
# Matches the CLI's BUILD_AGE_NUDGE_DAYS — one rule, two surfaces.
BUILD_AGE_NUDGE_DAYS = 30


def _cli_build_date(argv_prefix):
    """Extract the CLI's build date from `mesh-to-cad --version`.

    The CLI prints e.g. "mesh-to-cad 1.0.2 (built 2026-10-04)" in release
    builds. Returns a datetime.date, or None when the date is missing
    (dev run from source) or unparseable. Pure local parsing — the
    subprocess call is to our own CLI, zero network.
    """
    try:
        p = subprocess.run(argv_prefix + ["--version"], capture_output=True,
                           text=True, timeout=20)
        m = re.search(r"\(built (\d{4}-\d{2}-\d{2})\)", p.stdout or "")
        if m:
            return date.fromisoformat(m.group(1))
    except Exception:
        pass
    return None


def _friendly_result(manifest):
    """Turn a pipeline manifest.json into plain-English lines."""
    lines = []
    # Units
    uc = manifest.get("source", {}).get("units_check", {})
    sugg = uc.get("suggestion", "?")
    conf = uc.get("confidence", "?")
    if sugg == "millimeters":
        lines.append(f"Units: looks like millimeters ({conf} confidence) — good.")
    else:
        lines.append(f"Units: looks like {sugg} (confidence: {conf}). "
                     "You confirmed this before the run.")
    # Quality
    qv = manifest.get("quality", "?")
    reasons = manifest.get("quality_reasons", []) or []
    if qv == "clean":
        lines.append("Quality: Clean — the scan is solid, good to rebuild from.")
    elif qv == "noisy":
        first = reasons[0] if reasons else "see manifest.json for details"
        lines.append(f"Quality: Noisy — usable, but expect cleanup first.\n  Why: {first}")
    elif qv == "needs-rescan":
        first = reasons[0] if reasons else "see manifest.json for details"
        lines.append("Quality: Needs rescan — the scan is missing too much data.\n"
                     f"  Why: {first}\n"
                     "  No pipeline fixes missing data. Rescan the part and try again.")
    else:
        lines.append(f"Quality: {qv}")
    # Track
    track = manifest.get("track", "?")
    tconf = manifest.get("track_confidence", "?")
    if track == "prismatic":
        lines.append("Shape: Prismatic — flat faces and cylinders. "
                     "Good candidate for parametric CAD rebuild.")
    elif track == "organic":
        lines.append("Shape: Organic — curvy/freeform. Needs the surface-rebuild path.")
    elif track == "mixed":
        lines.append("Shape: Mixed — prismatic base with organic details. "
                     "Rebuild the base first, details after.")
    else:
        lines.append(f"Shape: {track} (confidence: {tconf})")
    return "\n".join(lines)


class MeshToCadGui:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("660x990")
        self.root.minsize(600, 700)

        self.cli_argv, _ = _find_cli()
        self.version = _cli_version(self.cli_argv) if self.cli_argv else "unknown"
        self.files = []            # list of Path, deduped
        self.msg_queue = queue.Queue()
        self.worker = None
        self.output_dir = tk.StringVar(
            value=str(Path.home() / "mesh-to-cad-projects"))

        self._apply_style()
        self._build_ui()
        if not self.cli_argv:
            messagebox.showwarning(
                "CLI not found",
                "Could not find the mesh-to-cad command.\n"
                "The GUI needs it next to the gui/ folder.\n\n"
                "Nothing will run until this is fixed.")
        self._poll_queue()

    # ---------------------------------------------------------------- style
    def _apply_style(self):
        """med-tracker palette via ttk. Style only — touches no logic."""
        self.root.configure(bg=C_BG)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")  # flat theme; honors bg colors
        except tk.TclError:
            pass
        f_body = ("TkDefaultFont", 11)
        style.configure("TFrame", background=C_BG)
        style.configure("Card.TFrame", background=C_CARD)
        style.configure("TLabel", background=C_BG, foreground=C_TEXT,
                        font=f_body)
        style.configure("Header.TFrame", background=C_HEADER_BG)
        style.configure("Header.TLabel", background=C_HEADER_BG,
                        foreground=C_HEADER_FG,
                        font=("TkDefaultFont", 18, "bold"))
        style.configure("HeaderMuted.TLabel", background=C_HEADER_BG,
                        foreground=C_HEADER_MUTED,
                        font=("TkDefaultFont", 10))
        style.configure("Muted.TLabel", background=C_BG, foreground=C_MUTED,
                        font=("TkDefaultFont", 9))
        # Age-nudge banner: warm amber strip, dismissible, not modal.
        # Points at the existing "Check for updates" button in the footer.
        style.configure("Nudge.TFrame", background="#fef3c7")
        style.configure("Nudge.TLabel", background="#fef3c7",
                        foreground="#92400e", font=("TkDefaultFont", 10))
        style.configure("TLabelframe", background=C_CARD,
                        bordercolor=C_BORDER, relief="flat", borderwidth=1)
        style.configure("TLabelframe.Label", background=C_CARD,
                        foreground=C_TEXT, font=("TkDefaultFont", 12, "bold"))
        # Primary action: solid teal, white text
        style.configure("Primary.TButton", background=C_PRIMARY,
                        foreground="#ffffff",
                        font=("TkDefaultFont", 13, "bold"),
                        padding=(18, 10), borderwidth=0)
        style.map("Primary.TButton",
                  background=[("active", C_PRIMARY_DARK),
                              ("disabled", C_PRIMARY_DISABLED)],
                  foreground=[("disabled", "#ffffff")])
        # Secondary actions: warm stone gray
        style.configure("Secondary.TButton", background=C_GRAY_BTN,
                        foreground=C_TEXT, font=("TkDefaultFont", 11),
                        padding=(14, 7), borderwidth=0)
        style.map("Secondary.TButton",
                  background=[("active", C_GRAY_BTN_DARK),
                              ("disabled", "#f0f0f0")],
                  foreground=[("disabled", C_MUTED)])
        style.configure("TEntry", fieldbackground=C_CARD, foreground=C_TEXT,
                        font=f_body)
        style.configure("TProgressbar", background=C_PRIMARY,
                        troughcolor="#e0e0e0", borderwidth=0)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pad = {"padx": 12, "pady": 8}

        # Header — full-bleed dark slate bar
        hdr = ttk.Frame(self.root, style="Header.TFrame")
        hdr.pack(fill="x")
        ttk.Label(hdr, text="mesh-to-cad",
                  style="Header.TLabel").pack(side="left",
                                             padx=(16, 0), pady=(12, 12))
        ttk.Label(hdr, text=f"v{self.version}",
                  style="HeaderMuted.TLabel").pack(side="left", padx=(10, 0))

        # Offline build-age nudge: a subtle dismissible banner, shown only
        # when the CLI build is 30+ days old. Same rule as the CLI's
        # stderr nudge — pure local date comparison, zero network.
        # Not modal, not nagging: one strip, one Dismiss button, gone.
        self._maybe_show_age_banner()

        # Drop zone (hero element)
        dz_frame = ttk.LabelFrame(self.root, text="1 — Add your files")
        dz_frame.pack(fill="x", **pad)
        self.drop_label = tk.Label(
            dz_frame,
            text=("Drop STL files here\n\n"
                  "(.stl, .obj, .ply, .3mf)"),
            font=("TkDefaultFont", 14),
            fg=C_DROP_FG,
            bg=C_DROP_BG,
            height=5,
            relief="flat",
            highlightthickness=2,
            highlightbackground=C_DROP_FG,
            highlightcolor=C_DROP_FG,
        )
        self.drop_label.pack(fill="x", padx=12, pady=(10, 6))
        if _DND_AVAILABLE:
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_label.dnd_bind("<<DragEnter>>",
                                     lambda e: self.drop_label.config(bg=C_DROP_HOVER))
            self.drop_label.dnd_bind("<<DragLeave>>",
                                     lambda e: self.drop_label.config(bg=C_DROP_BG))
        else:
            self.drop_label.config(
                text="Drag-and-drop isn't available\n(use the Browse button below)")
        ttk.Button(dz_frame, text="Browse files…", style="Secondary.TButton",
                   command=self._browse).pack(pady=(0, 10))

        # File list
        fl_frame = ttk.LabelFrame(self.root, text="Files to process")
        fl_frame.pack(fill="both", expand=False, **pad)
        list_row = ttk.Frame(fl_frame, style="Card.TFrame")
        list_row.pack(fill="x", padx=12, pady=10)
        self.file_listbox = tk.Listbox(
            list_row, height=4, selectmode=tk.EXTENDED,
            bg=C_CARD, fg=C_TEXT, font=("TkDefaultFont", 11),
            selectbackground=C_PRIMARY, selectforeground="#ffffff",
            relief="flat", highlightthickness=1,
            highlightbackground=C_BORDER)
        self.file_listbox.pack(side="left", fill="x", expand=True)
        sb = ttk.Scrollbar(list_row, orient="vertical",
                           command=self.file_listbox.yview)
        sb.pack(side="right", fill="y")
        self.file_listbox.config(yscrollcommand=sb.set)
        btn_col = ttk.Frame(fl_frame, style="Card.TFrame")
        btn_col.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(btn_col, text="Remove selected", style="Secondary.TButton",
                   command=self._remove_selected).pack(side="left")
        ttk.Button(btn_col, text="Clear all", style="Secondary.TButton",
                   command=self._clear_all).pack(side="left", padx=(8, 0))

        # Output folder
        out_frame = ttk.LabelFrame(self.root, text="2 — Where results go")
        out_frame.pack(fill="x", **pad)
        out_row = ttk.Frame(out_frame, style="Card.TFrame")
        out_row.pack(fill="x", padx=12, pady=10)
        ttk.Entry(out_row, textvariable=self.output_dir).pack(
            side="left", fill="x", expand=True)
        ttk.Button(out_row, text="Browse…", style="Secondary.TButton",
                   command=self._browse_output).pack(side="right", padx=(8, 0))

        # Run
        run_frame = ttk.Frame(self.root)
        run_frame.pack(fill="x", **pad)
        self.run_button = ttk.Button(run_frame, text="▶  RUN PIPELINE",
                                     style="Primary.TButton",
                                     command=self._run_clicked)
        self.run_button.pack(fill="x", ipady=8)

        # Progress
        prog_frame = ttk.Frame(self.root)
        prog_frame.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(fill="x")
        self.status_label = ttk.Label(prog_frame, text="Ready — add files above.",
                                      style="Muted.TLabel")
        self.status_label.pack(anchor="w", pady=(2, 0))

        # Results
        res_frame = ttk.LabelFrame(self.root, text="Results")
        res_frame.pack(fill="both", expand=True, **pad)
        self.results = scrolledtext.ScrolledText(
            res_frame, height=10, wrap="word", state="disabled",
            font=("TkDefaultFont", 11), bg=C_CARD, fg=C_TEXT,
            relief="flat", highlightthickness=1,
            highlightbackground=C_BORDER)
        self.results.pack(fill="both", expand=True, padx=12, pady=10)
        self.results.tag_configure("ok", foreground=C_SUCCESS,
                                   font=("TkDefaultFont", 11, "bold"))
        self.results.tag_configure("fail", foreground=C_ERROR,
                                   font=("TkDefaultFont", 11, "bold"))
        self.results.tag_configure("warn", foreground=C_WARN,
                                   font=("TkDefaultFont", 11, "bold"))

        # Footer
        foot = ttk.Frame(self.root)
        foot.pack(fill="x", **pad)
        ttk.Button(foot, text="Check for updates", style="Secondary.TButton",
                   command=self._check_updates).pack(side="left")
        ttk.Label(foot,
                  text="Update check only runs when you press the button.",
                  style="Muted.TLabel").pack(side="left", padx=(8, 0))

    def _maybe_show_age_banner(self):
        """Show the build-age banner if the CLI is 30+ days old.

        The date comes from `mesh-to-cad --version` (e.g. "mesh-to-cad
        1.0.2 (built 2026-10-04)"). Missing/unparseable date (dev run from
        source) or a fresh build: no banner, no error. One Dismiss button
        removes it for the session.
        """
        if not self.cli_argv:
            return
        built = _cli_build_date(self.cli_argv)
        if not built:
            return
        age_days = (date.today() - built).days
        if age_days < BUILD_AGE_NUDGE_DAYS:
            return
        banner = ttk.Frame(self.root, style="Nudge.TFrame")
        ttk.Label(
            banner,
            text=(f"This build is {age_days} days old — press "
                  f"\"Check for updates\" below to see what's new."),
            style="Nudge.TLabel",
        ).pack(side="left", padx=(12, 8), pady=8)
        ttk.Button(
            banner, text="Dismiss", style="Secondary.TButton",
            command=banner.destroy,
        ).pack(side="right", padx=(0, 12), pady=6)
        # Pack right after the header (which is the first packed child).
        banner.pack(fill="x", padx=12, pady=(8, 0), after=self.root.winfo_children()[0])

    # ------------------------------------------------------------- file mgmt
    def _add_files(self, paths):
        added, rejected = 0, []
        for p in paths:
            p = Path(p)
            if not p.is_file():
                continue
            if p.suffix.lower() not in ACCEPTED_EXTENSIONS:
                rejected.append(p.name)
                continue
            rp = p.resolve()
            if rp not in [f.resolve() for f in self.files]:
                self.files.append(rp)
                self.file_listbox.insert("end", rp.name)
                added += 1
        if rejected:
            messagebox.showinfo(
                "Skipped files",
                "These aren't mesh files, so they were skipped:\n\n"
                + "\n".join(rejected)
                + "\n\nAccepted: .stl, .obj, .ply, .3mf")
        if added:
            self._set_status(f"{len(self.files)} file(s) ready.")

    def _on_drop(self, event):
        self.drop_label.config(bg=C_DROP_BG)
        try:
            dropped = self.root.tk.splitlist(event.data)
        except Exception:
            dropped = [event.data]
        # splitlist can return a single string when only one file was dropped
        if isinstance(dropped, str):
            dropped = [dropped]
        self._add_files(dropped)

    def _browse(self):
        chosen = filedialog.askopenfilenames(
            title="Choose mesh files",
            filetypes=[("Mesh files", "*.stl *.obj *.ply *.3mf"),
                       ("All files", "*.*")])
        if chosen:
            self._add_files(chosen)

    def _remove_selected(self):
        for i in reversed(self.file_listbox.curselection()):
            del self.files[i]
            self.file_listbox.delete(i)

    def _clear_all(self):
        self.files.clear()
        self.file_listbox.delete(0, "end")

    def _browse_output(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.output_dir.set(d)

    # ------------------------------------------------------------------ run
    def _set_status(self, text):
        self.status_label.config(text=text)

    def _append_result(self, text):
        self.results.config(state="normal")
        start_idx = self.results.index(tk.INSERT)
        self.results.insert("end", text + "\n\n")
        # status coloring on the result marker line
        tag = {"✓": "ok", "✗": "fail", "■": "warn"}.get(text[:1])
        if tag:
            self.results.tag_add(tag, start_idx, f"{start_idx} lineend")
        self.results.see("end")
        self.results.config(state="disabled")

    def _run_clicked(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.cli_argv:
            messagebox.showerror("Can't run", "The mesh-to-cad command wasn't found.")
            return
        if not self.files:
            messagebox.showinfo("No files", "Drop some STL files on the window first.")
            return
        outdir = Path(self.output_dir.get()).expanduser()
        try:
            outdir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Bad output folder",
                                 f"Couldn't use that folder:\n{e}")
            return

        # Units pre-check (fast) + one confirmation for non-mm files.
        plan = []  # (Path, stdin_bytes_or_None, skip_reason_or_None)
        for f in self.files:
            try:
                p = subprocess.run(self.cli_argv + ["units", "--json", str(f)],
                                   capture_output=True, text=True, timeout=120)
                info = json.loads(p.stdout)
                sugg = info.get("suggestion", "millimeters")
            except Exception:
                plan.append((f, None, "couldn't read the file — it may be corrupted. "
                                     "Try opening it in MeshLab; if MeshLab can't "
                                     "open it either, the file is bad."))
                continue
            if sugg == "millimeters":
                plan.append((f, None, None))
            else:
                plan.append((f, "PENDING_CONFIRM", sugg))
        need_confirm = [(f, s) for f, st, s in plan if st == "PENDING_CONFIRM"]
        confirm_yes = True
        if need_confirm:
            names = "\n".join(f"  • {f.name} (looks like {s})"
                              for f, s in need_confirm)
            confirm_yes = messagebox.askyesno(
                "Check the units",
                "These files don't look like millimeters:\n\n" + names +
                "\n\nWrong units silently corrupt every measurement. "
                "Continue anyway?")
        final_plan = []
        for f, st, s in plan:
            if s and st is None and s.startswith("couldn't read"):
                final_plan.append((f, None, s))          # error entry
            elif st == "PENDING_CONFIRM":
                if confirm_yes:
                    final_plan.append((f, b"y\n", None))  # user confirmed
                else:
                    final_plan.append((f, None, "skipped — you didn't confirm the units."))
            else:
                final_plan.append((f, st, None))

        self.results.config(state="normal")
        self.results.delete("1.0", "end")
        self.results.config(state="disabled")
        self.progress["maximum"] = len(final_plan)
        self.progress["value"] = 0
        self.run_button.config(state="disabled")
        self.worker = threading.Thread(target=self._worker,
                                       args=(final_plan, outdir),
                                       daemon=True)
        self.worker.start()

    def _worker(self, plan, outdir):
        q = self.msg_queue
        for i, (fpath, stdin_data, skip_reason) in enumerate(plan, 1):
            q.put(("status", f"File {i}/{len(plan)}: {fpath.name}…"))
            if skip_reason:
                q.put(("result", f"■ {fpath.name}\n{skip_reason}"))
                q.put(("progress", i))
                continue
            proj = outdir / fpath.stem
            try:
                p = subprocess.Popen(
                    self.cli_argv + [str(fpath), "--output", str(proj)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(_PROJECT_DIR),
                )
                try:
                    out, _ = p.communicate(input=stdin_data.decode()
                                           if stdin_data else None,
                                           timeout=900)
                except subprocess.TimeoutExpired:
                    p.kill()
                    out, _ = p.communicate()
                    q.put(("result",
                           f"■ {fpath.name}\nTimed out after 15 minutes. "
                           "The file may be huge or the mesh may be pathological. "
                           "Try a smaller test file first."))
                    q.put(("progress", i))
                    continue
            except Exception as e:
                q.put(("result", f"■ {fpath.name}\nCouldn't start the pipeline: {e}"))
                q.put(("progress", i))
                continue

            # Stage tracking from stdout markers
            for line in out.splitlines():
                if "Step 1/3" in line:
                    q.put(("status", f"File {i}/{len(plan)}: {fpath.name} — checking units…"))
                elif "Step 2/3" in line:
                    q.put(("status", f"File {i}/{len(plan)}: {fpath.name} — quality gate…"))
                elif "Step 3/3" in line:
                    q.put(("status", f"File {i}/{len(plan)}: {fpath.name} — analyzing…"))

            if p.returncode == 0:
                man_path = proj / "manifest.json"
                try:
                    manifest = json.loads(man_path.read_text(encoding="utf-8"))
                    body = _friendly_result(manifest)
                except Exception:
                    body = ("Finished, but I couldn't read the results file.\n"
                            f"  Look in: {proj}")
                q.put(("result",
                       f"✓ {fpath.name}\n{body}\n  Outputs in: {proj}"))
            elif p.returncode == 2:
                # needs-rescan: intentional stop. Manifest was saved.
                man_path = proj / "manifest.json"
                try:
                    manifest = json.loads(man_path.read_text(encoding="utf-8"))
                    body = _friendly_result(manifest)
                except Exception:
                    body = ("The pipeline stopped on purpose: the scan needs "
                            "to be redone.")
                q.put(("result", f"■ {fpath.name}\n{body}"))
            else:
                # Pull the friendly error lines out of stdout (CLI prints
                # "error: ..." with what-to-do-next; never a traceback).
                err_lines = [ln for ln in out.splitlines()
                             if ln.strip().startswith("error:")
                             or "what to do" in ln.lower()]
                detail = "\n".join(err_lines[:6]) or (
                    "The pipeline failed. Full output was logged to the "
                    "terminal — run the command-line version to see it.")
                q.put(("result", f"✗ {fpath.name}\n{detail}"))
            q.put(("progress", i))
        q.put(("done", None))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "status":
                    self._set_status(payload)
                elif kind == "result":
                    self._append_result(payload)
                elif kind == "progress":
                    self.progress["value"] = payload
                elif kind == "done":
                    self.run_button.config(state="normal")
                    n = len(self.files)
                    self._set_status(f"Done — processed {n} file(s).")
                elif kind == "update_result":
                    self._show_update_result(payload)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    # ---------------------------------------------------------------- update
    def _check_updates(self):
        if not self.cli_argv:
            messagebox.showerror("Can't check", "The mesh-to-cad command wasn't found.")
            return
        self._set_status("Checking for updates… (only because you asked)")
        def _do():
            try:
                p = subprocess.run(self.cli_argv + ["update"],
                                   capture_output=True, text=True, timeout=60)
                out = (p.stdout or "") + (p.stderr or "")
                self.msg_queue.put(("update_result", out.strip()
                                    or "(no output from update check)"))
            except subprocess.TimeoutExpired:
                self.msg_queue.put(("update_result",
                                    "Update check timed out. Are you online?"))
            except Exception as e:
                self.msg_queue.put(("update_result",
                                    f"Couldn't check for updates: {e}\n"
                                    "This needs internet. The tool itself "
                                    "works fully offline."))
        threading.Thread(target=_do, daemon=True).start()

    def _show_update_result(self, text):
        self._set_status("Ready.")
        win = tk.Toplevel(self.root)
        win.title("Update check")
        win.geometry("520x380")
        win.configure(bg=C_BG)
        txt = scrolledtext.ScrolledText(win, wrap="word",
                                        font=("TkDefaultFont", 11),
                                        bg=C_CARD, fg=C_TEXT,
                                        relief="flat", highlightthickness=1,
                                        highlightbackground=C_BORDER)
        txt.pack(fill="both", expand=True, padx=12, pady=12)
        txt.insert("1.0", text)
        txt.config(state="disabled")
        ttk.Button(win, text="Close", style="Secondary.TButton",
                   command=win.destroy).pack(pady=(0, 12))


def main():
    # Hidden diagnostic: `mesh-to-cad-gui --selftest` verifies the bundle
    # without opening the window. Useful after installing on a new machine
    # to confirm drag-and-drop support loaded.
    if "--selftest" in sys.argv:
        root_cls = TkinterDnD.Tk if _DND_AVAILABLE else tk.Tk
        root = root_cls()
        root.withdraw()
        print(f"tkinter DnD available: {_DND_AVAILABLE}")
        if _DND_AVAILABLE:
            try:
                ver = root.tk.call("package", "require", "tkdnd")
                print(f"tkdnd version: {ver}")
            except Exception as e:
                print(f"tkdnd FAILED to load: {e}")
        cli_argv, _ = _find_cli()
        print(f"CLI found: {cli_argv is not None}")
        if cli_argv:
            print(f"CLI version: {_cli_version(cli_argv)}")
        root.destroy()
        return
    root_cls = TkinterDnD.Tk if _DND_AVAILABLE else tk.Tk
    root = root_cls()
    MeshToCadGui(root)  # wires its own queue poller via after()
    root.mainloop()


if __name__ == "__main__":
    main()
