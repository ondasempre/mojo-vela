/* SailWise UI.
 *
 * Rules this file follows, because they are product requirements and not style:
 *   - it never computes a score, a window or a warning; it renders what the API sent;
 *   - UNKNOWN renders as "sconosciuto", never as 0 (FR-P-03);
 *   - warning severity is carried by icon + label + border, never colour alone (NFR-U-03);
 *   - provenance and cache age are always visible (FR-C-04);
 *   - the disclaimer is always on screen (FR-Z-04).
 */

const $ = (id) => document.getElementById(id);

const COMPONENT_LABELS = {
  wind_quality: "Vento",
  wind_stability: "Stabilità",
  weather: "Meteo",
  rain: "Pioggia",
  temperature: "Temperatura",
  water_conditions: "Superficie",
  accessibility: "Accessibilità",
};

const TREND_LABELS = {
  RISING: "in aumento",
  EASING: "in calo",
  STEADY: "costante",
  RISING_THEN_EASING: "cresce e poi cala",
  EASING_THEN_RISING: "cala e poi cresce",
};

const SEVERITY_ICONS = { INFO: "ℹ", CAUTION: "⚠", CRITICAL: "⛔" };
const SEVERITY_LABELS = { INFO: "Nota", CAUTION: "Attenzione", CRITICAL: "Critico" };

/* Warnings arrive with a code, the numbers as `params`, and an English fallback
 * message. The engine stays language-free; the client renders. When a code is not
 * in this table the English message is shown rather than nothing — an untranslated
 * warning is still a warning. */
const WARNING_IT = {
  INSUFFICIENT_WIND: {
    message: (p, at) => `Vento medio ${p.mean_kn} kn, sotto i ${p.min_kn} kn che servono per questo tipo di uscita.`,
    recommendation: () => "Valuta un altro giorno o un altro tipo di uscita.",
  },
  GUST_ABOVE_LIMIT: {
    message: (p, at) => `Raffiche fino a ${p.gust_max_kn} kn${at}, sopra il tuo limite di ${p.limit_kn} kn.`,
    recommendation: () => "Programma di essere a riva prima che rinforzi.",
  },
  GUST_FAR_ABOVE_LIMIT: {
    message: (p, at) => `Raffiche fino a ${p.gust_max_kn} kn${at}, ben oltre il tuo limite di ${p.limit_kn} kn.`,
    recommendation: () => "Programma di essere a riva prima che rinforzi.",
  },
  WIND_ABOVE_RANGE: {
    message: (p, at) => `Picco di vento a ${p.max_kn} kn${at}, sopra il massimo della tua fascia ${p.band_min_kn}–${p.band_max_kn} kn.`,
  },
  RAPID_WIND_INCREASE: {
    message: (p, at) => `Il vento aumenta di ${p.delta_kn} kn o più nell'arco di un'ora${at}.`,
    recommendation: () => "Meglio ridurre la vela in anticipo che in ritardo.",
  },
  THUNDERSTORM_RISK: {
    message: (p, at) => `Probabilità di temporale al ${Math.round(p.probability * 100)}%${at}.`,
    recommendation: () => "Tieni d'occhio il cielo sopravvento e mantieni una via di fuga.",
  },
  THUNDERSTORM_LIKELY: {
    message: (p, at) => `Probabilità di temporale al ${Math.round(p.probability * 100)}%${at}.`,
    recommendation: () => "Non programmare di essere in acqua in questa fascia.",
  },
  VISIBILITY_REDUCED: {
    message: (p, at) => `La visibilità scende a ${p.visibility_m} m${at}.`,
  },
  VISIBILITY_LOW: {
    message: (p, at) => `La visibilità scende a ${p.visibility_m} m${at}.`,
    recommendation: () => "Non allontanarti da riva senza strumenti e conoscenza locale.",
  },
};

function localiseWarning(warning) {
  const entry = WARNING_IT[warning.code];
  if (!entry) {
    return { message: warning.message, recommendation: warning.recommendation };
  }
  const at =
    warning.from_hour !== null && warning.from_hour !== undefined
      ? ` dalle ${String(warning.from_hour).padStart(2, "0")}:00`
      : "";
  const params = warning.params || {};
  return {
    message: entry.message(params, at),
    recommendation: entry.recommendation ? entry.recommendation(params) : warning.recommendation,
  };
}

