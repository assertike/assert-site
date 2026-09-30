"""Authentication, CSRF protection and simple rate limiting."""
from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

# -- users -------------------------------------------------------------------

def find_user(store, username: str) -> dict | None:
    for user in store.read("users.json", []):
        if user["username"].lower() == username.lower():
            return user
    return None


def verify_user(store, username: str, password: str) -> dict | None:
    user = find_user(store, username)
    if user and check_password_hash(user["password"], password):
        return user
    # Constant-ish time for unknown users.
    check_password_hash(generate_password_hash("x"), password)
    return None


def set_password(store, username: str, password: str, name: str | None = None) -> None:
    users = store.read("users.json", [])
    for user in users:
        if user["username"].lower() == username.lower():
            user["password"] = generate_password_hash(password)
            if name:
                user["name"] = name
            break
    else:
        users.append({"username": username, "name": name or username,
                      "password": generate_password_hash(password)})
    store.write("users.json", users)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("admin.login", next=request.full_path))
        g.user = session["user"]
        return view(*args, **kwargs)
    return wrapped


# -- CSRF (admin, session based) ---------------------------------------------

def csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf() -> None:
    sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf", "")
    if not sent or not expected or not hmac.compare_digest(sent, expected):
        abort(400, "Invalid or missing security token. Reload the page and try again.")


# -- Public form tokens (cookie-free, signed & time-limited) -------------------

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="public-form")


def form_token() -> str:
    return _serializer().dumps({"t": time.time()})


def check_form_token(token: str, min_age: float = 2.0, max_age: int = 60 * 60 * 6) -> bool:
    """Valid if signed by us, not expired, and not submitted inhumanly fast."""
    try:
        data = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return False
    return time.time() - data.get("t", 0) >= min_age


# -- rate limiting (in-memory, per process) ------------------------------------

_hits: dict[str, deque] = defaultdict(deque)


def rate_limited(key: str, limit: int, window: int) -> bool:
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False
