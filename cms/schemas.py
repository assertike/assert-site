"""Content schemas.

Every editable document (site settings, each page, each collection item) is
described by a list of fields. The admin renders forms from these schemas and
``coerce`` cleans submitted data against them, so the JSON on disk always has
the expected shape.

Field types: text, textarea, markdown, url, email, number, bool, date, select,
icon, image, tags, list, group (nested dict) and repeater (list of dicts).
"""
from __future__ import annotations

import re
from typing import Any

ICONS = ["ai", "vision", "iot", "shield", "code", "consulting", "city", "factory",
         "building", "briefcase", "coffee", "scale", "chart", "gov", "radar", "chip",
         "cloud", "layers", "target", "spark"]


def F(key, label, type="text", **kw) -> dict:
    return {"key": key, "label": label, "type": type, **kw}


def group(key, label, fields, **kw):
    return F(key, label, "group", fields=fields, **kw)


def repeater(key, label, fields, **kw):
    return F(key, label, "repeater", fields=fields, **kw)


SEO = group("seo", "Search engine & social sharing", [
    F("title", "SEO title", help="Shown in search results and browser tabs. Aim for 50–60 characters.", max=70),
    F("description", "Meta description", "textarea", rows=3,
      help="Shown under the title in search results. Aim for 120–160 characters.", max=170),
    F("og_image", "Social sharing image", "image", help="Used by LinkedIn, X, Facebook etc. Defaults to the page image."),
    F("noindex", "Hide from search engines (noindex)", "bool"),
], collapsed=True)

CTA = group("cta", "Call to action band", [
    F("eyebrow", "Eyebrow"), F("title", "Title"), F("text", "Text", "textarea"),
    F("button_label", "Button label"), F("button_url", "Button link", "url"),
])

HERO = group("hero", "Page header", [
    F("eyebrow", "Eyebrow"), F("title", "Title (H1)", required=True),
    F("text", "Intro text", "textarea"), F("image", "Header image", "image"),
])

SECTION = [F("eyebrow", "Eyebrow"), F("title", "Title"), F("text", "Text", "textarea")]

ARTICLE_PAGE = [
    SEO,
    group("hero", "Page header", [F("title", "Title (H1)", required=True), F("text", "Intro", "textarea")]),
    F("updated", "Last updated", "date"),
    F("body", "Body", "markdown", rows=22),
]

