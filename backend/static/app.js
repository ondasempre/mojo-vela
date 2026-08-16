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
  $("water-body").addEventListener("change", () => {
    syncLakeChips();
    search();
  });
  $("theme-toggle").addEventListener("click", toggleTheme);
  initTabs();
  initNav();

  await Promise.all([loadHealth(), loadSpots(), loadProfiles(), loadImages()]);
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
    renderLakeChips(body.data.water_bodies, body.data.spots);
  } catch { /* the search call will surface the failure */ }
}

/** "Lago di Como" → "Como". The chips are a quick pick, not a legend. */
function shortLakeName(name) {
  return name.replace(/^lago\s+(di\s+|d['’]\s*)?/i, "").trim() || name;
}

/**
 * The chips and the <select> are two faces of the same value. The select stays
 * because it is the accessible, keyboard-native control and the only one that
 * scales past a screenful of lakes; the chips are there because picking a lake is
 * the first thing anyone does and it should take one tap.
 */
function renderLakeChips(waterBodies, spots) {
  const box = $("lake-chips");
  if (!box) return;
  const counts = {};
  for (const spot of spots) {
    if (spot.water_body) counts[spot.water_body] = (counts[spot.water_body] || 0) + 1;
  }

  const entries = [{ id: "", label: "Tutti", count: spots.length }];
  for (const wb of waterBodies) {
    entries.push({ id: wb.id, label: shortLakeName(wb.name), count: counts[wb.id] || 0 });
  }

  box.textContent = "";
  for (const entry of entries) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.dataset.value = entry.id;
    chip.append(entry.label);
    if (entry.count) {
      const badge = document.createElement("span");
      badge.className = "chip-count";
      badge.textContent = entry.count;
      // The count is decoration next to a name that already says it all.
      badge.setAttribute("aria-hidden", "true");
      chip.append(badge);
    }
    chip.addEventListener("click", () => {
      $("water-body").value = entry.id;
      syncLakeChips();
      search();
    });
    box.append(chip);
  }
  syncLakeChips();
}

function syncLakeChips() {
  const current = $("water-body").value;
  for (const chip of document.querySelectorAll("#lake-chips .chip")) {
    chip.setAttribute("aria-pressed", String(chip.dataset.value === current));
  }
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
  // Non-breaking spaces before the unit: if the hint wraps in a narrow column it
  // must break between the two facts, never between a number and its unit.
  $("profile-hint").textContent =
    `ideale ${ideal_lo}–${ideal_hi} kn · raffiche ≤${profile.gust_limit_kn} kn`;
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
    detailCache.events = {};  // the lake filter may have changed
    render(body);
  } catch (err) {
    $("error").hidden = false;
    $("error").textContent = `Non sono riuscito a calcolare i suggerimenti: ${err.message}`;
    $("hero").innerHTML = "";
    $("list").innerHTML = "";
    $("detail").hidden = true;
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
    $("detail").hidden = false;
    const top = results.find((r) => r.spot.id === state.selected) || results[0];
    loadImages(top.spot.water_body_id || null, top.spot.id);
    loadTab(activeTab);
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
        loadTab(activeTab);
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
  renderHeroBand();
}

boot();

/* ---------------------------------------------------------------------------
 * Detail tabs: services ashore, webcams, events, clubs.
 *
 * These are fetched lazily, per spot, when a tab is opened. POI lookups go to
 * Overpass, which is donated infrastructure — fetching them for every spot in the
 * ranking would be both slow and rude, so the ranking never does.
 * ------------------------------------------------------------------------- */

const detailCache = { places: {}, webcams: {}, events: {} };
let activeTab = "services";

function initTabs() {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => selectTab(tab.dataset.tab));
  }
}

function selectTab(name) {
  activeTab = name;
  for (const tab of document.querySelectorAll(".tab")) {
    tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  }
  for (const panel of document.querySelectorAll(".tab-panel")) {
    panel.hidden = panel.id !== `tab-${name}`;
  }
  loadTab(name);
}

function currentEntry() {
  return state.results.find((r) => r.spot.id === state.selected) || state.results[0];
}

