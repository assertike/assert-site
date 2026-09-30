"""Media library: image uploads are resized into responsive WebP variants.

Each record in ``data/media.json`` looks like::

    {"id": "smart-city", "alt": "...", "width": 1600, "height": 1067,
     "variants": {"480": "uploads/smart-city-480.webp", ...},
     "original": "uploads/smart-city.jpg", "created": "..."}

Content fields store only the media ``id``; alt text is managed centrally in
the library so it is written once and reused everywhere the image appears.
"""
from __future__ import annotations

import time
from pathlib import Path

from PIL import Image, ImageOps

from .store import Store, slugify

WIDTHS = (480, 960, 1600)
ALLOWED = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def process_image(src: Path | object, upload_dir: Path, base_name: str, store: Store,
                  alt: str = "", credit: str = "") -> dict:
    """Create WebP variants of ``src`` (a path or file object) and index them."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    existing = {m["id"] for m in store.read("media.json", [])}
    media_id = slugify(base_name)[:60]
    n = 2
    while media_id in existing:
        media_id = f"{slugify(base_name)[:56]}-{n}"
        n += 1

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if has_alpha else "RGB")
        width, height = im.size
        variants: dict[str, str] = {}
        for target in sorted({min(w, width) for w in WIDTHS}):
            resized = im if target == width else im.resize(
                (target, round(height * target / width)), Image.LANCZOS)
            name = f"{media_id}-{target}.webp"
            resized.save(upload_dir / name, "WEBP", quality=80, method=6)
            variants[str(target)] = f"uploads/{name}"
        largest = max(int(k) for k in variants)
        # A JPEG/PNG fallback for Open Graph scrapers that do not read WebP.
        og = im.convert("RGB") if not has_alpha else im
        og_w = min(1200, width)
        og = og.resize((og_w, round(height * og_w / width)), Image.LANCZOS)
        og_name = f"{media_id}-og.{'png' if has_alpha else 'jpg'}"
        og.save(upload_dir / og_name, quality=82, optimize=True)

    record = {
        "id": media_id,
        "alt": alt,
        "credit": credit,
        "width": largest,
        "height": round(height * largest / width),
        "variants": variants,
        "og": f"uploads/{og_name}",
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    store.append("media.json", record)
    return record


def delete_media(media_id: str, upload_dir: Path, store: Store) -> None:
    records = store.read("media.json", [])
    keep = []
    for rec in records:
        if rec["id"] == media_id:
            for rel in list(rec.get("variants", {}).values()) + [rec.get("og", "")]:
                if rel:
                    (upload_dir.parent / rel).unlink(missing_ok=True)
        else:
            keep.append(rec)
    store.write("media.json", keep)


def media_index(store: Store) -> dict[str, dict]:
    return {m["id"]: m for m in store.read("media.json", [])}
