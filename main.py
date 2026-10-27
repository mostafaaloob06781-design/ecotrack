import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from ai import ai_service
from .db import get_db, init_db, now
from .security import (client_ip, csrf_protect, csrf_token, hash_password, password_problem,
                       rate_limit, verify_password, EMAIL_RE)

BASE = Path(__file__).resolve().parent.parent
IS_PROD = os.environ.get("ENV", "dev") == "prod"
MEALS = {"lunch": "غداء", "dinner": "عشاء", "snacks": "سناكس", "desserts": "حلويات"}
STATUS = {"reserved": "محجوز", "collected": "تم الاستلام", "cancelled": "ملغي"}
DAYS_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

app = FastAPI(title="EcoTrack", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    https_only=IS_PROD, same_site="lax", max_age=8 * 3600,
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")  # autoescape ON (XSS protection)
templates.env.globals.update(csrf=csrf_token, MEALS=MEALS, STATUS=STATUS, DAYS_AR=DAYS_AR)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
        "img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'self'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    if IS_PROD:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp

@app.on_event("startup")
def startup():
    init_db()
    if os.environ.get("SEED_DEMO", "1") == "1":
        from .seed import seed
        seed()

# ---------- helpers ----------
def current_user(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None
    with get_db() as db:
        return db.execute("SELECT id,name,email,role FROM users WHERE id=?", (uid,)).fetchone()

def render(request: Request, name: str, **ctx):
    ctx.setdefault("user", current_user(request))
    ctx.setdefault("error", None)
    return templates.TemplateResponse(request, name, ctx)

def need_user(request: Request, role: str | None = None):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "سجّل الدخول الأول")
    if role and user["role"] != role:
        raise HTTPException(403, "مش مسموح لك بالعملية دي")
    return user

@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    if exc.status_code == 401:
        return RedirectResponse("/login", 303)
    return templates.TemplateResponse(
        request, "error.html",
        {"user": current_user(request), "code": exc.status_code, "message": exc.detail, "error": None},
        status_code=exc.status_code)

# ---------- public pages ----------
@app.get("/")
def home(request: Request, meal: str = ""):
    sql = ("SELECT o.*, u.name AS restaurant FROM offers o JOIN users u ON u.id=o.restaurant_id "
           "WHERE o.qty_left>0 AND o.pickup_by>?")
    args: list = [now().isoformat(" ")]
    if meal in MEALS:
        sql += " AND o.meal_type=?"
        args.append(meal)
    with get_db() as db:
        offers = db.execute(sql + " ORDER BY o.pickup_by", args).fetchall()
    return render(request, "index.html", offers=offers, meal=meal, notice=request.query_params.get("ok"))

@app.get("/stats")
def stats(request: Request):
    with get_db() as db:
        s = db.execute(
            "SELECT COALESCE(SUM(qty),0) meals, COUNT(*) n, "
            "COALESCE(SUM(qty*o.original_price*o.discount_pct/100.0),0) saved "
            "FROM orders r JOIN offers o ON o.id=r.offer_id WHERE r.status='collected'").fetchone()
        reserved = db.execute("SELECT COALESCE(SUM(qty),0) FROM orders WHERE status='reserved'").fetchone()[0]
        restaurants = db.execute("SELECT COUNT(*) FROM users WHERE role='restaurant'").fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM offers WHERE qty_left>0 AND pickup_by>?",
                            (now().isoformat(" "),)).fetchone()[0]
    return render(request, "stats.html", s=s, reserved=reserved, restaurants=restaurants, active=active,
                  metrics=ai_service.model_metrics()["models"])

# ---------- auth ----------
@app.get("/register")
def register_page(request: Request):
    return render(request, "register.html")

@app.post("/register", dependencies=[Depends(csrf_protect)])
def register(request: Request, name: str = Form(...), email: str = Form(...),
             password: str = Form(...), role: str = Form(...)):
    rate_limit(f"reg:{client_ip(request)}", 10, 3600)
    name, email = name.strip()[:80], email.strip().lower()
    err = None
    if not name:
        err = "اكتب الاسم"
    elif not EMAIL_RE.match(email):
        err = "الإيميل غير صحيح"
    elif role not in ("restaurant", "beneficiary"):
        err = "اختار نوع الحساب"
    else:
        err = password_problem(password)
    if err:
        return render(request, "register.html", error=err)
    try:
        with get_db() as db:
            cur = db.execute("INSERT INTO users(name,email,pw_hash,role,created_at) VALUES(?,?,?,?,?)",
                             (name, email, hash_password(password), role, now().isoformat(" ")))
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        return render(request, "register.html", error="الإيميل ده مسجّل قبل كده")
    request.session.clear()
    request.session["uid"] = uid
    return RedirectResponse("/dashboard", 303)

@app.get("/login")
def login_page(request: Request):
    return render(request, "login.html")

@app.post("/login", dependencies=[Depends(csrf_protect)])
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    rate_limit(f"login:{client_ip(request)}:{email}", 5, 300)  # brute-force protection
    with get_db() as db:
        u = db.execute("SELECT id,pw_hash FROM users WHERE email=?", (email,)).fetchone()
    if not u or not verify_password(password, u["pw_hash"]):
        return render(request, "login.html", error="الإيميل أو كلمة المرور غلط")
    request.session.clear()  # new session on login (prevents session fixation)
    request.session["uid"] = u["id"]
    return RedirectResponse("/dashboard", 303)