async function loadTab(name) {
  const entry = currentEntry();
  if (!entry) return;
  const spotId = entry.spot.id;
  const panel = $(`tab-${name}`);

  if (name === "services" || name === "clubs") {
    if (!detailCache.places[spotId]) {
      panel.innerHTML = `<p class="empty-note"><span class="spinner"></span> Cerco su OpenStreetMap…</p>`;
      detailCache.places[spotId] = await fetchJson(`/api/spots/${spotId}/places`);
    }
    const payload = detailCache.places[spotId];
    panel.innerHTML = name === "services" ? renderServices(payload) : renderClubs(payload, entry);
    return;
  }

  if (name === "webcams") {
    if (!detailCache.webcams[spotId]) {
      panel.innerHTML = `<p class="empty-note"><span class="spinner"></span> Cerco webcam…</p>`;
      detailCache.webcams[spotId] = await fetchJson(`/api/spots/${spotId}/webcams`);
    }
    panel.innerHTML = renderWebcams(detailCache.webcams[spotId]);
    return;
  }

  if (name === "photos") {
    const lake = entry.spot.water_body_id || null;
    panel.innerHTML = renderPhotos(await loadImages(lake, spotId));
    return;
  }

  if (name === "events") {
    const lake = entry.spot.water_body_id || $("water-body").value || "";
    const key = lake || "all";
    if (!detailCache.events[key]) {
      panel.innerHTML = `<p class="empty-note"><span class="spinner"></span> Cerco eventi…</p>`;
      detailCache.events[key] = await fetchJson(
        `/api/events${lake ? `?water_body=${encodeURIComponent(lake)}` : ""}`
      );
    }
    panel.innerHTML = renderEvents(detailCache.events[key]);
  }
}

async function fetchJson(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      return { error: detail.detail || `errore ${response.status}` };
    }
    return await response.json();
  } catch (err) {
    return { error: err.message };
  }
}

function renderServices(payload) {
  if (payload.error) {
    return `<p class="empty-note">⚠ Non sono riuscito a leggere i servizi: ${escapeHtml(payload.error)}</p>`;
  }
  if (payload.meta?.disabled) {
    return `<p class="empty-note">Ricerca punti di interesse disattivata (<code>SAILWISE_POI=0</code>).</p>`;
  }

  const data = payload.data;
  const car = data.parking;
  const moto = data.motorcycle_parking;

  const parkingCards = `
    <div class="parking-grid">
      ${parkingCard("🚗", "Auto", car)}
      ${parkingCard("🏍️", "Moto", moto)}
    </div>`;

  const sections = data.sections
    .filter((section) => section.count > 0)
    .map(
      (section) => `
      <section class="poi-section">
        <h4>${section.emoji} ${escapeHtml(section.label)} <span class="poi-count">${section.count}</span></h4>
        <ul class="poi-list">${section.places.map(poiRow).join("")}</ul>
      </section>`
    )
    .join("");

  const nothing = data.sections.every((s) => s.count === 0)
    ? `<p class="empty-note">Nessun punto di interesse mappato entro ${payload.meta.radius_m} m.
       Su OpenStreetMap questa zona è ancora scoperta — puoi contribuire tu.</p>`
    : "";

  return `
    ${parkingCards}
    ${sections}
    ${nothing}
    <p class="attribution">📍 ${escapeHtml(payload.meta.attribution)} · dati ODbL${
      payload.meta.retrieved_at ? ` · letti il ${payload.meta.retrieved_at.slice(0, 10)}` : ""
    }</p>`;
}

function parkingCard(emoji, label, assessment) {
  if (!assessment || assessment.score === null) {
    return `<div class="parking-card parking-unknown">
      <h4>${emoji} ${label}</h4>
      <p class="parking-score">sconosciuto</p>
      <p class="parking-reason">${escapeHtml(assessment?.reasons?.[0] || "nessun dato")}</p>
    </div>`;
  }
  const pct = Math.round(assessment.score * 100);
  const fee = assessment.free === true ? "gratuito" : assessment.free === false ? "a pagamento" : "tariffa sconosciuta";
  return `<div class="parking-card">
    <h4>${emoji} ${label}</h4>
    <p class="parking-score ${scoreClass(pct)}">${pct}<span class="unit">/100</span></p>
    <p class="parking-reason">a ${assessment.nearest_m} m · ${fee}</p>
    <ul class="parking-reasons">${assessment.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
  </div>`;
}