let state = { results: [], selected: null, meta: null };

// --- helpers ---------------------------------------------------------------

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );

const scoreClass = (score) => (score >= 75 ? "score-good" : score >= 55 ? "score-ok" : "score-bad");

function degToCardinal(deg) {
  const points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"];
  return points[Math.round(deg / 22.5) % 16];
}

// --- boot ------------------------------------------------------------------

async function boot() {
  $("day").value = new Date().toISOString().slice(0, 10);
  initTheme();

  $("controls").addEventListener("submit", (event) => {
    event.preventDefault();
    search();
  });
  $("profile").addEventListener("change", updateProfileHint);
  $("theme-toggle").addEventListener("click", toggleTheme);

  await Promise.all([loadHealth(), loadSpots(), loadProfiles()]);
  search();
}

async function loadHealth() {
  try {
    const health = await fetch("/api/health").then((r) => r.json());
    const badge = $("provider-badge");
    const demo = health.weather_provider === "fixture";
    badge.textContent = demo ? "dati sintetici" : `dati: ${health.weather_provider}`;
    badge.className = `badge ${demo ? "badge-demo" : "badge-live"}`;
    $("demo-banner").hidden = !demo;
    // The engine's disclaimer is canonical but English; the page carries the Italian
    // wording. It is kept as a title so the exact API text is still one hover away.
    $("disclaimer").title = health.disclaimer;
    updateWarmup(health.spots);
  } catch {
    $("provider-badge").textContent = "server non raggiungibile";
  }
}

function updateWarmup(spots) {
  if (!spots) return;
  const banner = $("warmup-banner");
  if (spots.pending > 0 && spots.warming) {
    banner.hidden = false;
    $("warmup-text").textContent =
      `Risoluzione coordinate: ${spots.resolved} di ${spots.total} spot pronti. ` +
      `La lista si allarga man mano (1 richiesta al secondo, come chiede la usage policy di OpenStreetMap).`;
    setTimeout(() => loadHealth().then(() => spots.pending > 0 && search()), 8000);
  } else {
    banner.hidden = true;
  }
}

async function loadSpots() {
  try {
    const body = await fetch("/api/spots").then((r) => r.json());
    const lakes = $("water-body");
    for (const wb of body.data.water_bodies) {
      lakes.add(new Option(wb.name, wb.id));
    }
    const origin = $("origin");
    for (const spot of body.data.spots) {
      origin.add(new Option(`${spot.name}${spot.lat === null ? " (non risolto)" : ""}`, spot.id));
    }
  } catch { /* the search call will surface the failure */ }
}

async function loadProfiles() {
  try {
    const body = await fetch("/api/profiles").then((r) => r.json());
    window.__profiles = Object.fromEntries(body.data.map((p) => [p.id, p]));
    updateProfileHint();
  } catch { /* hint stays as-is */ }
}

function updateProfileHint() {
  const profile = (window.__profiles || {})[$("profile").value];
  if (!profile) return;
  const [, ideal_lo, ideal_hi] = profile.wind_band_kn;
  $("profile-hint").textContent =
    `ideale ${ideal_lo}–${ideal_hi} kn · raffica max ${profile.gust_limit_kn} kn`;
}

// --- search ----------------------------------------------------------------

async function search() {
  const results = $("results");
  results.setAttribute("aria-busy", "true");
  $("loading").hidden = false;
  $("error").hidden = true;
  $("empty").hidden = true;
  $("submit").disabled = true;

  const maxDriving = Number($("max-driving").value);
  const originId = $("origin").value;

  const payload = {
    profile: $("profile").value,
    day: $("day").value || null,
    water_body: $("water-body").value || null,
    origin_spot_id: originId || null,
    max_driving_km: originId ? maxDriving : null,
    earliest_hour: Number($("earliest").value),
    latest_hour: Number($("latest").value),
    min_duration_h: Number($("min-duration").value),
    needs_ramp: $("needs-ramp").checked,
    limit: 10,
  };

  try {
    const response = await fetch("/api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `errore ${response.status}`);
    }
    const body = await response.json();
    state.results = body.data.results;
    state.meta = body.meta;
    state.selected = body.data.results[0]?.spot.id ?? null;
    render(body);
  } catch (err) {
    $("error").hidden = false;
    $("error").textContent = `Non sono riuscito a calcolare i suggerimenti: ${err.message}`;
    $("hero").innerHTML = "";
    $("list").innerHTML = "";
  } finally {
    $("loading").hidden = true;
    $("submit").disabled = false;
    results.setAttribute("aria-busy", "false");
  }
}

