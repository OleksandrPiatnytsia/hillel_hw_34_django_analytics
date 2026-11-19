/* The charts and the print view of the report pages.
 *
 * Every chart is a <canvas data-chart="chart-main"> plus a
 * <script type="application/json" id="chart-main"> made by Django's
 * json_script (reports/templates/reports/includes/chart.html):
 *   {"type": "line", "labels": [...], "datasets": [{"label", "data"}], "options": {...}}
 * Chart.js picks the colours itself (its Colors plugin).
 */
(function () {
  "use strict";

  document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
    var source = document.getElementById(canvas.dataset.chart);
    if (!source) {
      return;
    }
    var spec = JSON.parse(source.textContent);
    var options = Object.assign(
      {
        responsive: true,
        // The height comes from the CSS of .chart-box
        maintainAspectRatio: false,
        plugins: { legend: { display: spec.datasets.length > 1 || spec.type === "doughnut" } },
      },
      spec.options
    );
    new Chart(canvas, { type: spec.type, data: { labels: spec.labels, datasets: spec.datasets }, options: options });
  });

  // ?print=1: the page has every row; open the print dialog once it is drawn
  var script = document.currentScript;
  if (script && script.hasAttribute("data-autoprint")) {
    window.addEventListener("load", function () {
      window.print();
    });
  }
})();