function poiRow(place) {
  const bits = [];
  if (place.distance_m !== null) bits.push(`${place.distance_m} m · ${place.walk_min} min a piedi`);
  if (place.opening_hours) bits.push(`🕒 ${escapeHtml(place.opening_hours)}`);
  if (place.cuisine) bits.push(`cucina: ${escapeHtml(place.cuisine.replace(/;/g, ", "))}`);
  if (place.fee === "no") bits.push("gratuito");
  if (place.fee === "yes") bits.push("a pagamento");
  if (place.capacity) bits.push(`${escapeHtml(place.capacity)} posti`);

  return `<li class="poi">
    <span class="poi-emoji" aria-hidden="true">${place.emoji}</span>
    <span class="poi-body">
      <span class="poi-name">${escapeHtml(place.name || place.category_label)}</span>
      <span class="poi-meta">${bits.join(" · ")}</span>
    </span>
    <span class="poi-links">
      <a href="${place.maps_url}" target="_blank" rel="noopener noreferrer" title="Apri in Google Maps">🗺️</a>
      <a href="${place.directions_url}" target="_blank" rel="noopener noreferrer" title="Indicazioni stradali">🧭</a>
      ${place.website ? `<a href="${escapeHtml(place.website)}" target="_blank" rel="noopener noreferrer" title="Sito web">🌐</a>` : ""}
      ${place.phone ? `<a href="tel:${escapeHtml(place.phone)}" title="Telefono">📞</a>` : ""}
      <a href="${place.osm_url}" target="_blank" rel="noopener noreferrer" title="Scheda OpenStreetMap">🔎</a>
    </span>
  </li>`;
}

function renderClubs(payload, entry) {
  if (payload.error) return `<p class="empty-note">⚠ ${escapeHtml(payload.error)}</p>`;

  const data = payload.data;
  const clubs = data.sections.find((s) => s.id === "clubs");
  const launch = data.sections.find((s) => s.id === "launch");

  const spotLinks = `
    <div class="map-links">
      <a class="map-button" href="${data.maps_url}" target="_blank" rel="noopener noreferrer">🗺️ Apri lo spot in Google Maps</a>
      <a class="map-button" href="${data.directions_url}" target="_blank" rel="noopener noreferrer">🧭 Indicazioni stradali</a>
      <a class="map-button" href="https://www.openstreetmap.org/?mlat=${entry.spot.lat}&mlon=${entry.spot.lon}#map=15/${entry.spot.lat}/${entry.spot.lon}" target="_blank" rel="noopener noreferrer">🔎 OpenStreetMap</a>
      <a class="map-button" href="https://www.windy.com/?${entry.spot.lat},${entry.spot.lon},11" target="_blank" rel="noopener noreferrer">🌬️ Mappa vento su Windy</a>
    </div>`;

  const clubList = clubs && clubs.count
    ? `<section class="poi-section"><h4>🏛️ Circoli velici <span class="poi-count">${clubs.count}</span></h4>
       <ul class="poi-list">${clubs.places.map(poiRow).join("")}</ul></section>`
    : `<p class="empty-note">🏛️ Nessun circolo velico mappato entro ${payload.meta.radius_m} m su OpenStreetMap.
       Se ne conosci uno, aggiungerlo a OSM lo rende disponibile a tutti.</p>`;

  const launchList = launch && launch.count
    ? `<section class="poi-section"><h4>⛵ Messa in acqua <span class="poi-count">${launch.count}</span></h4>
       <ul class="poi-list">${launch.places.map(poiRow).join("")}</ul></section>`
    : `<p class="empty-note">⛵ Nessuno scivolo o porto mappato nel raggio di ricerca.</p>`;

  return `${spotLinks}${launchList}${clubList}
    <p class="attribution">📍 ${escapeHtml(payload.meta.attribution)}</p>`;
}