PAGES: dict[str, dict] = {
    "home": {"label": "Home", "path": "/", "fields": [
        SEO,
        group("hero", "Hero", [
            F("eyebrow", "Eyebrow"),
            F("title", "Headline (H1)", required=True),
            F("highlight", "Highlighted words", help="Part of the headline to emphasise; must appear in the headline."),
            F("text", "Intro text", "textarea"),
            F("image", "Background image", "image"),
            F("primary_label", "Primary button label"), F("primary_url", "Primary button link", "url"),
            F("secondary_label", "Secondary button label"), F("secondary_url", "Secondary button link", "url"),
            F("detections", "Vision overlay labels", "list", help="Short labels drawn on the hero's detection boxes (decorative)."),
        ]),
        repeater("stats", "Key figures", [F("value", "Value"), F("label", "Label")]),
        group("services_section", "Services section", SECTION),
        group("loop", "Sense → Understand → Act", SECTION + [
            repeater("steps", "Steps", [F("title", "Title"), F("text", "Text", "textarea"), F("icon", "Icon", "icon")]),
        ]),
        group("industries_section", "Industries section", SECTION),
        group("products_section", "Products section", SECTION),
        group("stack", "Technology section", SECTION + [F("items", "Technologies", "tags")]),
        group("insights_section", "Insights section", [F("eyebrow", "Eyebrow"), F("title", "Title")]),
        CTA,
    ]},
    "company": {"label": "Company", "path": "/company/", "fields": [
        SEO, HERO,
        group("story", "Our story", [F("eyebrow", "Eyebrow"), F("title", "Title"),
                                     F("body", "Text", "markdown"), F("image", "Image", "image")]),
        repeater("facts", "Key facts", [F("value", "Value"), F("label", "Label")]),
        group("mission", "Mission & vision", [F("mission", "Mission", "textarea"), F("vision", "Vision", "textarea"),
                                               F("motto", "Motto")]),
        group("process", "How we work", SECTION + [
            repeater("steps", "Steps", [F("title", "Title"), F("text", "Text", "textarea")]),
        ]),
        group("principles", "Principles", SECTION + [
            repeater("items", "Principles", [F("title", "Title"), F("text", "Text", "textarea"), F("icon", "Icon", "icon")]),
        ]),
        CTA,
    ]},
    "services": {"label": "Services", "path": "/services/", "fields": [
        SEO, HERO,
        group("why", "Why ASSERT", SECTION + [F("points", "Points", "list"), F("image", "Image", "image")]),
        CTA,
    ]},
    "products": {"label": "Products", "path": "/products/", "fields": [
        SEO, HERO,
        group("custom", "Custom products band", SECTION + [F("button_label", "Button label"), F("button_url", "Button link", "url")]),
        CTA,
    ]},
    "industries": {"label": "Industries", "path": "/industries/", "fields": [
        SEO, HERO,
        group("principle", "Principle", [F("title", "Title"), F("text", "Text", "textarea")]),
        CTA,
    ]},
    "projects": {"label": "Projects", "path": "/projects/", "fields": [
        SEO, HERO,
        group("empty", "When no case studies are published", [F("title", "Title"), F("text", "Text", "textarea")]),
        group("rnd", "R&D highlights", SECTION + [
            repeater("areas", "Research areas", [F("title", "Title"), F("text", "Text", "textarea"), F("icon", "Icon", "icon")]),
        ]),
        CTA,
    ]},
    "insights": {"label": "Insights & News", "path": "/insights/", "fields": [
        SEO, HERO,
        group("empty", "When no posts are published", [F("title", "Title"), F("text", "Text", "textarea")]),
    ]},
    "contact": {"label": "Contact", "path": "/contact/", "fields": [
        SEO, HERO,
        group("form", "Contact form", [
            F("title", "Form title"), F("intro", "Form intro", "textarea"),
            F("topics", "Topic options", "list"),
            F("success", "Success message", "textarea"),
            F("privacy_note", "Privacy note under the form", "textarea"),
        ]),
        group("tips", "What to include", [F("title", "Title"), F("items", "Items", "list")]),
    ]},
    "accessibility": {"label": "Accessibility statement", "path": "/accessibility/", "fields": ARTICLE_PAGE},
    "privacy": {"label": "Privacy policy", "path": "/privacy-policy/", "fields": ARTICLE_PAGE},
    "cookies": {"label": "Cookie policy", "path": "/cookie-policy/", "fields": ARTICLE_PAGE},
    "terms": {"label": "Terms & conditions", "path": "/terms/", "fields": ARTICLE_PAGE},
}

BASE_ITEM = [
    F("title", "Title", required=True),
    F("slug", "URL slug", help="Lower-case words separated by hyphens. Leave empty to generate from the title."),
    F("published", "Published", "bool", default=True),
    F("order", "Sort order", "number", default=0),
]

COLLECTIONS: dict[str, dict] = {
    "services": {"label": "Services", "singular": "Service", "path": "/services/", "fields": BASE_ITEM + [
        F("icon", "Icon", "icon"),
        F("summary", "Summary", "textarea", help="One or two sentences used on cards and listings."),
        F("image", "Image", "image"),
        F("intro", "Page intro", "textarea"),
        F("body", "Body", "markdown"),
        F("capabilities", "Capabilities", "list"),
        repeater("outcomes", "Outcomes", [F("title", "Title"), F("text", "Text", "textarea")]),
        F("technologies", "Technologies", "tags"),
        SEO,
    ]},
    "products": {"label": "Products", "singular": "Product", "path": "/products/", "fields": BASE_ITEM + [
        F("category", "Category"),
        F("status", "Status", "select", options=["", "Available", "In development", "Concept"]),
        F("tagline", "Tagline"),
        F("summary", "Summary", "textarea"),
        F("image", "Image", "image"),
        F("body", "Body", "markdown"),
        repeater("features", "Features", [F("title", "Title"), F("text", "Text", "textarea")]),
        F("tags", "Tags", "tags"),
        F("website", "Product website", "url"),
        SEO,
    ]},
    "industries": {"label": "Industries", "singular": "Industry", "path": "/industries/", "fields": BASE_ITEM + [
        F("icon", "Icon", "icon"),
        F("summary", "Summary", "textarea"),
        F("image", "Image", "image"),
        F("body", "Body", "markdown"),
        repeater("use_cases", "Use cases", [F("title", "Title"), F("text", "Text", "textarea")]),
        F("services", "Related services (slugs)", "tags"),
        SEO,
    ]},
    "projects": {"label": "Case studies", "singular": "Case study", "path": "/projects/", "fields": BASE_ITEM + [
        F("client", "Client"), F("sector", "Sector"), F("date", "Date", "date"),
        F("summary", "Summary", "textarea"),
        F("image", "Image", "image"),
        F("challenge", "Challenge", "markdown"),
        F("solution", "Solution", "markdown"),
        repeater("results", "Results", [F("value", "Value"), F("label", "Label")]),
        F("tags", "Tags", "tags"),
        SEO,
    ]},
    "insights": {"label": "Insights & News", "singular": "Post", "path": "/insights/", "fields": BASE_ITEM + [
        F("date", "Publish date", "date"),
        F("author", "Author"),
        F("category", "Category"),
        F("excerpt", "Excerpt", "textarea"),
        F("image", "Image", "image"),
        F("body", "Body", "markdown", rows=24),
        F("tags", "Tags", "tags"),
        SEO,
    ]},
}