// --- rendering -------------------------------------------------------------

function render(body) {
  const { results, excluded } = body.data;
  renderSources(body.meta);
  updateWarmup(body.meta.spots);

  if (!results.length) {
    $("hero").innerHTML = "";
    $("list").innerHTML = "";
    $("empty").hidden = false;
    $("empty").innerHTML = body.meta.spots && body.meta.spots.resolved === 0
      ? `Nessuno spot ha ancora coordinate. Attiva il geocoding oppure esegui
         <code>python3 scripts/fetch_spots.py</code> per popolare il dataset.`
      : "Nessuno spot soddisfa questi criteri. Prova ad allargare la distanza o la fascia oraria.";
  } else {
    $("empty").hidden = true;
    renderHero(results.find((r) => r.spot.id === state.selected) || results[0]);
    renderList(results);
  }

  renderExcluded(excluded);
}

function renderSources(meta) {
  const parts = [];
  for (const source of meta.sources || []) {
    const cache = source.cache?.state === "HIT"
      ? ` · da cache (${source.cache.age_s}s fa)`
      : source.cache?.state === "STALE"
        ? ` · CACHE SCADUTA (${source.cache.age_s}s fa)`
        : "";
    parts.push(`${source.attribution || source.id} · ${source.provenance}${cache}`);
  }
  parts.push("© OpenStreetMap contributors (coordinate)");
  $("sources").textContent = parts.join(" — ");
}

function renderHero(entry) {
  const wind = entry.wind;
  const window_ = entry.best_window;
  const warnings = entry.safety.warnings;
  const critical = entry.safety.has_critical;

  const verdict = critical
    ? "Ci sono avvisi critici: valuta di non uscire."
    : entry.recommended
      ? "Condizioni adatte a questo tipo di uscita."
      : "Condizioni sotto la soglia di raccomandazione.";

  $("hero").innerHTML = `
    <article class="panel hero">
      <div class="hero-head">
        <div class="hero-title">
          <h2>${escapeHtml(entry.spot.name)}
            ${entry.spot.verified ? "" : '<span class="pill">non verificato</span>'}
          </h2>
          <p class="hero-sub">${escapeHtml(entry.spot.water_body || "")}${
            entry.distance
              ? ` · ~${entry.distance.km} km, ~${entry.distance.minutes} min in auto <span class="pill">stima</span>`
              : ""
          }</p>
          <p class="verdict">${verdict}</p>
        </div>
        ${dial(entry.sailing_score)}
      </div>

      <dl class="stat-row">
        <div class="stat"><dt>Finestra migliore</dt><dd>${
          window_ ? `${window_.start}–${window_.end}` : "—"
        }</dd></div>
        <div class="stat"><dt>Vento medio</dt><dd>${wind.mean_kn}<span class="unit"> kn</span></dd></div>
        <div class="stat"><dt>Raffica max</dt><dd>${wind.gust_max_kn}<span class="unit"> kn</span></dd></div>
        <div class="stat"><dt>Andamento</dt><dd style="font-size:1rem">${
          TREND_LABELS[wind.trend] || wind.trend
        }</dd></div>
        <div class="stat"><dt>Costanza</dt><dd>${Math.round(wind.consistency * 100)}<span class="unit">%</span></dd></div>
        <div class="stat"><dt>Affidabilità dato</dt><dd>${Math.round(entry.confidence * 100)}<span class="unit">%</span></dd></div>
      </dl>

      ${window_ ? "" : `<p class="hint">${escapeHtml(entry.window_note || "Nessuna finestra utile.")}</p>`}

      <div class="chart-box">
        <h3>Vento orario</h3>
        ${windChart(entry)}
        <div class="chart-legend">
          <span><span class="legend-swatch" style="background:var(--accent)"></span>vento</span>
          <span><span class="legend-swatch" style="background:var(--text-soft)"></span>raffiche</span>
          <span><span class="legend-swatch" style="background:var(--good);opacity:.35;height:10px"></span>finestra consigliata</span>
          <span><span class="legend-swatch" style="background:var(--bad);opacity:.35;height:10px"></span>ora esclusa</span>
        </div>
      </div>

      <h3 class="section-title">Come nasce il punteggio</h3>
      <ul class="components">${entry.components.map(componentRow).join("")}</ul>

      ${warnings.length ? `<h3 class="section-title" style="margin-top:20px">Avvisi</h3>` : ""}
      <ul class="warnings">${warnings.map(warningRow).join("")}</ul>
      ${entry.safety.return_by
        ? `<p class="return-by">⚑ Rientro consigliato entro le ${entry.safety.return_by}</p>`
        : ""}
    </article>`;
}

