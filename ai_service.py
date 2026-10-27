"""AI functions used by the web app: surplus forecast (ML) and discount suggestion (rules)."""
import json
import joblib
import pandas as pd
from . import train_model as tm

MEAL_TYPES = ("lunch", "dinner", "snacks", "desserts")
_bundle = None

def _load():
    global _bundle
    if _bundle is None:
        try:
            _bundle = joblib.load(tm.MODEL)
        except Exception:  # missing file or scikit-learn version mismatch -> retrain
            tm.train(verbose=False)
            _bundle = joblib.load(tm.MODEL)
    return _bundle

def predict_surplus(day_of_week: int, meal_type: str, prepared_qty: int,
                    is_holiday: int = 0, last_week_surplus: float | None = None) -> dict:
    if meal_type not in MEAL_TYPES:
        raise ValueError("meal_type must be one of " + ", ".join(MEAL_TYPES))
    if not 0 <= day_of_week <= 6:
        raise ValueError("day_of_week must be 0-6")
    if not 1 <= prepared_qty <= 1000:
        raise ValueError("prepared_qty must be between 1 and 1000")
    b = _load()
    if last_week_surplus is None:
        last_week_surplus = b["meal_avg"][meal_type]
    row = pd.DataFrame([{
        "day_of_week": day_of_week, "meal_type": meal_type, "prepared_qty": prepared_qty,
        "is_holiday": int(bool(is_holiday)), "last_week_surplus": float(last_week_surplus),
    }])
    surplus = int(max(0, min(prepared_qty, round(float(b["pipeline"].predict(row)[0])))))
    cut = max(0, round(surplus * 0.8))  # trim most of the expected waste
    rec = (f"متوقع يفضل حوالي {surplus} وجبة. قلّل التحضير بحوالي {cut} وجبة."
           if surplus >= 3 else "التحضير الحالي مناسب، الفائض المتوقع قليل.")
    return {"predicted_surplus": surplus, "recommended_reduction": cut, "recommendation": rec}

def suggest_discount(qty_left: int, hours_left: float) -> dict:
    """Rule-based: less time and more quantity -> bigger discount (15%..70%, steps of 5)."""
    if qty_left < 1 or hours_left < 0:
        raise ValueError("qty_left must be >= 1 and hours_left >= 0")
    time_score = max(0.0, min(1.0, 1 - hours_left / 8))   # 0 at 8h+, 1 at 0h
    qty_score = max(0.0, min(1.0, qty_left / 50))         # 1 at 50+ meals
    raw = 15 + 55 * (0.65 * time_score + 0.35 * qty_score)
    pct = int(round(raw / 5) * 5)
    return {"discount_pct": max(15, min(70, pct)),
            "reason": f"الوقت المتبقي {hours_left:g} ساعة والكمية {qty_left} وجبة"}

def forecast_chart() -> dict:
    _load()
    data = json.loads(tm.METRICS.read_text())["chart_lunch"]
    return {"labels": [d["date"] for d in data],
            "actual": [d["actual"] for d in data],
            "predicted": [d["predicted"] for d in data]}

def model_metrics() -> dict:
    _load()
    return json.loads(tm.METRICS.read_text())