SITE = [
    group("brand", "Brand", [
        F("name", "Company name", required=True), F("legal_name", "Legal name"),
        F("tagline", "Tagline"), F("description", "Short description", "textarea"),
        F("founded", "Founding year"),
    ]),
    group("contact", "Contact details", [
        F("email", "Email", "email"), F("phone", "Phone"),
        F("street", "Street address"), F("locality", "City / area"), F("region", "Region"),
        F("postal_code", "Postal code"), F("country", "Country code", help="ISO code, e.g. GR"),
        F("hours", "Opening hours (display)"), F("hours_spec", "Opening hours (schema.org)", help="e.g. Mo-Fr 08:00-16:00"),
        F("map_url", "Map link", "url"), F("linkedin", "LinkedIn URL", "url"),
        F("notify_email", "Send form submissions to", "email", help="Stored for reference; the inbox is always in the admin."),
    ]),
    group("seo", "SEO defaults", [
        F("base_url", "Public site URL", "url", help="Used for canonical URLs, the sitemap and structured data."),
        F("title_suffix", "Title suffix", help="Appended to page titles, e.g. “ | ASSERT”."),
        F("description", "Default meta description", "textarea"),
        F("og_image", "Default social image", "image"),
        F("twitter", "X / Twitter handle"),
        F("google_verification", "Google Search Console verification code"),
        F("bing_verification", "Bing Webmaster verification code"),
    ]),
    repeater("navigation", "Main navigation", [
        F("label", "Label"), F("url", "Link", "url"),
        F("submenu", "Dropdown", "select", options=["", "services", "industries", "products"],
          help="Automatically list a collection under this item."),
    ]),
    group("footer", "Footer", [
        F("text", "Footer text", "textarea"),
        repeater("columns", "Link columns", [
            F("title", "Column title"),
            repeater("links", "Links", [F("label", "Label"), F("url", "Link", "url")]),
        ]),
        repeater("legal", "Legal links", [F("label", "Label"), F("url", "Link", "url")]),
    ]),
]


# -- coercion -----------------------------------------------------------------

def _clean_text(value: Any) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value if value is not None else "")).strip()


def coerce(fields: list[dict], data: Any) -> dict:
    data = data if isinstance(data, dict) else {}
    out: dict[str, Any] = {}
    for f in fields:
        out[f["key"]] = coerce_value(f, data.get(f["key"], f.get("default")))
    return out


def coerce_value(f: dict, value: Any) -> Any:
    t = f["type"]
    if t == "group":
        return coerce(f["fields"], value)
    if t == "repeater":
        return [coerce(f["fields"], v) for v in (value or []) if isinstance(v, dict)]
    if t in ("list", "tags"):
        if isinstance(value, str):
            value = value.split(",") if t == "tags" else value.splitlines()
        return [s for s in (_clean_text(v) for v in (value or [])) if s]
    if t == "bool":
        return bool(value) and value not in ("0", "false", "off")
    if t == "number":
        try:
            return int(value)
        except (TypeError, ValueError):
            return f.get("default", 0)
    if t == "select":
        v = _clean_text(value)
        return v if v in f.get("options", []) else (f.get("options") or [""])[0]
    if t == "icon":
        v = _clean_text(value)
        return v if v in ICONS or v == "" else ""
    if t == "url":
        v = _clean_text(value)
        if re.match(r"^\s*(javascript|data|vbscript):", v, re.I):
            return ""
        return v
    text = _clean_text(value)
    # Normalise line endings but keep paragraphs for textarea/markdown.
    return text.replace("\r\n", "\n")


def validate(fields: list[dict], data: dict, prefix: str = "") -> list[str]:
    """Return human-readable errors for required fields that are empty."""
    errors = []
    for f in fields:
        v = data.get(f["key"])
        label = f"{prefix}{f['label']}"
        if f.get("required") and not v:
            errors.append(f"“{label}” is required.")
        if f["type"] == "group":
            errors += validate(f["fields"], v or {}, f"{label} › ")
    return errors
