#!/usr/bin/env python3
"""Management commands for the ASSERT CMS.

    python manage.py create-admin [username]   create a user or reset a password
    python manage.py run [--port 8080]         development server
    python manage.py build [--out dist]        export the public site as static HTML
    python manage.py check                     render every page and report problems
"""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import sys
from pathlib import Path

from app import BASE_DIR, create_app
from cms.schemas import COLLECTIONS, PAGES
from cms.security import set_password


def all_urls(app) -> list[str]:
    store = app.store
    urls = [spec["path"] for spec in PAGES.values()]
    for spec_name, spec in COLLECTIONS.items():
        urls += [f"{spec['path']}{i['slug']}/" for i in store.collection(spec_name, published_only=True)]
    return urls


def cmd_create_admin(args):
    app = create_app()
    username = args.username or input("Username: ").strip()
    if not username:
        sys.exit("A username is required.")
    name = input(f"Display name [{username}]: ").strip() or username
    while True:
        pw = getpass.getpass("Password (min. 10 characters): ")
        if len(pw) < 10:
            print("Too short, try again.")
            continue
        if pw != getpass.getpass("Repeat password: "):
            print("Passwords do not match, try again.")
            continue
        break
    set_password(app.store, username, pw, name)
    print(f"✓ Admin user “{username}” saved. Sign in at /cms/")


def cmd_run(args):
    create_app().run(debug=True, port=args.port, host=args.host)


def cmd_check(_args):
    app = create_app()
    client = app.test_client()
    failures = 0
    for url in all_urls(app) + ["/sitemap.xml", "/robots.txt", "/feed.xml", "/site.webmanifest"]:
        resp = client.get(url)
        ok = resp.status_code == 200
        failures += not ok
        print(f"{'✓' if ok else '✗'} {resp.status_code} {url}")
    sys.exit(1 if failures else 0)


def cmd_build(args):
    app = create_app()
    app.config["STATIC_EXPORT"] = True
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    client = app.test_client()

    def write(url: str, target: Path):
        resp = client.get(url)
        if resp.status_code not in (200, 404):
            raise SystemExit(f"✗ {url} returned {resp.status_code}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(resp.data)
        print(f"  {url} → {target.relative_to(out)}")

    for url in all_urls(app):
        write(url, out / url.strip("/") / "index.html" if url != "/" else out / "index.html")
    for url in ("/sitemap.xml", "/robots.txt", "/feed.xml", "/site.webmanifest"):
        write(url, out / url.lstrip("/"))
    write("/__not-found__/", out / "404.html")
    shutil.copytree(BASE_DIR / "static", out / "static")
    print(f"✓ Static site written to {out}\n  Note: the contact form needs the Python app; in the static build it shows email/phone instead.")


def main():
    parser = argparse.ArgumentParser(description="ASSERT CMS management")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin"); p.add_argument("username", nargs="?"); p.set_defaults(fn=cmd_create_admin)
    p = sub.add_parser("run"); p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080))); p.add_argument("--host", default="127.0.0.1"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("build"); p.add_argument("--out", default=str(BASE_DIR / "dist")); p.set_defaults(fn=cmd_build)
    p = sub.add_parser("check"); p.set_defaults(fn=cmd_check)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
