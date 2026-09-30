"""SEO helpers: meta tags, schema.org JSON-LD and the XML sitemap."""
from __future__ import annotations

import json
from datetime import date
from xml.sax.saxutils import escape

from markupsafe import Markup

from .schemas import COLLECTIONS, PAGES


def absolute(site: dict, path: str) -> str:
    base = (site.get("seo", {}).get("base_url") or "").rstrip("/")
    if path.startswith(("http://", "https://")):
        return path
    return f"{base}/{path.lstrip('/')}"


def page_title(site: dict, title: str | None, is_home: bool = False) -> str:
    suffix = site.get("seo", {}).get("title_suffix", "")
    title = (title or site.get("brand", {}).get("name", "")).strip()
    brand = site.get("brand", {}).get("name", "")
    if is_home or not suffix or (brand and brand.lower() in title.lower()):
        return title
    return f"{title} {suffix.strip()}"


def organization(site: dict) -> dict:
    brand, contact = site.get("brand", {}), site.get("contact", {})
    base = absolute(site, "/")
    org = {
        "@type": ["Organization", "ProfessionalService"],
        "@id": f"{base}#organization",
        "name": brand.get("name"),
        "legalName": brand.get("legal_name") or None,
        "url": base,
        "logo": absolute(site, "/static/img/logo-dark.png"),
        "image": absolute(site, "/static/img/logo-dark.png"),
        "description": brand.get("description"),
        "slogan": brand.get("tagline"),
        "foundingDate": brand.get("founded") or None,
        "email": contact.get("email"),
        "telephone": contact.get("phone"),
        "openingHours": contact.get("hours_spec") or None,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": contact.get("street"),
            "addressLocality": contact.get("locality"),
            "addressRegion": contact.get("region"),
            "postalCode": contact.get("postal_code") or None,
            "addressCountry": contact.get("country"),
        },
        "areaServed": ["GR", "EU"],
        "sameAs": [u for u in [contact.get("linkedin")] if u],
        "contactPoint": {
            "@type": "ContactPoint", "contactType": "sales",
            "email": contact.get("email"), "telephone": contact.get("phone"),
            "availableLanguage": ["English", "Greek"],
        },
    }
    return _prune(org)


def website(site: dict) -> dict:
    base = absolute(site, "/")
    return {"@type": "WebSite", "@id": f"{base}#website", "url": base,
            "name": site.get("brand", {}).get("name"),
            "publisher": {"@id": f"{base}#organization"}, "inLanguage": "en"}


def breadcrumbs(site: dict, trail: list[tuple[str, str]]) -> dict:
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": absolute(site, url)}
        for i, (name, url) in enumerate(trail)]}


def jsonld(graph: list[dict]) -> Markup:
    payload = {"@context": "https://schema.org", "@graph": [g for g in graph if g]}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Prevent "</script>" breaking out of the tag.
    return Markup(text.replace("</", "<\\/"))


def _prune(obj):
    if isinstance(obj, dict):
        cleaned = {k: _prune(v) for k, v in obj.items()}
        return {k: v for k, v in cleaned.items() if v not in (None, "", [], {})}
    if isinstance(obj, list):
        return [_prune(v) for v in obj if v not in (None, "", [], {})]
    return obj


def sitemap(store, site: dict) -> str:
    today = date.today().isoformat()
    urls: list[tuple[str, str, str]] = []
    for name, spec in PAGES.items():
        page = store.page(name) or {}
        if page.get("seo", {}).get("noindex"):
            continue
        lastmod = page.get("updated") or today
        urls.append((spec["path"], lastmod, "1.0" if name == "home" else "0.8"))
    for cname, spec in COLLECTIONS.items():
        for item in store.collection(cname, published_only=True):
            if item.get("seo", {}).get("noindex"):
                continue
            urls.append((f"{spec['path']}{item['slug']}/", item.get("date") or today, "0.7"))
    rows = "".join(
        f"<url><loc>{escape(absolute(site, p))}</loc><lastmod>{escape(m)}</lastmod>"
        f"<priority>{pr}</priority></url>" for p, m, pr in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>\n')
