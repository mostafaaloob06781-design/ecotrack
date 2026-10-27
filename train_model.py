"""Train + evaluate surplus models. Saves model.pkl and metrics.json.

Split is TIME-BASED (last 20% of dates = test) which is how the model would be used in
reality: predict the future from the past.
"""
import json
from pathlib import Path
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "surplus.csv"
MODEL = ROOT / "ai" / "model.pkl"
METRICS = ROOT / "ai" / "metrics.json"

FEATURES = ["day_of_week", "meal_type", "prepared_qty", "is_holiday", "last_week_surplus"]
TARGET = "surplus"

def build(model):
    pre = ColumnTransformer(
        [("meal", OneHotEncoder(handle_unknown="ignore"), ["meal_type"])],
        remainder="passthrough",
    )
    return Pipeline([("pre", pre), ("model", model)])

def train(verbose: bool = True) -> dict:
    if not DATA.exists():
        from .generate_data import generate
        DATA.parent.mkdir(exist_ok=True)
        generate().to_csv(DATA, index=False)
    df = pd.read_csv(DATA).sort_values("date").reset_index(drop=True)
    cutoff = df["date"].quantile(0.8, interpolation="nearest")
    train_df, test_df = df[df["date"] <= cutoff], df[df["date"] > cutoff]

    candidates = {
        "Linear Regression": build(LinearRegression()),
        "Random Forest": build(RandomForestRegressor(n_estimators=200, max_depth=10,
                                                     random_state=42, n_jobs=-1)),
    }
    metrics = {"rows_train": len(train_df), "rows_test": len(test_df), "models": {}}
    for name, pipe in candidates.items():
        pipe.fit(train_df[FEATURES], train_df[TARGET])
        pred = pipe.predict(test_df[FEATURES])
        metrics["models"][name] = {
            "MAE": round(float(mean_absolute_error(test_df[TARGET], pred)), 2),
            "R2": round(float(r2_score(test_df[TARGET], pred)), 3),
        }
    final = candidates["Random Forest"]
    meal_avg = df.groupby("meal_type")["last_week_surplus"].mean().round(1).to_dict()
    chart = test_df[["date", "meal_type", "surplus"]].copy()
    chart["predicted"] = final.predict(test_df[FEATURES]).round(1)
    metrics["chart_lunch"] = chart[chart["meal_type"] == "lunch"].tail(14).drop(columns="meal_type") \
        .rename(columns={"surplus": "actual"}).to_dict(orient="records")
    final.fit(df[FEATURES], df[TARGET])  # refit on all data for deployment
    joblib.dump({"pipeline": final, "meal_avg": meal_avg}, MODEL)
    METRICS.write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    if verbose:
        print(f"Train rows: {len(train_df)} | Test rows: {len(test_df)} (time-based split)")
        print(f"{'Model':20s} {'MAE':>6s} {'R2':>7s}")
        for n, m in metrics["models"].items():
            print(f"{n:20s} {m['MAE']:6.2f} {m['R2']:7.3f}")
        print(f"Saved {MODEL.name} and {METRICS.name}")
    return metrics

if __name__ == "__main__":
    train()
