"""Security helpers: password hashing (bcrypt), CSRF tokens, rate limiting, validation."""
import re
import secrets
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import HTTPException, Request

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")

def hash_password(pw: str) -> bytes:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt())

def verify_password(pw: str, hashed: bytes) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed)
    except ValueError:
        return False

def password_problem(pw: str) -> str | None:
    if len(pw) < 8:
        return "كلمة المرور لازم تكون 8 حروف على الأقل"
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        return "كلمة المرور لازم تحتوي على حروف وأرقام"
    return None

# ---- CSRF (token stored in the signed session cookie) ----
def csrf_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]

async def csrf_protect(request: Request):
    sent = request.headers.get("x-csrf-token")
    if not sent and "form" in request.headers.get("content-type", ""):
        sent = (await request.form()).get("csrf_token")
    expected = request.session.get("csrf")
    if not sent or not expected or not secrets.compare_digest(str(sent), expected):
        raise HTTPException(403, "CSRF token missing or invalid")

# ---- Rate limiting (in-memory sliding window; fine for a single instance) ----
_hits: dict[str, deque] = defaultdict(deque)

def rate_limit(key: str, limit: int, window_s: int):
    t = time.monotonic()
    q = _hits[key]
    while q and t - q[0] > window_s:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "طلبات كتير، حاول مرة تانية بعد شوية")
    q.append(t)

def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