@app.post("/logout", dependencies=[Depends(csrf_protect)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", 303)

# ---------- dashboards ----------
@app.get("/dashboard")
def dashboard(request: Request):
    user = need_user(request)
    with get_db() as db:
        if user["role"] == "restaurant":
            offers = db.execute("SELECT * FROM offers WHERE restaurant_id=? ORDER BY id DESC", (user["id"],)).fetchall()
            orders = db.execute(
                "SELECT r.*, o.title, u.name AS customer FROM orders r JOIN offers o ON o.id=r.offer_id "
                "JOIN users u ON u.id=r.user_id WHERE o.restaurant_id=? ORDER BY r.id DESC", (user["id"],)).fetchall()
            return render(request, "restaurant.html", offers=offers, orders=orders,
                          default_pickup=(now() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
                          today=now().weekday())
        orders = db.execute(
            "SELECT r.*, o.title, o.pickup_by, o.original_price, o.discount_pct, u.name AS restaurant "
            "FROM orders r JOIN offers o ON o.id=r.offer_id JOIN users u ON u.id=o.restaurant_id "
            "WHERE r.user_id=? ORDER BY r.id DESC", (user["id"],)).fetchall()
    return render(request, "beneficiary.html", orders=orders)

@app.post("/offers", dependencies=[Depends(csrf_protect)])
def create_offer(request: Request, title: str = Form(...), description: str = Form(""),
                 meal_type: str = Form(...), qty: int = Form(...), original_price: float = Form(...),
                 discount_pct: int = Form(...), pickup_by: str = Form(...)):
    user = need_user(request, "restaurant")
    try:
        pickup = datetime.fromisoformat(pickup_by)
    except ValueError:
        raise HTTPException(400, "موعد الاستلام غير صحيح")
    title = title.strip()[:100]
    if (not title or meal_type not in MEALS or not 1 <= qty <= 1000 or not 0 <= original_price <= 100000
            or not 0 <= discount_pct <= 100 or pickup <= now()):
        raise HTTPException(400, "بيانات العرض غير صحيحة")
    with get_db() as db:
        db.execute("INSERT INTO offers(restaurant_id,title,description,meal_type,qty_total,qty_left,"
                   "original_price,discount_pct,pickup_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (user["id"], title, description.strip()[:500], meal_type, qty, qty, original_price,
                    discount_pct, pickup.isoformat(" "), now().isoformat(" ")))
    return RedirectResponse("/dashboard", 303)

@app.post("/offers/{offer_id}/book", dependencies=[Depends(csrf_protect)])
def book(request: Request, offer_id: int, qty: int = Form(...)):
    user = need_user(request, "beneficiary")
    if not 1 <= qty <= 5:
        raise HTTPException(400, "الحد الأقصى 5 وجبات في الحجز الواحد")
    with get_db() as db:
        # atomic: only succeeds if enough quantity is left and the offer has not expired
        cur = db.execute("UPDATE offers SET qty_left=qty_left-? WHERE id=? AND qty_left>=? AND pickup_by>?",
                         (qty, offer_id, qty, now().isoformat(" ")))
        if cur.rowcount == 0:
            raise HTTPException(409, "الكمية غير متاحة أو العرض انتهى")
        db.execute("INSERT INTO orders(offer_id,user_id,qty,created_at) VALUES(?,?,?,?)",
                   (offer_id, user["id"], qty, now().isoformat(" ")))
    return RedirectResponse("/dashboard", 303)

@app.post("/orders/{order_id}/status", dependencies=[Depends(csrf_protect)])
def order_status(request: Request, order_id: int, status: str = Form(...)):
    user = need_user(request)
    if status not in ("collected", "cancelled"):
        raise HTTPException(400, "حالة غير صحيحة")
    with get_db() as db:
        o = db.execute("SELECT r.*, f.restaurant_id FROM orders r JOIN offers f ON f.id=r.offer_id "
                       "WHERE r.id=?", (order_id,)).fetchone()
        if not o:
            raise HTTPException(404, "الطلب مش موجود")
        owner = (user["role"] == "restaurant" and o["restaurant_id"] == user["id"])
        customer = (user["role"] == "beneficiary" and o["user_id"] == user["id"] and status == "cancelled")
        if not (owner or customer):  # authorization (RBAC + ownership)
            raise HTTPException(403, "مش مسموح لك بالعملية دي")
        if o["status"] != "reserved":
            raise HTTPException(409, "الطلب اتقفل بالفعل")
        db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        if status == "cancelled":
            db.execute("UPDATE offers SET qty_left=qty_left+? WHERE id=?", (o["qty"], o["offer_id"]))
    return RedirectResponse("/dashboard", 303)

# ---------- AI API ----------
class SurplusIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    meal_type: str
    prepared_qty: int = Field(ge=1, le=1000)
    is_holiday: int = Field(default=0, ge=0, le=1)
    last_week_surplus: float | None = Field(default=None, ge=0, le=1000)

class DiscountIn(BaseModel):
    qty_left: int = Field(ge=1, le=1000)
    hours_left: float = Field(ge=0, le=72)

@app.post("/api/ai/predict-surplus", dependencies=[Depends(csrf_protect)])
def api_predict(request: Request, body: SurplusIn):
    user = need_user(request, "restaurant")
    rate_limit(f"ai:{user['id']}", 30, 60)
    try:
        return ai_service.predict_surplus(**body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/ai/suggest-discount", dependencies=[Depends(csrf_protect)])
def api_discount(request: Request, body: DiscountIn):
    user = need_user(request, "restaurant")
    rate_limit(f"ai:{user['id']}", 30, 60)
    return ai_service.suggest_discount(body.qty_left, body.hours_left)

@app.get("/api/ai/forecast-chart")
def api_chart():
    return ai_service.forecast_chart()

@app.get("/health")
def health():
    return {"status": "ok"}
