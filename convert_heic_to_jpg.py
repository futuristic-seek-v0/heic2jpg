# -*- coding: utf-8 -*-
"""
Convert .HEIC photos to .jpg while preserving size and EXIF where possible.

Usage:
  python convert_heic_to_jpg.py <input_path> [output_dir]

Examples:
  python convert_heic_to_jpg.py .\photos
  python convert_heic_to_jpg.py IMG_0001.HEIC .\jpgs
"""

import argparse
import os
import sys
from pathlib import Path


def _register_heif():
    """Register HEIF opener with Pillow."""
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        return "pillow-heif"
    except Exception:
        # Fallback to pyheif if pillow-heif is unavailable
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


def convert_file(src: Path, out_dir: Path, quality: int = 95):
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / (src.stem + ".jpg")

    with Image.open(src) as im:
        # Convert to RGB for JPEG
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGB")

        exif = im.info.get("exif")
        # Save with high quality and minimal subsampling to reduce loss
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


def main():
    parser = argparse.ArgumentParser(description="Convert HEIC to JPG.")
    parser.add_argument("input", help="HEIC file or folder")
    parser.add_argument("output", nargs="?", default=None, help="Output folder (default: <input>/jpg)")
    parser.add_argument("--quality", type=int, default=95, help="JPEG quality (1-100). Default 95")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else (input_path.parent if input_path.is_file() else input_path / "jpg")

    backend = _register_heif()
    if backend is None:
        print("Missing HEIC support. Install one of:")
        print("  pip install pillow-heif pillow")
        print("  pip install pyheif pillow")
        return 2

    count = 0
    for src in _iter_inputs(input_path):
        try:
            dst = convert_file(src, output_dir, quality=args.quality)
            print(f"{src} -> {dst}")
            count += 1
        except Exception as e:
            print(f"Failed: {src} ({e})")

    if count == 0:
        print("No .HEIC files found.")
    else:
        print(f"Converted {count} file(s) using {backend}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