function renderWebcams(payload) {
  if (payload.error) return `<p class="empty-note">⚠ ${escapeHtml(payload.error)}</p>`;

  const cams = payload.data.webcams;
  if (!cams.length) {
    return `<div class="empty-note">
      <p>📷 <strong>Nessuna webcam verificata per questo spot.</strong></p>
      <p>SailWise non pubblica link a webcam che non ha verificato: un link a una
         telecamera inesistente è peggio di una sezione vuota, perché ci conti e poi
         non c'è niente.</p>
      <p>Due strade, entrambe in <code>data/webcams/README.md</code>:
         aggiungi le webcam che già usi in <code>data/webcams/webcams.json</code>,
         oppure imposta <code>WINDY_WEBCAMS_API_KEY</code> per usare quelle di Windy.</p>
    </div>`;
  }

  return `<div class="webcam-grid">${cams
    .map(
      (cam) => `<article class="webcam-card">
        ${cam.image_url ? `<img src="${escapeHtml(cam.image_url)}" alt="Anteprima ${escapeHtml(cam.title)}" loading="lazy">` : `<div class="webcam-placeholder">📷</div>`}
        <div class="webcam-body">
          <h4>${escapeHtml(cam.title)}</h4>
          <p class="webcam-meta">
            ${cam.distance_km !== null ? `${cam.distance_km} km` : ""}
            ${cam.owner ? ` · ${escapeHtml(cam.owner)}` : ""}
            ${cam.last_updated ? ` · verificata ${escapeHtml(cam.last_updated)}` : ""}
          </p>
          ${cam.note ? `<p class="webcam-note">${escapeHtml(cam.note)}</p>` : ""}
          <a class="map-button" href="${escapeHtml(cam.url)}" target="_blank" rel="noopener noreferrer">📷 Apri la webcam</a>
        </div>
      </article>`
    )
    .join("")}</div>`;
}

function renderEvents(payload) {
  if (payload.error) return `<p class="empty-note">⚠ ${escapeHtml(payload.error)}</p>`;

  const events = payload.data.events;
  if (!events.length) {
    return `<div class="empty-note">
      <p>🏁 <strong>Nessun evento verificato per questo lago.</strong></p>
      <p>Non esiste un'API aperta per il calendario velico italiano, e SailWise non
         inventa regate. Puoi aggiungere eventi a mano in
         <code>data/events/events.json</code>, oppure iscrivere il calendario ICS del
         tuo circolo — istruzioni in <code>data/events/README.md</code>.</p>
    </div>`;
  }

  return `<ul class="event-list">${events
    .map(
      (event) => `<li class="event">
        <span class="event-date">
          <span class="event-day">${escapeHtml(event.start.slice(8, 10))}</span>
          <span class="event-month">${monthLabel(event.start)}</span>
        </span>
        <span class="event-body">
          <span class="event-title">${event.emoji} ${escapeHtml(event.title)}</span>
          <span class="event-meta">
            ${event.location ? `📍 ${escapeHtml(event.location)}` : ""}
            ${event.organiser ? ` · ${escapeHtml(event.organiser)}` : ""}
            ${event.end && event.end.slice(0, 10) !== event.start.slice(0, 10) ? ` · fino al ${escapeHtml(event.end.slice(0, 10))}` : ""}
          </span>
          ${event.description ? `<span class="event-desc">${escapeHtml(event.description)}</span>` : ""}
        </span>
        ${event.url ? `<a class="event-link" href="${escapeHtml(event.url)}" target="_blank" rel="noopener noreferrer">apri ↗</a>` : ""}
      </li>`
    )
    .join("")}</ul>
    <p class="attribution">Fonti: ${payload.data.sources.map(escapeHtml).join(", ") || "—"}</p>`;
}

function monthLabel(iso) {
  const months = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];
  const index = parseInt(iso.slice(5, 7), 10) - 1;
  return months[index] || "";
}

/* ---------------------------------------------------------------------------
 * Photographs: the hero band and the gallery tab.
 *
 * The built-in SVG illustrations are the fallback, so the page always has an
 * image and never needs a borrowed placeholder. Every photograph renders its
 * credit — an entry without one is dropped by the backend, not shown uncredited.
 * ------------------------------------------------------------------------- */

let imagesPayload = null;

function prefersDark() {
  const explicit = document.documentElement.dataset.theme;
  if (explicit) return explicit === "dark";
  return matchMedia("(prefers-color-scheme: dark)").matches;
}

async function loadImages(waterBody, spotId) {
  const params = new URLSearchParams();
  if (waterBody) params.set("water_body", waterBody);
  if (spotId) params.set("spot_id", spotId);
  const query = params.toString();
  imagesPayload = await fetchJson(`/api/images${query ? `?${query}` : ""}`);
  renderHeroBand();
  return imagesPayload;
}

function renderHeroBand() {
  if (!imagesPayload || imagesPayload.error) return;
  const data = imagesPayload.data;
  const hero = data.hero;
  const image = $("hero-image");
  const credit = $("hero-credit");

  // The built-in illustration comes in two versions; a real photograph does not.
  image.src = hero.builtin ? (prefersDark() ? data.builtin.dark : data.builtin.light) : hero.url;
  image.alt = hero.caption || "Barca a vela in navigazione";

  if (hero.builtin) {
    credit.textContent = "🎨 Illustrazione SailWise — aggiungi le tue foto in data/images/";
  } else {
    const bits = [hero.caption, hero.credit, hero.licence].filter(Boolean);
    credit.innerHTML = hero.source_url
      ? `📸 <a href="${escapeHtml(hero.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(bits.join(" · "))}</a>`
      : `📸 ${escapeHtml(bits.join(" · "))}`;
  }
}

