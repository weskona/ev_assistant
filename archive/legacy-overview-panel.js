/* Archiviert am 2026-09-24: der klassische "Übersicht"-Tab (Tab-Key
 * "uebersicht") wurde aus dem Live-Panel (frontend/ev-assistant-panel.js)
 * entfernt -- "Übersicht (Beta)" (Tab-Key "uebersicht_beta") ist jetzt der
 * einzige Übersicht-Tab. Dieser Code ist NICHT mehr eingebunden, rein zur
 * Referenz aufbewahrt (z.B. falls einzelne Bausteine -- Energiefluss-
 * Diagramm, Ring-Ladeleistung -- fürs Beta-Panel wiederverwendet werden
 * sollen).
 *
 * Kontext beim Entfernen: README dokumentierte den klassischen Tab seit
 * seiner Einführung als "shown side by side with the classic Overview tab
 * ... for comparison before it eventually replaces it" -- dieser Schritt
 * vollzieht das nach.
 *
 * Ursprüngliche Fundstellen in ev-assistant-panel.js (vor der Entfernung):
 * - Build-Seite: Zeilen 500-886 (_buildOverview() bis Ende _buildHomeStatsCard())
 * - Update-Seite: Zeilen 2976-3251 (_updateOverview() bis Ende _setBar())
 * - Tab-Liste: Zeile 365 (["uebersicht", "mdi:view-dashboard-outline", "Übersicht"])
 * - Initial-Default: Zeile 18 (this._view = "uebersicht"; -> jetzt "uebersicht_beta")
 * - Build-Dispatch: Zeile 475 (if (view === "uebersicht") ...)
 * - Update-Dispatch: Zeile 2966 (if (this._view === "uebersicht") ...)
 *
 * Zugehöriges CSS wurde ebenfalls aus dem Live-Style-Block entfernt (siehe
 * Liste exklusiver Klassen unten) -- hier nicht mit dupliziert, da es ohne
 * die Klassen-Definitionen ringsherum (Variablen, Media-Queries) nicht
 * eigenständig nutzbar wäre. Exklusive Klassen (waren nur hier verwendet):
 * batt-dot, daily-body/card/head/row, diag-grid, flow-card, flow-wrap,
 * hub-ring, lbl-badge/cap/val, lead, lead-svg, lead-end, lead-flow, muted,
 * pw-avail/grid/solar/stats, ring-center, ring-sub, ring-val, scene-hub/
 * lbl/stage, soc-bar-hdr/limit/track, soc-diag, soc-diag-title, soc-inner,
 * soc-labels, soc-left, soc-limit-lbl, soc-power, soc-sect, soc-card,
 * socbar, stat-label, stat-value, fn-unit, fn-v, pf-badge, num, live,
 * km-grid-1col.
 */

  // --- Tab: Übersicht (klassisch, entfernt 2026-09-24) ------------------------

  _buildOverview() {
    const div = (cls) => { const d = document.createElement("div"); d.className = cls; return d; };
    // Reiner Fremdlader (siehe _ladeModus()): Heim-/PV-/evcc-Karten
    // (Flow-Diagramm, Session/Stats/Tarif/Heimladen) waeren hier bedeutungslos
    // (evcc typischerweise gar nicht konfiguriert) -- bewusst gar nicht erst
    // aufgebaut statt leer angezeigt (siehe Aufgabenstellung). "gemischt"/
    // "nur_zuhause" bleiben exakt wie bisher.
    if (this._ladeModus() === "nur_auswaerts") {
      const stack = div("res-stack");
      stack.append(this._buildExpenseOverviewCard(), this._buildIceComparisonCard());
      return stack;
    }
    const chartGrid = div("charts-2x2");
    chartGrid.append(
      this._buildSessionCard(),
      this._buildStatsCard(),
      this._buildTariffCard(),
      this._buildHomeStatsCard()
    );
    const lower = div("resumen-lower");
    lower.append(this._buildFlowCard(), chartGrid);
    const stack = div("res-stack");
    stack.append(this._buildStatusCard(), lower);
    return stack;
  }

  // --- Uebersicht (nur_auswaerts): Ausgaben/kWh, EUR/100km, Verbrenner-Vergleich ---

  _buildExpenseOverviewCard() {
    const { card } = this._card("Ausgaben & Verbrauch", "mdi:cash-multiple");
    const kpis = document.createElement("div");
    kpis.className = "kpi-row";
    kpis.innerHTML = `
      <div class="kpi"><div class="kv" id="ov-total-kwh">—</div><div class="kl">kWh gesamt</div></div>
      <div class="kpi"><div class="kv" id="ov-total-cost">—</div><div class="kl">EUR gesamt</div></div>
      <div class="kpi"><div class="kv" id="ov-count">—</div><div class="kl">Ladungen</div></div>
      <div class="kpi"><div class="kv" id="ov-eur-100km">—</div><div class="kl">EUR/100km</div></div>
    `;
    card.appendChild(kpis);
    const divider = document.createElement("div");
    divider.className = "divider";
    card.appendChild(divider);
    const grid = document.createElement("div");
    grid.className = "km-grid km-grid-1col";
    grid.innerHTML = `
      <div class="km-col">
        <div class="sub-head">Ausgaben über Zeit</div>
        <div class="km-item"><span class="km-label">Heute</span><span class="km-val" id="ov-cost-day">—</span><span class="km-unit">EUR</span></div>
        <div class="km-item"><span class="km-label">Woche</span><span class="km-val" id="ov-cost-week">—</span><span class="km-unit">EUR</span></div>
        <div class="km-item"><span class="km-label">Monat</span><span class="km-val" id="ov-cost-month">—</span><span class="km-unit">EUR</span></div>
        <div class="km-item"><span class="km-label">Jahr</span><span class="km-val" id="ov-cost-year">—</span><span class="km-unit">EUR</span></div>
      </div>
    `;
    card.appendChild(grid);
    this._r.ovTotalKwh  = kpis.querySelector("#ov-total-kwh");
    this._r.ovTotalCost = kpis.querySelector("#ov-total-cost");
    this._r.ovCount     = kpis.querySelector("#ov-count");
    this._r.ovEur100km  = kpis.querySelector("#ov-eur-100km");
    this._r.ovCostDay   = grid.querySelector("#ov-cost-day");
    this._r.ovCostWeek  = grid.querySelector("#ov-cost-week");
    this._r.ovCostMonth = grid.querySelector("#ov-cost-month");
    this._r.ovCostYear  = grid.querySelector("#ov-cost-year");
    return card;
  }

  _buildIceComparisonCard() {
    const { card } = this._card("Vergleich zum Verbrenner", "mdi:gas-station-off");
    const kpis = document.createElement("div");
    kpis.className = "kpi-row";
    kpis.innerHTML = `
      <div class="kpi"><div class="kv" id="ov-savings">—</div><div class="kl">EUR gespart</div></div>
      <div class="kpi"><div class="kv" id="ov-co2-savings">—</div><div class="kl">kg CO2 gespart</div></div>
    `;
    card.appendChild(kpis);
    const divider = document.createElement("div");
    divider.className = "divider";
    card.appendChild(divider);
    const grid = document.createElement("div");
    grid.className = "km-grid";
    grid.innerHTML = `
      <div class="km-col">
        <div class="sub-head">EV</div>
        <div class="km-item"><span class="km-label">Kosten gesamt</span><span class="km-val" id="ov-ev-cost">—</span><span class="km-unit">EUR</span></div>
        <div class="km-item"><span class="km-label">Kosten/100km</span><span class="km-val" id="ov-ev-per100">—</span><span class="km-unit">EUR</span></div>
      </div>
      <div class="km-col">
        <div class="sub-head">Verbrenner (geschätzt)</div>
        <div class="km-item"><span class="km-label">Kosten gesamt</span><span class="km-val" id="ov-verb-cost">—</span><span class="km-unit">EUR</span></div>
        <div class="km-item"><span class="km-label">Kosten/100km</span><span class="km-val" id="ov-verb-per100">—</span><span class="km-unit">EUR</span></div>
      </div>
    `;
    card.appendChild(grid);
    this._r.ovSavings    = kpis.querySelector("#ov-savings");
    this._r.ovCo2Savings = kpis.querySelector("#ov-co2-savings");
    this._r.ovEvCost     = grid.querySelector("#ov-ev-cost");
    this._r.ovEvPer100   = grid.querySelector("#ov-ev-per100");
    this._r.ovVerbCost   = grid.querySelector("#ov-verb-cost");
    this._r.ovVerbPer100 = grid.querySelector("#ov-verb-per100");
    return card;
  }

  // --- Status card (omnibattery SOC card analog) ------------------------------

  _buildStatusCard() {
    const { card } = this._card("Systemstatus", "mdi:ev-station");
    card.classList.add("soc-card");

    // Ring: charge power donut (r=73, size=180px)
    const size = 180, stroke = 14, pad = 10;
    const rv = (size - stroke) / 2 - pad;   // = 73
    const circ = +(2 * Math.PI * rv).toFixed(2); // ≈ 458.67
    const cx = size / 2, cy = size / 2;

    const ring = document.createElement("div");
    ring.className = "ring";
    ring.style.cssText = `width:${size}px;height:${size}px`;
    ring.innerHTML = `
      <svg width="${size}" height="${size}" overflow="visible" style="transform:rotate(-90deg)">
        <circle cx="${cx}" cy="${cy}" r="${rv}" fill="none" stroke="var(--bg-0)" stroke-width="${stroke}"/>
        <circle class="ring-solar" cx="${cx}" cy="${cy}" r="${rv}" fill="none" stroke="#4ade80"
          stroke-width="${stroke}" stroke-linecap="round"
          stroke-dasharray="0 ${circ}" stroke-dashoffset="0"/>
        <circle class="ring-grid" cx="${cx}" cy="${cy}" r="${rv}" fill="none" stroke="var(--accent)"
          stroke-width="${stroke}" stroke-linecap="round"
          stroke-dasharray="0 ${circ}" stroke-dashoffset="0"/>
      </svg>
      <div class="ring-center">
        <div class="ring-val" id="st-kw">—<span>kW</span></div>
        <div class="dim ring-sub" id="st-sub">WARP 3 Pro</div>
      </div>`;

    // Power stat blocks (solar / grid kW)
    const pw = document.createElement("div");
    pw.className = "soc-power";
    pw.innerHTML = `
      <div class="pw-stats">
        <div class="statblock">
          <div class="stat-label"><ha-icon icon="mdi:solar-power"></ha-icon>Solar</div>
          <div class="stat-value pw-solar" style="color:#4ade80">—<span class="stat-unit"> kW</span></div>
        </div>
        <div class="statblock" style="text-align:right">
          <div class="stat-label" style="justify-content:flex-end">
            <ha-icon icon="mdi:transmission-tower"></ha-icon>Netz
          </div>
          <div class="stat-value pw-grid" style="color:var(--accent)">—<span class="stat-unit"> kW</span></div>
        </div>
      </div>
      <div class="socbar" style="height:6px;margin-top:9px"><span id="st-pw-bar"></span></div>
      <div class="dim pw-avail" id="st-pw-avail">—</div>`;

    // EV SOC bar (below power block)
    const socSect = document.createElement("div");
    socSect.className = "soc-sect";
    socSect.innerHTML = `
      <div class="soc-bar-hdr">Fahrzeug-Akku</div>
      <div class="soc-bar-track">
        <div class="soc-bar-fill" id="st-soc-fill"></div>
        <div class="soc-bar-limit" id="st-soc-limit"></div>
      </div>
      <div class="soc-labels">
        <span class="soc-val" id="st-soc-val">—</span>
        <span class="soc-limit-lbl" id="st-soc-lim-lbl"></span>
      </div>`;

    const left = document.createElement("div");
    left.className = "soc-left";
    left.append(ring, pw, socSect);

    card.appendChild(this._buildSocInner(left));

    // Store refs
    this._r.stCirc      = circ;
    this._r.stRingSolar = ring.querySelector(".ring-solar");
    this._r.stRingGrid  = ring.querySelector(".ring-grid");
    this._r.stKw        = ring.querySelector("#st-kw");
    this._r.stSub       = ring.querySelector("#st-sub");
    this._r.stPwSolar   = pw.querySelector(".pw-solar");
    this._r.stPwGrid    = pw.querySelector(".pw-grid");
    this._r.stPwBar     = pw.querySelector("#st-pw-bar");
    this._r.stPwAvail   = pw.querySelector("#st-pw-avail");
    this._r.stSocFill   = socSect.querySelector("#st-soc-fill");
    this._r.stSocLimit  = socSect.querySelector("#st-soc-limit");
    this._r.stSocVal    = socSect.querySelector("#st-soc-val");
    this._r.stSocLimLbl = socSect.querySelector("#st-soc-lim-lbl");

    return card;
  }

  _buildSocInner(left) {
    const diag = document.createElement("div");
    diag.className = "soc-diag";
    diag.innerHTML = `
      <div class="soc-diag-title">
        <ha-icon icon="mdi:information-outline"></ha-icon>Wallbox Status
      </div>
      <div class="diag-grid">
        <div class="diag-cell"><span class="diag-cell-label">Modus</span><span class="chip" id="dg-mode">—</span></div>
        <div class="diag-cell"><span class="diag-cell-label">Verbindung</span><span class="chip" id="dg-conn">—</span></div>
        <div class="diag-cell"><span class="diag-cell-label">Phasen</span><span class="chip" id="dg-phases">—</span></div>
        <div class="diag-cell"><span class="diag-cell-label">SOC Limit</span><span class="chip" id="dg-soc-lim">—</span></div>
        <div class="diag-cell"><span class="diag-cell-label">Netztarif</span><span class="chip" id="dg-tgrid">—</span></div>
        <div class="diag-cell"><span class="diag-cell-label">Einspeisung</span><span class="chip" id="dg-tfeedin">—</span></div>
        <div class="diag-cell"><span class="diag-cell-label">Session kWh</span><span class="chip" id="dg-sess-kwh">—</span></div>
        <div class="diag-cell"><span class="diag-cell-label">Solar-Anteil</span><span class="chip" id="dg-sess-sol">—</span></div>
        <div class="diag-cell"><span class="diag-cell-label">Session EUR</span><span class="chip" id="dg-sess-eur">—</span></div>
        <div class="diag-cell"><span class="diag-cell-label">Dauer</span><span class="chip" id="dg-dur">—</span></div>
      </div>`;

    const q = (s) => diag.querySelector(s);
    this._r.dgMode     = q("#dg-mode");
    this._r.dgConn     = q("#dg-conn");
    this._r.dgPhases   = q("#dg-phases");
    this._r.dgSocLim   = q("#dg-soc-lim");
    this._r.dgTgrid    = q("#dg-tgrid");
    this._r.dgTfeedin  = q("#dg-tfeedin");
    this._r.dgSessKwh  = q("#dg-sess-kwh");
    this._r.dgSessSol  = q("#dg-sess-sol");
    this._r.dgSessEur  = q("#dg-sess-eur");
    this._r.dgDur      = q("#dg-dur");

    const inner = document.createElement("div");
    inner.className = "soc-inner";
    inner.append(left, diag);
    return inner;
  }

  // --- Flow card (energy diagram: Solar/Grid → Wallbox → EV) -----------------

  _buildFlowCard() {
    const { card, head } = this._card("Energiefluss", "mdi:transit-connection-variant");
    card.classList.add("flow-card");

    const pill = document.createElement("span");
    pill.className = "pill";
    pill.style.marginLeft = "auto";
    pill.innerHTML = `<span class="dot live"></span>Live`;
    head.appendChild(pill);

    const GAP = 5;
    // (ex,ey) = hub connection point  (lx,ly) = label center
    const EDGES = [
      { key:"nSolar", edge:"solar", cap:"Solar",   ex:50, ey:47, lx:50, ly:7,  shape:"v" },
      { key:"nGrid",  edge:"grid",  cap:"Netz",    ex:42, ey:55, lx:7,  ly:55, shape:"h" },
      { key:"nEv",    edge:"ev",    cap:"EV",      ex:58, ey:55, lx:90, ly:55, shape:"h" },
      { key:"nBatt",  edge:"batt",  cap:"Speicher",ex:50, ey:63, lx:50, ly:93, shape:"v" },
    ];

    const leadPts = (e) => {
      if (e.shape === "v") {
        const y2 = e.ly < e.ey ? e.ly + GAP : e.ly - GAP;
        return `${e.ex},${e.ey} ${e.ex},${y2}`;
      }
      const x2 = e.lx < e.ex ? e.lx + GAP : e.lx - GAP;
      return `${e.ex},${e.ey} ${x2},${e.ey}`;
    };

    const stage = document.createElement("div");
    stage.className = "scene-stage";
    stage.innerHTML =
      `<svg class="lead-svg" viewBox="0 0 100 100" preserveAspectRatio="none">` +
        `<circle class="node-dot" style="fill:#4ade80;filter:drop-shadow(0 0 2px #4ade80)" cx="50" cy="9" r="3.5"/>` +
        `<circle class="node-dot" style="fill:var(--accent);filter:drop-shadow(0 0 2px var(--accent))" cx="8" cy="55" r="3.5"/>` +
        `<circle class="node-dot" style="fill:oklch(0.72 0.19 290);filter:drop-shadow(0 0 2px oklch(0.72 0.19 290))" cx="89" cy="55" r="3.5"/>` +
        `<circle class="node-dot batt-dot" style="fill:#fb923c;filter:drop-shadow(0 0 2px #fb923c)" cx="50" cy="91" r="3.5"/>` +
        `<circle class="hub-ring" cx="50" cy="55" r="8"/>` +
        EDGES.map(e =>
          `<polyline class="lead" data-edge="${e.edge}" points="${leadPts(e)}"/>` +
          `<polyline class="lead-flow" data-edge="${e.edge}" pathLength="100" points="${leadPts(e)}"/>` +
          `<circle class="lead-end" data-edge="${e.edge}" cx="${e.ex}" cy="${e.ey}" r="0.8"/>`
        ).join("") +
      `</svg>` +
      `<div class="scene-hub"><ha-icon icon="mdi:ev-station"></ha-icon></div>`;

    EDGES.forEach(e => {
      const n = document.createElement("div");
      n.className = "scene-lbl l-" + e.edge;
      n.style.left = e.lx + "%";
      n.style.top  = e.ly + "%";
      n.innerHTML =
        `<div class="lbl-val num"><span class="fn-v">—</span><span class="fn-unit"></span></div>` +
        `<div class="lbl-cap">${e.cap}</div>` +
        `<div class="lbl-badge pf-badge"></div>`;
      stage.appendChild(n);
      this._r[e.key] = {
        node: n,
        val: n.querySelector(".fn-v"),
        unit: n.querySelector(".fn-unit"),
        badge: n.querySelector(".pf-badge"),
      };
    });

    this._r.flowStage = stage;
    this._r.leads = {};
    this._r.flows = {};
    stage.querySelectorAll(".lead, .lead-end").forEach(el =>
      (this._r.leads[el.dataset.edge] = this._r.leads[el.dataset.edge] || []).push(el)
    );
    stage.querySelectorAll(".lead-flow").forEach(el =>
      (this._r.flows[el.dataset.edge] = this._r.flows[el.dataset.edge] || []).push(el)
    );

    const wrap = document.createElement("div");
    wrap.className = "flow-wrap";
    wrap.appendChild(stage);
    card.appendChild(wrap);
    return card;
  }

  // --- Bar-chart cards (omnibattery daily-energy analog) ----------------------

  _barCard(title, icon, rows, refPrefix) {
    const { card, head } = this._card(title, icon);
    card.classList.add("daily-card");
    const body = document.createElement("div");
    body.className = "daily-body";
    const u = (s) => `<span class="dim" style="font-size:11px">${s}</span>`;
    body.innerHTML = rows.map(([cls, label, color, unit]) => `
      <div class="daily-row">
        <div class="daily-head">
          <span class="muted">${label}</span>
          <span class="num daily-${cls}-v">—${unit ? u(" " + unit) : ""}</span>
        </div>
        <div class="socbar"><span class="daily-${cls}-bar" style="background:${color}"></span></div>
      </div>`).join("");
    card.appendChild(body);
    rows.forEach(([cls]) => {
      this._r[refPrefix + cls + "V"]   = body.querySelector(`.daily-${cls}-v`);
      this._r[refPrefix + cls + "Bar"] = body.querySelector(`.daily-${cls}-bar`);
    });
    return { card, head };
  }

  _buildSessionCard() {
    const { card, head } = this._barCard(
      "Aktuelle Session", "mdi:calendar-today",
      [
        ["kwh",   "Geladen",    "var(--accent)",         "kWh"],
        ["solar", "Solar",      "#4ade80",               "%"],
        ["price", "Preis",      "oklch(0.82 0.14 75)",   "EUR"],
        ["dur",   "Dauer",      "var(--ink-mid)",         "min"],
      ],
      "sess"
    );
    return card;
  }

  _buildStatsCard() {
    const { card } = this._barCard(
      "Gesamtstatistik", "mdi:chart-bar",
      [
        ["tk", "kWh gesamt",     "var(--accent)",       "kWh"],
        ["ts", "Solar gesamt",   "#4ade80",             "%"],
        ["ta", "Ø Preis",        "oklch(0.82 0.14 75)", "€/kWh"],
      ],
      "stat"
    );
    return card;
  }

  _buildTariffCard() {
    const { card, head } = this._barCard(
      "Aktueller Tarif", "mdi:cash-clock",
      [
        ["tg", "Netzbezug",   "var(--accent)", "€/kWh"],
        ["tf", "Einspeisung", "#4ade80",       "€/kWh"],
      ],
      "tariff"
    );
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.style.marginLeft = "auto";
    pill.innerHTML = `<span class="dot live"></span>Live`;
    head.appendChild(pill);
    return card;
  }

  _buildHomeStatsCard() {
    const { card } = this._barCard(
      "Heimladen", "mdi:home-lightning-bolt",
      [
        ["hk", "kWh gesamt",  "var(--accent)",       "kWh"],
        ["hc", "EUR gesamt",  "oklch(0.82 0.14 75)", "EUR"],
      ],
      "home"
    );
    return card;
  }

  // ============================================================================
  // UPDATE-SEITE (war Teil von _update(), siehe dortigen Dispatch)
  // ============================================================================

  _updateOverview() {
    if (this._ladeModus() === "nur_auswaerts") {
      this._updateOverviewAuswaerts();
      return;
    }
    const r = this._r;
    if (!r.stKw) return;

    // evcc-Live-Werte direkt vom evcc-Addon (siehe coordinator.py::evcc_live_attrs())
    const live = this._evccLive();
    const ev = (key) => (live[key] === undefined || live[key] === null) ? null : live[key];
    const power    = parseFloat(ev("charge_power")      ?? NaN);
    const phases   = ev("phases_active");
    const phaseNum = parseInt(phases ?? "3", 10) || 3;
    const maxKw    = phaseNum * 3.68;
    const solarPct = parseFloat(ev("session_solar_pct") ?? NaN);
    const socEid   = this._eid("soc_entity");
    const soc      = socEid ? parseFloat(this._raw(socEid) ?? NaN) : parseFloat(ev("vehicle_soc") ?? NaN);
    const socLim   = parseFloat(ev("limit_soc")         ?? NaN);
    const rawConn  = ev("charging");                         // boolean aus evccs Loadpoint-State
    const mode     = ev("mode")                              || "";
    const sessKwh  = parseFloat(ev("session_energy")    ?? NaN);
    const sessEur  = parseFloat(ev("session_price")     ?? NaN);
    const durSec   = parseFloat(ev("charge_duration")   ?? NaN);
    const tGrid    = parseFloat(ev("tariff_grid")       ?? NaN);
    const tFeedin  = parseFloat(ev("tariff_feedin")     ?? NaN);
    const totalKwh = parseFloat(ev("stat_total_kwh")    ?? NaN);
    const totalSol = parseFloat(ev("stat_solar_pct")    ?? NaN);
    const avgPrice = parseFloat(ev("stat_avg_price")    ?? NaN);
    const homeKwh  = parseFloat(this._state("home_kwh") ?? NaN);
    const homeCost = parseFloat(this._state("home_cost") ?? NaN);

    // Site-level power (W → kW). gridPower: positive = import, negative = export.
    // battPower: positive = charging, negative = discharging (providing power).
    const pvKw   = parseFloat(ev("pv_power")      ?? NaN) / 1000;
    const gridPw = parseFloat(ev("grid_power")    ?? NaN) / 1000;
    const battPw = parseFloat(ev("battery_power") ?? NaN) / 1000;

    const isCharging  = !isNaN(power) && power > 0.05;
    // Derive IEC 61851 status from evccs "charging"-Flag + tatsaechlicher Leistung
    const status = rawConn === true ? (isCharging ? "C" : "B") : "A";

    // ----- Status ring -----
    this._updateRing(r.stRingSolar, r.stRingGrid, power, maxKw, r.stCirc, solarPct);
    if (isCharging) {
      r.stKw.innerHTML = `${this._fmtNum(power, 1)}<span>kW</span>`;
    } else {
      r.stKw.innerHTML = `—<span>kW</span>`;
    }
    // Show actual site PV production and grid import/export
    const pvShow   = !isNaN(pvKw)   && pvKw   > 0.01;
    const gridShow = !isNaN(gridPw) && Math.abs(gridPw) > 0.01;
    r.stPwSolar.innerHTML = pvShow
      ? `${this._fmtNum(pvKw, 1)}<span class="stat-unit"> kW</span>`
      : `—<span class="stat-unit"> kW</span>`;
    r.stPwGrid.innerHTML  = gridShow
      ? `${this._fmtNum(Math.abs(gridPw), 1)}<span class="stat-unit"> kW ${gridPw < 0 ? "↑" : "↓"}</span>`
      : `—<span class="stat-unit"> kW</span>`;
    r.stPwBar.style.width = isCharging ? this._clamp(power / maxKw * 100, 0, 100) + "%" : "0%";
    r.stPwBar.style.background = (!isNaN(solarPct) && solarPct > 50) ? "#4ade80" : "var(--accent)";
    r.stPwAvail.textContent = `Max: ${this._fmtNum(maxKw, 1)} kW (${phaseNum}P)`;

    // EV SOC bar
    if (!isNaN(soc)) {
      r.stSocFill.style.width = this._clamp(soc, 0, 100) + "%";
      r.stSocVal.textContent  = Math.round(soc) + " %";
    } else {
      r.stSocFill.style.width = "0%";
      r.stSocVal.textContent  = "—";
    }
    if (!isNaN(socLim) && socLim < 100) {
      r.stSocLimit.style.left    = this._clamp(socLim, 0, 100) + "%";
      r.stSocLimit.style.display = "block";
      r.stSocLimLbl.textContent  = "Limit " + Math.round(socLim) + " %";
    } else {
      r.stSocLimit.style.display = "none";
      r.stSocLimLbl.textContent  = "";
    }

    // ----- Diagnostics chips -----
    // Beschriftung an evccs "Mode Redesign" (0.316.0, siehe _evccModeLabel())
    // angepasst -- separate Kopie hier, da dieser Chip absichtlich unabhaengig
    // gehalten war, siehe Kartenkommentar oben.
    const MODE_LABEL = { now: "Schnell", minpv: "Smart + Immer laden", pv: "Smart", off: "Aus" };
    this._setChip(r.dgMode, MODE_LABEL[mode] || mode || "—",
      mode === "off" ? "warn" : mode ? "good" : "");

    const connLabel = status === "A" ? "Getrennt" : status === "B" ? "Verbunden" : "Lädt";
    const connTone  = status === "A" ? "" : status === "B" ? "warn" : "good";
    this._setChip(r.dgConn, connLabel, connTone);
    this._setChip(r.dgPhases, phases ? phases + " Ph." : "—", "");
    this._setChip(r.dgSocLim, !isNaN(socLim) ? Math.round(socLim) + " %" : "—", "");
    this._setChip(r.dgTgrid,   !isNaN(tGrid)   ? this._fmtNum(tGrid, 3)   + " €/kWh" : "—", "");
    this._setChip(r.dgTfeedin, !isNaN(tFeedin) ? this._fmtNum(tFeedin, 3) + " €/kWh" : "—", "");
    this._setChip(r.dgSessKwh, !isNaN(sessKwh) ? this._fmtNum(sessKwh, 2) + " kWh" : "—", "");
    this._setChip(r.dgSessSol, !isNaN(solarPct) ? Math.round(solarPct) + " %" : "—",
      !isNaN(solarPct) && solarPct > 50 ? "good" : "");
    this._setChip(r.dgSessEur, !isNaN(sessEur) ? this._fmtNum(sessEur, 2) + " EUR" : "—", "");

    let durStr = "—";
    if (!isNaN(durSec) && durSec > 0) {
      const min = Math.round(durSec / 60);
      durStr = min < 60 ? min + " min" : `${Math.floor(min/60)}h ${min%60}m`;
    }
    this._setChip(r.dgDur, durStr, "");

    // ----- Flow diagram -----
    this._updateFlow(power, pvKw, gridPw, battPw, soc, status);

    // ----- Session bars -----
    const u = (s) => `<span class="dim" style="font-size:11px"> ${s}</span>`;
    const durMin = (!isNaN(durSec) && durSec > 0) ? Math.round(durSec / 60) : 0;
    this._setBar(r.sesskwhV,   r.sesskwhBar,   !isNaN(sessKwh) ? this._fmtNum(sessKwh, 2) + u("kWh") : "—",
      !isNaN(sessKwh) ? this._clamp(sessKwh / 100 * 100, 0, 100) : 0);
    this._setBar(r.sesssolarV, r.sesssolarBar, !isNaN(solarPct) ? Math.round(solarPct) + u("%") : "—",
      !isNaN(solarPct) ? this._clamp(solarPct, 0, 100) : 0);
    this._setBar(r.sesspriceV, r.sesspriceBar, !isNaN(sessEur) ? this._fmtNum(sessEur, 2) + u("EUR") : "—",
      !isNaN(sessEur) ? this._clamp(sessEur / 30 * 100, 0, 100) : 0);
    this._setBar(r.sessdurV, r.sessdurBar,
      durMin > 0 ? (durMin < 60 ? durMin + u("min") : Math.floor(durMin/60) + "h" + u("")) : "—",
      this._clamp(durMin / 480 * 100, 0, 100));

    // ----- Stats bars -----
    this._setBar(r.stattkV,   r.stattkBar,   !isNaN(totalKwh) ? this._fmtNum(totalKwh, 1) + u("kWh") : "—",
      !isNaN(totalKwh) ? this._clamp(totalKwh / 10000 * 100, 0, 100) : 0);
    this._setBar(r.stattsV,   r.stattsBar,   !isNaN(totalSol) ? Math.round(totalSol) + u("%") : "—",
      !isNaN(totalSol) ? this._clamp(totalSol, 0, 100) : 0);
    this._setBar(r.stattaV,   r.stattaBar,   !isNaN(avgPrice) ? this._fmtNum(avgPrice, 4) + u("€/kWh") : "—",
      !isNaN(avgPrice) ? this._clamp(avgPrice / 0.5 * 100, 0, 100) : 0);

    // ----- Tariff bars -----
    const maxT = Math.max(isNaN(tGrid) ? 0 : tGrid, isNaN(tFeedin) ? 0 : tFeedin, 0.5);
    this._setBar(r.tarifftgV,  r.tarifftgBar,  !isNaN(tGrid)   ? this._fmtNum(tGrid, 3)   + u("€/kWh") : "—",
      !isNaN(tGrid) ? this._clamp(tGrid / maxT * 100, 0, 100) : 0);
    this._setBar(r.tarifftfV,  r.tarifftfBar,  !isNaN(tFeedin) ? this._fmtNum(tFeedin, 3) + u("€/kWh") : "—",
      !isNaN(tFeedin) ? this._clamp(tFeedin / maxT * 100, 0, 100) : 0);

    // ----- Home bars -----
    this._setBar(r.homehkV,   r.homehkBar,   !isNaN(homeKwh)  ? this._fmtNum(homeKwh, 1)  + u("kWh") : "—",
      !isNaN(homeKwh)  ? this._clamp(homeKwh  / 10000 * 100, 0, 100) : 0);
    this._setBar(r.homehcV,   r.homehcBar,   !isNaN(homeCost) ? this._fmtNum(homeCost, 2)  + u("EUR") : "—",
      !isNaN(homeCost) ? this._clamp(homeCost / 3000 * 100, 0, 100) : 0);
  }

  // Uebersicht fuer "nur_auswaerts" -- dieselben Sensoren/Formeln, die die
  // Fahrzeuge-Tab-Verbrenner-Vergleichssektion ohnehin schon nutzt (siehe
  // _updateVehicle()), kein neuer Netzwerkweg/keine neue Backend-Logik.
  _updateOverviewAuswaerts() {
    const r = this._r;
    if (!r.ovTotalKwh) return;
    r.ovTotalKwh.textContent  = this._num("total_kwh", 1);
    r.ovTotalCost.textContent = this._num("total_cost", 2);
    r.ovCount.textContent     = this._num("count", 0);
    r.ovCostDay.textContent   = this._num("cost_day", 2);
    r.ovCostWeek.textContent  = this._num("cost_week", 2);
    r.ovCostMonth.textContent = this._num("cost_month", 2);
    r.ovCostYear.textContent  = this._num("cost_year", 2);

    const savEid = this._eid("savings");
    const savState = savEid && this._hass ? this._hass.states[savEid] : null;
    const attr = savState ? (savState.attributes || {}) : {};
    const ersparnis  = parseFloat(savState ? savState.state : NaN);
    const evCost     = parseFloat(attr.kosten_ev_gesamt);
    const verbCost   = parseFloat(attr.kosten_verbrenner_geschaetzt);
    const gefahrenKm = parseFloat(attr.gefahrene_km);
    const fmt2 = (v) => isNaN(v) ? "—" : this._fmtNum(v, 2);
    const per100 = (cost) => (!isNaN(cost) && !isNaN(gefahrenKm) && gefahrenKm > 0)
      ? this._fmtNum(cost / gefahrenKm * 100, 2) : "—";

    r.ovEur100km.textContent  = per100(evCost);
    r.ovSavings.textContent   = fmt2(ersparnis);
    r.ovCo2Savings.textContent = this._num("co2_savings", 1);
    r.ovEvCost.textContent    = fmt2(evCost);
    r.ovEvPer100.textContent  = per100(evCost);
    r.ovVerbCost.textContent  = fmt2(verbCost);
    r.ovVerbPer100.textContent = per100(verbCost);
  }

  // pvKw: PV production (always ≥ 0)
  // gridPw: positive = importing from grid, negative = exporting
  // battPw: positive = battery charging, negative = battery discharging (providing power)
  _updateFlow(power, pvKw, gridPw, battPw, soc, status) {
    const r = this._r;
    if (!r.flowStage) return;

    const isCharging  = !isNaN(power) && power > 0.05;
    const isConnected = status && status !== "A";
    const solActive   = !isNaN(pvKw)   && pvKw   > 0.05;
    const gridImport  = !isNaN(gridPw) && gridPw > 0.05;   // importing from grid
    const gridExport  = !isNaN(gridPw) && gridPw < -0.05;  // exporting to grid
    const battDisc    = !isNaN(battPw) && battPw < -0.05;  // discharging (source)
    const battChg     = !isNaN(battPw) && battPw > 0.05;   // charging (load)

    // Solar node
    r.nSolar.node.classList.toggle("active", solActive);
    r.nSolar.val.textContent  = solActive ? this._fmtNum(pvKw, 1) : "—";
    r.nSolar.unit.textContent = solActive ? " kW" : "";

    // Grid node — shows import or export
    const gridActive = gridImport || gridExport;
    r.nGrid.node.classList.toggle("active", gridActive);
    r.nGrid.val.textContent  = gridActive ? this._fmtNum(Math.abs(gridPw), 1) : "—";
    r.nGrid.unit.textContent = gridActive ? " kW" : "";
    r.nGrid.badge.textContent = gridExport ? "↑ Einspeisung" : "";

    // Battery node — orange when active
    const battActive = battDisc || battChg;
    if (r.nBatt) {
      r.nBatt.node.classList.toggle("active", battActive);
      r.nBatt.val.textContent  = battActive ? this._fmtNum(Math.abs(battPw), 1) : "—";
      r.nBatt.unit.textContent = battActive ? " kW" : "";
      r.nBatt.badge.textContent = battChg ? "Lädt" : battDisc ? "Entlädt" : "";
    }

    // EV node
    r.nEv.node.classList.toggle("active", isConnected);
    r.nEv.val.textContent  = !isNaN(soc) ? Math.round(soc) : "—";
    r.nEv.unit.textContent = !isNaN(soc) ? " %" : "";
    r.nEv.badge.textContent = isCharging ? "Lädt" : isConnected ? "Verbunden" : "Getrennt";

    // Leader lines
    const lead = (edge, on) =>
      (r.leads[edge] || []).forEach(el => el.classList.toggle("on", on));
    lead("solar", solActive);
    lead("grid",  gridActive);
    lead("ev",    isConnected);
    lead("batt",  battActive);

    // Animated flow snakes
    const flow = (edge, on, color) =>
      (r.flows[edge] || []).forEach(el => {
        el.classList.toggle("on", on);
        if (color) el.style.color = color;
      });
    flow("solar", solActive,   "#4ade80");
    flow("grid",  gridImport,  "var(--accent)");
    flow("batt",  battDisc,    "#fb923c");
    // EV edge: dominant color based on source mix
    const evColor = isCharging
      ? (solActive && !gridImport ? "#4ade80" : battDisc && !gridImport ? "#fb923c" : "var(--accent)")
      : "var(--ink-dim)";
    flow("ev", isCharging, evColor);
  }

  _updateRing(solarEl, gridEl, powerKw, maxKw, circ, solarPct) {
    const C   = circ;
    const GAP = 0.02 * C;
    if (isNaN(powerKw) || powerKw <= 0 || isNaN(maxKw) || maxKw <= 0) {
      [solarEl, gridEl].forEach(el => { el.style.strokeDasharray = `0 ${C}`; });
      return;
    }
    const totalArc  = this._clamp(powerKw / maxKw, 0, 1) * C;
    const solarFrac = isNaN(solarPct) ? 0 : this._clamp(solarPct / 100, 0, 1);
    const solarArc  = totalArc * solarFrac;
    const gridArc   = totalArc - solarArc;
    const hasGap    = solarArc > 0 && gridArc > 0;

    const solarDraw = Math.max(solarArc - (hasGap ? GAP / 2 : 0), 0);
    solarEl.style.strokeDasharray  = `${solarDraw} ${C - solarDraw}`;
    solarEl.style.strokeDashoffset = "0";

    const gridDraw = Math.max(gridArc - (hasGap ? GAP / 2 : 0), 0);
    gridEl.style.strokeDasharray  = `${gridDraw} ${C - gridDraw}`;
    gridEl.style.strokeDashoffset = String(-solarArc);
  }

  _setChip(el, text, tone) {
    if (!el) return;
    el.textContent = text;
    el.className   = "chip" + (tone ? " chip-" + tone : "");
  }

  _setBar(valEl, barEl, html, pct) {
    if (valEl) valEl.innerHTML = html;
    if (barEl) barEl.style.width = pct + "%";
  }
