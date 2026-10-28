/*
 * charts.js -- Draws chart specs built in Python (intelligence/charts.py).
 * Reads colours from CSS custom properties so theme changes recolour charts.
 * Canvas must be inside a .chart-frame with position:relative and explicit height.
 */
(function () {
  "use strict";

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function palette() {
    return {
      text: css('--text-muted') || '#94A3B8',
      grid: css('--border') || '#2B3544',
      series: [
        css('--series-1') || '#3987E5',
        css('--series-2') || '#D95926',
        css('--series-3') || '#199E70',
        css('--series-4') || '#C98500',
      ],
      accent: css('--accent') || '#2DD4BF',
      muted: css('--text-muted') || '#94A3B8',
    };
  }

  var compactNum = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });

  function baseOpts(spec, p, mini) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 150 },
      spanGaps: false,
      plugins: {
        legend: {
          display: !mini || (spec.series && spec.series.length > 1),
          labels: { color: p.text, boxWidth: 10, font: { size: mini ? 10 : 11 } }
        },
        title: { display: false },
        tooltip: { enabled: true }
      },
      scales: {
        x: {
          title: { display: !mini && !!spec.x_label, text: spec.x_label || '', color: p.text, font: { size: 10 } },
          ticks: { color: p.text, font: { size: mini ? 9 : 10 }, maxTicksLimit: mini ? 6 : undefined },
          grid: { color: p.grid + '33' }
        },
        y: {
          title: { display: !mini && !!spec.y_label, text: spec.y_label || '', color: p.text, font: { size: 10 } },
          ticks: {
            color: p.text,
            font: { size: mini ? 9 : 10 },
            maxTicksLimit: mini ? 4 : undefined,
            callback: function(v) {
              if (spec.y_format === 'percent') return (v * 100).toFixed(1) + '%';
              if (spec.y_format === 'ratio') return v.toFixed(1) + 'x';
              if (Math.abs(v) >= 1e6) return compactNum.format(v);
              return v;
            }
          },
          grid: { color: p.grid + '33' }
        }
      }
    };
  }

  function colorForIdx(p, i) { return p.series[i % p.series.length]; }

  function groupedBar(ctx, spec, p, mini) {
    var ds = spec.series.map(function (s, i) {
      return {
        label: s.name, data: s.data,
        backgroundColor: s.color || colorForIdx(p, i),
        borderWidth: 0, borderRadius: 2
      };
    });
    var opts = baseOpts(spec, p, mini);
    if (spec.annotations) {
      opts.plugins.tooltip.callbacks = {
        afterBody: function (items) {
          var idx = items[0].dataIndex;
          var g = spec.annotations[idx];
          return g == null ? '' : 'vs prior: ' + (g > 0 ? '+' : '') + g + '%';
        }
      };
    }
    return new Chart(ctx, { type: 'bar', data: { labels: spec.labels, datasets: ds }, options: opts });
  }

  var RENDERERS = { grouped_bar: groupedBar };

  function drawSpec(canvas, spec, mini) {
    var p = palette();
    var existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    var fn = RENDERERS[spec.kind];
    if (fn) fn(canvas.getContext('2d'), spec, p, mini !== false);
  }

  // Expose for dialog reuse
  window._drawChartSpec = function(canvas, spec) { drawSpec(canvas, spec, false); };

  function renderOne(canvas) {
    if (canvas.dataset.shafinRendered === '1') return;
    var raw = canvas.getAttribute('data-shafin-chart');
    if (!raw) return;
    var spec;
    try { spec = JSON.parse(raw); } catch (e) { return; }
    canvas.dataset.shafinRendered = '1';

    try {
      drawSpec(canvas, spec, true);
    } catch (e) {
      canvas.insertAdjacentHTML('afterend',
        '<div style="font-size:0.75rem;color:var(--text-muted)">Chart could not be drawn.</div>');
    }
  }

  function renderAll(root) {
    (root || document).querySelectorAll('canvas[data-shafin-chart]').forEach(renderOne);
  }

  // Print handler
  window.addEventListener('beforeprint', function () {
    Chart.helpers.each(Chart.instances, function (c) { if (c) c.resize(); });
  });

  document.addEventListener('DOMContentLoaded', function () { renderAll(); });
  document.addEventListener('htmx:afterSettle', function (e) { renderAll(e.target); });

  // Event delegation for .chart-open buttons — works after any HTMX swap
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.chart-open');
    if (!btn) return;
    var canvas = btn.querySelector('canvas[data-shafin-chart]');
    if (!canvas) return;
    var raw = canvas.getAttribute('data-shafin-chart');
    if (!raw) return;
    try {
      var spec = JSON.parse(raw);
      if (window.openChartDialog) window.openChartDialog(spec.title || '', spec);
    } catch (err) {}
  });
})();
