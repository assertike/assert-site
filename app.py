"""ASSERT website — public site + CMS admin.

Run locally:   python app.py            (http://127.0.0.1:8080, CMS at /cms/; override with PORT)
Production:    docker compose up -d    (see README.md)
"""
from __future__ import annotations

import os
import re
import secrets
import time
import uuid
from datetime import date, datetime
from email.utils import format_datetime
from pathlib import Path

import bleach
import markdown as md_lib
from flask import (Flask, Response, abort, g, redirect, render_template, request,
                   url_for)
from markupsafe import Markup, escape

from cms import seo
from cms.admin import URL_PREFIX as CMS_PREFIX, bp as admin_bp
from cms.media import media_index
from cms.schemas import COLLECTIONS
from cms.security import check_form_token, csrf_token, form_token, rate_limited
from cms.store import Store

BASE_DIR = Path(__file__).resolve().parent

ALLOWED_TAGS = ["p", "br", "h2", "h3", "h4", "ul", "ol", "li", "a", "strong", "em", "b", "i",
                "blockquote", "code", "pre", "hr", "table", "thead", "tbody", "tr", "th", "td",
                "abbr", "sup", "sub", "dl", "dt", "dd"]
ALLOWED_ATTRS = {"a": ["href", "title", "rel", "target"], "abbr": ["title"], "th": ["scope"],
                 "h2": ["id"], "h3": ["id"], "h4": ["id"]}


def _secret_key(data_dir: Path) -> str:
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    key_file = data_dir / ".secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
        key_file.chmod(0o600)
    return key_file.read_text().strip()


def create_app(data_dir: str | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    data_path = Path(data_dir or os.environ.get("CMS_DATA_DIR", BASE_DIR / "data"))
    app.config.update(
        DATA_DIR=data_path,
        UPLOAD_DIR=BASE_DIR / "static" / "uploads",
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
        SEND_FILE_MAX_AGE_DEFAULT=60 * 60 * 24 * 30,
        STATIC_EXPORT=False,
    )
    app.secret_key = _secret_key(data_path)
    if os.environ.get("TRUST_PROXY", "0") == "1":
        # Behind exactly one reverse proxy (Caddy/Nginx): trust its X-Forwarded-* headers.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.store = Store(data_path)
    app.register_blueprint(admin_bp)
    _register_helpers(app)
    _register_routes(app)
    return app


# -----------------------------------------------------------------------------
# Template helpers
# -----------------------------------------------------------------------------

def _register_helpers(app: Flask) -> None:
    store: Store = app.store

    def media(mid: str | None) -> dict | None:
        if not mid:
            return None
        if "media" not in g:
            g.media = media_index(store)
        return g.media.get(mid)

    def media_url(mid: str | None, width: int = 1600, og: bool = False) -> str:
        m = media(mid)
        if not m:
            return ""
        if og:
            return url_for("static", filename=m["og"])
        best = min(m["variants"], key=lambda w: abs(int(w) - width))
        return url_for("static", filename=m["variants"][best])

    def img(mid, sizes="100vw", cls="", eager=False, alt=None, decorative=False):
        m = media(mid)
        if not m:
            return Markup("")
        srcset = ", ".join(f"{url_for('static', filename=p)} {w}w"
                           for w, p in sorted(m["variants"].items(), key=lambda kv: int(kv[0])))
        text = "" if decorative else (alt if alt is not None else m.get("alt", ""))
        largest = max(m["variants"], key=int)
        attrs = {
            "src": url_for("static", filename=m["variants"][largest]),
            "srcset": srcset, "sizes": sizes, "alt": text,
            "width": m["width"], "height": m["height"],
            "loading": "eager" if eager else "lazy",
            "decoding": "async",
        }
        if eager:
            attrs["fetchpriority"] = "high"
        if cls:
            attrs["class"] = cls
        html = " ".join(f'{k}="{escape(v)}"' for k, v in attrs.items())
        return Markup(f"<img {html}>")

    def icon(name: str | None, cls: str = "icon") -> Markup:
        if not name:
            return Markup("")
        href = url_for("static", filename="img/icons.svg") + f"#i-{escape(name)}"
        return Markup(f'<svg class="{escape(cls)}" aria-hidden="true" focusable="false">'
                      f'<use href="{href}"></use></svg>')

    def render_md(text: str | None, shift: int = 0) -> Markup:
        if not text:
            return Markup("")
        html = md_lib.markdown(text, extensions=["extra", "sane_lists", "smarty", "toc"],
                               extension_configs={"toc": {"permalink": False}})
        if shift:  # demote headings so the page keeps a single H1
            for lvl in range(4, 0, -1):
                html = re.sub(rf"<(/?)h{lvl}\b", rf"<\1h{min(lvl + shift, 6)}", html)
        clean = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS,
                             protocols=["http", "https", "mailto", "tel"], strip=True)
        clean = re.sub(r'<a href="(https?://(?!assert\.gr)[^"]+)"',
                       r'<a href="\1" rel="noopener" target="_blank"', clean)
        return Markup(clean)

    def highlight(title: str, words: str | None) -> Markup:
        title_e = str(escape(title or ""))
        if words and words in (title or ""):
            w = str(escape(words))
            return Markup(title_e.replace(w, f'<span class="hl">{w}</span>', 1))
        return Markup(title_e)

    def fmt_date(value: str | None, fmt: str = "%d %B %Y") -> str:
        if not value:
            return ""
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").strftime(fmt).lstrip("0")
        except ValueError:
            return value

    def link(url: str | None) -> str:
        """Resolve CMS links: absolute URLs, mailto/tel and site paths."""
        return url or "#"

    def is_active(url: str) -> bool:
        path = request.path
        if url in ("/", ""):
            return path == "/"
        return path.startswith(url)

    app.render_md = render_md

    @app.context_processor
    def inject():
        site = store.site()
        dropdowns = {name: store.collection(name, published_only=True)
                     for name in ("services", "industries", "products")}
        return {
            "site": site, "dropdowns": dropdowns, "img": img, "icon": icon, "md": render_md,
            "media_url": media_url, "media": media, "highlight": highlight, "fmt_date": fmt_date,
            "link": link, "is_active": is_active, "abs_url": lambda p: seo.absolute(site, p),
            "page_title": lambda t, home=False: seo.page_title(site, t, home),
            "csrf_token": csrf_token, "year": date.today().year,
            "static_export": app.config["STATIC_EXPORT"],
            "asset_v": _asset_version(),
        }

    @app.template_filter("reading_time")
    def reading_time(text: str | None) -> int:
        return max(1, round(len((text or "").split()) / 220))


