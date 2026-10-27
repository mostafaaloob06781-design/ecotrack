import os, re, tempfile
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
from app.main import app

def token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)

def login(c, email, pw="Demo1234"):
    r = c.post("/login", data={"email": email, "password": pw, "csrf_token": token(c, "/login")}, follow_redirects=False)
    return r

with TestClient(app) as client:
    # public pages
    assert client.get("/").status_code == 200 and "كشري" in client.get("/").text
    assert client.get("/stats").status_code == 200
    assert client.get("/api/ai/forecast-chart").json()["labels"]
    print("public pages OK")

    # security headers + CSRF
    assert "default-src" in client.get("/").headers["content-security-policy"]
    assert client.post("/login", data={"email": "a@b.co", "password": "x"}).status_code == 403
    print("headers + CSRF OK")

    # wrong password, then login as student
    assert "غلط" in login(client, "student@ecotrack.test", "Wrong1234").text
    assert login(client, "student@ecotrack.test").status_code == 303
    # RBAC: student can't use restaurant AI API or create offers
    t = token(client, "/dashboard")
    assert client.post("/api/ai/predict-surplus", headers={"X-CSRF-Token": t},
                       json={"day_of_week": 3, "meal_type": "lunch", "prepared_qty": 100}).status_code == 403
    assert client.post("/offers", data={"csrf_token": t, "title": "x", "meal_type": "lunch", "qty": 1,
                       "original_price": 1, "discount_pct": 10, "pickup_by": "2099-01-01T10:00"}).status_code == 403
    print("RBAC OK")

    # booking: over-limit rejected, valid booking reduces quantity
    t = token(client, "/")
    assert client.post("/offers/1/book", data={"csrf_token": t, "qty": 9}).status_code == 400
    assert client.post("/offers/1/book", data={"csrf_token": t, "qty": 2}, follow_redirects=False).status_code == 303
    assert "28 وجبة" in client.get("/").text
    assert "وجبات كشري" in client.get("/dashboard").text
    print("booking OK")
    client.post("/logout", data={"csrf_token": token(client, "/")})

    # restaurant: AI endpoints, create offer, XSS escaping, mark collected
    assert login(client, "restaurant@ecotrack.test").status_code == 303
    t = token(client, "/dashboard")
    r = client.post("/api/ai/predict-surplus", headers={"X-CSRF-Token": t},
                    json={"day_of_week": 3, "meal_type": "lunch", "prepared_qty": 100})
    assert r.status_code == 200 and r.json()["predicted_surplus"] > 0, r.text
    assert client.post("/api/ai/predict-surplus", headers={"X-CSRF-Token": t},
                       json={"day_of_week": 9, "meal_type": "lunch", "prepared_qty": 100}).status_code == 422
    assert client.post("/api/ai/suggest-discount", headers={"X-CSRF-Token": t},
                       json={"qty_left": 50, "hours_left": 1}).json()["discount_pct"] == 65
    client.post("/offers", data={"csrf_token": t, "title": "<script>alert(1)</script>", "meal_type": "lunch", "qty": 5,
                "original_price": 10, "discount_pct": 50, "pickup_by": "2099-01-01T10:00"})
    home = client.get("/").text
    assert "<script>alert(1)</script>" not in home and "&lt;script&gt;" in home
    print("restaurant + AI + XSS OK")
    assert client.post("/orders/3/status", data={"csrf_token": t, "status": "collected"}, follow_redirects=False).status_code == 303
    client.post("/logout", data={"csrf_token": token(client, "/")})

    # other restaurant cannot touch it; SQL-injection-style login fails safely
    assert login(client, "oasis@ecotrack.test").status_code == 303
    t = token(client, "/dashboard")
    assert client.post("/orders/3/status", data={"csrf_token": t, "status": "cancelled"}).status_code in (403, 409)
    client.post("/logout", data={"csrf_token": token(client, "/")})
    assert "غلط" in login(client, "' OR 1=1 --@x.co", "x").text
    print("ownership + SQLi OK")

    # brute force protection: 6th attempt -> 429
    codes = [login(client, "brute@x.co", "Wrong1234").status_code for _ in range(7)]
    assert 429 in codes, codes
    print("rate limit OK")

    # registration validation
    t = token(client, "/register")
    assert "8" in client.post("/register", data={"csrf_token": t, "name": "n", "email": "n@x.co", "password": "abc", "role": "beneficiary"}).text
    r = client.post("/register", data={"csrf_token": t, "name": "New", "email": "new@x.co", "password": "Passw0rd1", "role": "beneficiary"}, follow_redirects=False)
    assert r.status_code == 303
    print("ALL TESTS PASSED")