function renderPhotos(payload) {
  if (!payload || payload.error) {
    return `<p class="empty-note">⚠ ${escapeHtml(payload?.error || "errore")}</p>`;
  }
  const data = payload.data;
  const photos = data.gallery.filter((p) => !p.builtin);

  const problems = data.problems && data.problems.length
    ? `<p class="empty-note">⚠ Voci ignorate nel manifest:<br>${data.problems.map(escapeHtml).join("<br>")}</p>`
    : "";

  if (!photos.length) {
    return `${problems}<div class="empty-note">
      <p>📸 <strong>Nessuna fotografia nel manifest.</strong></p>
      <p>Le foto hanno un autore, quindi SailWise non ne include di terzi: al loro
         posto vedi l'illustrazione disegnata per il progetto.</p>
      <p>Metti le tue in <code>data/images/photos/</code> ed elencale in
         <code>data/images/images.json</code> — istruzioni in
         <code>data/images/README.md</code>. Bastano <code>file</code> e
         <code>credit</code>.</p>
    </div>`;
  }

  return `${problems}<div class="photo-grid">${photos
    .map(
      (photo) => `<figure class="photo-card">
        <img src="${escapeHtml(photo.url)}" alt="${escapeHtml(photo.caption || "Barca a vela")}" loading="lazy">
        <figcaption class="photo-body">
          ${photo.caption ? `<p class="photo-caption">${escapeHtml(photo.caption)}</p>` : ""}
          <p class="photo-credit">📸 ${escapeHtml(photo.credit)}${
            photo.licence ? ` · ${escapeHtml(photo.licence)}` : ""
          }</p>
        </figcaption>
      </figure>`
    )
    .join("")}</div>`;
}

/* ---------------------------------------------------------------------------
 * Guides: winds, mooring, knots, safety.
 *
 * Editorial content, fetched from /api/knowledge and rendered here. The rules of
 * the rest of the app still apply: a claim about a specific lake shows its source,
 * and a section with nothing sourced says so instead of filling the space.
 * ------------------------------------------------------------------------- */

const guideCache = {};
let currentView = "plan";

function initNav() {
  for (const link of document.querySelectorAll(".navlink")) {
    link.addEventListener("click", () => showView(link.dataset.view));
  }
}

async function showView(view) {
  currentView = view;
  for (const link of document.querySelectorAll(".navlink")) {
    if (link.dataset.view === view) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }

  const isPlan = view === "plan";
  $("view-plan").hidden = !isPlan;
  $("view-guide").hidden = isPlan;
  // The hero band is scene-setting on the planner and just a space-eater on a
  // page you came to read, so it shrinks out of the way.
  $("hero-band").classList.toggle("compact", !isPlan);
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (isPlan) return;

  const panel = $("view-guide");
  if (!guideCache[view]) {
    panel.innerHTML = `<div class="panel empty"><span class="spinner"></span> Carico…</div>`;
    guideCache[view] = await fetchJson(`/api/knowledge/${view}`);
  }
  const payload = guideCache[view];
  if (payload.error) {
    panel.innerHTML = `<div class="panel error">Non riesco a caricare la guida: ${escapeHtml(payload.error)}</div>`;
    return;
  }

  const renderers = { winds: renderWinds, mooring: renderMooring, knots: renderKnots, safety: renderSafety };
  panel.innerHTML = (renderers[view] || (() => ""))(payload.data);
}

function guideHeader(data) {
  return `<header class="guide-head">
    <h2>${data.emoji} ${escapeHtml(data.title)}</h2>
    <p class="guide-intro">${escapeHtml(data.intro)}</p>
    ${data.caveat ? `<p class="guide-caveat">${escapeHtml(data.caveat)}</p>` : ""}
  </header>`;
}

