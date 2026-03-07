# -*- coding: utf-8 -*-
"""
Simple GUI for converting HEIC to JPG or PNG.
"""

import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def _register_heif():
    """Register HEIF opener with Pillow."""
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        return "pillow-heif"
    except Exception:
        try:
            import pyheif  # noqa: F401
            from PIL import Image

            def _heif_open(fp):
                heif_file = pyheif.read(fp)
                image = Image.frombytes(
                    heif_file.mode,
                    heif_file.size,
                    heif_file.data,
                    "raw",
                    heif_file.mode,
                    heif_file.stride,
                )
                image.info["exif"] = heif_file.metadata["Exif"][0][1] if heif_file.metadata and "Exif" in heif_file.metadata[0][0] else None
                return image

            Image.register_open("HEIF", _heif_open)
            return "pyheif"
        except Exception:
            return None


def _iter_inputs(path: Path):
    if path.is_file():
        yield path
        return
    if path.is_dir():
        for p in path.rglob("*.heic"):
            yield p
        for p in path.rglob("*.HEIC"):
            yield p
        return
    raise FileNotFoundError(f"Not found: {path}")


def convert_file_jpg(src: Path, out_dir: Path, quality: int):
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / (src.stem + ".jpg")

    with Image.open(src) as im:
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGB")

        exif = im.info.get("exif")
        save_kwargs = {
            "format": "JPEG",
            "quality": quality,
            "subsampling": 0,
            "optimize": True,
        }
        if exif:
            save_kwargs["exif"] = exif

        im.save(dst, **save_kwargs)

    return dst


def convert_file_png(src: Path, out_dir: Path):
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / (src.stem + ".png")

    with Image.open(src) as im:
        if im.mode == "P":
            im = im.convert("RGBA")

        exif = im.info.get("exif")
        save_kwargs = {"format": "PNG", "optimize": True}
        if exif:
            save_kwargs["exif"] = exif

        im.save(dst, **save_kwargs)

    return dst


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HEIC 转换器")
        self.geometry("680x520")
        self.resizable(False, False)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.format_var = tk.StringVar(value="jpg")
        self.quality_var = tk.IntVar(value=95)
        self.status_var = tk.StringVar(value="就绪")

        self._queue = queue.Queue()
        self._worker = None

        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="输入文件/目录").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.input_var, width=60).grid(row=0, column=1, **pad)
        ttk.Button(frm, text="选择...", command=self._pick_input).grid(row=0, column=2, **pad)

        ttk.Label(frm, text="输出目录（可选）").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.output_var, width=60).grid(row=1, column=1, **pad)
        ttk.Button(frm, text="选择...", command=self._pick_output).grid(row=1, column=2, **pad)

        ttk.Label(frm, text="格式").grid(row=2, column=0, sticky="w", **pad)
        fmt_frame = ttk.Frame(frm)
        fmt_frame.grid(row=2, column=1, sticky="w", **pad)
        ttk.Radiobutton(fmt_frame, text="JPG", value="jpg", variable=self.format_var, command=self._on_format_change).pack(side="left", padx=4)
        ttk.Radiobutton(fmt_frame, text="PNG", value="png", variable=self.format_var, command=self._on_format_change).pack(side="left", padx=4)

        self.quality_label = ttk.Label(frm, text="JPG 质量 (1-100)")
        self.quality_label.grid(row=3, column=0, sticky="w", **pad)
        self.quality_scale = ttk.Scale(frm, from_=1, to=100, variable=self.quality_var, orient="horizontal")
        self.quality_scale.grid(row=3, column=1, sticky="we", **pad)
        self.quality_value = ttk.Label(frm, textvariable=self.quality_var, width=4)
        self.quality_value.grid(row=3, column=2, sticky="w", **pad)

        ttk.Button(frm, text="开始转换", command=self._start).grid(row=4, column=1, sticky="w", **pad)

        ttk.Label(frm, text="日志").grid(row=5, column=0, sticky="w", **pad)
        self.log = tk.Text(frm, height=16, width=80)
        self.log.grid(row=6, column=0, columnspan=3, **pad)
        self.log.configure(state="disabled")

        ttk.Label(frm, textvariable=self.status_var).grid(row=7, column=0, columnspan=3, sticky="w", **pad)

        frm.columnconfigure(1, weight=1)
        self._on_format_change()

    def _on_format_change(self):
        is_jpg = self.format_var.get() == "jpg"
        state = "normal" if is_jpg else "disabled"
        self.quality_scale.configure(state=state)
        self.quality_value.configure(state=state)
        self.quality_label.configure(state=state)

    def _pick_input(self):
        path = filedialog.askdirectory(title="选择包含 HEIC 的目录")
        if path:
            self.input_var.set(path)

    def _pick_output(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_var.set(path)

    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self):
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("提示", "转换正在进行中")
            return

        input_path = self.input_var.get().strip()
        if not input_path:
            messagebox.showerror("错误", "请先选择输入目录")
            return

        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.status_var.set("准备中...")

        self._worker = threading.Thread(target=self._run_convert, daemon=True)
        self._worker.start()

    def _run_convert(self):
        try:
            backend = _register_heif()
            if backend is None:
                self._queue.put(("log", "缺少 HEIC 支持，请先安装：pip install pillow-heif pillow"))
                self._queue.put(("status", "失败"))
                return

            input_path = Path(self.input_var.get().strip())
            out_raw = self.output_var.get().strip()

            if out_raw:
                output_dir = Path(out_raw)
            else:
                if input_path.is_file():
                    output_dir = input_path.parent
                else:
                    output_dir = input_path / ("jpg" if self.format_var.get() == "jpg" else "png")

            count = 0
            for src in _iter_inputs(input_path):
                try:
                    if self.format_var.get() == "jpg":
                        dst = convert_file_jpg(src, output_dir, quality=self.quality_var.get())
                    else:
                        dst = convert_file_png(src, output_dir)
                    self._queue.put(("log", f"{src} -> {dst}"))
                    count += 1
                except Exception as e:
                    self._queue.put(("log", f"失败: {src} ({e})"))

            if count == 0:
                self._queue.put(("log", "未找到 .HEIC 文件"))
                self._queue.put(("status", "完成（0）"))
            else:
                self._queue.put(("log", f"完成：共转换 {count} 个文件（{backend}）"))
                self._queue.put(("status", f"完成（{count}）"))
        except Exception as e:
            self._queue.put(("log", f"发生错误: {e}"))
            self._queue.put(("status", "失败"))

    def _poll_queue(self):
        try:
            while True:
                kind, value = self._queue.get_nowait()
                if kind == "log":
                    self._log(value)
                elif kind == "status":
                    self.status_var.set(value)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)


if __name__ == "__main__":
    app = App()
    app.mainloop()
