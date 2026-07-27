/*
 * EV Assistant — custom sidebar panel.
 * Übersicht modelled after the omnibattery Resumen layout:
 *   top: full-width status card (ring + diagnostics grid)
 *   lower: energy-flow diagram (left) + 2×2 bar-chart cards (right)
 * Fahrzeuge tab unchanged.
 */

const ACCENT_H = 220;

class EVAssistantPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._built = false;
    this._view = "uebersicht";
    this._tabs = {};
    this._r = {};
    this._main = null;
    this._edgeSig = {};
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first || !this._built) { this._renderShell(); this._built = true; }
    this._update();
  }
  get hass() { return this._hass; }

  set panel(panel) { this._config = (panel && panel.config) || {}; }
  set narrow(v)    { this._narrow = v; }
  set route(_v)    {}

  // --- Helpers ----------------------------------------------------------------

  _eid(key)  { return (this._config.entities || {})[key]; }
  _title()   { return this._config.title || "EV Assistant"; }

  _state(key) {
    const eid = this._eid(key);
    if (!eid || !this._hass) return null;
    const s = this._hass.states[eid];
    if (!s || s.state === "unavailable" || s.state === "unknown") return null;
    return s.state;
  }
  _isOn(key) {
    const eid = this._eid(key);
    if (!eid || !this._hass) return false;
    return (this._hass.states[eid] || {}).state === "on";
  }
  _num(key, decimals = 1) {
    const v = parseFloat(this._state(key));
    if (isNaN(v)) return "—";
    return decimals === 0 ? Math.round(v).toString() : v.toFixed(decimals);
  }
  _duration(key) {
    const eid = this._eid(key);
    if (!eid || !this._hass) return "—";
    const s = this._hass.states[eid];
    if (!s || s.state === "unavailable" || s.state === "unknown") return "—";
    const raw = parseFloat(s.state);
    if (isNaN(raw)) return "—";
    const unit = (s.attributes && s.attributes.unit_of_measurement) || "";
    const min = unit.toLowerCase().includes("s") ? Math.round(raw / 60) : Math.round(raw);
    if (min < 60) return min + " min";
    return `${Math.floor(min / 60)}h ${min % 60}m`;
  }
  _raw(entityId) {
    if (!this._hass) return null;
    const s = this._hass.states[entityId];
    if (!s || s.state === "unavailable" || s.state === "unknown") return null;
    return s.state;
  }
  _rawNum(entityId, decimals = 1) {
    const v = parseFloat(this._raw(entityId));
    if (isNaN(v)) return "—";
    return decimals === 0 ? Math.round(v).toString() : v.toFixed(decimals);
  }
  _clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // --- Shell ------------------------------------------------------------------

  _renderShell() {
    this.shadowRoot.innerHTML = "";
    this.shadowRoot.appendChild(this._buildStyles());
    const app = document.createElement("div");
    app.className = "app";
    app.appendChild(this._buildAppbar());
    const main = document.createElement("div");
    main.className = "main";
    app.appendChild(main);
    this._main = main;
    this.shadowRoot.appendChild(app);
    this._switchView(this._view);
  }

  _buildAppbar() {
    const bar = document.createElement("div");
    bar.className = "appbar";
    const brand = document.createElement("div");
    brand.className = "brand";
    brand.innerHTML = `
      <div class="logo"><ha-icon icon="mdi:car-electric"></ha-icon></div>
      <div class="btext">
        <div class="bt-name">EV Assistant</div>
      </div>`;
    brand.querySelector(".logo").addEventListener("click", () =>
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }))
    );
    const tabBar = document.createElement("div");
    tabBar.className = "tabs";
    const TAB_DEFS = [
      ["uebersicht", "mdi:view-dashboard-outline", "Übersicht"],
      ["fahrzeuge",  "mdi:car-electric",           "Fahrzeuge"],
    ];
    this._tabs = {};
    for (const [id, icon, label] of TAB_DEFS) {
      const btn = document.createElement("button");
      btn.className = "tab";
      btn.innerHTML = `<ha-icon icon="${icon}"></ha-icon><span class="tab-label">${label}</span>`;
      btn.addEventListener("click", () => this._switchView(id));
      this._tabs[id] = btn;
      tabBar.appendChild(btn);
    }
    bar.appendChild(brand);
    bar.appendChild(tabBar);
    return bar;
  }

  _switchView(view) {
    this._view = view;
    for (const [id, el] of Object.entries(this._tabs))
      el.classList.toggle("active", id === view);
    if (!this._main) return;
    this._main.innerHTML = "";
    this._r = {};
    this._edgeSig = {};
    if (view === "uebersicht") this._main.appendChild(this._buildOverview());
    else if (view === "fahrzeuge") this._main.appendChild(this._buildVehicle());
    this._update();
  }

  // --- Shared card builder (omnibattery pattern) ------------------------------

  _card(title, icon) {
    const card = document.createElement("div");
    card.className = "card";
    const head = document.createElement("div");
    head.className = "card-head";
    head.innerHTML = `<span class="ic"><ha-icon icon="${icon}"></ha-icon></span><h2>${title}</h2>`;
    card.appendChild(head);
    return { card, head };
  }

  // --- Tab: Übersicht ---------------------------------------------------------

  _buildOverview() {
    const div = (cls) => { const d = document.createElement("div"); d.className = cls; return d; };
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

  // --- Tab: Fahrzeuge (unchanged) ---------------------------------------------

  _buildVehicle() {
    const wrap = document.createElement("div");
    wrap.className = "tab-wrap";
    wrap.innerHTML = `
      <div class="badge-row">
        <div class="badge badge-ext hidden" id="vh-badge-ext">
          <ha-icon icon="mdi:ev-station"></ha-icon> Fremdladung läuft
        </div>
        <div class="badge badge-trip hidden" id="vh-badge-trip">
          <ha-icon icon="mdi:road-variant"></ha-icon> Fahrt läuft
        </div>
      </div>
      <div class="card est-card hidden" id="est-card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:motion-sensor"></ha-icon></span>
          <h2>Laufende Erfassung</h2>
        </div>
        <div class="est-list">
          <div class="est-item hidden" id="est-ext-item">
            <ha-icon icon="mdi:ev-station" class="ci orange"></ha-icon>
            <span>Fremdladung</span><strong id="est-ext-val">—</strong>
            <span class="dim">kWh (Schätzung)</span>
          </div>
          <div class="est-item hidden" id="est-trip-item">
            <ha-icon icon="mdi:road-variant" class="ci blue"></ha-icon>
            <span>Fahrt</span><strong id="est-trip-val">—</strong>
            <span class="dim">km (Schätzung)</span>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:ev-station"></ha-icon></span><h2>Fremdladung</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv vh-ext-kwh-total">—</div><div class="kl">kWh gesamt</div></div>
          <div class="kpi"><div class="kv vh-ext-cost-total">—</div><div class="kl">EUR gesamt</div></div>
          <div class="kpi"><div class="kv vh-ext-count">—</div><div class="kl">Ladevorgänge</div></div>
        </div>
        <div class="divider"></div>
        <div class="sub-head">Letzte Fremdladung</div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv vh-ext-kwh-last">—</div><div class="kl">kWh</div></div>
          <div class="kpi"><div class="kv vh-ext-cost-last">—</div><div class="kl">EUR</div></div>
          <div class="kpi"><div class="kv vh-ext-price-last">—</div><div class="kl">EUR/kWh</div></div>
          <div class="kpi"><div class="kv vh-ext-duration-last">—</div><div class="kl">Dauer</div></div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:home-lightning-bolt"></ha-icon></span><h2>Heimladen</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv vh-home-kwh">—</div><div class="kl">kWh gesamt</div></div>
          <div class="kpi"><div class="kv vh-home-cost">—</div><div class="kl">EUR gesamt</div></div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:book-open-page-variant"></ha-icon></span><h2>Fahrtenbuch</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv vh-trip-km-last">—</div><div class="kl">km letzte Fahrt</div></div>
          <div class="kpi"><div class="kv vh-trip-count">—</div><div class="kl">Fahrten</div></div>
          <div class="kpi"><div class="kv vh-trip-km-total">—</div><div class="kl">km gesamt</div></div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:car-info"></ha-icon></span><h2>Fahrzeug</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv vh-odo">—</div><div class="kl">km Kilometerstand</div></div>
          <div class="kpi"><div class="kv vh-efficiency">—</div><div class="kl">% Ladewirkungsgrad</div></div>
          <div class="kpi"><div class="kv green vh-savings">—</div><div class="kl">EUR Ersparnis ggü. Verbrenner</div></div>
        </div>
      </div>`;

    const q = (s) => wrap.querySelector(s);
    this._r = {
      vhBadgeExt:     q("#vh-badge-ext"),
      vhBadgeTrip:    q("#vh-badge-trip"),
      estCard:        q("#est-card"),
      estExtItem:     q("#est-ext-item"),
      estTripItem:    q("#est-trip-item"),
      estExtVal:      q("#est-ext-val"),
      estTripVal:     q("#est-trip-val"),
      vhExtKwhTotal:  q(".vh-ext-kwh-total"),
      vhExtCostTotal: q(".vh-ext-cost-total"),
      vhExtCount:     q(".vh-ext-count"),
      vhExtKwhLast:   q(".vh-ext-kwh-last"),
      vhExtCostLast:  q(".vh-ext-cost-last"),
      vhExtPriceLast: q(".vh-ext-price-last"),
      vhExtDurLast:   q(".vh-ext-duration-last"),
      vhHomeKwh:      q(".vh-home-kwh"),
      vhHomeCost:     q(".vh-home-cost"),
      vhTripKmLast:   q(".vh-trip-km-last"),
      vhTripCount:    q(".vh-trip-count"),
      vhTripKmTotal:  q(".vh-trip-km-total"),
      vhOdo:          q(".vh-odo"),
      vhEfficiency:   q(".vh-efficiency"),
      vhSavings:      q(".vh-savings"),
    };
    return wrap;
  }

  // --- Update loop ------------------------------------------------------------

  _update() {
    if (!this._built || !this._hass) return;
    if (this._view === "uebersicht") this._updateOverview();
    else if (this._view === "fahrzeuge") this._updateVehicle();
  }

  _updateOverview() {
    const r = this._r;
    if (!r.stKw) return;

    // evcc values via configured entity IDs (set in config flow, step 8/8)
    const ev = (key) => { const eid = this._eid(key); return eid ? this._raw(eid) : null; };
    const power    = parseFloat(ev("evcc_charge_power")      ?? NaN);
    const phases   = ev("evcc_phases_active");
    const phaseNum = parseInt(phases ?? "3", 10) || 3;
    const maxKw    = phaseNum * 3.68;
    const solarPct = parseFloat(ev("evcc_session_solar_pct") ?? NaN);
    const soc      = parseFloat(ev("evcc_vehicle_soc")       ?? NaN);
    const socLim   = parseFloat(ev("evcc_limit_soc")         ?? NaN);
    const rawConn  = ev("evcc_charge_status");               // binary_sensor → "on"/"off"
    const mode     = ev("evcc_mode")                         || "";
    const sessKwh  = parseFloat(ev("evcc_session_energy")    ?? NaN);
    const sessEur  = parseFloat(ev("evcc_session_price")     ?? NaN);
    const durSec   = parseFloat(ev("evcc_charge_duration")   ?? NaN);
    const tGrid    = parseFloat(ev("evcc_tariff_grid")       ?? NaN);
    const tFeedin  = parseFloat(ev("evcc_tariff_feedin")     ?? NaN);
    const totalKwh = parseFloat(ev("evcc_stat_total_kwh")    ?? NaN);
    const totalSol = parseFloat(ev("evcc_stat_solar_pct")    ?? NaN);
    const avgPrice = parseFloat(ev("evcc_stat_avg_price")    ?? NaN);
    const homeKwh  = parseFloat(this._state("home_kwh") ?? NaN);
    const homeCost = parseFloat(this._state("home_cost") ?? NaN);

    // Site-level power (W → kW). gridPower: positive = import, negative = export.
    // battPower: positive = charging, negative = discharging (providing power).
    const pvKw   = parseFloat(ev("evcc_pv_power")      ?? NaN) / 1000;
    const gridPw = parseFloat(ev("evcc_grid_power")    ?? NaN) / 1000;
    const battPw = parseFloat(ev("evcc_battery_power") ?? NaN) / 1000;

    const isCharging  = !isNaN(power) && power > 0.05;
    // Derive IEC 61851 status from connected binary_sensor + actual power
    const status = rawConn === "on" ? (isCharging ? "C" : "B") : "A";

    // ----- Status ring -----
    this._updateRing(r.stRingSolar, r.stRingGrid, power, maxKw, r.stCirc, solarPct);
    if (isCharging) {
      r.stKw.innerHTML = `${power.toFixed(1)}<span>kW</span>`;
    } else {
      r.stKw.innerHTML = `—<span>kW</span>`;
    }
    // Show actual site PV production and grid import/export
    const pvShow   = !isNaN(pvKw)   && pvKw   > 0.01;
    const gridShow = !isNaN(gridPw) && Math.abs(gridPw) > 0.01;
    r.stPwSolar.innerHTML = pvShow
      ? `${pvKw.toFixed(1)}<span class="stat-unit"> kW</span>`
      : `—<span class="stat-unit"> kW</span>`;
    r.stPwGrid.innerHTML  = gridShow
      ? `${Math.abs(gridPw).toFixed(1)}<span class="stat-unit"> kW ${gridPw < 0 ? "↑" : "↓"}</span>`
      : `—<span class="stat-unit"> kW</span>`;
    r.stPwBar.style.width = isCharging ? this._clamp(power / maxKw * 100, 0, 100) + "%" : "0%";
    r.stPwBar.style.background = (!isNaN(solarPct) && solarPct > 50) ? "#4ade80" : "var(--accent)";
    r.stPwAvail.textContent = `Max: ${maxKw.toFixed(1)} kW (${phaseNum}P)`;

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
    const MODE_LABEL = { now: "Sofort", minpv: "Min+PV", pv: "Nur PV", off: "Aus" };
    this._setChip(r.dgMode, MODE_LABEL[mode] || mode || "—",
      mode === "off" ? "warn" : mode ? "good" : "");

    const connLabel = status === "A" ? "Getrennt" : status === "B" ? "Verbunden" : "Lädt";
    const connTone  = status === "A" ? "" : status === "B" ? "warn" : "good";
    this._setChip(r.dgConn, connLabel, connTone);
    this._setChip(r.dgPhases, phases ? phases + " Ph." : "—", "");
    this._setChip(r.dgSocLim, !isNaN(socLim) ? Math.round(socLim) + " %" : "—", "");
    this._setChip(r.dgTgrid,   !isNaN(tGrid)   ? tGrid.toFixed(3)   + " €/kWh" : "—", "");
    this._setChip(r.dgTfeedin, !isNaN(tFeedin) ? tFeedin.toFixed(3) + " €/kWh" : "—", "");
    this._setChip(r.dgSessKwh, !isNaN(sessKwh) ? sessKwh.toFixed(2) + " kWh" : "—", "");
    this._setChip(r.dgSessSol, !isNaN(solarPct) ? Math.round(solarPct) + " %" : "—",
      !isNaN(solarPct) && solarPct > 50 ? "good" : "");
    this._setChip(r.dgSessEur, !isNaN(sessEur) ? sessEur.toFixed(2) + " EUR" : "—", "");

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
    this._setBar(r.sesskwhV,   r.sesskwhBar,   !isNaN(sessKwh) ? sessKwh.toFixed(2) + u("kWh") : "—",
      !isNaN(sessKwh) ? this._clamp(sessKwh / 100 * 100, 0, 100) : 0);
    this._setBar(r.sesssolarV, r.sesssolarBar, !isNaN(solarPct) ? Math.round(solarPct) + u("%") : "—",
      !isNaN(solarPct) ? this._clamp(solarPct, 0, 100) : 0);
    this._setBar(r.sesspriceV, r.sesspriceBar, !isNaN(sessEur) ? sessEur.toFixed(2) + u("EUR") : "—",
      !isNaN(sessEur) ? this._clamp(sessEur / 30 * 100, 0, 100) : 0);
    this._setBar(r.sessdurV, r.sessdurBar,
      durMin > 0 ? (durMin < 60 ? durMin + u("min") : Math.floor(durMin/60) + "h" + u("")) : "—",
      this._clamp(durMin / 480 * 100, 0, 100));

    // ----- Stats bars -----
    this._setBar(r.stattkV,   r.stattkBar,   !isNaN(totalKwh) ? totalKwh.toFixed(1) + u("kWh") : "—",
      !isNaN(totalKwh) ? this._clamp(totalKwh / 10000 * 100, 0, 100) : 0);
    this._setBar(r.stattsV,   r.stattsBar,   !isNaN(totalSol) ? Math.round(totalSol) + u("%") : "—",
      !isNaN(totalSol) ? this._clamp(totalSol, 0, 100) : 0);
    this._setBar(r.stattaV,   r.stattaBar,   !isNaN(avgPrice) ? avgPrice.toFixed(4) + u("€/kWh") : "—",
      !isNaN(avgPrice) ? this._clamp(avgPrice / 0.5 * 100, 0, 100) : 0);

    // ----- Tariff bars -----
    const maxT = Math.max(isNaN(tGrid) ? 0 : tGrid, isNaN(tFeedin) ? 0 : tFeedin, 0.5);
    this._setBar(r.tarifftgV,  r.tarifftgBar,  !isNaN(tGrid)   ? tGrid.toFixed(3)   + u("€/kWh") : "—",
      !isNaN(tGrid) ? this._clamp(tGrid / maxT * 100, 0, 100) : 0);
    this._setBar(r.tarifftfV,  r.tarifftfBar,  !isNaN(tFeedin) ? tFeedin.toFixed(3) + u("€/kWh") : "—",
      !isNaN(tFeedin) ? this._clamp(tFeedin / maxT * 100, 0, 100) : 0);

    // ----- Home bars -----
    this._setBar(r.homehkV,   r.homehkBar,   !isNaN(homeKwh)  ? homeKwh.toFixed(1)  + u("kWh") : "—",
      !isNaN(homeKwh)  ? this._clamp(homeKwh  / 10000 * 100, 0, 100) : 0);
    this._setBar(r.homehcV,   r.homehcBar,   !isNaN(homeCost) ? homeCost.toFixed(2)  + u("EUR") : "—",
      !isNaN(homeCost) ? this._clamp(homeCost / 3000 * 100, 0, 100) : 0);
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
    r.nSolar.val.textContent  = solActive ? pvKw.toFixed(1) : "—";
    r.nSolar.unit.textContent = solActive ? " kW" : "";

    // Grid node — shows import or export
    const gridActive = gridImport || gridExport;
    r.nGrid.node.classList.toggle("active", gridActive);
    r.nGrid.val.textContent  = gridActive ? Math.abs(gridPw).toFixed(1) : "—";
    r.nGrid.unit.textContent = gridActive ? " kW" : "";
    r.nGrid.badge.textContent = gridExport ? "↑ Einspeisung" : "";

    // Battery node — orange when active
    const battActive = battDisc || battChg;
    if (r.nBatt) {
      r.nBatt.node.classList.toggle("active", battActive);
      r.nBatt.val.textContent  = battActive ? Math.abs(battPw).toFixed(1) : "—";
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

  // --- Update: Fahrzeuge (unchanged) ------------------------------------------

  _updateVehicle() {
    const r = this._r;
    if (!r.vhExtKwhTotal) return;

    r.vhBadgeExt.classList.toggle("hidden", !this._isOn("pending"));
    r.vhBadgeTrip.classList.toggle("hidden", !this._isOn("trip_pending"));

    const estExt  = this._state("pending_estimate");
    const estTrip = this._state("trip_pending_estimate");
    const showEst = estExt !== null || estTrip !== null;
    r.estCard.classList.toggle("hidden", !showEst);
    r.estExtItem.classList.toggle("hidden", estExt === null);
    r.estTripItem.classList.toggle("hidden", estTrip === null);
    if (estExt !== null)  r.estExtVal.textContent  = parseFloat(estExt).toFixed(2);
    if (estTrip !== null) r.estTripVal.textContent = parseFloat(estTrip).toFixed(1);

    r.vhExtKwhTotal.textContent  = this._num("total_kwh", 1);
    r.vhExtCostTotal.textContent = this._num("total_cost", 2);
    r.vhExtCount.textContent     = this._num("count", 0);
    r.vhExtKwhLast.textContent   = this._num("last_kwh", 2);
    r.vhExtCostLast.textContent  = this._num("last_cost", 2);
    r.vhExtPriceLast.textContent = this._num("last_price", 4);
    r.vhExtDurLast.textContent   = this._duration("last_duration");
    r.vhHomeKwh.textContent      = this._num("home_kwh", 1);
    r.vhHomeCost.textContent     = this._num("home_cost", 2);
    r.vhTripKmLast.textContent   = this._num("last_trip_km", 0);
    r.vhTripCount.textContent    = this._num("trip_count", 0);
    r.vhTripKmTotal.textContent  = this._num("total_trip_km", 0);
    r.vhOdo.textContent          = this._num("odo", 0);
    r.vhEfficiency.textContent   = this._num("measured_efficiency", 1);
    r.vhSavings.textContent      = this._num("savings", 2);
  }

  // --- Styles -----------------------------------------------------------------

  _buildStyles() {
    const el = document.createElement("style");
    el.textContent = `
      :host {
        display: block; height: 100%;
        --accent: #3b82f6;
        --bg-0: var(--primary-background-color, #0f172a);
        --bg-1: var(--card-background-color, #1e293b);
        --bg-2: color-mix(in oklab, var(--bg-1) 60%, var(--bg-0));
        --ink: var(--primary-text-color, #f1f5f9);
        --ink-mid: var(--secondary-text-color, #94a3b8);
        --ink-dim: var(--disabled-text-color, #64748b);
        --line: var(--divider-color, rgba(255,255,255,0.07));
        --line-s: rgba(255,255,255,0.13);
        --radius: 14px; --pad: 20px; --gap: 14px;
        font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        color: var(--ink); background: var(--bg-0);
      }
      .app { display: flex; flex-direction: column; height: 100%; }

      /* Appbar */
      .appbar {
        display: flex; align-items: center; gap: 26px;
        height: 66px; padding: 0 30px; flex-shrink: 0;
        border-bottom: 1px solid var(--line);
        background: color-mix(in oklab, var(--bg-1) 85%, transparent);
        backdrop-filter: blur(10px);
      }
      .brand { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
      .brand .logo {
        width: 38px; height: 38px; border-radius: 11px;
        display: grid; place-items: center; cursor: pointer;
        background: var(--accent); color: #fff;
        box-shadow: 0 4px 14px oklch(0.6 0.2 ${ACCENT_H} / 0.35);
        --mdc-icon-size: 22px;
      }
      .brand .bt-name { font-size: 15px; font-weight: 700; }
      .brand .bt-sub  { font-size: 11px; color: var(--ink-dim); margin-top: 1px; }
      .tabs { display: flex; align-items: stretch; gap: 2px; height: 100%; overflow-x: auto; scrollbar-width: none; }
      .tabs::-webkit-scrollbar { display: none; }
      .tab {
        display: flex; align-items: center; gap: 8px; padding: 0 18px; height: 100%;
        border: none; background: none; cursor: pointer; color: var(--ink-mid);
        font-size: 14px; font-weight: 600; border-bottom: 2.5px solid transparent;
        transition: color 0.15s; white-space: nowrap; --mdc-icon-size: 18px;
      }
      .tab:hover { color: var(--ink); }
      .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

      /* Main scroll area */
      .main { flex: 1; overflow-y: auto; padding: 24px 28px 40px; }
      .main::-webkit-scrollbar { width: 8px; }
      .main::-webkit-scrollbar-thumb {
        background: var(--line-s); border-radius: 8px;
        border: 2px solid transparent; background-clip: content-box;
      }

      /* Cards */
      .card { background: var(--bg-1); border: 1px solid var(--line); border-radius: var(--radius); padding: var(--pad); }
      .card-head { display: flex; align-items: center; gap: 9px; margin-bottom: 16px; --mdc-icon-size: 17px; }
      .card-head h2 { font-size: 12px; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; color: var(--ink-mid); margin: 0; }
      .card-head .ic { color: var(--ink-dim); display: grid; place-items: center; }
      .divider { height: 1px; background: var(--line); margin: 14px 0; }
      .sub-head { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-dim); margin-bottom: 10px; }
      .dim { color: var(--ink-dim); font-size: 0.78rem; }
      .muted { color: var(--ink-mid); }
      .num { font-variant-numeric: tabular-nums; }
      .hidden { display: none !important; }

      /* Pill (live indicator) */
      .pill {
        display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px;
        border-radius: 999px; background: var(--bg-1); border: 1px solid var(--line);
        font-size: 12px; color: var(--ink-mid);
      }
      .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
      .dot.live { background: #4ade80; animation: mv-pulse 2.4s ease-in-out infinite; }
      @keyframes mv-pulse { 0%,100%{opacity:1} 50%{opacity:.35} }

      /* ===== Übersicht layout ===== */
      .res-stack { display: flex; flex-direction: column; gap: var(--gap); }
      .resumen-lower { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1.55fr); gap: var(--gap); align-items: stretch; }
      .charts-2x2 { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: min-content min-content; gap: var(--gap); min-width: 0; }
      .charts-2x2 > .card { min-width: 0; }
      @media (max-width: 1080px) { .resumen-lower { grid-template-columns: 1fr; } }
      @media (max-width: 720px)  { .charts-2x2 { grid-template-columns: 1fr; grid-template-rows: none; } }

      /* Status card (SOC analog) */
      .soc-card { display: flex; flex-direction: column; gap: 18px; }
      .soc-card .card-head { align-self: stretch; margin-bottom: 4px; }
      .soc-inner { display: flex; gap: 30px; align-items: stretch; }
      .soc-left  { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; flex: 0 0 auto; }
      .soc-diag  { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; justify-content: center; border-left: 1px solid var(--line); padding-left: 28px; }
      .soc-diag-title { display: flex; align-items: center; gap: 9px; margin-bottom: 8px; font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-mid); --mdc-icon-size: 16px; }
      .soc-diag-title ha-icon { color: var(--ink-dim); }
      .diag-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 28px; }
      .diag-cell { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-width: 0; padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 13px; }
      .diag-cell-label { color: var(--ink-mid); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .diag-cell .chip { flex-shrink: 0; max-width: 60%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      @media (max-width: 860px) {
        .soc-inner { flex-direction: column; align-items: center; gap: 20px; }
        .soc-diag { align-self: stretch; border-left: none; padding-left: 0; border-top: 1px solid var(--line); padding-top: 18px; }
      }
      @media (max-width: 560px) { .diag-grid { grid-template-columns: 1fr; } }

      /* Ring (SVG donut) */
      .ring { position: relative; }
      .ring svg { overflow: visible; }
      .ring-solar, .ring-grid {
        transition: stroke-dasharray 0.6s cubic-bezier(.4,0,.2,1), stroke-dashoffset 0.6s cubic-bezier(.4,0,.2,1);
      }
      .ring-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 2px; }
      .ring-val { font-size: 38px; font-weight: 700; line-height: 1; }
      .ring-val span { font-size: 0.38em; color: var(--ink-mid); margin-left: 2px; }
      .ring-sub { font-size: 11px; }

      /* Power stat blocks */
      .soc-power { width: 100%; max-width: 260px; }
      .pw-stats { display: flex; justify-content: space-between; gap: 16px; }
      .statblock { display: flex; flex-direction: column; gap: 4px; }
      .stat-label { font-size: 12px; color: var(--ink-mid); font-weight: 600; display: flex; align-items: center; gap: 6px; --mdc-icon-size: 14px; }
      .stat-value { font-weight: 700; letter-spacing: -0.02em; line-height: 1; font-size: 22px; }
      .stat-unit  { color: var(--ink-dim); font-weight: 500; font-size: 0.5em; }
      .pw-avail   { font-size: 11px; margin-top: 6px; text-align: center; }

      /* SOC bar */
      .soc-sect { width: 100%; max-width: 260px; }
      .soc-bar-hdr { font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--dim); margin-bottom: 5px; }
      .soc-bar-track { position: relative; height: 10px; border-radius: 9999px; background: var(--bg-0); border: 1px solid var(--line-s); overflow: visible; }
      .soc-bar-fill  { height: 100%; border-radius: 9999px; background: linear-gradient(90deg, var(--accent), #34d399); transition: width 0.4s ease; }
      .soc-bar-limit { display: none; position: absolute; top: -3px; width: 2px; height: 16px; background: #f59e0b; border-radius: 2px; transform: translateX(-50%); }
      .soc-labels    { display: flex; justify-content: space-between; margin-top: 6px; }
      .soc-val       { font-size: 1.3rem; font-weight: 700; }
      .soc-limit-lbl { font-size: 0.72rem; color: #f59e0b; align-self: center; }

      /* SOC bar (omnibattery) */
      .socbar { height: 8px; border-radius: 999px; background: var(--bg-2); overflow: hidden; }
      .socbar > span { display: block; height: 100%; border-radius: 999px; background: var(--accent); transition: width 0.8s cubic-bezier(.4,0,.2,1); }

      /* Chips */
      .chip { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; border: 1px solid var(--line); background: var(--bg-2); color: var(--ink-mid); }
      .chip-good { color: var(--accent); border-color: color-mix(in oklab, var(--accent) 35%, transparent); background: color-mix(in oklab, var(--accent) 12%, transparent); }
      .chip-warn { color: oklch(0.82 0.14 75); border-color: oklch(0.82 0.14 75 / 0.35); background: oklch(0.82 0.14 75 / 0.12); }
      .chip-bad  { color: oklch(0.7 0.18 25); border-color: oklch(0.7 0.18 25 / 0.4); background: oklch(0.7 0.18 25 / 0.12); }

      /* Daily bar-chart cards */
      .daily-card { align-self: start; }
      .daily-body { display: flex; flex-direction: column; gap: 10px; }
      .daily-row  { display: flex; flex-direction: column; gap: 4px; }
      .daily-head { display: flex; justify-content: space-between; font-size: 13px; font-weight: 600; }

      /* Flow card */
      .flow-card { position: relative; overflow: hidden; }
      .flow-wrap { display: grid; place-items: center; }
      .scene-stage { position: relative; width: 100%; max-width: 520px; aspect-ratio: 1; margin: 0 auto; container-type: inline-size; background: var(--bg-0); border-radius: 12px; }
      .lead-svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
      .node-dot { }
      .hub-ring { fill: var(--bg-1); stroke: var(--accent); stroke-width: 0.8; filter: drop-shadow(0 0 3px var(--accent)); }
      .lead { fill: none; stroke: #6b7280; stroke-width: 0.5; opacity: 0.5; stroke-linecap: round; stroke-linejoin: round; transition: opacity 0.4s, stroke-width 0.3s; }
      .lead.on { opacity: 0.9; stroke-width: 0.6; }
      .lead-end { fill: #9ca3af; opacity: 0.4; transition: opacity 0.4s; }
      .lead-end.on { opacity: 0.9; }
      /* Animated snake (same technique as omnibattery) */
      .lead-flow {
        fill: none; stroke: currentColor; color: var(--accent); stroke-width: 0.7;
        stroke-linecap: round; stroke-linejoin: round;
        stroke-dasharray: 38 12; stroke-dashoffset: 0; opacity: 0;
        pointer-events: none; transition: opacity 0.45s ease;
        filter: drop-shadow(0 0 0.8px currentColor) drop-shadow(0 0 2px currentColor);
      }
      .lead-flow.on { opacity: 0.95; animation: ev-snake 1.6s linear infinite; }
      @keyframes ev-snake { from { stroke-dashoffset: 0; } to { stroke-dashoffset: 50; } }
      @media (prefers-reduced-motion: reduce) { .lead-flow.on { animation: none; opacity: 0.65; } }

      /* Flow node labels */
      .scene-lbl { position: absolute; transform: translate(-50%, -50%); display: flex; flex-direction: column; align-items: center; gap: 1px; text-align: center; pointer-events: none; }
      .lbl-val { font-size: clamp(11px, 3.5cqw, 18px); font-weight: 700; color: var(--ink-mid); line-height: 1; white-space: nowrap; }
      .lbl-val .fn-unit { font-size: 0.65em; font-weight: 600; color: var(--ink-dim); margin-left: 1px; }
      .lbl-cap { font-size: clamp(7px, 1.7cqw, 9px); letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-dim); font-weight: 600; margin-top: 2px; }
      .lbl-badge { font-size: clamp(7px, 1.8cqw, 9.5px); color: var(--ink-dim); margin-top: 1px; }
      .scene-lbl.active .lbl-val { color: var(--ink); }
      .scene-lbl.active .lbl-cap { color: var(--ink-mid); }

      /* Hub center icon overlay */
      .scene-hub {
        position: absolute; left: 50%; top: 55%; transform: translate(-50%, -50%);
        width: 14cqw; height: 14cqw; border-radius: 50%;
        background: var(--bg-1); border: 2px solid var(--accent);
        box-shadow: 0 0 18px oklch(0.6 0.2 ${ACCENT_H} / 0.3);
        display: flex; align-items: center; justify-content: center;
        color: var(--accent); --mdc-icon-size: 6cqw;
      }

      /* Fahrzeuge tab */
      .tab-wrap { display: flex; flex-direction: column; gap: var(--gap); }
      .badge-row { display: flex; gap: 8px; flex-wrap: wrap; }
      .badge { display: flex; align-items: center; gap: 6px; font-size: 0.72rem; font-weight: 700; padding: 5px 12px; border-radius: 9999px; --mdc-icon-size: 14px; }
      .badge-ext  { background: #7c2d12; color: #fed7aa; border: 1px solid #9a3412; }
      .badge-trip { background: #1e3a5f; color: #bfdbfe; border: 1px solid #1d4ed8; }
      .kpi-row { display: flex; flex-wrap: wrap; gap: 12px 28px; }
      .kpi     { min-width: 60px; }
      .kv      { font-size: 1.55rem; font-weight: 700; line-height: 1.1; }
      .kl      { font-size: 0.7rem; color: var(--ink-mid); margin-top: 2px; }
      .kv.green { color: #4ade80; }
      .est-card { border-color: rgba(251,146,60,0.25); }
      .est-list  { display: flex; flex-direction: column; gap: 8px; }
      .est-item  { display: flex; align-items: center; gap: 8px; font-size: 0.88rem; }
      .est-item strong { font-size: 1rem; font-weight: 700; }
      .ci { --mdc-icon-size: 18px; }
      .ci.orange { color: #fb923c; }
      .ci.blue   { color: #60a5fa; }

      @media (max-width: 500px) {
        .appbar { padding: 0 14px; gap: 12px; }
        .brand .btext { display: none; }
        .tab { padding: 0 12px; }
        .main { padding: 16px 14px 30px; }
      }
    `;
    return el;
  }
}

customElements.define("ev-assistant-panel", EVAssistantPanel);
