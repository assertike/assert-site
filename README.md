# ASSERT website + CMS

A corporate website for ASSERT with its own lightweight content management system,
written in Python (Flask). All content lives in JSON files, so there is no database server.

## Quick start

```bash
cd assert-cms
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py create-admin          # choose a username and password
python app.py                          # http://127.0.0.1:8080  ·  CMS: /cms/
```

The dev server uses port **8080** (macOS AirPlay Receiver occupies 5000). Change it with `PORT=9000 python app.py`
or `python manage.py run --port 9000`.

## What's inside

```
app.py               Public routes, template helpers, security headers
manage.py            create-admin · run · check · build (static export)
cms/
  store.py           JSON "database": atomic writes plus automatic backups (data/.backups)
  schemas.py         Field definitions for every page and collection; they drive the admin forms
  admin.py           Admin panel: pages, collections, media, messages, settings, SEO check
  media.py           Uploads are converted to responsive WebP (480/960/1600) plus an OG JPEG
  seo.py             Meta titles, schema.org JSON-LD and sitemap.xml
  security.py        Password hashing, CSRF, signed cookie-free form tokens, rate limiting
data/
  site.json          Brand, contact details, navigation, footer, SEO defaults
  pages/*.json       Home, Company, Services, Products, Industries, Projects, Insights, Contact, legal pages
  collections/*.json Services, Industries, Products, Case studies (projects), Insights (posts)
  media.json         Media library index (alt text, credits)
  messages.json      Contact form submissions
  users.json         Admin users (hashed passwords)
templates/           Jinja templates (public + admin/)
static/              CSS, JS, self-hosted fonts, icons, logos, uploads/
```

### Editing content
- **Pages**: every section of every page (hero, stats, steps, CTAs, SEO fields) can be edited in *Admin → Pages*.
- **Collections**: add, edit, duplicate, reorder or unpublish (draft) services, industries, products, case studies and posts. Each item gets its own SEO-friendly URL, e.g. `/services/computer-vision/`.
- **Media library**: upload images, write alternative text once, and see where each image is used. An image that is still in use cannot be deleted.
- **Messages**: contact-form submissions, with a read/unread state and CSV export.
- **Dashboard SEO & accessibility check**: flags missing meta descriptions, over-long titles, missing images and missing alt text.
- To add a new field, add it to `cms/schemas.py` and use it in the template. The admin form updates automatically.

## SEO
Server-rendered HTML, clean URLs, per-page titles and descriptions, canonical URLs, Open Graph and Twitter cards,
JSON-LD (Organization/ProfessionalService, WebSite, BreadcrumbList, Service, SoftwareApplication,
BlogPosting, ContactPage), a dynamic `sitemap.xml`, `robots.txt`, an RSS feed at `/feed.xml`, responsive WebP images
with width and height set (no layout shift), self-hosted fonts, and a per-item `noindex` switch.
Set **Site settings → SEO defaults → Public site URL** before going live.

## Design & accessibility (WCAG 2.1 AA)
The public site is **dark by default**: a near-black canvas, one mint accent, oversized type and large image panels.
Visitors can switch to a light theme with the sun/moon button in the header. The choice is remembered in their browser.
All colours are CSS tokens in `static/css/site.css` (`[data-theme="dark"]` / `[data-theme="light"]`), with the contrast ratio of each noted beside it.

Accessibility features:

- Text contrast of at least 4.5:1, and at least 3:1 for UI component boundaries, in **both** themes.
- Skip link and landmarks; one H1 per page; logical heading order.
- Visible focus outlines.
- Keyboard-operable menus; Escape closes them.
- An accessible theme toggle (`aria-pressed`).
- Reflow down to 320px with no horizontal scrolling.
- Reduced-motion and forced-colours support.
- Accessible form errors (summary with field links, `aria-invalid`).
- Alt text managed centrally in the media library.

Every public page type was audited with axe-core (WCAG 2.0/2.1 A + AA rules) in both themes, at desktop and mobile widths,
including the contact form's error and success states: zero violations. The public site sets **no cookies**.

## Deployment (Docker)

```bash
cp .env.example .env              # set DOMAIN, ACME_EMAIL and SECRET_KEY
docker compose up -d --build
docker compose exec app python manage.py create-admin
```

The stack has two containers:

- **app**: gunicorn serving the Flask CMS, running as a non-root user on a read-only filesystem.
  Content (`data/`) and uploads (`static/uploads/`) live in the named volumes `assert-data` and `assert-uploads`.
  On first start they are seeded with the shipped content; after that, your edits are never overwritten by a rebuild.
- **caddy**: the public entry point on ports 80 and 443, with automatic Let's Encrypt HTTPS, HSTS,
  gzip/zstd compression and a www → apex redirect.

Other notes:

- The app runs **one gunicorn worker with 8 threads**. The JSON store and the rate limiter are per-process, so do not raise the worker count. Scale threads with `GUNICORN_THREADS` instead.
- `TRUST_PROXY=1` (already set in compose) makes the app read the client IP and HTTPS scheme from Caddy's headers.
  Only enable it when the app sits behind exactly one proxy.
- The container health check hits `/healthz`.
- To try the stack locally, set `DOMAIN=localhost`; Caddy then uses its own local certificate.

**Backups:** everything that changes is in the two app volumes:
```bash
docker run --rm -v assert-cms_assert-data:/d -v assert-cms_assert-uploads:/u -v "$PWD":/b alpine \
  tar czf /b/assert-backup-$(date +%F).tgz -C / d u
```

**Updating the code:** `git pull && docker compose up -d --build`. Content in the volumes is preserved.

**Static hosting alternative:** `python manage.py build` writes the whole public site to `dist/`.
In the static build, the contact form is replaced by the email address and phone number.

## Before launch — please review
- LawFlow's status and website link are left blank, since neither could be verified. Set them in Admin → Products.
- Three product concepts from the previous draft (OpsSight AI, CivicFlow, SecureEdge AI) are kept as **drafts** (unpublished).
- There are no case studies yet: the Projects page shows a "coming soon" message until you add one.
- The three Insights articles are starter content. Review them, or unpublish them.
- The privacy, cookie and terms pages are sensible templates. Have them reviewed by legal counsel.
- Confirm the postal code (Site settings → Contact) and the LinkedIn URL.
- Images: photos marked "ASSERT" come from the current assert.gr site; the others are from Unsplash (free licence). Credits are kept in the media library.