def _asset_version() -> str:
    css = BASE_DIR / "static" / "css" / "site.css"
    js = BASE_DIR / "static" / "js" / "site.js"
    stamp = max((p.stat().st_mtime for p in (css, js) if p.exists()), default=0)
    return str(int(stamp))


# -----------------------------------------------------------------------------
# Public routes
# -----------------------------------------------------------------------------

def _register_routes(app: Flask) -> None:
    store: Store = app.store

    def get_page(name: str) -> dict:
        page = store.page(name)
        if page is None:
            abort(404)
        return page

    def graph(*extra) -> list[dict]:
        site = store.site()
        return [seo.organization(site), seo.website(site), *extra]

    @app.after_request
    def headers(resp: Response):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "font-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'")
        if request.path == CMS_PREFIX or request.path.startswith(CMS_PREFIX + "/"):
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    @app.route("/")
    def home():
        page = get_page("home")
        return render_template(
            "home.html", page=page,
            services=store.collection("services", True),
            industries=store.collection("industries", True),
            products=store.collection("products", True),
            posts=_posts(store)[:3],
            jsonld=seo.jsonld(graph()))

    @app.route("/company/")
    def company():
        site = store.site()
        page = get_page("company")
        about = {"@type": "AboutPage", "url": seo.absolute(site, "/company/"), "name": page["hero"]["title"],
                 "about": {"@id": seo.absolute(site, "/") + "#organization"}}
        return render_template("company.html", page=page, jsonld=seo.jsonld(graph(
            about, seo.breadcrumbs(site, [("Home", "/"), ("Company", "/company/")]))))

    def listing(name: str, template: str, **extra):
        site = store.site()
        page = get_page(name)
        spec = COLLECTIONS[name]
        items = store.collection(name, True)
        item_list = {"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": seo.absolute(site, f"{spec['path']}{it['slug']}/"),
             "name": it["title"]} for i, it in enumerate(items)]}
        crumbs = seo.breadcrumbs(site, [("Home", "/"), (spec["label"], spec["path"])])
        return render_template(template, page=page, items=items, name=name,
                               jsonld=seo.jsonld(graph(item_list, crumbs)), **extra)

    def detail(name: str, slug: str, template: str, schema_builder):
        site = store.site()
        item = store.item(name, slug, published_only=True)
        if not item:
            abort(404)
        spec = COLLECTIONS[name]
        others = [i for i in store.collection(name, True) if i["slug"] != slug]
        crumbs = seo.breadcrumbs(site, [("Home", "/"), (spec["label"], spec["path"]),
                                        (item["title"], f"{spec['path']}{slug}/")])
        entity = schema_builder(site, item, f"{spec['path']}{slug}/")
        return render_template(template, item=item, others=others, spec=spec, name=name,
                               jsonld=seo.jsonld(graph(*entity, crumbs)))

    def org_ref(site):
        return {"@id": seo.absolute(site, "/") + "#organization"}

    def image_abs(site, item):
        mid = item.get("image")
        m = media_index(store).get(mid) if mid else None
        return seo.absolute(site, "/static/" + m["og"]) if m else None

    def service_schema(site, item, path):
        ent = [{"@type": "Service", "name": item["title"], "description": item.get("summary"),
                "url": seo.absolute(site, path), "provider": org_ref(site), "image": image_abs(site, item),
                "areaServed": ["GR", "EU"], "serviceType": item["title"]}]
        return [seo._prune(e) for e in ent]

    def product_schema(site, item, path):
        return [seo._prune({"@type": "SoftwareApplication", "name": item["title"],
                            "description": item.get("summary"), "url": item.get("website") or seo.absolute(site, path),
                            "applicationCategory": "BusinessApplication", "operatingSystem": "Web",
                            "image": image_abs(site, item), "publisher": org_ref(site)})]

    def industry_schema(site, item, path):
        return [seo._prune({"@type": "WebPage", "name": item["title"], "description": item.get("summary"),
                            "url": seo.absolute(site, path), "image": image_abs(site, item),
                            "publisher": org_ref(site)})]

    def project_schema(site, item, path):
        return [seo._prune({"@type": "CreativeWork", "name": item["title"], "description": item.get("summary"),
                            "url": seo.absolute(site, path), "image": image_abs(site, item),
                            "creator": org_ref(site), "dateCreated": item.get("date")})]

    def post_schema(site, item, path):
        return [seo._prune({"@type": "BlogPosting", "headline": item["title"],
                            "description": item.get("excerpt"), "url": seo.absolute(site, path),
                            "mainEntityOfPage": seo.absolute(site, path), "image": image_abs(site, item),
                            "datePublished": item.get("date"), "dateModified": item.get("date"),
                            "author": {"@type": "Organization", "name": item.get("author") or site["brand"]["name"]},
                            "publisher": org_ref(site), "keywords": ", ".join(item.get("tags", []))})]

    @app.route("/services/")
    def services():
        return listing("services", "services.html")

    @app.route("/services/<slug>/")
    def service(slug):
        return detail("services", slug, "service.html", service_schema)

    @app.route("/products/")
    def products():
        return listing("products", "products.html")

    @app.route("/products/<slug>/")
    def product(slug):
        return detail("products", slug, "product.html", product_schema)

    @app.route("/industries/")
    def industries():
        return listing("industries", "industries.html")

    @app.route("/industries/<slug>/")
    def industry(slug):
        site = store.site()
        item = store.item("industries", slug, True)
        if not item:
            abort(404)
        related = [s for s in store.collection("services", True) if s["slug"] in item.get("services", [])]
        others = [i for i in store.collection("industries", True) if i["slug"] != slug]
        crumbs = seo.breadcrumbs(site, [("Home", "/"), ("Industries", "/industries/"),
                                        (item["title"], f"/industries/{slug}/")])
        return render_template("industry.html", item=item, related=related, others=others,
                               jsonld=seo.jsonld(graph(*industry_schema(site, item, f"/industries/{slug}/"), crumbs)))

    @app.route("/projects/")
    def projects():
        return listing("projects", "projects.html")

    @app.route("/projects/<slug>/")
    def project(slug):
        return detail("projects", slug, "project.html", project_schema)

    @app.route("/insights/")
    def insights():
        site = store.site()
        page = get_page("insights")
        posts = _posts(store)
        category = request.args.get("category")
        shown = [p for p in posts if not category or p.get("category") == category]
        categories = sorted({p.get("category") for p in posts if p.get("category")})
        crumbs = seo.breadcrumbs(site, [("Home", "/"), ("Insights", "/insights/")])
        blog = {"@type": "Blog", "name": page["hero"]["title"], "url": seo.absolute(site, "/insights/"),
                "publisher": org_ref(site)}
        return render_template("insights.html", page=page, items=shown, categories=categories,
                               category=category, jsonld=seo.jsonld(graph(blog, crumbs)))

    @app.route("/insights/<slug>/")
    def post(slug):
        return detail("insights", slug, "post.html", post_schema)

    @app.route("/contact/", methods=["GET", "POST"])
    def contact():
        site = store.site()
        page = get_page("contact")
        errors: dict[str, str] = {}
        values: dict[str, str] = {}
        if request.method == "POST":
            values = {k: (request.form.get(k) or "").strip()[:5000] for k in
                      ("name", "email", "company", "phone", "topic", "message")}
            ip = request.remote_addr or ""  # real client IP when TRUST_PROXY is set (ProxyFix)
            if request.form.get("website"):  # honeypot
                return redirect(url_for("contact", sent=1) + "#form-status", 303)
            if not check_form_token(request.form.get("token", "")):
                errors["form"] = "Your session expired. Please submit the form again."
            if rate_limited(f"contact:{ip}", 5, 3600):
                errors["form"] = "Too many messages from your connection. Please try again later or email us directly."
            if len(values["name"]) < 2:
                errors["name"] = "Please enter your name."
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", values["email"]):
                errors["email"] = "Please enter a valid email address, for example name@company.com."
            if len(values["message"]) < 10:
                errors["message"] = "Please tell us a little more (at least 10 characters)."
            if not request.form.get("consent"):
                errors["consent"] = "Please confirm that we may use your details to reply."
            if not errors:
                store.append("messages.json", {
                    "id": uuid.uuid4().hex[:12], "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "read": False, "ip": ip, **values})
                return redirect(url_for("contact", sent=1) + "#form-status", 303)
        crumbs = seo.breadcrumbs(site, [("Home", "/"), ("Contact", "/contact/")])
        contact_page = {"@type": "ContactPage", "url": seo.absolute(site, "/contact/"),
                        "about": org_ref(site)}
        status = 422 if errors else 200
        return render_template("contact.html", page=page, errors=errors, values=values,
                               sent=request.args.get("sent") == "1", token=form_token(),
                               jsonld=seo.jsonld(graph(contact_page, crumbs))), status

    for name, path in (("accessibility", "/accessibility/"), ("privacy", "/privacy-policy/"),
                       ("cookies", "/cookie-policy/"), ("terms", "/terms/")):
        def view(name=name, path=path):
            site = store.site()
            page = get_page(name)
            crumbs = seo.breadcrumbs(site, [("Home", "/"), (page["hero"]["title"], path)])
            return render_template("article_page.html", page=page, jsonld=seo.jsonld(graph(crumbs)))
        app.add_url_rule(path, name, view)

    @app.route("/sitemap.xml")
    def sitemap_xml():
        return Response(seo.sitemap(store, store.site()), mimetype="application/xml")

    @app.route("/healthz")
    def healthz():
        return Response("ok", mimetype="text/plain", headers={"Cache-Control": "no-store"})

    @app.route("/robots.txt")
    def robots():
        site = store.site()
        body = ("User-agent: *\nAllow: /\nDisallow: " + CMS_PREFIX + "/\n\n"
                f"Sitemap: {seo.absolute(site, '/sitemap.xml')}\n")
        return Response(body, mimetype="text/plain")

    @app.route("/feed.xml")
    def feed():
        site = store.site()
        posts = _posts(store)[:20]
        items = "".join(
            f"<item><title>{escape(p['title'])}</title>"
            f"<link>{escape(seo.absolute(site, '/insights/' + p['slug'] + '/'))}</link>"
            f"<guid>{escape(seo.absolute(site, '/insights/' + p['slug'] + '/'))}</guid>"
            f"<pubDate>{format_datetime(datetime.strptime(p['date'], '%Y-%m-%d')) if p.get('date') else ''}</pubDate>"
            f"<description>{escape(p.get('excerpt', ''))}</description></item>" for p in posts)
        body = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
                f"<title>{escape(site['brand']['name'])} — Insights</title>"
                f"<link>{escape(seo.absolute(site, '/insights/'))}</link>"
                f"<description>{escape(site['seo'].get('description', ''))}</description>"
                f"<language>en</language>{items}</channel></rss>")
        return Response(body, mimetype="application/rss+xml")

    @app.route("/site.webmanifest")
    def manifest():
        site = store.site()
        return {"name": site["brand"]["name"], "short_name": site["brand"]["name"],
                "icons": [{"src": url_for("static", filename="img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
                          {"src": url_for("static", filename="img/icon-512.png"), "sizes": "512x512", "type": "image/png"}],
                "theme_color": "#0A1020", "background_color": "#0A1020", "display": "standalone", "start_url": "/"}

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, title="Page not found",
                               text="The page you are looking for has moved or no longer exists."), 404

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("error.html", code=500, title="Something went wrong",
                               text="An unexpected error occurred. Please try again in a moment."), 500


def _posts(store: Store) -> list[dict]:
    today = date.today().isoformat()
    posts = [p for p in store.collection("insights", True) if (p.get("date") or "") <= today]
    return sorted(posts, key=lambda p: p.get("date") or "", reverse=True)


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 8080)))
