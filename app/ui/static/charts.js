// Charts. The server writes each figure, with its summary, its table and its numbers as JSON: this file only draws.
// Chart.js loads when a page has a chart, once, with its integrity, so a page without one does not pay for it.
(() => {
  const COLOURS = ["primary", "secondary", "accent", "info", "success", "warning", "error"];
  const ROUND = new Set(["pie", "doughnut", "polarArea"]);
  const POINTS = new Set(["scatter", "bubble"]);
  const NAMES = { stacked: "bar", area: "line", polar: "polarArea", mixed: "bar" };
  const LABEL_GAP = 4;
  const language = document.documentElement.lang;
  const drawn = new Map();
  let theme = {};

  // Themes use oklch, which Chart.js cannot mix or lighten. One pixel painted on a canvas gives the same colour in rgb.
  const pixel = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  function toRgb(value) {
    pixel.clearRect(0, 0, 1, 1);
    pixel.fillStyle = value;
    pixel.fillRect(0, 0, 1, 1);
    const [red, green, blue] = pixel.getImageData(0, 0, 1, 1).data;
    return { red, green, blue };
  }
  const solid = ({ red, green, blue }) => `rgb(${red}, ${green}, ${blue})`;
  const faint = ({ red, green, blue }, alpha) => `rgba(${red}, ${green}, ${blue}, ${alpha})`;

  function readTheme() {
    const style = getComputedStyle(document.documentElement);
    const read = (name) => toRgb(style.getPropertyValue(`--color-${name}`).trim());
    const found = Object.fromEntries(COLOURS.map((name) => [name, read(name)]));
    return { ...found, text: read("base-content"), surface: read("base-100"), grid: read("base-300"), font: style.fontFamily };
  }

  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const number = (value, places = 2) => new Intl.NumberFormat(language, { maximumFractionDigits: places }).format(value);

  function axisNumber(value, scale) {
    const large = Math.abs(scale.max) >= 10000 || Math.abs(scale.min) >= 10000;
    return large ? new Intl.NumberFormat(language, { notation: "compact" }).format(value) : number(value);
  }

  // A thin line down the month under the pointer, so the eye can follow it across every series.
  const guideLine = {
    id: "guideLine",
    afterDatasetsDraw(chart) {
      const active = chart.tooltip?.getActiveElements() ?? [];
      if (!active.length || !chart.options.plugins.guideLine?.show) {
        return;
      }
      const x = chart.scales.x.getPixelForValue(active[0].index);
      const { top, bottom } = chart.chartArea;
      const { ctx } = chart;
      ctx.save();
      ctx.strokeStyle = faint(theme.text, 0.45);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.stroke();
      ctx.restore();
    },
  };

  function seriesStyle(spec, series, position) {
    const colour = theme[series.colour];
    const line = series.kind === "line" || ["line", "area", "radar"].includes(NAMES[spec.type] ?? spec.type);
    if (line) {
      return {
        borderColor: solid(colour),
        backgroundColor: spec.type === "line" || series.kind === "line" ? solid(colour) : faint(colour, 0.15),
        pointBackgroundColor: solid(colour),
        pointBorderColor: solid(theme.surface),
        pointHoverBackgroundColor: solid(colour),
        pointHoverBorderColor: solid(theme.surface),
      };
    }
    if (POINTS.has(spec.type)) {
      return { backgroundColor: faint(colour, 0.7), borderColor: solid(theme.surface), hoverBorderColor: solid(theme.text) };
    }
    return {
      backgroundColor: solid(colour),
      hoverBackgroundColor: solid(colour),
      borderColor: solid(theme.surface),
      hoverBorderColor: solid(theme.surface),
      order: position + 1,
    };
  }

  function sliceStyle(spec) {
    const alpha = spec.type === "polar" ? 0.75 : 1;
    const colours = spec.colours.map((name) => faint(theme[name], alpha));
    return {
      backgroundColor: colours,
      hoverBackgroundColor: colours,
      borderColor: solid(theme.surface),
      hoverBorderColor: solid(theme.surface),
    };
  }

  function dataset(spec, series, position) {
    if (POINTS.has(spec.type)) {
      const points = series.values.map(({ x, y, r, label }) => ({ x: Number(x), y: Number(y), r: Number(r ?? 5), label }));
      const size = spec.type === "scatter" ? { pointRadius: 5, pointHoverRadius: 7 } : {};
      return { label: series.label, data: points, borderWidth: 2, hoverBorderWidth: 2, ...size, ...seriesStyle(spec, series, position) };
    }
    const data = series.values.map((value) => (value === null ? null : Number(value)));
    if (ROUND.has(NAMES[spec.type] ?? spec.type)) {
      const hole = spec.type === "doughnut" ? { cutout: "62%" } : {};
      return { label: series.label, data, borderWidth: 2, hoverOffset: 10, ...hole, ...sliceStyle(spec) };
    }
    const type = series.kind === "line" ? "line" : undefined;
    const line = type || ["line", "area", "radar"].includes(NAMES[spec.type] ?? spec.type);
    const shape = line
      ? { borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, pointBorderWidth: 2, tension: 0.25, fill: spec.type === "area" || spec.type === "radar" }
      : { borderWidth: { top: 0, right: 0, bottom: 0, left: 0 }, borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 24 };
    if (spec.type === "stacked") {
      shape.borderWidth = { top: 2, right: 0, bottom: 0, left: 0 };
      shape.borderSkipped = false;
      shape.borderRadius = 2;
    }
    return { type, label: series.label, data, order: type ? 0 : position + 1, ...shape, ...seriesStyle(spec, series, position) };
  }

  // Chart.js thins an axis at even steps from the start, which can leave out the last month. So every label that fits
  // stays, and when they do not all fit they spread evenly with both ends kept.
  function thinLabels(scale) {
    const { ctx: context, ticks } = scale;
    context.save();
    context.font = Chart.helpers.toFont(scale.options.ticks.font).string;
    const widest = Math.max(...ticks.map((tick) => context.measureText(tick.label).width));
    context.restore();
    const room = Math.max(Math.floor((scale.width + LABEL_GAP) / (widest + LABEL_GAP)), 2);
    if (room >= ticks.length) {
      return;
    }
    const last = ticks.length - 1;
    // A step that lands on the last label looks regular. Where none does, the labels spread as evenly as they can.
    const places = Array.from({ length: room - 2 }, (_, less) => room - less).find((count) => last % (count - 1) === 0) ?? room;
    const kept = new Set(Array.from({ length: places }, (_, place) => Math.round((place * last) / (places - 1))));
    ticks.forEach((tick, position) => {
      if (!kept.has(position)) {
        tick.label = "";
      }
    });
  }

  function axis(title, extra = {}) {
    return {
      grid: { color: solid(theme.grid), drawTicks: false },
      border: { display: false },
      ticks: { color: solid(theme.text), padding: 6, maxTicksLimit: 6, callback(value) { return axisNumber(value, this); } },
      title: { display: Boolean(title), text: title, color: solid(theme.text) },
      ...extra,
    };
  }

  function scales(spec, type) {
    if (ROUND.has(type) && type !== "polarArea") {
      return {};
    }
    if (type === "radar" || type === "polarArea") {
      return {
        r: {
          beginAtZero: true,
          grid: { color: solid(theme.grid) },
          angleLines: { color: solid(theme.grid) },
          pointLabels: { color: solid(theme.text), font: { size: 12 } },
          ticks: { color: solid(theme.text), backdropColor: faint(theme.surface, 0.85), maxTicksLimit: 5, callback: (value) => number(value) },
        },
      };
    }
    if (POINTS.has(type)) {
      return { x: axis(spec.axes.x, { type: "linear" }), y: axis(spec.axes.y) };
    }
    const categories = {
      grid: { display: false },
      border: { color: solid(theme.grid) },
      ticks: { color: solid(theme.text), maxRotation: 0, autoSkip: false },
      afterTickToLabelConversion: thinLabels,
      title: { display: Boolean(spec.axes.x), text: spec.axes.x, color: solid(theme.text) },
      stacked: spec.type === "stacked",
    };
    return {
      x: categories,
      y: axis(spec.axes.y, { beginAtZero: spec.type !== "line", stacked: spec.type === "stacked" }),
    };
  }

  function tooltipLabel(spec) {
    const unit = spec.unit ? ` ${spec.unit}` : "";
    if (POINTS.has(spec.type)) {
      return (item) => {
        const { x, y, r, label } = item.raw;
        const lines = [label, `${spec.axes.x}: ${number(x)}`, `${spec.axes.y}: ${number(y)}${unit}`];
        return spec.axes.size ? [...lines, `${spec.axes.size}: ${number(r)}`] : lines;
      };
    }
    return (item) => {
      const value = `${number(item.raw, spec.places)}${unit}`;
      if (ROUND.has(item.chart.config.type)) {
        return `${item.label}: ${value}`;
      }
      return item.chart.data.datasets.length > 1 ? `${item.dataset.label}: ${value}` : value;
    };
  }

  // A chart that leads somewhere: a click on a part follows the link of its row in the table, so htmx, the address and
  // the keyboard's way in are all the table's, and nothing here decides where to go.
  function choosing(canvas) {
    const links = canvas.closest("[data-chart]").querySelectorAll("tbody th a");
    return {
      onClick(_event, elements) {
        links[elements[0]?.index]?.click();
      },
      onHover(_event, elements) {
        canvas.style.cursor = elements.length ? "pointer" : "";
      },
    };
  }

  function optionsOf(spec, canvas) {
    const type = NAMES[spec.type] ?? spec.type;
    const round = ROUND.has(type);
    const byMark = round || POINTS.has(type);
    return {
      ...(spec.links ? choosing(canvas) : {}),
      responsive: true,
      maintainAspectRatio: false,
      locale: language,
      animation: reducedMotion.matches ? false : { duration: 300 },
      interaction: byMark ? { mode: "nearest", intersect: true } : { mode: "index", intersect: false },
      layout: { padding: round ? 12 : 0 },
      scales: scales(spec, type),
      font: { family: theme.font },
      plugins: {
        guideLine: { show: type === "bar" || type === "line" },
        legend: {
          display: round || spec.series.length > 1,
          position: "bottom",
          labels: { color: solid(theme.text), usePointStyle: true, boxHeight: 7, padding: 16, sort: (a, b) => a.datasetIndex - b.datasetIndex },
        },
        tooltip: {
          backgroundColor: solid(theme.surface),
          titleColor: solid(theme.text),
          bodyColor: solid(theme.text),
          borderColor: solid(theme.grid),
          borderWidth: 1,
          padding: 10,
          caretPadding: 8,
          boxPadding: 4,
          itemSort: (a, b) => a.datasetIndex - b.datasetIndex,
          usePointStyle: true,
          displayColors: !POINTS.has(type),
          callbacks: {
            title: byMark ? () => "" : undefined,
            label: tooltipLabel(spec),
          },
        },
      },
    };
  }

  function draw(figure) {
    const canvas = figure.querySelector("canvas");
    if (drawn.has(canvas)) {
      return;
    }
    try {
      const spec = JSON.parse(figure.querySelector('script[type="application/json"]').textContent);
      const chart = new Chart(canvas, {
        type: NAMES[spec.type] ?? spec.type,
        data: { labels: spec.labels, datasets: spec.series.map((series, position) => dataset(spec, series, position)) },
        options: optionsOf(spec, canvas),
      });
      drawn.set(canvas, { chart, spec });
    } catch (error) {
      console.warn("A chart could not be drawn: its table stays", error);
      Chart.getChart(canvas)?.destroy(); // a chart that failed half way stays attached to its canvas
      withoutPicture([figure]);
    }
  }

  // Colours change with no reload when the theme does. Series a person hid in the legend stay hidden.
  function repaint() {
    theme = readTheme();
    for (const [canvas, { chart, spec }] of drawn) {
      if (!canvas.isConnected) {
        chart.destroy();
        drawn.delete(canvas);
        continue;
      }
      try {
        chart.options = optionsOf(spec, canvas);
        spec.series.forEach((series, position) => {
          const style = ROUND.has(chart.config.type) ? sliceStyle(spec) : seriesStyle(spec, series, position);
          Object.assign(chart.data.datasets[position], style);
        });
        chart.update("none");
      } catch (error) {
        console.warn("A chart could not follow the theme", error);
      }
    }
  }

  let library = null;
  function loadLibrary(figure) {
    library ??= new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = figure.dataset.chartLibrary;
      script.integrity = figure.dataset.chartIntegrity;
      script.crossOrigin = "anonymous";
      script.onload = resolve;
      script.onerror = reject;
      document.head.append(script);
    });
    return library;
  }

  // Without its picture a figure still has its summary and its table, so the table opens by itself.
  function withoutPicture(figures) {
    for (const figure of figures) {
      figure.querySelector("[data-chart-box]").hidden = true;
      figure.querySelector("details").open = true;
    }
  }

  async function start(root) {
    const figures = [...root.querySelectorAll("[data-chart]")];
    if (!figures.length) {
      return;
    }
    try {
      await loadLibrary(figures[0]);
    } catch {
      withoutPicture(figures);
      return;
    }
    Chart.register(guideLine);
    theme = readTheme();
    Chart.defaults.font.family = theme.font;
    figures.forEach(draw);
    document.documentElement.dataset.chartsReady = "";
  }

  start(document);
  document.addEventListener("htmx:afterSettle", (event) => start(event.detail.target));
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", repaint);
  reducedMotion.addEventListener("change", repaint);
  new MutationObserver(repaint).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  document.addEventListener("change", (event) => {
    if (event.target.matches(".theme-controller")) {
      requestAnimationFrame(repaint);
    }
  });
})();
