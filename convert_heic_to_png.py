# -*- coding: utf-8 -*-
"""
Convert .HEIC photos to .png while preserving size and EXIF where possible.

Usage:
  python convert_heic_to_png.py <input_path> [output_dir]
"""

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def _register_heif():
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


def convert_file(src: Path, out_dir: Path):
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / (src.stem + ".png")

    with Image.open(src) as im:
        # PNG supports RGB/RGBA; keep alpha if present
        if im.mode == "P":
            im = im.convert("RGBA")

        exif = im.info.get("exif")
        save_kwargs = {"format": "PNG", "optimize": True}
        if exif:
            save_kwargs["exif"] = exif

        im.save(dst, **save_kwargs)

    return dst


def main():
    parser = argparse.ArgumentParser(description="Convert HEIC to PNG.")
    parser.add_argument("input", help="HEIC file or folder")
    parser.add_argument("output", nargs="?", default=None, help="Output folder (default: <input>/png)")
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(32, (os.cpu_count() or 1) * 2)),
        help="Number of worker threads (default: auto)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else (input_path.parent if input_path.is_file() else input_path / "png")

    backend = _register_heif()
    if backend is None:
        print("Missing HEIC support. Install one of:")
        print("  pip install pillow-heif pillow")
        print("  pip install pyheif pillow")
        return 2

    sources = list(_iter_inputs(input_path))
    if not sources:
        print("No .HEIC files found.")
        return 0

    workers = max(1, args.workers)
    count = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_src = {executor.submit(convert_file, src, output_dir): src for src in sources}
        for future in as_completed(future_to_src):
            src = future_to_src[future]
            try:
                dst = future.result()
                print(f"{src} -> {dst}")
                count += 1
            except Exception as e:
                print(f"Failed: {src} ({e})")

    print(f"Converted {count} file(s) using {backend} with {workers} worker(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
