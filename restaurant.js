const csrf = document.currentScript.dataset.csrf;
const post = (url, body) => fetch(url, {
  method: "POST",
  headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
  body: JSON.stringify(body),
}).then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j.error || "حصل خطأ"); return j; });

document.getElementById("predict-form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = new FormData(e.target), out = document.getElementById("predict-result");
  out.hidden = false; out.textContent = "جاري الحساب...";
  try {
    const j = await post("/api/ai/predict-surplus", {
      day_of_week: +f.get("day_of_week"), meal_type: f.get("meal_type"),
      prepared_qty: +f.get("prepared_qty"), is_holiday: f.get("is_holiday") ? 1 : 0,
    });
    out.textContent = j.recommendation;
  } catch (err) { out.textContent = err.message; }
});

document.getElementById("suggest-btn").addEventListener("click", async () => {
  const f = document.getElementById("offer-form"), out = document.getElementById("suggest-result");
  const pickup = new Date(f.pickup_by.value), hours = Math.max(0, (pickup - new Date()) / 36e5);
  out.hidden = false; out.textContent = "جاري الحساب...";
  try {
    const j = await post("/api/ai/suggest-discount",
      {qty_left: Math.max(1, +f.qty.value || 1), hours_left: Math.round(hours * 10) / 10});
    document.getElementById("discount").value = j.discount_pct;
    out.textContent = `الخصم المقترح ${j.discount_pct}% (${j.reason})`;
  } catch (err) { out.textContent = err.message; }
});
