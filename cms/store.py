"""JSON-file database.

Layout under ``data/``::

    site.json                 global settings (brand, contact, navigation, SEO defaults)
    pages/<page>.json         one document per page
    collections/<name>.json   ordered list of items (services, products, ...)
    media.json                media library index
    messages.json             contact-form submissions
    users.json                admin users (hashed passwords)

Writes are atomic (temp file + rename) and the previous version of every file is
kept in ``data/.backups`` so an accidental save can be rolled back by hand.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

_lock = threading.RLock()
MAX_BACKUPS = 20


class Store:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)
        self.backups = self.root / ".backups"
        self._cache: dict[Path, tuple[float, Any]] = {}

    # -- low level ----------------------------------------------------------
    def _path(self, rel: str) -> Path:
        path = (self.root / rel).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"Path escapes data directory: {rel}")
        return path

    def read(self, rel: str, default: Any = None) -> Any:
        path = self._path(rel)
        with _lock:
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                return default
            cached = self._cache.get(path)
            if cached and cached[0] == mtime:
                return json.loads(json.dumps(cached[1]))  # defensive copy
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            self._cache[path] = (mtime, data)
            return json.loads(json.dumps(data))

    def write(self, rel: str, data: Any) -> None:
        path = self._path(rel)
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                self._backup(path, rel)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, path)
            self._cache.pop(path, None)

    def _backup(self, path: Path, rel: str) -> None:
        target_dir = self.backups / Path(rel).parent
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() // 1000 % 1_000_000:06d}"
        shutil.copy2(path, target_dir / f"{path.stem}.{stamp}.json")
        old = sorted(target_dir.glob(f"{path.stem}.*.json"))
        for stale in old[:-MAX_BACKUPS]:
            stale.unlink(missing_ok=True)

    # -- site & pages -------------------------------------------------------
    def site(self) -> dict:
        return self.read("site.json", {})

    def save_site(self, data: dict) -> None:
        self.write("site.json", data)

    def page(self, name: str) -> dict | None:
        return self.read(f"pages/{name}.json")

    def save_page(self, name: str, data: dict) -> None:
        self.write(f"pages/{name}.json", data)

    # -- collections --------------------------------------------------------
    def collection(self, name: str, published_only: bool = False) -> list[dict]:
        items = self.read(f"collections/{name}.json", [])
        items.sort(key=lambda i: (i.get("order", 0), i.get("title", "")))
        if published_only:
            items = [i for i in items if i.get("published", True)]
        return items

    def item(self, name: str, slug: str, published_only: bool = False) -> dict | None:
        for it in self.collection(name, published_only):
            if it.get("slug") == slug:
                return it
        return None

    def save_item(self, name: str, item: dict, original_slug: str | None = None) -> None:
        with _lock:
            items = self.read(f"collections/{name}.json", [])
            key = original_slug or item["slug"]
            for idx, existing in enumerate(items):
                if existing.get("slug") == key:
                    items[idx] = item
                    break
            else:
                items.append(item)
            self.write(f"collections/{name}.json", items)

    def delete_item(self, name: str, slug: str) -> None:
        with _lock:
            items = [i for i in self.read(f"collections/{name}.json", []) if i.get("slug") != slug]
            self.write(f"collections/{name}.json", items)

    # -- generic lists (media, messages) -----------------------------------
    def append(self, rel: str, record: dict) -> None:
        with _lock:
            records = self.read(rel, [])
            records.append(record)
            self.write(rel, records)


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s_]+", "-", value).strip("-") or "item"
