fetch("/api/ai/forecast-chart").then(r => r.json()).then(d => {
  new Chart(document.getElementById("chart"), {
    type: "line",
    data: {
      labels: d.labels.map(x => x.slice(5)),
      datasets: [
        {label: "الفعلي", data: d.actual, borderColor: "#1d6b4a", backgroundColor: "#1d6b4a", tension: .25},
        {label: "المتوقع", data: d.predicted, borderColor: "#d9822b", backgroundColor: "#d9822b", borderDash: [6, 4], tension: .25},
      ],
    },
    options: {plugins: {legend: {labels: {font: {family: "Readex Pro"}}}}, scales: {y: {beginAtZero: true}}},
  });
});
