"""Generate a realistic SYNTHETIC dataset of daily surplus meals per meal type.

Patterns baked in (so the model has something real to learn):
- Thursday and Saturday leave more surplus (fewer students on campus the next day).
- Holidays/exams raise surplus; desserts and snacks waste more than lunch.
- Surplus is autocorrelated with last week's surplus on the same weekday.
"""
import numpy as np
import pandas as pd
from pathlib import Path

MEALS = {  # base waste rate, typical prepared quantity range
    "lunch": (0.10, (80, 160)),
    "dinner": (0.14, (60, 120)),
    "snacks": (0.18, (40, 90)),
    "desserts": (0.22, (30, 70)),
}
DAY_FACTOR = {0: 1.0, 1: 0.9, 2: 0.95, 3: 1.35, 4: 1.2, 5: 1.4, 6: 1.05}  # Mon=0 ... Sun=6
DAYS = 200  # per meal type -> 800 rows

def generate(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2026-01-04")  # a Sunday
    rows = []
    for meal, (rate, (lo, hi)) in MEALS.items():
        history = []
        for d in range(DAYS):
            date = start + pd.Timedelta(days=d)
            dow = int(date.dayofweek)
            holiday = int(rng.random() < 0.12)
            prepared = int(rng.integers(lo, hi))
            expected = prepared * rate * DAY_FACTOR[dow] * (1.5 if holiday else 1.0)
            last_week = history[-7] if len(history) >= 7 else expected
            surplus = 0.75 * expected + 0.25 * last_week + rng.normal(0, 2.5)
            surplus = int(np.clip(round(surplus), 0, prepared))
            history.append(surplus)
            rows.append((date.date().isoformat(), dow, meal, prepared, holiday,
                         round(float(last_week), 1), surplus))
    cols = ["date", "day_of_week", "meal_type", "prepared_qty", "is_holiday",
            "last_week_surplus", "surplus"]
    return pd.DataFrame(rows, columns=cols).sort_values(["date", "meal_type"]).reset_index(drop=True)

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data" / "surplus.csv"
    out.parent.mkdir(exist_ok=True)
    df = generate()
    df.to_csv(out, index=False)
    print(f"Saved {len(df)} rows to {out}")
    print(df.head())
