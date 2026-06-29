#!/usr/bin/env python3
"""
Image to JPG Converter
-----------------------
A small, fully local desktop app for converting PNG, HEIC, and JPEG images
to JPG.

Nothing leaves your machine: no network calls, no uploads, no cloud APIs.
Conversion happens with the Pillow image library, run entirely on disk.

Requirements:
    pip install Pillow pillow-heif

(pillow-heif adds HEIC/HEIF support. If it isn't installed, PNG and JPEG
conversion still work fine — only HEIC files will show an error asking you
to install it.)

Run:
    python png_to_jpg_converter.py
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image
except ImportError:
    print("This app requires the 'Pillow' library.\n"
          "Install it with:\n\n    pip install Pillow\n")
    sys.exit(1)

# HEIC/HEIF support is optional — Pillow can't read it natively.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False

# Extensions this app will offer to convert.
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".heic", ".heif")


class PngToJpgConverter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Image → JPG Converter (local, offline)")
        self.geometry("640x580")
        self.minsize(560, 500)

        self.files = []  # selected source image paths (png/jpg/jpeg/heic/heif)
        self.output_dir = tk.StringVar(value="")
        self.use_source_dir = tk.BooleanVar(value=True)
        self.quality = tk.IntVar(value=90)
        self.recursive = tk.BooleanVar(value=True)
        self.overwrite = tk.BooleanVar(value=False)

        self._build_ui()

    # ---------------------------------------------------------------- UI ---
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # --- File selection buttons ---
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        ttk.Button(top, text="Add image files…", command=self.add_files).pack(side="left")
        ttk.Button(top, text="Add folder…", command=self.add_folder).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(top, text="Include subfolders", variable=self.recursive).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Clear list", command=self.clear_files).pack(side="right")

        if not HEIF_SUPPORTED:
            ttk.Label(
                self,
                text="Note: HEIC support needs 'pillow-heif' (pip install pillow-heif). "
                     "PNG and JPEG conversion work without it.",
                foreground="#8a6d00",
            ).pack(fill="x", padx=10)

        # --- File list ---
        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        self.listbox = tk.Listbox(list_frame, selectmode="extended")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.count_label = ttk.Label(self, text="0 files selected")
        self.count_label.pack(anchor="w", padx=10)

        # --- Output options ---
        out_frame = ttk.LabelFrame(self, text="Output")
        out_frame.pack(fill="x", padx=10, pady=8)

        ttk.Radiobutton(
            out_frame, text="Save next to each original image",
            variable=self.use_source_dir, value=True
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 0))

        ttk.Radiobutton(
            out_frame, text="Save to a specific folder:",
            variable=self.use_source_dir, value=False
        ).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 6))

        self.output_entry = ttk.Entry(out_frame, textvariable=self.output_dir, width=40)
        self.output_entry.grid(row=1, column=1, sticky="we", padx=4)
        ttk.Button(out_frame, text="Browse…", command=self.choose_output_dir).grid(row=1, column=2, padx=4)
        out_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            out_frame, text="Overwrite existing .jpg files",
            variable=self.overwrite
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))

        # --- Quality slider ---
        qf = ttk.Frame(self)
        qf.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(qf, text="JPEG quality:").pack(side="left")
        self.quality_value_label = ttk.Label(qf, text="90")
        self.quality_value_label.pack(side="right")
        quality_slider = ttk.Scale(
            qf, from_=1, to=100, orient="horizontal",
            variable=self.quality,
            command=lambda v: self.quality_value_label.configure(text=str(int(float(v))))
        )
        quality_slider.pack(side="left", fill="x", expand=True, padx=8)

        # --- Convert button + progress ---
        action = ttk.Frame(self)
        action.pack(fill="x", padx=10, pady=(0, 6))
        self.convert_btn = ttk.Button(action, text="Convert", command=self.start_conversion)
        self.convert_btn.pack(side="left")

        self.progress = ttk.Progressbar(action, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=8)

        self.status_label = ttk.Label(self, text="Ready.", anchor="w")
        self.status_label.pack(fill="x", padx=10, pady=(0, 10))

    # ------------------------------------------------------------- actions ---
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select images (PNG, JPEG, or HEIC)",
            filetypes=[
                ("Supported images", "*.png *.jpg *.jpeg *.heic *.heif"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("HEIC/HEIF", "*.heic *.heif"),
                ("All files", "*.*"),
            ],
        )
        for p in paths:
            if p.lower().endswith(SUPPORTED_EXTENSIONS) and p not in self.files:
                self.files.append(p)
                self.listbox.insert("end", p)
        self._refresh_count()

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select a folder containing images")
        if not folder:
            return
        found = []
        if self.recursive.get():
            for root, _, names in os.walk(folder):
                for name in names:
                    if name.lower().endswith(SUPPORTED_EXTENSIONS):
                        found.append(os.path.join(root, name))
        else:
            for name in os.listdir(folder):
                full = os.path.join(folder, name)
                if os.path.isfile(full) and name.lower().endswith(SUPPORTED_EXTENSIONS):
                    found.append(full)

        for p in found:
            if p not in self.files:
                self.files.append(p)
                self.listbox.insert("end", p)
        self._refresh_count()

    def clear_files(self):
        self.files.clear()
        self.listbox.delete(0, "end")
        self._refresh_count()

    def choose_output_dir(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_dir.set(folder)
            self.use_source_dir.set(False)

    def _refresh_count(self):
        self.count_label.configure(text=f"{len(self.files)} file(s) selected")

    # ---------------------------------------------------------- conversion ---
    def start_conversion(self):
        if not self.files:
            messagebox.showinfo("No files", "Add at least one PNG, JPEG, or HEIC file first.")
            return

        if not self.use_source_dir.get() and not self.output_dir.get():
            messagebox.showwarning("No output folder", "Choose an output folder, or pick "
                                    "'Save next to each original image'.")
            return

        self.convert_btn.configure(state="disabled")
        self.progress.configure(maximum=len(self.files), value=0)
        self.status_label.configure(text="Converting…")

        # Run in a background thread so the GUI doesn't freeze on big batches.
        thread = threading.Thread(target=self._convert_all, daemon=True)
        thread.start()

    def _convert_all(self):
        succeeded, skipped, failed = 0, 0, []

        for i, src_path in enumerate(self.files, start=1):
            try:
                if self.use_source_dir.get():
                    dest_dir = os.path.dirname(src_path)
                else:
                    dest_dir = self.output_dir.get()
                    os.makedirs(dest_dir, exist_ok=True)

                base_name = os.path.splitext(os.path.basename(src_path))[0]
                dest_path = os.path.join(dest_dir, base_name + ".jpg")

                if os.path.exists(dest_path) and not self.overwrite.get():
                    skipped += 1
                else:
                    self._convert_one(src_path, dest_path)
                    succeeded += 1

            except Exception as e:
                failed.append((src_path, str(e)))

            self.after(0, self._update_progress, i, len(self.files))

        self.after(0, self._conversion_done, succeeded, skipped, failed)

    @staticmethod
    def _convert_one(src_path, dest_path):
        if src_path.lower().endswith((".heic", ".heif")) and not HEIF_SUPPORTED:
            raise RuntimeError("HEIC support needs 'pillow-heif' — run: pip install pillow-heif")

        with Image.open(src_path) as img:
            # JPG has no alpha channel, so flatten any transparency onto white.
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")

            # Force pixel data to load now, while the file is still open below,
            # so we can safely write back to the same path (e.g. re-compressing
            # a .jpg in place) once the source file handle is closed.
            img.load()

        quality = PngToJpgConverter._current_quality
        img.save(dest_path, "JPEG", quality=quality, optimize=True)

    def _update_progress(self, done, total):
        self.progress.configure(value=done)
        self.status_label.configure(text=f"Converting… {done}/{total}")

    def _conversion_done(self, succeeded, skipped, failed):
        self.convert_btn.configure(state="normal")
        summary = f"Done. Converted: {succeeded}, Skipped (already existed): {skipped}, Failed: {len(failed)}."
        self.status_label.configure(text=summary)

        if failed:
            details = "\n".join(f"- {os.path.basename(p)}: {err}" for p, err in failed[:10])
            more = "" if len(failed) <= 10 else f"\n…and {len(failed) - 10} more."
            messagebox.showwarning("Some files failed", f"{summary}\n\n{details}{more}")
        else:
            messagebox.showinfo("Conversion complete", summary)

    # Quality is read fresh from the slider each run via this property.
    @property
    def _current_quality_value(self):
        return self.quality.get()


# _convert_one is a staticmethod but needs the live quality value; patch it in
# via a tiny class attribute set right before each run.
def _patch_quality(app):
    PngToJpgConverter._current_quality = app.quality.get()


def main():
    app = PngToJpgConverter()
    # Keep the quality value in sync with the slider whenever conversion starts.
    original_start = app.start_conversion

    def start_with_quality():
        _patch_quality(app)
        original_start()

    app.start_conversion = start_with_quality
    app.convert_btn.configure(command=app.start_conversion)
    app.mainloop()


if __name__ == "__main__":
    main()