/* Content files use **bold** in a few places; this is the only markup allowed. */
function bold(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function bulletCard(section) {
  return `<section class="panel guide-card">
    <h3>${section.emoji || "•"} ${escapeHtml(section.title)}</h3>
    <ul class="guide-list">${section.items.map((i) => `<li>${bold(i)}</li>`).join("")}</ul>
  </section>`;
}

// --- winds -----------------------------------------------------------------

function renderWinds(data) {
  const how = (data.sections || [])
    .map(
      (section) => `<section class="panel guide-card">
        <h3>${section.emoji} ${escapeHtml(section.title)}</h3>
        ${section.body.map((p) => `<p>${bold(p)}</p>`).join("")}
      </section>`
    )
    .join("");

  const lakes = data.lakes
    .map((lake) => {
      const cards = lake.winds.length
        ? `<div class="wind-grid">${lake.winds.map(windCard).join("")}</div>`
        : `<p class="empty-note">${escapeHtml(lake.unknown_note || "Nessuna scheda disponibile.")}</p>`;
      return `<section class="lake-block">
        <h3 class="lake-title">${lake.emoji} ${escapeHtml(lake.name)}</h3>
        <p class="lake-note">${escapeHtml(lake.note)}</p>
        ${cards}
      </section>`;
    })
    .join("");

  return `${guideHeader(data)}${how}${lakes}
    ${bulletCard(data.reading_the_water)}
    <p class="attribution">${escapeHtml(data.sources_note)}</p>`;
}

function windCard(wind) {
  const rows = [
    ["Tipo", wind.type],
    ["Direzione", wind.direction],
    ["Orario tipico", wind.hours],
    ["Intensità", wind.strength],
  ];
  return `<article class="panel wind-card">
    <h4>${escapeHtml(wind.name)}${
      wind.aka && wind.aka.length ? ` <span class="wind-aka">${escapeHtml(wind.aka.join(", "))}</span>` : ""
    }</h4>
    <dl class="wind-facts">
      ${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${escapeHtml(v)}</dd></div>`).join("")}
    </dl>
    <p class="wind-sailing">${bold(wind.sailing)}</p>
    ${wind.source ? `<p class="wind-source">Fonte: <a href="${escapeHtml(wind.source)}" target="_blank" rel="noopener noreferrer">${escapeHtml(new URL(wind.source).hostname)}</a></p>` : ""}
  </article>`;
}

// --- mooring ---------------------------------------------------------------

function renderMooring(data) {
  const types = data.types
    .map(
      (t) => `<article class="panel guide-card">
        <h3>${t.emoji} ${escapeHtml(t.title)} <span class="pill">${escapeHtml(t.difficulty)}</span></h3>
        <p class="guide-when"><strong>Quando:</strong> ${escapeHtml(t.when)}</p>
        <ol class="guide-steps">${t.steps.map((s) => `<li>${bold(s)}</li>`).join("")}</ol>
        <p class="guide-lines"><strong>Cime:</strong> ${escapeHtml(t.lines)}</p>
        <p class="guide-tip">💡 ${bold(t.tip)}</p>
      </article>`
    )
    .join("");

  return `${guideHeader(data)}
    ${bulletCard(data.golden_rules)}
    ${bulletCard(data.before)}
    ${types}
    ${bulletCard(data.kit)}`;
}

// --- knots -----------------------------------------------------------------

function renderKnots(data) {
  const knots = data.knots
    .map(
      (k) => `<article class="panel knot-card">
        <div class="knot-figure">
          <img src="${escapeHtml(k.image)}" alt="Schema del nodo ${escapeHtml(k.name)}" loading="lazy">
        </div>
        <div class="knot-body">
          <h3>${escapeHtml(k.name)} <span class="knot-aka">${escapeHtml(k.aka)}</span></h3>
          <p class="knot-rating">${k.emoji} ${escapeHtml(k.rating)}</p>
          <p><strong>A cosa serve:</strong> ${escapeHtml(k.use)}</p>
          <p><strong>Perché questo:</strong> ${escapeHtml(k.why)}</p>
          <ol class="guide-steps">${k.steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>
          <p class="knot-mnemonic">🧠 ${escapeHtml(k.mnemonic)}</p>
          <p class="knot-warning">${bold(k.warning)}</p>
        </div>
      </article>`
    )
    .join("");

  return `${guideHeader(data)}${knots}${bulletCard(data.practice)}`;
}

// --- safety ----------------------------------------------------------------

function renderSafety(data) {
  return `${guideHeader(data)}
    ${data.sections.map(bulletCard).join("")}
    <p class="guide-disclaimer">${escapeHtml(data.disclaimer)}</p>`;
}
