"""CMS admin panel (mounted at /cms/)."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)

from .media import ALLOWED, delete_media, media_index, process_image
from .schemas import COLLECTIONS, ICONS, PAGES, SITE, coerce, validate
from .security import (check_csrf, login_required, rate_limited, set_password,
                       verify_user)
from .store import slugify

URL_PREFIX = "/cms"

bp = Blueprint("admin", __name__, url_prefix=URL_PREFIX, template_folder="../templates/admin")


def store():
    return current_app.store


@bp.before_request
def _csrf_guard():
    if request.method == "POST":
        check_csrf()


@bp.app_context_processor
def _admin_ctx():
    return {"ICONS": ICONS, "PAGES": PAGES, "COLLECTIONS": COLLECTIONS,
            "unread": sum(1 for m in store().read("messages.json", []) if not m.get("read"))
            if session.get("user") else 0}


# -- auth -----------------------------------------------------------------------

@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        ip = request.remote_addr or ""
        if rate_limited(f"login:{ip}", 10, 900):
            error = "Too many attempts. Please wait 15 minutes."
        else:
            user = verify_user(store(), request.form.get("username", ""), request.form.get("password", ""))
            if user:
                session.clear()
                session.permanent = True
                session["user"] = {"username": user["username"], "name": user.get("name", user["username"])}
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith(URL_PREFIX + "/") else url_for("admin.dashboard"))
            error = "Incorrect username or password."
    has_users = bool(store().read("users.json", []))
    return render_template("admin/login.html", error=error, has_users=has_users), (401 if error else 200)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        current = request.form.get("current", "")
        new = request.form.get("new", "")
        if not verify_user(store(), g.user["username"], current):
            flash("Your current password is incorrect.", "error")
        elif len(new) < 10:
            flash("Use at least 10 characters for the new password.", "error")
        elif new != request.form.get("confirm"):
            flash("The new passwords do not match.", "error")
        else:
            set_password(store(), g.user["username"], new)
            flash("Password updated.", "success")
            return redirect(url_for("admin.account"))
    return render_template("admin/account.html")


# -- dashboard ------------------------------------------------------------------

def seo_audit() -> list[dict]:
    """Flag common SEO / accessibility gaps across all content."""
    issues = []
    for name, spec in PAGES.items():
        page = store().page(name) or {}
        s = page.get("seo", {})
        edit = url_for("admin.edit_page", name=name)
        if not s.get("description"):
            issues.append({"where": spec["label"], "what": "Missing meta description", "url": edit})
        elif len(s["description"]) > 165:
            issues.append({"where": spec["label"], "what": "Meta description longer than 165 characters", "url": edit})
        if s.get("title") and len(s["title"]) > 65:
            issues.append({"where": spec["label"], "what": "SEO title longer than 65 characters", "url": edit})
    for cname, spec in COLLECTIONS.items():
        for item in store().collection(cname, published_only=True):
            edit = url_for("admin.edit_item", collection=cname, slug=item["slug"])
            s = item.get("seo", {})
            if not (s.get("description") or item.get("summary") or item.get("excerpt")):
                issues.append({"where": f"{spec['singular']}: {item['title']}", "what": "No description for search results", "url": edit})
            if not item.get("image"):
                issues.append({"where": f"{spec['singular']}: {item['title']}", "what": "No image (used for cards & social sharing)", "url": edit})
    for m in store().read("media.json", []):
        if not m.get("alt") and not m.get("decorative"):
            issues.append({"where": f"Media: {m['id']}", "what": "Missing alternative text",
                           "url": url_for("admin.media", q=m["id"])})
    return issues


@bp.route("/")
@login_required
def dashboard():
    counts = {name: len(store().collection(name)) for name in COLLECTIONS}
    messages = sorted(store().read("messages.json", []), key=lambda m: m["created"], reverse=True)[:5]
    return render_template("admin/dashboard.html", counts=counts, messages=messages,
                           issues=seo_audit(), media_count=len(store().read("media.json", [])))


# -- editor helpers -----------------------------------------------------------------

def _payload() -> dict:
    try:
        data = json.loads(request.form.get("payload", "{}"))
    except json.JSONDecodeError:
        abort(400, "The form data could not be read. Please try again.")
    if not isinstance(data, dict):
        abort(400)
    return data


# -- site settings --------------------------------------------------------------

@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    data = store().site()
    errors = []
    if request.method == "POST":
        data = coerce(SITE, _payload())
        errors = validate(SITE, data)
        if not errors:
            store().save_site(data)
            flash("Site settings saved.", "success")
            return redirect(url_for("admin.settings"))
    return render_template("admin/editor.html", title="Site settings", fields=SITE, data=data,
                           errors=errors, view_url="/")


# -- pages ----------------------------------------------------------------------

@bp.route("/pages/")
@login_required
def pages():
    return render_template("admin/pages.html")


@bp.route("/pages/<name>", methods=["GET", "POST"])
@login_required
def edit_page(name):
    spec = PAGES.get(name) or abort(404)
    data = store().page(name) or {}
    errors = []
    if request.method == "POST":
        data = coerce(spec["fields"], _payload())
        errors = validate(spec["fields"], data)
        if not errors:
            store().save_page(name, data)
            flash(f"“{spec['label']}” saved.", "success")
            return redirect(url_for("admin.edit_page", name=name))
    return render_template("admin/editor.html", title=f"Page: {spec['label']}", fields=spec["fields"],
                           data=data, errors=errors, view_url=spec["path"], back=url_for("admin.pages"))


# -- collections ------------------------------------------------------------------

@bp.route("/c/<collection>/")
@login_required
def collection(collection):
    spec = COLLECTIONS.get(collection) or abort(404)
    return render_template("admin/collection.html", name=collection, spec=spec,
                           items=store().collection(collection))


@bp.route("/c/<collection>/new", methods=["GET", "POST"])
@bp.route("/c/<collection>/<slug>/edit", methods=["GET", "POST"])
@login_required
def edit_item(collection, slug=None):
    spec = COLLECTIONS.get(collection) or abort(404)
    fields = spec["fields"]
    if slug:
        data = store().item(collection, slug) or abort(404)
    else:
        data = coerce(fields, {})
        dup = request.args.get("duplicate")
        if dup and (src := store().item(collection, dup)):
            data = {**src, "title": src["title"] + " (copy)", "slug": "", "published": False}
    errors = []
    if request.method == "POST":
        data = coerce(fields, _payload())
        data["slug"] = slugify(data.get("slug") or data.get("title", ""))
        errors = validate(fields, data)
        taken = {i["slug"] for i in store().collection(collection) if i["slug"] != slug}
        if data["slug"] in taken:
            errors.append(f"Another {spec['singular'].lower()} already uses the URL slug “{data['slug']}”.")
        if not errors:
            store().save_item(collection, data, original_slug=slug)
            flash(f"{spec['singular']} “{data['title']}” saved.", "success")
            return redirect(url_for("admin.edit_item", collection=collection, slug=data["slug"]))
    view_url = f"{spec['path']}{data['slug']}/" if slug and data.get("published") else None
    return render_template("admin/editor.html",
                           title=(f"Edit {spec['singular'].lower()}" if slug else f"New {spec['singular'].lower()}"),
                           fields=fields, data=data, errors=errors, view_url=view_url,
                           back=url_for("admin.collection", collection=collection),
                           delete_url=url_for("admin.delete_item", collection=collection, slug=slug) if slug else None)


@bp.route("/c/<collection>/<slug>/delete", methods=["POST"])
@login_required
def delete_item(collection, slug):
    spec = COLLECTIONS.get(collection) or abort(404)
    store().delete_item(collection, slug)
    flash(f"{spec['singular']} deleted. A backup was kept in data/.backups.", "success")
    return redirect(url_for("admin.collection", collection=collection))


@bp.route("/c/<collection>/reorder", methods=["POST"])
@login_required
def reorder(collection):
    COLLECTIONS.get(collection) or abort(404)
    order = request.form.getlist("slug")
    items = store().read(f"collections/{collection}.json", [])
    pos = {s: i for i, s in enumerate(order)}
    for it in items:
        if it["slug"] in pos:
            it["order"] = pos[it["slug"]] + 1
    store().write(f"collections/{collection}.json", items)
    flash("Order saved.", "success")
    return redirect(url_for("admin.collection", collection=collection))


# -- media ----------------------------------------------------------------------

def _usage() -> dict[str, list[str]]:
    """Which documents reference each media id."""
    usage: dict[str, list[str]] = {}

    def walk(obj, where):
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v, where)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, where)
        elif isinstance(obj, str) and obj in ids:
            usage.setdefault(obj, []).append(where)

    ids = set(media_index(store()))
    walk(store().site(), "Site settings")
    for name, spec in PAGES.items():
        walk(store().page(name) or {}, spec["label"])
    for cname, spec in COLLECTIONS.items():
        for item in store().collection(cname):
            walk(item, f"{spec['singular']}: {item['title']}")
    return usage


@bp.route("/media/", methods=["GET", "POST"])
@login_required
def media():
    if request.method == "POST":
        files = request.files.getlist("files")
        alt = request.form.get("alt", "").strip()
        done = 0
        for fh in files:
            ext = Path(fh.filename or "").suffix.lower()
            if ext not in ALLOWED:
                flash(f"“{fh.filename}” is not a supported image type ({', '.join(sorted(ALLOWED))}).", "error")
                continue
            try:
                process_image(fh.stream, current_app.config["UPLOAD_DIR"], Path(fh.filename).stem, store(), alt=alt)
                done += 1
            except Exception as exc:  # noqa: BLE001 — surface any image error to the editor
                flash(f"Could not process “{fh.filename}”: {exc}", "error")
        if done:
            flash(f"Uploaded {done} image{'s' if done != 1 else ''}. Remember to add alternative text.", "success")
        return redirect(url_for("admin.media"))
    q = request.args.get("q", "").lower()
    items = sorted(store().read("media.json", []), key=lambda m: m["created"], reverse=True)
    if q:
        items = [m for m in items if q in m["id"] or q in m.get("alt", "").lower()]
    for m in items:
        widths = sorted(m["variants"], key=int)
        m["thumb"] = url_for("static", filename=m["variants"][widths[0]])
        m["full"] = url_for("static", filename=m["variants"][widths[-1]])
    return render_template("admin/media.html", items=items, usage=_usage(), q=q)


@bp.route("/media/<mid>", methods=["POST"])
@login_required
def media_update(mid):
    records = store().read("media.json", [])
    for rec in records:
        if rec["id"] == mid:
            rec["alt"] = request.form.get("alt", "").strip()[:300]
            rec["credit"] = request.form.get("credit", "").strip()[:200]
            rec["decorative"] = bool(request.form.get("decorative"))
    store().write("media.json", records)
    flash("Image details saved.", "success")
    return redirect(url_for("admin.media", q=request.args.get("q", "")) + f"#m-{mid}")


@bp.route("/media/<mid>/delete", methods=["POST"])
@login_required
def media_delete(mid):
    if _usage().get(mid):
        flash("This image is still used on the site. Replace it everywhere before deleting.", "error")
    else:
        delete_media(mid, current_app.config["UPLOAD_DIR"], store())
        flash("Image deleted.", "success")
    return redirect(url_for("admin.media"))


@bp.route("/media.json")
@login_required
def media_json():
    items = sorted(store().read("media.json", []), key=lambda m: m["created"], reverse=True)
    return jsonify([{"id": m["id"], "alt": m.get("alt", ""),
                     "thumb": url_for("static", filename=m["variants"][min(m["variants"], key=int)])}
                    for m in items])


@bp.route("/preview", methods=["POST"])
@login_required
def preview():
    text = (request.get_json(silent=True) or {}).get("text", "")
    return jsonify({"html": str(current_app.render_md(text[:100_000], shift=1))})


# -- messages -------------------------------------------------------------------

@bp.route("/messages/")
@login_required
def messages():
    items = sorted(store().read("messages.json", []), key=lambda m: m["created"], reverse=True)
    return render_template("admin/messages.html", items=items)


@bp.route("/messages/<mid>", methods=["GET", "POST"])
@login_required
def message(mid):
    records = store().read("messages.json", [])
    msg = next((m for m in records if m["id"] == mid), None) or abort(404)
    if request.method == "POST":
        if request.form.get("action") == "delete":
            store().write("messages.json", [m for m in records if m["id"] != mid])
            flash("Message deleted.", "success")
            return redirect(url_for("admin.messages"))
        msg["read"] = not msg.get("read")
        store().write("messages.json", records)
        return redirect(url_for("admin.message", mid=mid))
    if not msg.get("read"):
        msg["read"] = True
        store().write("messages.json", records)
    return render_template("admin/message.html", m=msg)


@bp.route("/messages.csv")
@login_required
def messages_csv():
    buf = io.StringIO()
    cols = ["created", "name", "email", "company", "phone", "topic", "message"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for m in store().read("messages.json", []):
        # Neutralise spreadsheet formula injection.
        w.writerow({k: ("'" + v if isinstance(v, str) and v and v[0] in "=+-@" else v) for k, v in m.items()})
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=messages.csv"})