function dial(score) {
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const filled = (Math.max(0, Math.min(100, score)) / 100) * circumference;
  const colour = score >= 75 ? "var(--good)" : score >= 55 ? "var(--ok)" : "var(--bad)";
  return `
    <div class="dial">
      <svg width="86" height="86" viewBox="0 0 86 86" role="img"
           aria-label="Punteggio ${score} su 100">
        <circle cx="43" cy="43" r="${radius}" fill="none" stroke="var(--border)" stroke-width="8"/>
        <circle cx="43" cy="43" r="${radius}" fill="none" stroke="${colour}" stroke-width="8"
                stroke-linecap="round" stroke-dasharray="${filled} ${circumference}"
                transform="rotate(-90 43 43)"/>
      </svg>
      <div>
        <div class="dial-value ${scoreClass(score)}">${score}</div>
        <div class="dial-max">/ 100</div>
        <div class="dial-label">Sailing score</div>
      </div>
    </div>`;
}

function windChart(entry) {
  const hours = entry.hourly;
  if (!hours.length) return "";

  const W = 720, H = 220, padL = 34, padR = 12, padT = 12, padB = 30;
  const maxValue = Math.max(12, ...hours.map((h) => h.gust_kn)) * 1.15;
  const x = (i) => padL + (i * (W - padL - padR)) / Math.max(1, hours.length - 1);
  const y = (v) => H - padB - (v / maxValue) * (H - padT - padB);

  const line = (key, colour, dash) =>
    `<polyline fill="none" stroke="${colour}" stroke-width="2.5" ${dash}
       points="${hours.map((h, i) => `${x(i)},${y(h[key])}`).join(" ")}"/>`;

  const windowBand = entry.best_window
    ? (() => {
        const startIndex = hours.findIndex((h) => h.hour === parseInt(entry.best_window.start, 10));
        const endIndex = hours.findIndex((h) => h.hour === parseInt(entry.best_window.end, 10) - 1);
        if (startIndex < 0 || endIndex < 0) return "";
        return `<rect x="${x(startIndex)}" y="${padT}" width="${x(endIndex) - x(startIndex)}"
                 height="${H - padT - padB}" fill="var(--good)" opacity=".14"/>`;
      })()
    : "";

  const excludedBands = hours
    .map((h, i) =>
      h.excluded
        ? `<rect x="${x(i) - 6}" y="${padT}" width="12" height="${H - padT - padB}"
             fill="var(--bad)" opacity=".16"><title>${escapeHtml(h.excluded_reason || "ora esclusa")}</title></rect>`
        : ""
    )
    .join("");

  const gridLines = [0, 0.25, 0.5, 0.75, 1]
    .map((f) => {
      const value = maxValue * f;
      return `<line x1="${padL}" x2="${W - padR}" y1="${y(value)}" y2="${y(value)}"
                stroke="var(--border)" stroke-width="1"/>
              <text x="4" y="${y(value) + 4}" font-size="11" fill="var(--text-soft)">${Math.round(value)}</text>`;
    })
    .join("");

  const labels = hours
    .map((h, i) =>
      i % Math.ceil(hours.length / 8) === 0
        ? `<text x="${x(i)}" y="${H - 10}" font-size="11" text-anchor="middle" fill="var(--text-soft)">${String(h.hour).padStart(2, "0")}</text>`
        : ""
    )
    .join("");

  const points = hours
    .map(
      (h, i) => `<circle cx="${x(i)}" cy="${y(h.wind_kn)}" r="3" fill="var(--accent)">
        <title>${String(h.hour).padStart(2, "0")}:00 — ${h.wind_kn} kn, raffiche ${h.gust_kn} kn, ${degToCardinal(h.wind_dir_deg)}${
          h.excluded ? ` — ESCLUSA: ${escapeHtml(h.excluded_reason)}` : ""
        }</title></circle>`
    )
    .join("");

  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img"
      aria-label="Grafico del vento orario in nodi">
      ${gridLines}${windowBand}${excludedBands}
      ${line("gust_kn", "var(--text-soft)", 'stroke-dasharray="4 4"')}
      ${line("wind_kn", "var(--accent)", "")}
      ${points}${labels}
    </svg>`;
}

function componentRow(component) {
  const label = COMPONENT_LABELS[component.id] || component.id;
  if (!component.known) {
    return `<li class="component component-unknown">
      <span class="component-name">${label}</span>
      <span class="bar-track"></span>
      <span class="component-value">sconosciuto</span>
    </li>`;
  }
  const pct = component.max_points ? (component.points / component.max_points) * 100 : 0;
  return `<li class="component">
    <span class="component-name">${label}</span>
    <span class="bar-track"><span class="bar-fill" style="width:${pct.toFixed(0)}%"></span></span>
    <span class="component-value">${component.points.toFixed(1)} / ${component.max_points.toFixed(1)}</span>
  </li>`;
}

function warningRow(warning) {
  const severity = warning.severity;
  const cls = severity === "CRITICAL" ? "warning-critical" : severity === "CAUTION" ? "warning-caution" : "";
  const text = localiseWarning(warning);
  return `<li class="warning ${cls}">
    <span class="warning-icon" aria-hidden="true">${SEVERITY_ICONS[severity] || "•"}</span>
    <span class="warning-body">
      <span class="warning-severity sev-${severity}">${SEVERITY_LABELS[severity] || severity}</span>
      <p>${escapeHtml(text.message)}</p>
      ${text.recommendation ? `<p class="warning-reco">${escapeHtml(text.recommendation)}</p>` : ""}
    </span>
  </li>`;
}

function renderList(results) {
  $("list").innerHTML = `<div class="list">${results
    .map((entry, index) => {
      const window_ = entry.best_window;
      const worst = entry.safety.worst_severity;
      const flag = worst === "CRITICAL" ? "⛔" : worst === "CAUTION" ? "⚠" : "";
      return `<button type="button" class="row" data-id="${entry.spot.id}"
                aria-pressed="${entry.spot.id === state.selected}">
        <span class="rank">${index + 1}</span>
        <span>
          <span class="row-name">${escapeHtml(entry.spot.name)}</span>
          <span class="row-flag">${flag}</span>
          <br>
          <span class="row-meta">
            ${escapeHtml(entry.spot.water_body || "")} ·
            ${entry.wind.mean_kn} kn medi ·
            ${window_ ? `${window_.start}–${window_.end}` : "nessuna finestra"}
            ${entry.distance ? ` · ~${entry.distance.km} km` : ""}
          </span>
        </span>
        <span class="row-score ${scoreClass(entry.sailing_score)}">${entry.sailing_score}</span>
      </button>`;
    })
    .join("")}</div>`;

  for (const row of document.querySelectorAll(".row")) {
    row.addEventListener("click", () => {
      state.selected = row.dataset.id;
      const entry = state.results.find((r) => r.spot.id === state.selected);
      if (entry) {
        renderHero(entry);
        renderList(state.results);
        $("hero").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }
}

function renderExcluded(excluded) {
  const box = $("excluded-box");
  if (!excluded || !excluded.length) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  $("excluded-count").textContent = excluded.length;
  $("excluded-list").innerHTML = excluded
    .map((item) => `<li><strong>${escapeHtml(item.name)}</strong> — ${escapeHtml(item.reason)}</li>`)
    .join("");
}

// --- theme -----------------------------------------------------------------

function initTheme() {
  const saved = localStorage.getItem("sailwise-theme");
  if (saved) document.documentElement.dataset.theme = saved;
}

function toggleTheme() {
  const current =
    document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("sailwise-theme", next);
}

boot();
