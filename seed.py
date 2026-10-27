"""Demo data so the deployed site is never empty (demo accounts: see README)."""
from datetime import timedelta
from .db import get_db, now
from .security import hash_password

def seed():
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return
        t = now()
        ins = lambda *a: db.execute(*a).lastrowid
        rest = ins("INSERT INTO users(name,email,pw_hash,role,created_at) VALUES(?,?,?,?,?)",
                   ("كافيتريا الجامعة", "restaurant@ecotrack.test", hash_password("Demo1234"), "restaurant", t.isoformat(" ")))
        rest2 = ins("INSERT INTO users(name,email,pw_hash,role,created_at) VALUES(?,?,?,?,?)",
                    ("مطعم الواحة", "oasis@ecotrack.test", hash_password("Demo1234"), "restaurant", t.isoformat(" ")))
        stud = ins("INSERT INTO users(name,email,pw_hash,role,created_at) VALUES(?,?,?,?,?)",
                   ("طالب تجريبي", "student@ecotrack.test", hash_password("Demo1234"), "beneficiary", t.isoformat(" ")))
        def offer(r, title, desc, meal, qty, left, price, disc, hours):
            return ins("INSERT INTO offers(restaurant_id,title,description,meal_type,qty_total,qty_left,"
                       "original_price,discount_pct,pickup_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (r, title, desc, meal, qty, left, price, disc, (t + timedelta(hours=hours)).isoformat(" "), t.isoformat(" ")))
        offer(rest, "وجبات كشري", "كشري بالصلصة والدقة، متاح للاستلام من الكافيتريا", "lunch", 30, 30, 25, 50, 3)
        offer(rest, "ساندوتشات جبنة وتونة", "ساندوتشات اتعملت النهارده", "snacks", 20, 20, 15, 40, 4)
        offer(rest2, "أرز بالخلطة والدجاج", "وجبة كاملة مع سلطة", "dinner", 15, 15, 60, 60, 2)
        offer(rest2, "كيك وكوكيز", "حلويات متنوعة", "desserts", 25, 25, 20, 35, 5)
        old = offer(rest, "وجبات غداء امبارح", "عرض سابق", "lunch", 40, 0, 30, 50, -20)
        db.execute("INSERT INTO orders(offer_id,user_id,qty,status,created_at) VALUES(?,?,?,?,?)",
                   (old, stud, 25, "collected", (t - timedelta(days=1)).isoformat(" ")))
        db.execute("INSERT INTO orders(offer_id,user_id,qty,status,created_at) VALUES(?,?,?,?,?)",
                   (old, stud, 15, "collected", (t - timedelta(days=1)).isoformat(" ")))
