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
    this._formState = {};
    this._pendChargeSig = null;
    this._pendTripSig = null;
    this._histChargeSig = null;
    this._histTripSig = null;
    this._histChargeExpanded = false;
    this._histTripExpanded = false;
    this._histHomeSig = null;
    this._histHomeExpanded = false;
    this._homeSessions = null;
    this._homeSessionsFetching = false;
    this._homeSessionsFetchedAt = 0;
    this._homeVehicleFilter = null;
    this._homeVehicleFilterInitialized = false;
    this._vehicleIdx = 0;
    this._vtBtns = [];
    this._chartPeriod = "woche";
    this._chartNavOffset = 0;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first || !this._built) { this._renderShell(); this._built = true; }
    // hass wird sehr haeufig neu gesetzt (praktisch bei jeder Sensor-Aenderung
    // im System) und _update() baut Listen-Inhalte per innerHTML neu auf, wenn
    // sich deren sig aendert -- das kann den Scroll-Container zuruecksetzen.
    // Aber: NUR eingreifen, wenn sich die Scrollposition durch _update()
    // tatsaechlich veraendert hat (seltener Rebuild-Fall) -- ein Schreiben auf
    // scrollTop bei JEDEM Tick (auch auf denselben Wert) unterbricht sonst die
    // native Traegheits-/Momentum-Scroll-Animation des Browsers -> Ruckeln.
    // JS ist single-threaded, also kann sich scrollTop zwischen den beiden
    // Messungen nur durch _update() selbst geaendert haben, nie durch
    // gleichzeitiges Scrollen der Nutzerin.
    const mainScroll = this._main ? this._main.scrollTop : null;
    const winY = window.scrollY;
    this._update();
    if (mainScroll !== null && this._main && this._main.scrollTop !== mainScroll) {
      this._main.scrollTop = mainScroll;
    }
    if (window.scrollY !== winY) {
      window.scrollTo(window.scrollX, winY);
    }
  }
  get hass() { return this._hass; }

  set panel(panel) { this._config = (panel && panel.config) || {}; }
  set narrow(v)    { this._narrow = v; }
  set route(_v)    {}

  // --- Helpers ----------------------------------------------------------------

  // Gibt die Config des aktuell ausgewählten Fahrzeugs zurück.
  // Fällt auf this._config zurück wenn kein vehicles-Array vorhanden (Rückwärtskompatibilität).
  _vehicleConf() {
    const vs = this._config.vehicles;
    if (vs && vs.length > 0) return vs[Math.min(this._vehicleIdx, vs.length - 1)];
    return this._config;
  }

  _eid(key)  { return (this._vehicleConf().entities || {})[key]; }
  _title()   { return this._config.title || "EV Assistant"; }

  // Lade-Modus (siehe const.py::resolve_lade_modus()) -- als Attribut am
  // "count"-Sensor mitgeliefert (coordinator.py::lade_modus(), sensor.py::
  // CountSensor.extra_state_attributes), kein eigener Netzwerkweg/Sensor
  // dafuer noetig. Steuert NUR Sichtbarkeit, siehe _buildOverview()/
  // _updateOverview() -- bewusst als eigene Methode, damit weitere Tabs
  // spaeter denselben Modus ohne Zusatzaufwand abfragen koennen.
  _ladeModus() {
    const eid = this._eid("count");
    const s = eid && this._hass ? this._hass.states[eid] : null;
    return (s && s.attributes && s.attributes.lade_modus) || "gemischt";
  }

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
  _fmtNum(value, decimals) {
    const v = Number(value);
    if (isNaN(v)) return "—";
    const loc = this._hass?.locale;
    const fmt = loc?.number_format;
    if (fmt === "none") return v.toFixed(decimals);
    let locale;
    if (fmt === "comma_decimal") locale = "en-US";
    else if (fmt === "decimal_comma") locale = "de";
    else if (fmt === "space_comma") locale = "fr";
    else locale = loc?.language || this._hass?.language || undefined;
    return v.toLocaleString(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  }
  _num(key, decimals = 1) {
    const v = parseFloat(this._state(key));
    if (isNaN(v)) return "—";
    return this._fmtNum(v, decimals);
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
    return this._fmtNum(v, decimals);
  }
  _clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // --- Service calls / config_entry_id -----------------------------------------

  _configEntryId() {
    const vc = this._vehicleConf();
    if (vc.config_entry_id) return vc.config_entry_id;
    const candidates = ["pending", "trip_pending", "count", "odo"];
    for (const key of candidates) {
      const eid = this._eid(key);
      if (!eid || !this._hass || !this._hass.entities) continue;
      const entry = this._hass.entities[eid];
      if (entry && entry.config_entry_id) return entry.config_entry_id;
    }
    return null;
  }

  // config_entry_id of the evcc_intg integration — tries three routes:
  // 1. Directly injected from panel config (Python sets this if evcc_intg is loaded)
  // 2. hass.entities scan (only works if display-registry includes platform+config_entry_id)
  // 3. Async entity registry lookup (see _resolveEvccEntryId)
  _evccEntryId() {
    if (this._config.evcc_entry_id) return this._config.evcc_entry_id;
    if (this._evccEntryIdCache) return this._evccEntryIdCache;
    if (!this._hass || !this._hass.entities) return null;
    for (const eid in this._hass.entities) {
      const entry = this._hass.entities[eid];
      if (entry && entry.platform === "evcc_intg" && entry.config_entry_id) return entry.config_entry_id;
    }
    return null;
  }

  // Resolves evcc entry_id via entity registry WS when hass.entities lacks platform info.
  // Result is cached in this._evccEntryIdCache so subsequent calls are synchronous.
  async _resolveEvccEntryId() {
    if (this._evccEntryIdCache) return this._evccEntryIdCache;
    if (!this._hass || !this._hass.callWS) return null;
    const entities = this._vehicleConf().entities || {};
    const keys = ["evcc_tariff_grid", "evcc_charge_power", "evcc_session_energy", "evcc_grid_power", "evcc_tariff_feedin"];
    for (const key of keys) {
      const eid = entities[key];
      if (!eid) continue;
      try {
        const reg = await this._hass.callWS({ type: "config/entity_registry/get", entity_id: eid });
        if (reg && reg.config_entry_id) {
          this._evccEntryIdCache = reg.config_entry_id;
          return reg.config_entry_id;
        }
      } catch (_) { /* try next key */ }
    }
    return null;
  }

  _call(service, data) {
    const config_entry_id = this._configEntryId();
    if (!config_entry_id) return;
    this._hass.callService("ev_assistant", service, { config_entry_id, ...data });
  }

  // --- Shell ------------------------------------------------------------------

  _renderShell() {
    this.shadowRoot.innerHTML = "";
    this.shadowRoot.appendChild(this._buildStyles());
    const app = document.createElement("div");
    app.className = "app";
    // Fahrzeugauswahl VOR der Tab-Leiste: erst das Fahrzeug waehlen, dann
    // dessen Tabs -- eigene Zeile statt Teil der App-Bar, sonst konkurriert
    // der Umschalter mit der Tab-Leiste um den Platz und schiebt hintere
    // Tabs aus dem sichtbaren (scrollbaren, aber nicht offensichtlichen)
    // Bereich.
    const vehicleBar = this._buildVehicleBar();
    if (vehicleBar) app.appendChild(vehicleBar);
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
      ["fahrzeuge",  "mdi:car-electric",           "Fahrzeug"],
      ["profil",     "mdi:calendar-week",          "Nutzungsprofil"],
      ["analyse",    "mdi:chart-line",             "Analyse"],
      ["leasing",    "mdi:file-document-outline",  "Leasing"],
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

  // Eigene Zeile unter der App-Bar, nur wenn mehr als ein Fahrzeug konfiguriert
  // ist -- wirkt global auf ALLE Tabs (siehe _switchVehicle()).
  _buildVehicleBar() {
    const vehicles = this._config.vehicles;
    this._vtBtns = [];
    if (!vehicles || vehicles.length < 2) return null;

    const row = document.createElement("div");
    row.className = "vt-bar";
    const pills = document.createElement("div");
    pills.className = "vt-pills";
    vehicles.forEach((v, idx) => {
      const btn = document.createElement("button");
      btn.className = "vt-pill" + (idx === this._vehicleIdx ? " active" : "");
      btn.textContent = v.name || v.title;
      btn.addEventListener("click", () => this._switchVehicle(idx));
      this._vtBtns.push(btn);
      pills.appendChild(btn);
    });
    row.appendChild(pills);
    return row;
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
    else if (view === "profil") this._main.appendChild(this._buildProfil());
    else if (view === "analyse") this._main.appendChild(this._buildAnalyse());
    else if (view === "leasing") this._main.appendChild(this._buildLeasing());
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

  // --- Tab: Fahrzeuge ---------------------------------------------------------

  // Umschalter sitzt global in der App-Bar (siehe _buildAppbar()) -- wirkt
  // auf ALLE Tabs, nicht nur "Fahrzeuge", da _vehicleConf()/_eid() ueberall
  // von derselben _vehicleIdx abhaengen. Deshalb wird hier der komplette
  // aktuelle Tab neu aufgebaut (nicht nur die Fahrzeugkarte), sonst wuerden
  // z.B. Analyse/Leasing beim Fahrzeugwechsel stehenbleiben.
  _switchVehicle(idx) {
    if (idx === this._vehicleIdx) return;
    this._vehicleIdx = idx;
    this._vtBtns.forEach((b, i) => b.classList.toggle("active", i === idx));
    // Fahrzeug-State zurücksetzen (evcc-Cache bleibt — gleiche Integration)
    this._homeVehicleFilter = null;
    this._homeVehicleFilterInitialized = false;
    this._histHomeSig = null;
    this._histChargeExpanded = false;
    this._histTripExpanded = false;
    this._pendChargeSig = null;
    this._pendTripSig = null;
    this._histChargeSig = null;
    this._histTripSig = null;
    this._formState = {};
    this._switchView(this._view);
    if (this._main) {
      this._main.classList.remove("vh-fade");
      void this._main.offsetWidth;
      this._main.classList.add("vh-fade");
    }
  }

  _buildVehicle() {
    const wrap = document.createElement("div");
    wrap.className = "tab-wrap";

    const content = document.createElement("div");
    content.id = "vh-content";
    wrap.appendChild(content);
    this._fillVehicleContent(content);
    return wrap;
  }

  _fillVehicleContent(container) {
    container.innerHTML = `
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
          <div class="pend-list hidden" id="est-ext-item"></div>
          <div class="pend-list hidden" id="est-trip-item"></div>
        </div>
      </div>

      <div class="card card-vehicle">
        <div class="veh-header">
          <div class="veh-name-block">
            <div class="card-head" style="margin-bottom:6px">
              <span class="ic"><ha-icon icon="mdi:car-electric"></ha-icon></span><h2>Fahrzeug</h2>
            </div>
            <div class="veh-name vh-veh-name">—</div>
          </div>
          <div class="veh-soc-block">
            <div class="veh-soc-pct"><span class="vh-soc-val">—</span><small>%</small></div>
            <div class="veh-soc-bar-wrap">
              <div class="veh-soc-bar-fill vh-soc-fill"></div>
            </div>
            <div class="veh-soc-label">SOC</div>
          </div>
        </div>
        <div class="divider"></div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv vh-odo">—</div><div class="kl">km Kilometerstand</div></div>
          <div class="kpi"><div class="kv vh-range">—</div><div class="kl">km Reichweite (geschätzt)</div></div>
          <div class="kpi"><div class="kv vh-avg-consumption">—</div><div class="kl">kWh/100km Ø Verbrauch</div></div>
          <div class="kpi"><div class="kv vh-efficiency">—</div><div class="kl">% Ladewirkungsgrad</div></div>
          <div class="kpi"><div class="kv green vh-savings">—</div><div class="kl">EUR Ersparnis ggü. Verbrenner</div></div>
        </div>
        <div class="divider"></div>
        <div class="vh-bottom-grid">
          <div class="vh-bottom-col">
            <div class="sub-head">Kilometerleistung</div>
            <div class="km-grid">
              <div class="km-col">
                <div class="km-item"><span class="km-label">Heute</span><span class="km-val vh-odo-day">—</span><span class="km-unit">km</span></div>
                <div class="km-item"><span class="km-label">Woche</span><span class="km-val vh-odo-week">—</span><span class="km-unit">km</span></div>
                <div class="km-item"><span class="km-label">Monat</span><span class="km-val vh-odo-month">—</span><span class="km-unit">km</span></div>
                <div class="km-item"><span class="km-label">Jahr</span><span class="km-val vh-odo-year">—</span><span class="km-unit">km</span></div>
              </div>
              <div class="km-col">
                <div class="km-item"><span class="km-label">Ø / Tag</span><span class="km-val vh-avg-day">—</span><span class="km-unit">km</span></div>
                <div class="km-item"><span class="km-label">Ø / Woche</span><span class="km-val vh-avg-week">—</span><span class="km-unit">km</span></div>
                <div class="km-item"><span class="km-label">Ø / Monat</span><span class="km-val vh-avg-month">—</span><span class="km-unit">km</span></div>
                <div class="km-item"><span class="km-label">Ø / Jahr</span><span class="km-val vh-avg-year">—</span><span class="km-unit">km</span></div>
                <div class="km-sep"></div>
                <div class="km-item"><span class="km-label">Erwartet KJ</span><span class="km-val vh-year-proj">—</span><span class="km-unit">km</span></div>
                <div class="km-item"><span class="km-label">Seit EZ</span><span class="km-val vh-annual-reg">—</span><span class="km-unit">km/J</span></div>
              </div>
            </div>
          </div>
          <div class="vh-bottom-divider"></div>
          <div class="vh-bottom-col">
            <div class="sub-head">Kosten</div>
            <div class="km-grid km-grid-1col">
              <div class="km-col">
                <div class="km-item"><span class="km-label">Heute</span><span class="km-val vh-cost-day">—</span><span class="km-unit">EUR</span></div>
                <div class="km-item"><span class="km-label">Woche</span><span class="km-val vh-cost-week">—</span><span class="km-unit">EUR</span></div>
                <div class="km-item"><span class="km-label">Monat</span><span class="km-val vh-cost-month">—</span><span class="km-unit">EUR</span></div>
                <div class="km-item"><span class="km-label">Jahr</span><span class="km-val vh-cost-year">—</span><span class="km-unit">EUR</span></div>
              </div>
            </div>
          </div>
          <div class="vh-bottom-divider"></div>
          <div class="vh-bottom-col">
            <div class="sub-head">Verbrenner-Vergleich</div>
            <div class="sav-grid">
              <div class="km-item"><span class="km-label">Ersparnis</span><span class="km-val green vh-sav-ersparnis">—</span><span class="km-unit">EUR</span></div>
              <div class="km-item"><span class="km-label">CO₂-Ersparnis</span><span class="km-val green vh-sav-co2">—</span><span class="km-unit">kg</span></div>
              <div class="km-sep"></div>
              <div class="km-item"><span class="km-label">EV-Kosten</span><span class="km-val vh-sav-ev-cost">—</span><span class="km-unit">EUR</span></div>
              <div class="km-item"><span class="km-label">Verbrenner</span><span class="km-val vh-sav-verb-cost">—</span><span class="km-unit">EUR</span></div>
              <div class="km-sep"></div>
              <div class="km-item"><span class="km-label">Kosten/100km EV</span><span class="km-val vh-sav-ev-per100">—</span><span class="km-unit">EUR</span></div>
              <div class="km-item"><span class="km-label">Kosten/100km Verb.</span><span class="km-val vh-sav-verb-per100">—</span><span class="km-unit">EUR</span></div>
            </div>
          </div>
        </div>
      </div>

      <div class="card card-charts">
        <div class="card-head card-head-charts">
          <span class="ic"><ha-icon icon="mdi:chart-bar"></ha-icon></span>
          <h2>Diagramme</h2>
          <div class="chart-controls">
            <div class="chart-pills">
              <button class="pill${this._chartPeriod === "woche" ? " active" : ""}" data-period="woche">Woche</button>
              <button class="pill${this._chartPeriod === "monat" ? " active" : ""}" data-period="monat">Monat</button>
              <button class="pill${this._chartPeriod === "jahr"  ? " active" : ""}" data-period="jahr">Jahr</button>
            </div>
            <div class="chart-nav" id="chart-nav">
              <button class="nav-arrow" id="chart-nav-prev">&#8249;</button>
              <span class="nav-label" id="chart-nav-label"></span>
              <button class="nav-arrow" id="chart-nav-next">&#8250;</button>
            </div>
          </div>
        </div>
        <div class="charts-grid">
          <div class="chart-col">
            <div class="chart-col-title">Ladeübersicht</div>
            <div class="chart-legend">
              <span class="cleg"><span class="cleg-dot home"></span>Heimladen</span>
              <span class="cleg"><span class="cleg-dot ext"></span>Fremdladung</span>
            </div>
            <div id="overview-chart"></div>
          </div>
          <div class="chart-col">
            <div class="chart-col-title">Kostenübersicht</div>
            <div class="chart-legend">
              <span class="cleg"><span class="cleg-dot home"></span>Heimladen</span>
              <span class="cleg"><span class="cleg-dot ext"></span>Fremdladung</span>
            </div>
            <div id="kosten-chart"></div>
          </div>
          <div class="chart-col">
            <div class="chart-col-title">Solaranteil</div>
            <div class="chart-legend">
              <span class="cleg"><span class="cleg-dot solar"></span>Solar Ø</span>
            </div>
            <div id="solar-chart"></div>
          </div>
        </div>
      </div>

      <div class="vh-3col">
        <div class="vh-col">
          <div class="card card-home">
            <div class="card-head">
              <span class="ic"><ha-icon icon="mdi:home-lightning-bolt"></ha-icon></span><h2>Heimladen</h2>
            </div>
            <div class="kpi-row">
              <div class="kpi"><div class="kv vh-home-kwh">—</div><div class="kl">kWh gesamt</div></div>
              <div class="kpi"><div class="kv vh-home-cost">—</div><div class="kl">EUR gesamt</div></div>
              <div class="kpi"><div class="kv vh-home-count">—</div><div class="kl">Ladevorgänge</div></div>
              <div class="kpi"><div class="kv vh-home-solar">—</div><div class="kl">% Solar Ø</div></div>
            </div>
            <div class="letzte-section">
              <div class="sub-head">Letzte Heimladung</div>
              <div class="kpi-row">
                <div class="kpi"><div class="kv vh-home-kwh-last">—</div><div class="kl">kWh</div></div>
                <div class="kpi"><div class="kv vh-home-cost-last">—</div><div class="kl">EUR</div></div>
                <div class="kpi"><div class="kv vh-home-solar-last">—</div><div class="kl">% Solar</div></div>
                <div class="kpi"><div class="kv vh-home-dur-last">—</div><div class="kl">Dauer</div></div>
              </div>
            </div>
            <div class="hist-section">
              <div class="hist-section-head">
                <span>Historie</span>
              </div>
              <div class="hist-list" id="hist-home-list"></div>
            </div>
          </div>
        </div>
        <div class="vh-col">
          <div class="card card-ext">
            <div class="card-head">
              <span class="ic"><ha-icon icon="mdi:ev-station"></ha-icon></span><h2>Fremdladung</h2>
            </div>
            <div class="kpi-row">
              <div class="kpi"><div class="kv vh-ext-kwh-total">—</div><div class="kl">kWh gesamt</div></div>
              <div class="kpi"><div class="kv vh-ext-cost-total">—</div><div class="kl">EUR gesamt</div></div>
              <div class="kpi"><div class="kv vh-ext-count">—</div><div class="kl">Ladevorgänge</div></div>
            </div>
            <div class="letzte-section">
              <div class="sub-head">Letzte Fremdladung</div>
              <div class="kpi-row">
                <div class="kpi"><div class="kv vh-ext-kwh-last">—</div><div class="kl">kWh</div></div>
                <div class="kpi"><div class="kv vh-ext-cost-last">—</div><div class="kl">EUR</div></div>
                <div class="kpi"><div class="kv vh-ext-price-last">—</div><div class="kl">EUR/kWh</div></div>
                <div class="kpi"><div class="kv vh-ext-duration-last">—</div><div class="kl">Dauer</div></div>
              </div>
            </div>
            <div class="hist-section">
              <div class="hist-section-head">
                <span>Historie</span>
                <button class="btn btn-ghost ext-manual-toggle"><ha-icon icon="mdi:plus" style="--mdc-icon-size:14px;vertical-align:-2px"></ha-icon> Manuell erfassen</button>
              </div>
              <div class="hist-edit-form hidden" id="ext-manual-form">
                <label>Start<input type="datetime-local" class="em-start-ts"></label>
                <label>Ende (optional)<input type="datetime-local" class="em-end-ts"></label>
                <label>kWh<input type="text" inputmode="decimal" class="em-kwh" placeholder="0,0"></label>
                <label>EUR/kWh<input type="text" inputmode="decimal" class="em-price" placeholder="0,000"></label>
                <label>SoC Start % (optional)<input type="text" inputmode="decimal" class="em-soc-start" placeholder="0"></label>
                <label>SoC Ende % (optional)<input type="text" inputmode="decimal" class="em-soc-end" placeholder="0"></label>
                <label>Startgebühr € (optional)<input type="text" inputmode="decimal" class="em-fee" placeholder="0,00"></label>
                <label>Blockiergebühr € (optional)<input type="text" inputmode="decimal" class="em-block-fee" placeholder="0,00"></label>
                <label>Zeitgebühr € (optional)<input type="text" inputmode="decimal" class="em-time-fee" placeholder="0,00"></label>
                <button class="btn btn-primary em-save" disabled>Speichern</button>
                <button class="btn btn-ghost em-cancel">Abbrechen</button>
              </div>
              <div class="hist-list" id="hist-charge-list"></div>
            </div>
          </div>
        </div>
        <div class="vh-col">
          <div class="card card-trip">
            <div class="card-head">
              <span class="ic"><ha-icon icon="mdi:book-open-page-variant"></ha-icon></span><h2>Fahrtenbuch</h2>
            </div>
            <div class="kpi-row">
              <div class="kpi"><div class="kv vh-trip-count">—</div><div class="kl">Fahrten</div></div>
              <div class="kpi"><div class="kv vh-trip-km-total">—</div><div class="kl">km gesamt</div></div>
            </div>
            <div class="letzte-section">
              <div class="sub-head">Letzte Fahrt</div>
              <div class="kpi-row">
                <div class="kpi"><div class="kv vh-trip-km-last">—</div><div class="kl">km</div></div>
                <div class="kpi"><div class="kv-sm vh-trip-route-last">—</div><div class="kl">Route</div></div>
              </div>
            </div>
            <div class="hist-section">
              <div class="hist-section-head">
                <span>Historie</span>
              </div>
              <div class="hist-list" id="hist-trip-list"></div>
            </div>
          </div>
        </div>
      </div>`;

    const q = (s) => container.querySelector(s);
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
      vhHomeKwh:       q(".vh-home-kwh"),
      vhHomeCost:      q(".vh-home-cost"),
      vhHomeCount:     q(".vh-home-count"),
      vhHomeSolar:     q(".vh-home-solar"),
      vhHomeKwhLast:   q(".vh-home-kwh-last"),
      vhHomeCostLast:  q(".vh-home-cost-last"),
      vhHomeSolarLast: q(".vh-home-solar-last"),
      vhHomeDurLast:   q(".vh-home-dur-last"),
      vhTripKmLast:    q(".vh-trip-km-last"),
      vhTripCount:     q(".vh-trip-count"),
      vhTripKmTotal:   q(".vh-trip-km-total"),
      vhTripRouteLast: q(".vh-trip-route-last"),
      vhOdo:          q(".vh-odo"),
      vhRange:        q(".vh-range"),
      vhAvgConsumption: q(".vh-avg-consumption"),
      vhOdoDay:       q(".vh-odo-day"),
      vhOdoWeek:      q(".vh-odo-week"),
      vhOdoMonth:     q(".vh-odo-month"),
      vhOdoYear:      q(".vh-odo-year"),
      vhAvgDay:       q(".vh-avg-day"),
      vhAvgWeek:      q(".vh-avg-week"),
      vhAvgMonth:     q(".vh-avg-month"),
      vhAvgYear:      q(".vh-avg-year"),
      vhYearProj:     q(".vh-year-proj"),
      vhAnnualReg:    q(".vh-annual-reg"),
      vhCostDay:      q(".vh-cost-day"),
      vhCostWeek:     q(".vh-cost-week"),
      vhCostMonth:    q(".vh-cost-month"),
      vhCostYear:     q(".vh-cost-year"),

      vhEfficiency:    q(".vh-efficiency"),
      vhSavings:       q(".vh-savings"),
      vhSavErsparnis:  q(".vh-sav-ersparnis"),
      vhSavCo2:        q(".vh-sav-co2"),
      vhSavEvCost:     q(".vh-sav-ev-cost"),
      vhSavVerbCost:   q(".vh-sav-verb-cost"),
      vhSavEvPer100:   q(".vh-sav-ev-per100"),
      vhSavVerbPer100: q(".vh-sav-verb-per100"),
      vhVehName:      q(".vh-veh-name"),
      vhSocVal:       q(".vh-soc-val"),
      vhSocFill:      q(".vh-soc-fill"),
      histChargeList: q("#hist-charge-list"),
      histTripList:   q("#hist-trip-list"),
      histHomeList:   q("#hist-home-list"),
      overviewChart:  q("#overview-chart"),
      kostenChart:    q("#kosten-chart"),
      solarChart:     q("#solar-chart"),
      chartNav:       q("#chart-nav"),
      chartNavLabel:  q("#chart-nav-label"),
      chartNavPrev:   q("#chart-nav-prev"),
      chartNavNext:   q("#chart-nav-next"),
      extManualForm:  q("#ext-manual-form"),
    };
    this._wireExtManualForm(container);
    container.querySelectorAll(".chart-pills .pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._chartPeriod = btn.dataset.period;
        this._chartNavOffset = 0;
        container.querySelectorAll(".chart-pills .pill").forEach((b) => b.classList.toggle("active", b === btn));
        this._updateChartNav();
        this._renderAllCharts();
      });
    });
    const navPrev = q("#chart-nav-prev");
    const navNext = q("#chart-nav-next");
    if (navPrev) navPrev.addEventListener("click", () => {
      this._chartNavOffset--;
      this._updateChartNav();
      this._renderAllCharts();
    });
    if (navNext) navNext.addEventListener("click", () => {
      if (this._chartNavOffset < 0) {
        this._chartNavOffset++;
        this._updateChartNav();
        this._renderAllCharts();
      }
    });
    this._updateChartNav();
    this._pendChargeSig = null;
    this._pendTripSig = null;
    this._histChargeSig = null;
    this._histTripSig = null;
    this._histHomeSig = null;
  }

  // Fremdladung komplett manuell erfassen (ohne vorherige automatische
  // Erkennung) -- log_charge unterstuetzt das schon immer (siehe
  // services.yaml: "Ohne offene Ladung wird ein Einzeleintrag angelegt"),
  // bisher gab es im Panel nur kein Formular dafuer.
  _wireExtManualForm(container) {
    const toggle = container.querySelector(".ext-manual-toggle");
    const form = this._r.extManualForm;
    if (!toggle || !form) return;
    const kwhInput      = form.querySelector(".em-kwh");
    const priceInput    = form.querySelector(".em-price");
    const socStartInput = form.querySelector(".em-soc-start");
    const socEndInput   = form.querySelector(".em-soc-end");
    const feeInput      = form.querySelector(".em-fee");
    const blockFeeInput = form.querySelector(".em-block-fee");
    const timeFeeInput  = form.querySelector(".em-time-fee");
    const startTsInput  = form.querySelector(".em-start-ts");
    const endTsInput    = form.querySelector(".em-end-ts");
    const saveBtn   = form.querySelector(".em-save");
    const cancelBtn = form.querySelector(".em-cancel");

    const updateValidity = () => {
      const kwh = parseFloat(kwhInput.value.replace(",", "."));
      const price = parseFloat(priceInput.value.replace(",", "."));
      saveBtn.disabled = isNaN(kwh) || isNaN(price);
    };
    kwhInput.addEventListener("input", updateValidity);
    priceInput.addEventListener("input", updateValidity);

    toggle.addEventListener("click", () => {
      const opening = form.classList.contains("hidden");
      form.classList.toggle("hidden");
      if (opening) {
        startTsInput.value = this._toDatetimeLocal(Math.floor(Date.now() / 1000));
        endTsInput.value = "";
        kwhInput.value = "";
        priceInput.value = "";
        socStartInput.value = "";
        socEndInput.value = "";
        feeInput.value = "";
        blockFeeInput.value = "";
        timeFeeInput.value = "";
        updateValidity();
      }
    });
    cancelBtn.addEventListener("click", () => form.classList.add("hidden"));
    saveBtn.addEventListener("click", () => {
      const kwh = parseFloat(kwhInput.value.replace(",", "."));
      const price = parseFloat(priceInput.value.replace(",", "."));
      if (isNaN(kwh) || isNaN(price)) return;
      const socStart = parseFloat(socStartInput.value.replace(",", "."));
      const socEnd = parseFloat(socEndInput.value.replace(",", "."));
      const fee = parseFloat(feeInput.value.replace(",", "."));
      const blockFee = parseFloat(blockFeeInput.value.replace(",", "."));
      const timeFee = parseFloat(timeFeeInput.value.replace(",", "."));
      const startTs = this._fromDatetimeLocal(startTsInput.value);
      const endTs = this._fromDatetimeLocal(endTsInput.value);
      const payload = { kwh, price_kwh: price };
      if (startTs != null) payload.start_ts = startTs;
      if (endTs != null) payload.end_ts = endTs;
      if (!isNaN(socStart)) payload.soc_start = socStart;
      if (!isNaN(socEnd)) payload.soc_end = socEnd;
      if (!isNaN(fee)) payload.start_fee = fee;
      if (!isNaN(blockFee)) payload.block_fee = blockFee;
      if (!isNaN(timeFee)) payload.time_fee = timeFee;
      this._call("log_charge", payload);
      form.classList.add("hidden");
    });
  }

  // --- Nutzungsprofil-Tab -------------------------------------------------

  _buildProfil() {
    const wrap = document.createElement("div");
    wrap.className = "tab-wrap";
    wrap.innerHTML = `
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:calendar-week"></ha-icon></span><h2>Nutzungsprofil</h2>
        </div>
        <div class="profil-empty hidden" id="profil-empty">
          Noch nicht genug Fahrtenbuch-Historie (mindestens 7 Tage) für ein aussagekräftiges Nutzungsprofil.
          Bestätige weiter Fahrten, das Profil füllt sich automatisch.
        </div>
        <div id="profil-content">
          <div class="profil-recommend" id="profil-recommend">
            <ha-icon class="profil-recommend-icon" id="profil-recommend-icon" icon="mdi:battery-charging"></ha-icon>
            <div class="profil-recommend-text" id="profil-recommend-text">—</div>
          </div>
          <div class="kpi-row">
            <div class="kpi"><div class="kv" id="profil-available">—</div><div class="kl">kWh verfügbar</div></div>
            <div class="kpi"><div class="kv" id="profil-need-tomorrow">—</div><div class="kl">kWh benötigt morgen</div></div>
            <div class="kpi"><div class="kv" id="profil-buffer">—</div><div class="kl">% Puffer</div></div>
            <div class="kpi hidden" id="profil-pv-forecast-kpi"><div class="kv" id="profil-pv-forecast">—</div><div class="kl">kWh PV-Prognose morgen</div></div>
          </div>
          <div class="divider"></div>
          <div class="sub-head">Ø kWh-Bedarf pro Wochentag</div>
          <div class="weekday-chart" id="profil-weekday-chart"></div>
        </div>
      </div>`;

    const q = (s) => wrap.querySelector(s);
    this._r = {
      profilEmpty:        q("#profil-empty"),
      profilContent:       q("#profil-content"),
      profilRecommendIcon: q("#profil-recommend-icon"),
      profilRecommendText: q("#profil-recommend-text"),
      profilAvailable:     q("#profil-available"),
      profilNeedTomorrow:  q("#profil-need-tomorrow"),
      profilBuffer:        q("#profil-buffer"),
      profilPvForecastKpi: q("#profil-pv-forecast-kpi"),
      profilPvForecast:    q("#profil-pv-forecast"),
      profilWeekdayChart:  q("#profil-weekday-chart"),
    };
    return wrap;
  }

  // --- Tab: Analyse ------------------------------------------------------

  _buildAnalyse() {
    const wrap = document.createElement("div");
    wrap.className = "tab-wrap";
    wrap.innerHTML = `
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:battery-heart-variant"></ha-icon></span><h2>Batteriekapazität</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv" id="analyse-capacity">—</div><div class="kl">kWh geschätzte Kapazität</div></div>
          <div class="kpi"><div class="kv" id="analyse-cycles">—</div><div class="kl">äquivalente Vollzyklen</div></div>
        </div>
        <div class="profil-empty">
          Rollierender Schnitt aus Fremd- und Heim-Ladesessions mit großem SoC-Hub. Der absolute Wert liegt
          typischerweise über der echten Kapazität (Ladeverluste nicht modelliert) — entscheidend ist der Trend
          über Monate/Jahre, nicht die einzelne Zahl. Vollzyklen aus Fahrtenbuch, Fremd- und Heim-Ladungen
          (0→100→0 wäre 1 Zyklus).
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:thermometer"></ha-icon></span><h2>Verbrauch nach Temperatur</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv" id="analyse-outside-temp">—</div><div class="kl">°C Außentemperatur aktuell</div></div>
        </div>
        <div class="divider"></div>
        <div class="profil-empty hidden" id="analyse-temp-empty">
          Noch keine Außentemperatur-Entität konfiguriert oder noch nicht genug Fahrten pro Temperaturband
          (mindestens 3) für einen verlässlichen Schnitt.
        </div>
        <div id="analyse-temp-content">
          <div class="sub-head">Ø kWh/100km je Temperaturband</div>
          <div class="weekday-chart" id="analyse-temp-chart"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:chart-donut"></ha-icon></span><h2>Ladeort-Aufschlüsselung</h2>
        </div>
        <div class="km-grid">
          <div class="km-col">
            <div class="sub-head">Heim</div>
            <div class="km-item"><span class="km-label">kWh</span><span class="km-val" id="analyse-loc-home-kwh">—</span><span class="km-unit">kWh</span></div>
            <div class="km-item"><span class="km-label">Kosten</span><span class="km-val" id="analyse-loc-home-cost">—</span><span class="km-unit">EUR</span></div>
            <div class="km-item"><span class="km-label">Anteil</span><span class="km-val" id="analyse-loc-home-pct">—</span><span class="km-unit">%</span></div>
            <div class="km-item"><span class="km-label">Ø Preis</span><span class="km-val" id="analyse-loc-home-price">—</span><span class="km-unit">EUR/kWh</span></div>
            <div class="km-item"><span class="km-label">Solaranteil</span><span class="km-val green" id="analyse-loc-home-solar">—</span><span class="km-unit">%</span></div>
          </div>
          <div class="km-col">
            <div class="sub-head">Fremd</div>
            <div class="km-item"><span class="km-label">kWh</span><span class="km-val" id="analyse-loc-ext-kwh">—</span><span class="km-unit">kWh</span></div>
            <div class="km-item"><span class="km-label">Kosten</span><span class="km-val" id="analyse-loc-ext-cost">—</span><span class="km-unit">EUR</span></div>
            <div class="km-item"><span class="km-label">Anteil</span><span class="km-val" id="analyse-loc-ext-pct">—</span><span class="km-unit">%</span></div>
            <div class="km-item"><span class="km-label">Ø Preis</span><span class="km-val" id="analyse-loc-ext-price">—</span><span class="km-unit">EUR/kWh</span></div>
          </div>
        </div>
        <div class="divider"></div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv" id="analyse-loc-eur100">—</div><div class="kl">EUR/100km gesamt (Heim + Fremd)</div></div>
        </div>
        <div class="profil-empty">
          Solaranteil nur für Heimladungen, die evcc gesteuert hat. EUR/100km ist fahrzeugweit über die
          Gesamtstrecke — km lassen sich keinem einzelnen Ladeort zuordnen.
        </div>
      </div>`;

    const q = (s) => wrap.querySelector(s);
    this._r = {
      analyseCapacity:    q("#analyse-capacity"),
      analyseCycles:      q("#analyse-cycles"),
      analyseOutsideTemp: q("#analyse-outside-temp"),
      analyseTempEmpty:   q("#analyse-temp-empty"),
      analyseTempContent: q("#analyse-temp-content"),
      analyseTempChart:   q("#analyse-temp-chart"),
      analyseLocHomeKwh:   q("#analyse-loc-home-kwh"),
      analyseLocHomeCost:  q("#analyse-loc-home-cost"),
      analyseLocHomePct:   q("#analyse-loc-home-pct"),
      analyseLocHomePrice: q("#analyse-loc-home-price"),
      analyseLocHomeSolar: q("#analyse-loc-home-solar"),
      analyseLocExtKwh:    q("#analyse-loc-ext-kwh"),
      analyseLocExtCost:   q("#analyse-loc-ext-cost"),
      analyseLocExtPct:    q("#analyse-loc-ext-pct"),
      analyseLocExtPrice:  q("#analyse-loc-ext-price"),
      analyseLocEur100:    q("#analyse-loc-eur100"),
    };
    return wrap;
  }

  _updateProfil() {
    const r = this._r;
    if (!r.profilRecommendText) return;

    const profile = this._eid("usage_profile") ? this._hass.states[this._eid("usage_profile")] : null;
    const hasProfile = !!(profile && profile.attributes && profile.attributes.montag !== undefined);
    r.profilEmpty.classList.toggle("hidden", hasProfile);
    r.profilContent.classList.toggle("hidden", !hasProfile);
    if (!hasProfile) return;

    const WEEKDAYS = [
      ["montag", "Mo"], ["dienstag", "Di"], ["mittwoch", "Mi"], ["donnerstag", "Do"],
      ["freitag", "Fr"], ["samstag", "Sa"], ["sonntag", "So"],
    ];
    const values = WEEKDAYS.map(([key]) => parseFloat(profile.attributes[key]) || 0);
    const maxVal = Math.max(...values, 0.1);
    const todayWd = new Date().getDay(); // 0=Sonntag..6=Samstag (JS-Konvention)
    const todayIdx = todayWd === 0 ? 6 : todayWd - 1; // -> 0=Montag..6=Sonntag
    const tomorrowIdx = (todayIdx + 1) % 7;

    r.profilWeekdayChart.innerHTML = WEEKDAYS.map(([, label], i) => {
      const pct = Math.max(2, Math.round((values[i] / maxVal) * 100));
      const cls = i === tomorrowIdx ? "wd-bar tomorrow" : (i === todayIdx ? "wd-bar today" : "wd-bar");
      return `
        <div class="wd-col">
          <div class="wd-val">${this._fmtNum(values[i], 1)}</div>
          <div class="wd-bar-track"><div class="${cls}" style="height:${pct}%"></div></div>
          <div class="wd-label">${label}</div>
        </div>`;
    }).join("");

    const availEid = this._eid("available_kwh");
    const available = availEid ? parseFloat(this._raw(availEid)) : NaN;
    r.profilAvailable.textContent = isNaN(available) ? "—" : this._fmtNum(available, 1);

    const needEid = this._eid("usage_profile_tomorrow");
    const needState = needEid ? this._hass.states[needEid] : null;
    const need = needState ? parseFloat(needState.state) : NaN;
    r.profilNeedTomorrow.textContent = isNaN(need) ? "—" : this._fmtNum(need, 1);
    const bufferPct = needState && needState.attributes ? parseFloat(needState.attributes.puffer_prozent) : NaN;
    r.profilBuffer.textContent = isNaN(bufferPct) ? "—" : this._fmtNum(bufferPct, 0);

    const recEid = this._eid("charge_before_pv_recommended");
    const recState = recEid ? this._hass.states[recEid] : null;
    const pvForecast = recState && recState.attributes ? parseFloat(recState.attributes.pv_prognose_morgen_kwh) : NaN;
    const hasPvForecast = !isNaN(pvForecast);
    r.profilPvForecastKpi.classList.toggle("hidden", !hasPvForecast);
    if (hasPvForecast) r.profilPvForecast.textContent = this._fmtNum(pvForecast, 1);

    if (!recState || recState.state === "unknown" || recState.state === "unavailable") {
      r.profilRecommendIcon.setAttribute("icon", "mdi:battery-unknown");
      r.profilRecommendText.textContent = "Noch keine Empfehlung möglich.";
      r.profilRecommendText.parentElement.classList.remove("rec-yes", "rec-no");
    } else if (recState.state === "on") {
      r.profilRecommendIcon.setAttribute("icon", "mdi:battery-alert");
      r.profilRecommendText.textContent = hasPvForecast
        ? "Laden empfehlenswert — Akkustand plus PV-Prognose für morgen reichen laut Profil nicht sicher aus."
        : "Laden empfehlenswert — der aktuelle Akkustand reicht laut Profil nicht sicher bis morgen.";
      r.profilRecommendText.parentElement.classList.add("rec-yes");
      r.profilRecommendText.parentElement.classList.remove("rec-no");
    } else {
      r.profilRecommendIcon.setAttribute("icon", "mdi:battery-charging-100");
      r.profilRecommendText.textContent = hasPvForecast
        ? "Reicht bis morgen — Akkustand plus PV-Prognose decken den Bedarf, Laden kann warten."
        : "Reicht bis morgen — Laden kann warten, z.B. auf PV-Überschuss.";
      r.profilRecommendText.parentElement.classList.add("rec-no");
      r.profilRecommendText.parentElement.classList.remove("rec-yes");
    }
  }

  _updateAnalyse() {
    const r = this._r;
    if (!r.analyseCapacity) return;

    r.analyseCapacity.textContent = this._num("battery_capacity", 1);
    r.analyseCycles.textContent = this._num("equivalent_full_cycles", 1);

    const locEid = this._eid("charging_location_breakdown");
    const locState = locEid ? this._hass.states[locEid] : null;
    const locAttrs = (locState && locState.attributes) || {};
    const fmt = (v, decimals = 1) => (typeof v === "number" ? this._fmtNum(v, decimals) : "—");
    const heim = locAttrs.heim || {};
    const fremd = locAttrs.fremd || {};
    r.analyseLocHomeKwh.textContent = fmt(heim.kwh, 1);
    r.analyseLocHomeCost.textContent = fmt(heim.kosten, 2);
    r.analyseLocHomePct.textContent = fmt(heim.kwh_anteil_pct, 1);
    r.analyseLocHomePrice.textContent = fmt(heim.preis_je_kwh, 3);
    r.analyseLocHomeSolar.textContent = fmt(heim.solar_pct, 1);
    r.analyseLocExtKwh.textContent = fmt(fremd.kwh, 1);
    r.analyseLocExtCost.textContent = fmt(fremd.kosten, 2);
    r.analyseLocExtPct.textContent = fmt(fremd.kwh_anteil_pct, 1);
    r.analyseLocExtPrice.textContent = fmt(fremd.preis_je_kwh, 3);
    r.analyseLocEur100.textContent = fmt(locAttrs.eur_je_100km, 2);

    const rangeEid = this._eid("range_estimate");
    const rangeState = rangeEid ? this._hass.states[rangeEid] : null;
    const attrs = (rangeState && rangeState.attributes) || {};
    const outsideTemp = attrs.aussentemperatur;
    r.analyseOutsideTemp.textContent = typeof outsideTemp === "number" ? this._fmtNum(outsideTemp, 1) : "—";
    const buckets = attrs.verbrauch_nach_temperatur || null;
    const activeBucket = attrs.temperaturband_aktuell || null;
    const hasBuckets = !!(buckets && Object.keys(buckets).length > 0);
    r.analyseTempEmpty.classList.toggle("hidden", hasBuckets);
    r.analyseTempContent.classList.toggle("hidden", !hasBuckets);
    if (!hasBuckets) return;

    const ORDER = ["<0°C", "0-10°C", "10-20°C", ">20°C"];
    const labels = ORDER.filter((k) => buckets[k] !== undefined);
    const values = labels.map((k) => buckets[k]);
    const maxVal = Math.max(...values, 0.1);

    r.analyseTempChart.innerHTML = labels.map((label, i) => {
      const pct = Math.max(2, Math.round((values[i] / maxVal) * 100));
      const cls = label === activeBucket ? "wd-bar today" : "wd-bar";
      return `
        <div class="wd-col">
          <div class="wd-val">${this._fmtNum(values[i], 1)}</div>
          <div class="wd-bar-track"><div class="${cls}" style="height:${pct}%"></div></div>
          <div class="wd-label">${label}</div>
        </div>`;
    }).join("");
  }

  // --- Tab: Leasing --------------------------------------------------------

  _buildLeasing() {
    const wrap = document.createElement("div");
    wrap.className = "tab-wrap";
    wrap.innerHTML = `
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:file-document-outline"></ha-icon></span><h2>Leasing-Kilometerbudget</h2>
        </div>
        <div class="profil-empty" id="leasing-empty">
          Noch nicht eingerichtet — hinterlege Vertrags-Kilometerstand, Enddatum und Gesamt-km in den Optionen,
          um hier eine Soll-Ist-Prognose zu sehen.
        </div>
        <div class="hidden" id="leasing-content">
          <div class="kpi-row">
            <div class="kpi"><div class="kv" id="leasing-km-vor-ruecklauf">—</div><div class="kl">km vor Rücklauf (Ist − Soll)</div></div>
            <div class="kpi"><div class="kv" id="leasing-status">—</div><div class="kl">Status</div></div>
            <div class="kpi"><div class="kv" id="leasing-resttage">—</div><div class="kl">Tage bis Vertragsende</div></div>
            <div class="kpi"><div class="kv" id="leasing-tagesbudget">—</div><div class="kl">km/Tag Restbudget</div></div>
          </div>
          <div class="sub-head" style="margin-top:6px" id="leasing-bar-caption">Kilometerstand — 0 von 0 km</div>
          <div class="veh-soc-bar-wrap" id="leasing-bar-wrap" style="width:100%;position:relative">
            <div class="veh-soc-bar-fill" id="leasing-bar-fill"></div>
            <div id="leasing-bar-marker" style="position:absolute;top:0;bottom:0;width:2px;background:rgba(255,255,255,0.7)"></div>
          </div>
          <div class="profil-empty" style="padding:4px 0 0;font-size:0.72rem">Graue Linie = Soll-Stand heute (linearer Vertrags-Plan).</div>
          <div class="km-grid" style="margin-top:8px">
            <div class="km-col">
              <div class="sub-head">Vertrag</div>
              <div class="km-item"><span class="km-label">Beginn</span><span class="km-val" id="leasing-start-datum">—</span><span class="km-unit"></span></div>
              <div class="km-item"><span class="km-label">Ende</span><span class="km-val" id="leasing-end-datum">—</span><span class="km-unit"></span></div>
              <div class="km-item"><span class="km-label">Laufzeit</span><span class="km-val" id="leasing-laufzeit">—</span><span class="km-unit"></span></div>
              <div class="km-item"><span class="km-label">Kilometerstand bei Beginn</span><span class="km-val" id="leasing-start-km">—</span><span class="km-unit">km</span></div>
              <div class="km-item"><span class="km-label">Inklusive</span><span class="km-val" id="leasing-inkl-km">—</span><span class="km-unit">km</span></div>
            </div>
            <div class="km-col">
              <div class="sub-head">Kilometer</div>
              <div class="km-item"><span class="km-label">Seit Beginn gefahren</span><span class="km-val" id="leasing-gefahren">—</span><span class="km-unit">km</span></div>
              <div class="km-item"><span class="km-label">Soll bis heute</span><span class="km-val" id="leasing-soll">—</span><span class="km-unit">km</span></div>
              <div class="km-item"><span class="km-label">Noch erlaubt bis Ende</span><span class="km-val" id="leasing-resterlaubt">—</span><span class="km-unit">km</span></div>
              <div class="km-item hidden" id="leasing-preis-mehr-row"><span class="km-label">Preis Mehr-km</span><span class="km-val" id="leasing-preis-mehr">—</span><span class="km-unit">EUR/km</span></div>
              <div class="km-item hidden" id="leasing-preis-minder-row"><span class="km-label">Preis Minder-km</span><span class="km-val" id="leasing-preis-minder">—</span><span class="km-unit">EUR/km</span></div>
            </div>
          </div>
          <div class="divider"></div>
          <div class="km-grid">
            <div class="km-col">
              <div class="sub-head">Linear — Ø seit Vertragsbeginn</div>
              <div class="km-item"><span class="km-label">Ø km/Tag</span><span class="km-val" id="leasing-lin-tempo">—</span><span class="km-unit">km/Tag</span></div>
              <div class="km-item"><span class="km-label">Erwarteter Endstand</span><span class="km-val" id="leasing-lin-end">—</span><span class="km-unit">km</span></div>
              <div class="km-item"><span class="km-label">Erwartete Mehr/Minder-km</span><span class="km-val" id="leasing-lin-diff">—</span><span class="km-unit">km</span></div>
              <div class="km-item hidden" id="leasing-lin-eur-row"><span class="km-label" id="leasing-lin-eur-label">Kosten</span><span class="km-val" id="leasing-lin-eur">—</span><span class="km-unit">EUR</span></div>
            </div>
            <div class="km-col">
              <div class="sub-head">Rollierend — Ø letzte 30 Fahrtage</div>
              <div class="km-item"><span class="km-label">Ø km/Tag</span><span class="km-val" id="leasing-roll-tempo">—</span><span class="km-unit">km/Tag</span></div>
              <div class="km-item"><span class="km-label">Erwarteter Endstand</span><span class="km-val" id="leasing-roll-end">—</span><span class="km-unit">km</span></div>
              <div class="km-item"><span class="km-label">Erwartete Mehr/Minder-km</span><span class="km-val" id="leasing-roll-diff">—</span><span class="km-unit">km</span></div>
              <div class="km-item hidden" id="leasing-roll-eur-row"><span class="km-label" id="leasing-roll-eur-label">Kosten</span><span class="km-val" id="leasing-roll-eur">—</span><span class="km-unit">EUR</span></div>
            </div>
          </div>
          <div class="profil-empty">
            Beide Projektionen sind Schätzungen: linear rechnet den Gesamtschnitt seit Vertragsbeginn hoch,
            rollierend die letzten 30 Fahrtage — reagiert schneller auf verändertes Fahrverhalten. Eine
            Gutschrift für Minderkilometer erscheint nur, wenn dafür ein Preis hinterlegt ist (viele Verträge
            erstatten das nicht).
          </div>
        </div>
      </div>`;

    const q = (s) => wrap.querySelector(s);
    this._r = {
      leasingEmpty:         q("#leasing-empty"),
      leasingContent:       q("#leasing-content"),
      leasingKmVorRuecklauf: q("#leasing-km-vor-ruecklauf"),
      leasingStatus:        q("#leasing-status"),
      leasingResttage:      q("#leasing-resttage"),
      leasingTagesbudget:   q("#leasing-tagesbudget"),
      leasingBarCaption:    q("#leasing-bar-caption"),
      leasingBarFill:       q("#leasing-bar-fill"),
      leasingBarMarker:     q("#leasing-bar-marker"),
      leasingStartDatum:    q("#leasing-start-datum"),
      leasingEndDatum:      q("#leasing-end-datum"),
      leasingLaufzeit:      q("#leasing-laufzeit"),
      leasingStartKm:       q("#leasing-start-km"),
      leasingInklKm:        q("#leasing-inkl-km"),
      leasingGefahren:      q("#leasing-gefahren"),
      leasingSoll:          q("#leasing-soll"),
      leasingResterlaubt:   q("#leasing-resterlaubt"),
      leasingPreisMehrRow:  q("#leasing-preis-mehr-row"),
      leasingPreisMehr:     q("#leasing-preis-mehr"),
      leasingPreisMinderRow: q("#leasing-preis-minder-row"),
      leasingPreisMinder:   q("#leasing-preis-minder"),
      leasingLinTempo:      q("#leasing-lin-tempo"),
      leasingLinEnd:        q("#leasing-lin-end"),
      leasingLinDiff:       q("#leasing-lin-diff"),
      leasingLinEurRow:     q("#leasing-lin-eur-row"),
      leasingLinEurLabel:   q("#leasing-lin-eur-label"),
      leasingLinEur:        q("#leasing-lin-eur"),
      leasingRollTempo:     q("#leasing-roll-tempo"),
      leasingRollEnd:       q("#leasing-roll-end"),
      leasingRollDiff:      q("#leasing-roll-diff"),
      leasingRollEurRow:    q("#leasing-roll-eur-row"),
      leasingRollEurLabel:  q("#leasing-roll-eur-label"),
      leasingRollEur:       q("#leasing-roll-eur"),
    };
    return wrap;
  }

  _updateLeasing() {
    const r = this._r;
    if (!r.leasingContent) return;

    const eid = this._eid("leasing_km_vor_ruecklauf");
    const state = eid ? this._hass.states[eid] : null;
    const attrs = (state && state.attributes) || {};
    const configured = !!(state && state.state !== "unavailable" && state.state !== "unknown");
    r.leasingEmpty.classList.toggle("hidden", configured);
    r.leasingContent.classList.toggle("hidden", !configured);
    if (!configured) return;

    const STATUS_LABELS = { im_budget: "Im Budget", knapp: "Knapp", ueber: "Über Budget" };
    const STATUS_COLORS = { im_budget: "#4ade80", knapp: "#f97316", ueber: "#ef4444" };
    const status = attrs.status || null;

    const km = parseFloat(state.state);
    r.leasingKmVorRuecklauf.textContent = isNaN(km) ? "—" : `${km > 0 ? "+" : ""}${this._fmtNum(km, 1)}`;
    r.leasingStatus.textContent = STATUS_LABELS[status] || "—";
    r.leasingStatus.style.color = STATUS_COLORS[status] || "";

    const resttage = attrs.verbleibende_tage;
    r.leasingResttage.textContent = typeof resttage === "number" ? this._fmtNum(resttage, 0) : "—";
    const tagesbudget = attrs.verbleibendes_tagesbudget_km;
    r.leasingTagesbudget.textContent = typeof tagesbudget === "number" ? this._fmtNum(tagesbudget, 1) : "—";

    const fmtDate = (iso) => {
      if (!iso) return "—";
      const d = new Date(iso);
      return isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-DE");
    };
    r.leasingStartDatum.textContent = fmtDate(attrs.vertrag_start_datum);
    r.leasingEndDatum.textContent = fmtDate(attrs.vertrag_end_datum);
    const vergangeneTage = attrs.vergangene_tage;
    const vertragTage = attrs.vertrag_tage;
    r.leasingLaufzeit.textContent = (typeof vergangeneTage === "number" && typeof vertragTage === "number")
      ? `Tag ${this._fmtNum(vergangeneTage, 0)} von ${this._fmtNum(vertragTage, 0)}`
      : "—";
    r.leasingStartKm.textContent = typeof attrs.vertrag_start_km === "number" ? this._fmtNum(attrs.vertrag_start_km, 0) : "—";
    r.leasingInklKm.textContent = typeof attrs.vertrag_inkl_km === "number" ? this._fmtNum(attrs.vertrag_inkl_km, 0) : "—";

    const gefahren = attrs.gefahrene_vertrags_km;
    const soll = attrs.soll_km_bis_heute;
    r.leasingGefahren.textContent = typeof gefahren === "number" ? this._fmtNum(gefahren, 1) : "—";
    r.leasingSoll.textContent = typeof soll === "number" ? this._fmtNum(soll, 1) : "—";
    const resterlaubt = attrs.resterlaubte_km;
    r.leasingResterlaubt.textContent = typeof resterlaubt === "number" ? this._fmtNum(resterlaubt, 1) : "—";

    const hasPreisMehr = typeof attrs.preis_mehr_km === "number";
    r.leasingPreisMehrRow.classList.toggle("hidden", !hasPreisMehr);
    if (hasPreisMehr) r.leasingPreisMehr.textContent = this._fmtNum(attrs.preis_mehr_km, 2);
    const hasPreisMinder = typeof attrs.preis_minder_km === "number";
    r.leasingPreisMinderRow.classList.toggle("hidden", !hasPreisMinder);
    if (hasPreisMinder) r.leasingPreisMinder.textContent = this._fmtNum(attrs.preis_minder_km, 2);

    const inklKm = attrs.vertrag_inkl_km;
    const hasInklKm = typeof inklKm === "number" && inklKm > 0;
    const fillPct = hasInklKm && typeof gefahren === "number" ? this._clamp((gefahren / inklKm) * 100, 0, 100) : 0;
    const markerPct = hasInklKm && typeof soll === "number" ? this._clamp((soll / inklKm) * 100, 0, 100) : null;
    r.leasingBarFill.style.width = `${fillPct}%`;
    r.leasingBarFill.style.background = STATUS_COLORS[status] || "var(--accent)";
    r.leasingBarMarker.style.display = markerPct === null ? "none" : "block";
    if (markerPct !== null) r.leasingBarMarker.style.left = `${markerPct}%`;
    if (hasInklKm && typeof gefahren === "number") {
      const usedPct = this._fmtNum((gefahren / inklKm) * 100, 1);
      r.leasingBarCaption.textContent =
        `Kilometerstand — ${this._fmtNum(gefahren, 0)} von ${this._fmtNum(inklKm, 0)} km (${usedPct} %)`;
    } else {
      r.leasingBarCaption.textContent = "Kilometerstand";
    }

    const fillProjection = (proj, tempoEl, endEl, diffEl, eurRowEl, eurLabelEl, eurEl) => {
      if (!proj) {
        tempoEl.textContent = "—";
        endEl.textContent = "—";
        diffEl.textContent = "—";
        eurRowEl.classList.add("hidden");
        return;
      }
      tempoEl.textContent = this._fmtNum(proj.tempo_km_pro_tag, 1);
      endEl.textContent = this._fmtNum(proj.erwartete_end_km, 0);
      const diff = proj.erwartete_mehr_bzw_minder_km;
      diffEl.textContent = typeof diff === "number" ? `${diff > 0 ? "+" : ""}${this._fmtNum(diff, 0)}` : "—";
      if (typeof proj.mehrkosten_eur === "number") {
        eurRowEl.classList.remove("hidden");
        eurLabelEl.textContent = "Mehrkosten";
        eurEl.textContent = this._fmtNum(proj.mehrkosten_eur, 2);
      } else if (typeof proj.gutschrift_eur === "number") {
        eurRowEl.classList.remove("hidden");
        eurLabelEl.textContent = "Gutschrift";
        eurEl.textContent = this._fmtNum(proj.gutschrift_eur, 2);
      } else {
        eurRowEl.classList.add("hidden");
      }
    };

    fillProjection(
      attrs.linear, r.leasingLinTempo, r.leasingLinEnd, r.leasingLinDiff,
      r.leasingLinEurRow, r.leasingLinEurLabel, r.leasingLinEur,
    );
    fillProjection(
      attrs.rollierend, r.leasingRollTempo, r.leasingRollEnd, r.leasingRollDiff,
      r.leasingRollEurRow, r.leasingRollEurLabel, r.leasingRollEur,
    );
  }

  // --- Update loop ------------------------------------------------------------

  _update() {
    if (!this._built || !this._hass) return;
    if (this._view === "uebersicht") this._updateOverview();
    else if (this._view === "fahrzeuge") this._updateVehicle();
    else if (this._view === "profil") this._updateProfil();
    else if (this._view === "analyse") this._updateAnalyse();
    else if (this._view === "leasing") this._updateLeasing();
  }

  _updateOverview() {
    if (this._ladeModus() === "nur_auswaerts") {
      this._updateOverviewAuswaerts();
      return;
    }
    const r = this._r;
    if (!r.stKw) return;

    // evcc values via configured entity IDs (set in config flow, step 9/9)
    const ev = (key) => { const eid = this._eid(key); return eid ? this._raw(eid) : null; };
    const power    = parseFloat(ev("evcc_charge_power")      ?? NaN);
    const phases   = ev("evcc_phases_active");
    const phaseNum = parseInt(phases ?? "3", 10) || 3;
    const maxKw    = phaseNum * 3.68;
    const solarPct = parseFloat(ev("evcc_session_solar_pct") ?? NaN);
    const socEid   = this._eid("soc_entity");
    const soc      = socEid ? parseFloat(this._raw(socEid) ?? NaN) : parseFloat(ev("evcc_vehicle_soc") ?? NaN);
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
    const MODE_LABEL = { now: "Sofort", minpv: "Min+PV", pv: "Nur PV", off: "Aus" };
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

  // --- Update: Fahrzeuge (unchanged) ------------------------------------------

  _updateVehicle() {
    const r = this._r;
    if (!r.vhExtKwhTotal) return;

    r.vhBadgeExt.classList.toggle("hidden", !this._isOn("pending"));
    r.vhBadgeTrip.classList.toggle("hidden", !this._isOn("trip_pending"));

    const pendingCharges = this._pendingList("pending", "offene_ladungen");
    const pendingTrips = this._pendingList("trip_pending", "offene_fahrten");
    const showEst = pendingCharges.length > 0 || pendingTrips.length > 0;
    r.estCard.classList.toggle("hidden", !showEst);
    r.estExtItem.classList.toggle("hidden", pendingCharges.length === 0);
    r.estTripItem.classList.toggle("hidden", pendingTrips.length === 0);
    this._renderPendingCharges(pendingCharges);
    this._renderPendingTrips(pendingTrips);
    this._renderChargeHistory();
    this._renderTripHistory();
    // evcc-Sessions kommen per WS-Abruf (keine reaktive hass.states-Aktualisierung wie
    // sonst) — daher alle 5 Minuten neu holen, damit neu abgeschlossene Heimladungen
    // auftauchen, ohne bei jedem hass-Update (praktisch dauernd) nachzufragen.
    if (this._homeSessions === null || Date.now() - this._homeSessionsFetchedAt > 300000) {
      this._fetchHomeSessions();
    } else {
      this._renderHomeHistory();
    }

    r.vhExtKwhTotal.textContent  = this._num("total_kwh", 1);
    r.vhExtCostTotal.textContent = this._num("total_cost", 2);
    r.vhExtCount.textContent     = this._num("count", 0);
    r.vhExtKwhLast.textContent   = this._num("last_kwh", 2);
    r.vhExtCostLast.textContent  = this._num("last_cost", 2);
    r.vhExtPriceLast.textContent = this._num("last_price", 4);
    r.vhExtDurLast.textContent   = this._duration("last_duration");
    r.vhHomeKwh.textContent      = this._num("home_kwh", 1);
    r.vhHomeCost.textContent     = this._num("home_cost", 2);
    r.vhTripCount.textContent    = this._num("trip_count", 0);
    this._renderAllCharts();
    r.vhTripKmTotal.textContent  = this._num("total_trip_km", 0);
    r.vhOdo.textContent          = this._num("odo", 0);
    r.vhRange.textContent       = this._num("range_estimate", 0);
    r.vhAvgConsumption.textContent = this._num("vehicle_avg_consumption", 1);
    r.vhOdoDay.textContent       = this._num("odo_day_km", 0);
    r.vhOdoWeek.textContent      = this._num("odo_week_km", 0);
    r.vhOdoMonth.textContent     = this._num("odo_month_km", 0);
    r.vhOdoYear.textContent      = this._num("odo_year_km", 0);
    r.vhAvgDay.textContent       = this._num("odo_avg_day", 0);
    r.vhAvgWeek.textContent      = this._num("odo_avg_week", 0);
    r.vhAvgMonth.textContent     = this._num("odo_avg_month", 0);
    r.vhAvgYear.textContent      = this._num("odo_avg_year", 0);
    r.vhYearProj.textContent     = this._num("odo_year_projected", 0);
    r.vhAnnualReg.textContent    = this._num("odo_annual_from_reg", 0);
    r.vhCostDay.textContent      = this._num("cost_day", 2);
    r.vhCostWeek.textContent     = this._num("cost_week", 2);
    r.vhCostMonth.textContent    = this._num("cost_month", 2);
    r.vhCostYear.textContent     = this._num("cost_year", 2);
    r.vhEfficiency.textContent   = this._num("measured_efficiency", 1);
    r.vhSavings.textContent      = this._num("savings", 2);

    // Verbrenner-Vergleich aus savings-Sensor-Attributen
    {
      const savEid = this._eid("savings");
      const savState = savEid && this._hass ? this._hass.states[savEid] : null;
      const attr = savState ? (savState.attributes || {}) : {};
      const ersparnis   = parseFloat(savState ? savState.state : NaN);
      const evCost      = parseFloat(attr.kosten_ev_gesamt);
      const verbCost    = parseFloat(attr.kosten_verbrenner_geschaetzt);
      const gefahrenKm  = parseFloat(attr.gefahrene_km);
      const fmt2 = (v) => isNaN(v) ? "—" : this._fmtNum(v, 2);
      r.vhSavErsparnis.textContent  = fmt2(ersparnis);
      r.vhSavCo2.textContent        = this._num("co2_savings", 1);
      r.vhSavEvCost.textContent     = fmt2(evCost);
      r.vhSavVerbCost.textContent   = fmt2(verbCost);
      r.vhSavEvPer100.textContent   = (!isNaN(evCost) && !isNaN(gefahrenKm) && gefahrenKm > 0)
        ? this._fmtNum(evCost / gefahrenKm * 100, 2) : "—";
      r.vhSavVerbPer100.textContent = (!isNaN(verbCost) && !isNaN(gefahrenKm) && gefahrenKm > 0)
        ? this._fmtNum(verbCost / gefahrenKm * 100, 2) : "—";
    }

    // Fahrzeugname
    if (r.vhVehName) {
      r.vhVehName.textContent = this._vehicleConf().name || "—";
    }

    // SOC — von der Fahrzeug-eigenen SoC-Entitaet (Schritt 1, immer konfiguriert),
    // nicht von evcc_vehicle_soc (optional, evcc-Namensschema-abhaengig).
    const socEid = this._eid("soc_entity");
    const socState = socEid && this._hass ? this._hass.states[socEid] : null;
    const soc = socState ? parseFloat(socState.state) : null;
    if (r.vhSocVal) r.vhSocVal.textContent = soc != null && !isNaN(soc) ? Math.round(soc) : "—";
    if (r.vhSocFill && soc != null && !isNaN(soc)) {
      r.vhSocFill.style.width = `${Math.max(0, Math.min(100, soc))}%`;
      r.vhSocFill.style.background = soc < 20 ? "#ef4444" : soc < 40 ? "#f97316" : "var(--accent)";
    }

    // Letzte Fahrt aus Fahrtenbuch-Attribut
    const tripEid = this._eid("last_trip_km");
    const tripState = tripEid && this._hass ? this._hass.states[tripEid] : null;
    const trips = tripState && Array.isArray((tripState.attributes || {}).fahrtenbuch)
      ? tripState.attributes.fahrtenbuch : [];
    const lastTrip = trips.length > 0 ? trips[0] : null;
    r.vhTripKmLast.textContent   = lastTrip ? this._fmtNum(lastTrip.km, 1) : "—";
    r.vhTripRouteLast.textContent = lastTrip ? `${lastTrip.start_ort} → ${lastTrip.end_ort}` : "—";
  }

  // --- Pending items: confirm/discard ------------------------------------------

  _pendingList(binaryKey, attrKey) {
    const eid = this._eid(binaryKey);
    if (!eid || !this._hass) return [];
    const s = this._hass.states[eid];
    if (!s) return [];
    const list = (s.attributes || {})[attrKey];
    return Array.isArray(list) ? list : [];
  }

  _fmtDate(ts) {
    if (ts === null || ts === undefined) return "—";
    const d = new Date(ts * 1000);
    return d.toLocaleDateString("de-DE") + " " + d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  }

  _fmtTime(ts) {
    if (ts === null || ts === undefined) return null;
    return new Date(ts * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  }

  // Unix-Timestamp (s) <-> <input type="datetime-local">-Wert, jeweils in
  // Browser-Lokalzeit -- passend zu _fmtDate()/_fmtTime() oben, die ebenfalls
  // ueber Date() lokal formatieren statt UTC.
  _toDatetimeLocal(ts) {
    if (ts === null || ts === undefined) return "";
    const d = new Date(ts * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  _fromDatetimeLocal(value) {
    if (!value) return null;
    const ms = new Date(value).getTime();
    return isNaN(ms) ? null : ms / 1000;
  }

  _fmtDuration(minutes) {
    const m = parseFloat(minutes);
    if (isNaN(m) || m < 0) return null;
    if (m < 60) return `${Math.round(m)} min`;
    const h = Math.floor(m / 60);
    const rem = Math.round(m % 60);
    return rem ? `${h}h ${rem}min` : `${h}h`;
  }

  _renderPendingCharges(items) {
    const el = this._r.estExtItem;
    if (!el) return;
    const sig = items.map((p) => p.start_ts).join(",");
    if (sig === this._pendChargeSig && el.dataset.built === "1") return;
    this._pendChargeSig = sig;
    el.dataset.built = "1";
    el.innerHTML = "";
    items.forEach((p) => {
      const key = p.start_ts;
      const fs = (this._formState.charge ||= {});
      const st = (fs[key] ||= {
        kwh: p.energy_kwh != null ? Number(p.energy_kwh).toFixed(2) : "", price: "", fee: "", blockFee: "", timeFee: "",
      });

      const soc = (p.soc_start != null && p.soc_end != null)
        ? `${Math.round(p.soc_start)}% → ${Math.round(p.soc_end)}%` : "";
      const durStr = this._fmtDuration(p.duration_min);
      const metaParts = [this._fmtDate(p.start_ts)];
      if (durStr) metaParts.push(durStr);

      const row = document.createElement("div");
      row.className = "pend-card";
      row.innerHTML = `
        <div class="pend-top">
          <span class="pend-icon"><ha-icon icon="mdi:ev-station"></ha-icon></span>
          <div class="pend-top-text">
            <span class="pend-title">Fremdladung erkannt</span>
            <span class="pend-meta">${metaParts.join(" · ")}</span>
          </div>
        </div>
        <div class="pend-estimate">
          <span class="pend-estimate-val">${p.energy_kwh != null ? this._fmtNum(p.energy_kwh, 2) : "—"}<small>kWh geschätzt</small></span>
          ${soc ? `<span class="pend-estimate-sub">${soc}</span>` : ""}
        </div>
        <div class="pend-inputs">
          <label>kWh (Beleg)<input type="text" inputmode="decimal" class="pf-kwh" value="${st.kwh}"></label>
          <label>EUR/kWh (Beleg)<input type="text" inputmode="decimal" class="pf-price" value="${st.price}" placeholder="0,000"></label>
          <label>Startgebühr € (optional)<input type="text" inputmode="decimal" class="pf-fee" value="${st.fee}" placeholder="0,00"></label>
          <label>Blockiergebühr € (optional)<input type="text" inputmode="decimal" class="pf-block-fee" value="${st.blockFee}" placeholder="0,00"></label>
          <label>Zeitgebühr € (optional)<input type="text" inputmode="decimal" class="pf-time-fee" value="${st.timeFee}" placeholder="0,00"></label>
        </div>
        <div class="pend-actions">
          <button class="btn btn-ghost pf-discard">Verwerfen</button>
          <button class="btn btn-primary pf-confirm" disabled>Bestätigen</button>
        </div>`;

      const kwhInput = row.querySelector(".pf-kwh");
      const priceInput = row.querySelector(".pf-price");
      const feeInput = row.querySelector(".pf-fee");
      const blockFeeInput = row.querySelector(".pf-block-fee");
      const timeFeeInput = row.querySelector(".pf-time-fee");
      const confirmBtn = row.querySelector(".pf-confirm");
      const updateValidity = () => {
        const valid = !isNaN(parseFloat(st.kwh)) && !isNaN(parseFloat(st.price));
        confirmBtn.disabled = !valid;
        confirmBtn.title = valid ? "" : "Bitte kWh und Preis eintragen";
      };
      updateValidity();

      kwhInput.addEventListener("input", (e) => { st.kwh = e.target.value.replace(",", "."); updateValidity(); });
      priceInput.addEventListener("input", (e) => { st.price = e.target.value.replace(",", "."); updateValidity(); });
      feeInput.addEventListener("input", (e) => { st.fee = e.target.value.replace(",", "."); });
      blockFeeInput.addEventListener("input", (e) => { st.blockFee = e.target.value.replace(",", "."); });
      timeFeeInput.addEventListener("input", (e) => { st.timeFee = e.target.value.replace(",", "."); });
      confirmBtn.addEventListener("click", () => {
        const kwh = parseFloat(st.kwh), price = parseFloat(st.price);
        if (isNaN(kwh) || isNaN(price)) return;
        const fee = parseFloat(st.fee);
        const blockFee = parseFloat(st.blockFee);
        const timeFee = parseFloat(st.timeFee);
        this._call("log_charge", {
          kwh, price_kwh: price, start_ts: key,
          start_fee: isNaN(fee) ? 0 : fee, block_fee: isNaN(blockFee) ? 0 : blockFee,
          time_fee: isNaN(timeFee) ? 0 : timeFee,
        });
        delete fs[key];
      });
      row.querySelector(".pf-discard").addEventListener("click", () => {
        this._call("discard_pending", { start_ts: key });
        delete fs[key];
      });
      el.appendChild(row);
    });
  }

  _renderPendingTrips(items) {
    const el = this._r.estTripItem;
    if (!el) return;
    const sig = items.map((p) => p.start_ts).join(",");
    if (sig === this._pendTripSig && el.dataset.built === "1") return;
    this._pendTripSig = sig;
    el.dataset.built = "1";
    el.innerHTML = "";
    items.forEach((p) => {
      const key = p.start_ts;
      const fs = (this._formState.trip ||= {});
      const st = (fs[key] ||= {
        start_ort: p.start_ort_vorschlag || "",
        end_ort: p.end_ort_vorschlag || "",
      });

      const durStr = this._fmtDuration(p.duration_min);
      const metaParts = [this._fmtDate(p.start_ts)];
      if (durStr) metaParts.push(durStr);

      const row = document.createElement("div");
      row.className = "pend-card";
      row.innerHTML = `
        <div class="pend-top">
          <span class="pend-icon"><ha-icon icon="mdi:road-variant"></ha-icon></span>
          <div class="pend-top-text">
            <span class="pend-title">Fahrt erkannt</span>
            <span class="pend-meta">${metaParts.join(" · ")}</span>
          </div>
        </div>
        <div class="pend-estimate">
          <span class="pend-estimate-val">${p.km != null ? this._fmtNum(p.km, 1) : "—"}<small>km</small></span>
        </div>
        <div class="pend-inputs">
          <label>Startort<input type="text" class="pf-start" value="${st.start_ort}"></label>
          <label>Zielort<input type="text" class="pf-end" value="${st.end_ort}"></label>
        </div>
        <div class="pend-actions">
          <button class="btn btn-ghost pf-discard">Verwerfen</button>
          <button class="btn btn-primary pf-confirm" disabled>Bestätigen</button>
        </div>`;

      const startInput = row.querySelector(".pf-start");
      const endInput = row.querySelector(".pf-end");
      const confirmBtn = row.querySelector(".pf-confirm");
      const updateValidity = () => {
        const valid = !!st.start_ort && !!st.end_ort;
        confirmBtn.disabled = !valid;
        confirmBtn.title = valid ? "" : "Bitte Start- und Zielort eintragen";
      };
      updateValidity();

      startInput.addEventListener("input", (e) => { st.start_ort = e.target.value; updateValidity(); });
      endInput.addEventListener("input", (e) => { st.end_ort = e.target.value; updateValidity(); });
      confirmBtn.addEventListener("click", () => {
        if (!st.start_ort || !st.end_ort) return;
        this._call("log_trip", { start_ort: st.start_ort, end_ort: st.end_ort, start_ts: key });
        delete fs[key];
      });
      row.querySelector(".pf-discard").addEventListener("click", () => {
        this._call("discard_pending_trip", { start_ts: key });
        delete fs[key];
      });
      el.appendChild(row);
    });
  }

  // --- History: edit/delete -----------------------------------------------------

  _renderChargeHistory() {
    const list = this._r.histChargeList;
    if (!list) return;
    const eid = this._eid("last_cost");
    const s = eid && this._hass ? this._hass.states[eid] : null;
    const full = (s && Array.isArray((s.attributes || {}).historie)) ? s.attributes.historie : [];
    const expanded = this._histChargeExpanded;
    const hist = expanded ? full : full.slice(0, 5);
    const sig = expanded + "|" + full.map((h) => h.erfasst_ts).join(",");
    if (sig === this._histChargeSig && list.dataset.built === "1") return;
    this._histChargeSig = sig;
    list.dataset.built = "1";
    list.innerHTML = "";
    if (full.length === 0) {
      list.innerHTML = `<div class="dim">Noch keine bestätigten Fremdladungen.</div>`;
      return;
    }
    const scroll = document.createElement("div");
    scroll.className = "hist-scroll" + (expanded ? " expanded" : "");
    hist.forEach((h) => {
      const ts = h.erfasst_ts;
      const row = document.createElement("div");
      row.className = "hist-card";
      const delta = (h.soc_start != null && h.soc_end != null) ? Math.round(h.soc_end - h.soc_start) : null;
      const soc = (h.soc_start != null && h.soc_end != null)
        ? `${Math.round(h.soc_start)}% → ${Math.round(h.soc_end)}%${delta != null ? ` (${delta >= 0 ? "+" : ""}${delta}%)` : ""}`
        : "";
      // Datum zeigt den tatsächlichen Ladebeginn (start_ts), nicht den Bestätigungs-
      // zeitpunkt (erfasst_ts) — sonst kann "bis HH:MM" scheinbar vor dem Datum liegen,
      // wenn die Bestätigung erst nach Ladeende erfolgte.
      const displayTs = h.start_ts != null ? h.start_ts : ts;
      const endTs = (h.start_ts != null && h.dauer_min != null) ? h.start_ts + h.dauer_min * 60 : null;
      const endTime = this._fmtTime(endTs);
      const durStr = this._fmtDuration(h.dauer_min);
      const metaParts = [];
      if (endTime) metaParts.push(`bis ${endTime}`);
      if (durStr) metaParts.push(durStr);
      const meta = metaParts.join(" · ");
      row.innerHTML = `
        <div class="hist-top">
          <span class="hist-date">${this._fmtDate(displayTs)}${meta ? ` <span class="hist-meta">· ${meta}</span>` : ""}</span>
          <div class="hist-actions">
            <button class="btn-icon sm hist-edit" title="Bearbeiten"><ha-icon icon="mdi:pencil"></ha-icon></button>
            <button class="btn-icon sm hist-delete" title="Löschen"><ha-icon icon="mdi:delete"></ha-icon></button>
          </div>
        </div>
        <div class="hist-figures">
          <div class="hist-figures-left">
            ${soc ? `<span class="hist-soc">${soc}</span>` : ""}
            <span class="hist-kwh">${this._fmtNum(h.kwh, 2)}<small>kWh</small></span>
            ${(() => { const p = h.dauer_min >= 5 ? h.kwh / (h.dauer_min / 60) : null; return (p >= 1 && p <= 350) ? `<span class="hist-power">Ø ${this._fmtNum(p, 1)}<small>kW</small></span>` : ""; })()}
            <span class="hist-price">${this._fmtNum(h.preis_kwh, 3)} €/kWh</span>
            ${h.startgebuehr ? `<span class="hist-fee">+ ${this._fmtNum(h.startgebuehr, 2)} € Startgebühr</span>` : ""}
            ${h.blockiergebuehr ? `<span class="hist-fee">+ ${this._fmtNum(h.blockiergebuehr, 2)} € Blockiergebühr</span>` : ""}
            ${h.zeitgebuehr ? `<span class="hist-fee">+ ${this._fmtNum(h.zeitgebuehr, 2)} € Zeitgebühr</span>` : ""}
          </div>
          <span class="hist-cost">${this._fmtNum(h.kosten, 2)} €</span>
        </div>
        ${(h.soc_start != null && h.soc_end != null) ? `<div class="soc-bar-wrap"><div class="soc-bar-fill ext" style="--soc-w:${Math.min(100, Math.max(0, h.soc_end - h.soc_start) * 2).toFixed(1)}%"></div></div>` : ""}
        <div class="hist-edit-form hidden">
          <label>kWh<input type="text" inputmode="decimal" class="hf-kwh" value="${h.kwh}"></label>
          <label>EUR/kWh<input type="text" inputmode="decimal" class="hf-price" value="${h.preis_kwh}"></label>
          <label>Startgebühr €<input type="text" inputmode="decimal" class="hf-fee" value="${h.startgebuehr || 0}"></label>
          <label>Blockiergebühr €<input type="text" inputmode="decimal" class="hf-block-fee" value="${h.blockiergebuehr || 0}"></label>
          <label>Zeitgebühr €<input type="text" inputmode="decimal" class="hf-time-fee" value="${h.zeitgebuehr || 0}"></label>
          <label>Start<input type="datetime-local" class="hf-start-ts" value="${this._toDatetimeLocal(h.start_ts)}"></label>
          <label>Ende<input type="datetime-local" class="hf-end-ts" value="${this._toDatetimeLocal(endTs)}"></label>
          <label>SoC Start (%)<input type="text" inputmode="decimal" class="hf-soc-start" value="${h.soc_start ?? ""}"></label>
          <label>SoC Ende (%)<input type="text" inputmode="decimal" class="hf-soc-end" value="${h.soc_end ?? ""}"></label>
          <button class="btn btn-primary hf-save">Speichern</button>
          <button class="btn btn-ghost hf-cancel">Abbrechen</button>
        </div>
        <div class="hist-delete-confirm hidden">
          <span class="hist-delete-text">Diesen Eintrag dauerhaft löschen?</span>
          <button class="btn btn-danger hd-confirm">Löschen</button>
          <button class="btn btn-ghost hd-cancel">Abbrechen</button>
        </div>`;
      const form = row.querySelector(".hist-edit-form");
      const delConfirm = row.querySelector(".hist-delete-confirm");
      row.querySelector(".hist-edit").addEventListener("click", () => {
        delConfirm.classList.add("hidden");
        form.classList.toggle("hidden");
      });
      row.querySelector(".hf-cancel").addEventListener("click", () => form.classList.add("hidden"));
      row.querySelector(".hf-save").addEventListener("click", () => {
        const num = (sel) => {
          const raw = row.querySelector(sel).value.trim().replace(",", ".");
          if (raw === "") return null;
          const v = parseFloat(raw);
          return isNaN(v) ? null : v;
        };
        const payload = { erfasst_ts: ts };
        const kwh = num(".hf-kwh"); if (kwh != null) payload.kwh = kwh;
        const price = num(".hf-price"); if (price != null) payload.price_kwh = price;
        const fee = num(".hf-fee"); if (fee != null) payload.start_fee = fee;
        const blockFee = num(".hf-block-fee"); if (blockFee != null) payload.block_fee = blockFee;
        const timeFee = num(".hf-time-fee"); if (timeFee != null) payload.time_fee = timeFee;
        const startTsVal = this._fromDatetimeLocal(row.querySelector(".hf-start-ts").value);
        if (startTsVal != null) payload.start_ts = startTsVal;
        const endTsVal = this._fromDatetimeLocal(row.querySelector(".hf-end-ts").value);
        if (endTsVal != null) payload.end_ts = endTsVal;
        const socStart = num(".hf-soc-start"); if (socStart != null) payload.soc_start = socStart;
        const socEnd = num(".hf-soc-end"); if (socEnd != null) payload.soc_end = socEnd;
        this._call("edit_charge", payload);
        form.classList.add("hidden");
      });
      row.querySelector(".hist-delete").addEventListener("click", () => {
        form.classList.add("hidden");
        delConfirm.classList.toggle("hidden");
      });
      row.querySelector(".hd-cancel").addEventListener("click", () => delConfirm.classList.add("hidden"));
      row.querySelector(".hd-confirm").addEventListener("click", () => {
        this._call("delete_charge", { erfasst_ts: ts });
        delConfirm.classList.add("hidden");
      });
      scroll.appendChild(row);
    });
    list.appendChild(scroll);
    if (full.length > 5) {
      const toggle = document.createElement("button");
      toggle.className = "hist-toggle";
      toggle.textContent = expanded ? "Weniger anzeigen" : `Alle anzeigen (${full.length})`;
      toggle.addEventListener("click", () => {
        const scrollTop = this._main ? this._main.scrollTop : 0;
        const winY = window.scrollY;
        this._histChargeExpanded = !this._histChargeExpanded;
        this._histChargeSig = null;
        this._renderChargeHistory();
        const restore = () => {
          if (this._main) this._main.scrollTop = scrollTop;
          window.scrollTo(window.scrollX, winY);
        };
        restore();
        requestAnimationFrame(restore);
      });
      list.appendChild(toggle);
    }
  }

  _renderTripHistory() {
    const list = this._r.histTripList;
    if (!list) return;
    const eid = this._eid("last_trip_km");
    const s = eid && this._hass ? this._hass.states[eid] : null;
    const full = (s && Array.isArray((s.attributes || {}).fahrtenbuch)) ? s.attributes.fahrtenbuch : [];
    const expanded = this._histTripExpanded;
    const hist = expanded ? full : full.slice(0, 5);
    const sig = expanded + "|" + full.map((h) => h.erfasst_ts).join(",");
    if (sig === this._histTripSig && list.dataset.built === "1") return;
    this._histTripSig = sig;
    list.dataset.built = "1";
    list.innerHTML = "";
    if (full.length === 0) {
      list.innerHTML = `<div class="dim">Noch keine bestätigten Fahrten.</div>`;
      return;
    }
    const scroll = document.createElement("div");
    scroll.className = "hist-scroll" + (expanded ? " expanded" : "");
    hist.forEach((h) => {
      const ts = h.erfasst_ts;
      const row = document.createElement("div");
      row.className = "hist-card";
      const tSocStr = (h.soc_start != null && h.soc_end != null)
        ? `${h.soc_start} → ${h.soc_end}% (−${Math.abs(Math.round(h.soc_start - h.soc_end))}%)`
        : null;
      const tDurMin = (h.end_ts && h.start_ts) ? (h.end_ts - h.start_ts) / 60 : null;
      const tDurStr = tDurMin ? this._fmtDuration(tDurMin) : null;
      const tSpeed = (tDurMin && tDurMin > 0 && h.km) ? h.km / (tDurMin / 60) : null;
      const tDisplayTs = h.start_ts != null ? h.start_ts : h.erfasst_ts;
      const tEndTime = this._fmtTime(h.end_ts);
      const tMetaParts = [];
      if (tEndTime) tMetaParts.push(`bis ${tEndTime}`);
      if (tDurStr) tMetaParts.push(tDurStr);
      const tMeta = tMetaParts.join(" · ");
      row.innerHTML = `
        <div class="hist-top">
          <span class="hist-date">${this._fmtDate(tDisplayTs)}${tMeta ? ` <span class="hist-meta">· ${tMeta}</span>` : ""}</span>
          <div class="hist-actions">
            <button class="btn-icon sm hist-edit" title="Bearbeiten"><ha-icon icon="mdi:pencil"></ha-icon></button>
            <button class="btn-icon sm hist-delete" title="Löschen"><ha-icon icon="mdi:delete"></ha-icon></button>
          </div>
        </div>
        <div class="hist-figures">
          <div class="hist-figures-left">
            ${tSocStr ? `<span class="hist-soc">${tSocStr}</span>` : ""}
            <span class="hist-kwh">${this._fmtNum(h.km, 1)}<small>km</small></span>
            ${(h.verbrauch_kwh != null) ? `<span class="hist-power" title="${h.verbrauch_unsicher ? "Aus SoC-Delta geschätzt, unplausibel (evtl. Sensor-Aussetzer) – bitte prüfen" : "Verbrauch dieser Fahrt gesamt"}">${h.verbrauch_unsicher ? "⚠️ " : ""}${this._fmtNum(h.verbrauch_kwh, 1)}<small>kWh</small></span>` : ""}
            ${(h.verbrauch_kwh != null && h.km) ? `<span class="hist-power" title="Verbrauch dieser Fahrt je 100 km">${this._fmtNum(h.verbrauch_kwh / h.km * 100, 1)}<small>kWh/100km</small></span>` : ""}
            ${(tSpeed && tSpeed > 0 && tSpeed < 300) ? `<span class="hist-power">Ø ${this._fmtNum(tSpeed, 0)}<small>km/h</small></span>` : ""}
          </div>
        </div>
        ${(h.soc_start != null && h.soc_end != null) ? `<div class="soc-bar-wrap"><div class="soc-bar-fill trip" style="--soc-w:${Math.min(100, Math.max(0, h.soc_start - h.soc_end) * 2).toFixed(1)}%"></div></div>` : ""}
        <div class="hist-route">${h.start_ort} → ${h.end_ort}</div>
        <div class="hist-edit-form hidden">
          <label>Startort<input type="text" class="hf-start" value="${h.start_ort}"></label>
          <label>Zielort<input type="text" class="hf-end" value="${h.end_ort}"></label>
          <label>Start<input type="datetime-local" class="hf-start-ts" value="${this._toDatetimeLocal(h.start_ts)}"></label>
          <label>Ende<input type="datetime-local" class="hf-end-ts" value="${this._toDatetimeLocal(h.end_ts)}"></label>
          <label>Strecke (km)<input type="text" inputmode="decimal" class="hf-km" value="${h.km ?? ""}"></label>
          <label>km Start<input type="text" inputmode="decimal" class="hf-odo-start" value="${h.odo_start ?? ""}"></label>
          <label>km Ende<input type="text" inputmode="decimal" class="hf-odo-end" value="${h.odo_end ?? ""}"></label>
          <label>SoC Start (%)<input type="text" inputmode="decimal" class="hf-soc-start" value="${h.soc_start ?? ""}"></label>
          <label>SoC Ende (%)<input type="text" inputmode="decimal" class="hf-soc-end" value="${h.soc_end ?? ""}"></label>
          <label>Verbrauch (kWh)<input type="text" inputmode="decimal" class="hf-verbrauch" value="${h.verbrauch_kwh ?? ""}"></label>
          <button class="btn btn-primary hf-save">Speichern</button>
          <button class="btn btn-ghost hf-cancel">Abbrechen</button>
        </div>
        <div class="hist-delete-confirm hidden">
          <span class="hist-delete-text">Diesen Eintrag dauerhaft löschen?</span>
          <button class="btn btn-danger hd-confirm">Löschen</button>
          <button class="btn btn-ghost hd-cancel">Abbrechen</button>
        </div>`;
      const form = row.querySelector(".hist-edit-form");
      const delConfirm = row.querySelector(".hist-delete-confirm");
      row.querySelector(".hist-edit").addEventListener("click", () => {
        delConfirm.classList.add("hidden");
        form.classList.toggle("hidden");
      });
      row.querySelector(".hf-cancel").addEventListener("click", () => form.classList.add("hidden"));
      row.querySelector(".hf-save").addEventListener("click", () => {
        const start_ort = row.querySelector(".hf-start").value;
        const end_ort = row.querySelector(".hf-end").value;
        if (!start_ort || !end_ort) return;
        const num = (sel) => {
          const raw = row.querySelector(sel).value.trim().replace(",", ".");
          if (raw === "") return null;
          const v = parseFloat(raw);
          return isNaN(v) ? null : v;
        };
        const payload = { erfasst_ts: ts, start_ort, end_ort };
        const startTs = this._fromDatetimeLocal(row.querySelector(".hf-start-ts").value);
        if (startTs != null) payload.start_ts = startTs;
        const endTs = this._fromDatetimeLocal(row.querySelector(".hf-end-ts").value);
        if (endTs != null) payload.end_ts = endTs;
        const km = num(".hf-km"); if (km != null) payload.km = km;
        const odoStart = num(".hf-odo-start"); if (odoStart != null) payload.odo_start = odoStart;
        const odoEnd = num(".hf-odo-end"); if (odoEnd != null) payload.odo_end = odoEnd;
        const socStart = num(".hf-soc-start"); if (socStart != null) payload.soc_start = socStart;
        const socEnd = num(".hf-soc-end"); if (socEnd != null) payload.soc_end = socEnd;
        const verbrauch = num(".hf-verbrauch"); if (verbrauch != null) payload.verbrauch_kwh = verbrauch;
        this._call("edit_trip", payload);
        form.classList.add("hidden");
      });
      row.querySelector(".hist-delete").addEventListener("click", () => {
        form.classList.add("hidden");
        delConfirm.classList.toggle("hidden");
      });
      row.querySelector(".hd-cancel").addEventListener("click", () => delConfirm.classList.add("hidden"));
      row.querySelector(".hd-confirm").addEventListener("click", () => {
        this._call("delete_trip", { erfasst_ts: ts });
        delConfirm.classList.add("hidden");
      });
      scroll.appendChild(row);
    });
    list.appendChild(scroll);
    if (full.length > 5) {
      const toggle = document.createElement("button");
      toggle.className = "hist-toggle";
      toggle.textContent = expanded ? "Weniger anzeigen" : `Alle anzeigen (${full.length})`;
      toggle.addEventListener("click", () => {
        const scrollTop = this._main ? this._main.scrollTop : 0;
        const winY = window.scrollY;
        this._histTripExpanded = !this._histTripExpanded;
        this._histTripSig = null;
        this._renderTripHistory();
        const restore = () => {
          if (this._main) this._main.scrollTop = scrollTop;
          window.scrollTo(window.scrollX, winY);
        };
        restore();
        requestAnimationFrame(restore);
      });
      list.appendChild(toggle);
    }
  }

  // --- Heimladen: evcc-Ladelogbuch (read-only, keine Bearbeitung/Löschung) -----

  async _fetchHomeSessions() {
    if (this._homeSessionsFetching) return;
    this._homeSessionsFetching = true;
    this._homeSessionsFetchedAt = Date.now();
    // Try fast synchronous lookup first; fall back to async entity registry WS call
    let entryId = this._evccEntryId();
    if (!entryId && this._hass && this._hass.callWS) entryId = await this._resolveEvccEntryId();
    if (!entryId || !this._hass || !this._hass.callWS) {
      // _homeSessions bleibt null (nicht []), damit ohne Dauerschleife erneut
      // versucht wird, sobald z. B. die Entity-Registry nachträglich verfügbar ist.
      this._homeSessionsFetching = false;
      this._renderHomeHistory();
      return;
    }
    try {
      const res = await this._hass.callWS({ type: "evcc_intg/sessions", entry_id: entryId });
      this._homeSessions = Array.isArray(res && res.sessions) ? res.sessions : [];
    } catch (err) {
      this._homeSessions = [];
    } finally {
      this._homeSessionsFetching = false;
      this._renderHomeHistory();
    }
  }

  _renderHomeHistory() {
    const list = this._r.histHomeList;
    if (!list) return;
    const raw = Array.isArray(this._homeSessions) ? this._homeSessions : [];
    const parsed = raw.map((s) => {
      const startTs = s.created ? Date.parse(s.created) / 1000 : null;
      const endTs = s.finished ? Date.parse(s.finished) / 1000 : null;
      let durMin = null;
      if (typeof s.chargeDuration === "number" && s.chargeDuration > 0) {
        durMin = s.chargeDuration / 1e9 / 60;
      } else if (startTs != null && endTs != null && endTs > startTs) {
        durMin = (endTs - startTs) / 60;
      }
      const kwh = typeof s.chargedEnergy === "number" ? s.chargedEnergy : null;
      const cost = typeof s.price === "number" ? s.price : null;
      const solarPct = typeof s.solarPercentage === "number" ? s.solarPercentage : null;
      const vehicle = typeof s.vehicle === "string" && s.vehicle.length > 0 ? s.vehicle : null;
      const socStart = typeof s.socStart === "number" ? s.socStart : null;
      const socEnd = typeof s.socEnd === "number" ? s.socEnd : null;
      const pricePerKwh = typeof s.pricePerKWh === "number" ? s.pricePerKWh : null;
      return { startTs, endTs, durMin, kwh, cost, solarPct, vehicle, socStart, socEnd, pricePerKwh };
    }).filter((s) => s.startTs != null && s.endTs != null)
      .sort((a, b) => b.startTs - a.startTs);

    // Mehrere Fahrzeuge in evcc -> Auswahl anbieten; bei genau einem (oder keinem
    // erkennbaren) Fahrzeugnamen ist ein Filter unnötige UI und bleibt weg.
    const vehicles = [...new Set(parsed.map((p) => p.vehicle).filter(Boolean))].sort();
    // Config-Vorgabe (Schritt 8/8: evcc_vehicle_name) als Default übernehmen —
    // aber nur EINMAL und erst sobald echte Sessions da sind, sonst würde eine
    // spätere bewusste Nutzerwahl ("Alle Fahrzeuge") bei jedem Re-Render wieder
    // überschrieben werden.
    if (!this._homeVehicleFilterInitialized && vehicles.length > 0) {
      this._homeVehicleFilterInitialized = true;
      const configured = this._vehicleConf().evcc_vehicle_name;
      if (configured) {
        const match = vehicles.find((v) => v.toLowerCase() === configured.toLowerCase());
        if (match) this._homeVehicleFilter = match;
      } else if (vehicles.length > 1) {
        // Auto-Erkennung: Tab-Bezeichnung gegen evcc-Fahrzeugnamen abgleichen
        const label = (this._vehicleConf().name || "").toLowerCase();
        const match = vehicles.find((v) =>
          label.includes(v.toLowerCase()) || v.toLowerCase().split(/\s+/).every((w) => label.includes(w))
        );
        if (match) this._homeVehicleFilter = match;
      }
    }
    if (this._homeVehicleFilter && !vehicles.includes(this._homeVehicleFilter)) {
      this._homeVehicleFilter = null;
    }
    const filtered = this._homeVehicleFilter
      ? parsed.filter((p) => p.vehicle === this._homeVehicleFilter)
      : parsed;

    // Solaranteil-Auswertung vor Sig-Check, damit KPIs immer aktuell sind.
    const withSolar = filtered.filter((p) => p.solarPct != null && p.kwh != null && p.kwh > 0);
    const solarKwhSum = withSolar.reduce((sum, p) => sum + p.kwh, 0);
    const avgSolar = solarKwhSum > 0
      ? withSolar.reduce((sum, p) => sum + p.kwh * p.solarPct, 0) / solarKwhSum
      : null;

    // KPI-Zellen synchron befüllen (Übersicht + Letzte Heimladung)
    const lastHome = filtered[0] || null;
    const r = this._r;
    if (r.vhHomeKwhLast) {
      r.vhHomeKwhLast.textContent   = lastHome && lastHome.kwh != null      ? this._fmtNum(lastHome.kwh, 2)        : "—";
      r.vhHomeCostLast.textContent  = lastHome && lastHome.cost != null     ? this._fmtNum(lastHome.cost, 2)       : "—";
      r.vhHomeSolarLast.textContent = lastHome && lastHome.solarPct != null ? Math.round(lastHome.solarPct)        : "—";
      r.vhHomeDurLast.textContent   = lastHome && lastHome.durMin != null   ? this._fmtDuration(lastHome.durMin)   : "—";
      r.vhHomeCount.textContent     = filtered.length > 0 ? String(filtered.length)       : "—";
      r.vhHomeSolar.textContent     = avgSolar != null    ? String(Math.round(avgSolar))   : "—";
    }
    this._renderAllCharts();

    const expanded = this._histHomeExpanded;
    const hist = expanded ? filtered : filtered.slice(0, 5);
    const sig = expanded + "|" + (this._homeVehicleFilter || "") + "|" + filtered.map((h) => h.startTs).join(",");
    if (sig === this._histHomeSig && list.dataset.built === "1") return;
    this._histHomeSig = sig;
    list.dataset.built = "1";
    list.innerHTML = "";
    if (parsed.length === 0) {
      list.innerHTML = `<div class="dim">Noch keine Heimladungen im evcc-Logbuch.</div>`;
      return;
    }

    // Dropdown nur zeigen wenn mehrere evcc-Fahrzeuge vorhanden UND kein Fahrzeug
    // per Config voreingestellt ist.
    const configuredVehicle = this._vehicleConf().evcc_vehicle_name;
    const showVehicleSelect = vehicles.length > 1 && !configuredVehicle;
    if (showVehicleSelect) {
      const toolbar = document.createElement("div");
      toolbar.className = "hist-toolbar";
      toolbar.innerHTML = `
        <select class="hist-vehicle-select">
          <option value="">Alle Fahrzeuge</option>
          ${vehicles.map((v) => `<option value="${v}"${v === this._homeVehicleFilter ? " selected" : ""}>${v}</option>`).join("")}
        </select>`;
      const select = toolbar.querySelector(".hist-vehicle-select");
      if (select) {
        select.addEventListener("change", () => {
          this._homeVehicleFilter = select.value || null;
          this._histHomeSig = null;
          this._renderHomeHistory();
          this._renderAllCharts();
        });
      }
      list.appendChild(toolbar);
    }

    if (filtered.length === 0) {
      const empty = document.createElement("div");
      empty.className = "dim";
      empty.textContent = "Keine Heimladungen für dieses Fahrzeug.";
      list.appendChild(empty);
      return;
    }

    const scroll = document.createElement("div");
    scroll.className = "hist-scroll" + (expanded ? " expanded" : "");
    hist.forEach((h) => {
      const row = document.createElement("div");
      row.className = "hist-card";
      const durStr = this._fmtDuration(h.durMin);
      const socDelta = (h.socStart != null && h.socEnd != null) ? Math.round(h.socEnd - h.socStart) : null;
      const socStr = (h.socStart != null && h.socEnd != null)
        ? `${Math.round(h.socStart)}% → ${Math.round(h.socEnd)}%${socDelta != null ? ` (${socDelta >= 0 ? "+" : ""}${socDelta}%)` : ""}`
        : null;
      const socBarHtml = (h.socStart != null && h.socEnd != null)
        ? `<div class="soc-bar-wrap"><div class="soc-bar-fill" style="--soc-w:${Math.min(100, Math.max(0, h.socEnd - h.socStart) * 2).toFixed(1)}%"></div></div>`
        : "";
      row.innerHTML = `
        <div class="hist-top">
          <span class="hist-date">${this._fmtDate(h.startTs)}${durStr ? ` · ${durStr}` : ""}</span>
          ${h.solarPct != null ? `<span class="hist-solar">☀ ${Math.round(h.solarPct)}%</span>` : ""}
        </div>
        <div class="hist-figures">
          <div class="hist-figures-left">
            ${socStr ? `<span class="hist-soc">${socStr}</span>` : ""}
            <span class="hist-kwh">${h.kwh != null ? this._fmtNum(h.kwh, 2) : "—"}<small>kWh</small></span>
            ${(() => { const p = h.durMin >= 5 && h.kwh ? h.kwh / (h.durMin / 60) : null; return (p >= 1 && p <= 350) ? `<span class="hist-power">Ø ${this._fmtNum(p, 1)}<small>kW</small></span>` : ""; })()}
            ${h.pricePerKwh != null ? `<span class="hist-price">${this._fmtNum(h.pricePerKwh, 3)} €/kWh</span>` : ""}
          </div>
          <span class="hist-cost">${h.cost != null ? this._fmtNum(h.cost, 2) + " €" : "—"}</span>
        </div>
        ${socBarHtml}`;
      scroll.appendChild(row);
    });
    list.appendChild(scroll);
    if (filtered.length > 5) {
      const toggle = document.createElement("button");
      toggle.className = "hist-toggle";
      toggle.textContent = expanded ? "Weniger anzeigen" : `Alle anzeigen (${filtered.length})`;
      toggle.addEventListener("click", () => {
        const scrollTop = this._main ? this._main.scrollTop : 0;
        const winY = window.scrollY;
        this._histHomeExpanded = !this._histHomeExpanded;
        this._histHomeSig = null;
        this._renderHomeHistory();
        const restore = () => {
          if (this._main) this._main.scrollTop = scrollTop;
          window.scrollTo(window.scrollX, winY);
        };
        restore();
        requestAnimationFrame(restore);
      });
      list.appendChild(toggle);
    }
  }

  // --- Ladeübersicht Balkendiagramm -------------------------------------------

  _updateChartNav() {
    const nav  = this._r && this._r.chartNav;
    const lbl  = this._r && this._r.chartNavLabel;
    const next = this._r && this._r.chartNavNext;
    if (!nav) return;
    const period = this._chartPeriod || "woche";
    nav.style.display = "flex";
    if (!lbl) return;
    const now = new Date();
    const offset = this._chartNavOffset || 0;
    if (period === "monat") {
      const d = new Date(now.getFullYear(), now.getMonth() + offset, 1);
      lbl.textContent = d.toLocaleDateString("de-DE", { month: "long", year: "numeric" });
    } else if (period === "jahr") {
      lbl.textContent = String(now.getFullYear() + offset);
    } else {
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const daysToMon = today.getDay() === 0 ? 6 : today.getDay() - 1;
      const mon = new Date(today.getTime() + (offset * 7 - daysToMon) * 86400000);
      const utc = new Date(Date.UTC(mon.getFullYear(), mon.getMonth(), mon.getDate()));
      utc.setUTCDate(utc.getUTCDate() + 4 - (utc.getUTCDay() || 7));
      const yearStart = new Date(Date.UTC(utc.getUTCFullYear(), 0, 1));
      const kw = Math.ceil((((utc - yearStart) / 86400000) + 1) / 7);
      lbl.textContent = `KW ${kw}`;
    }
    if (next) next.disabled = offset >= 0;
  }

  _buildBuckets() {
    const period = this._chartPeriod || "woche";
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const offset = this._chartNavOffset || 0;
    const buckets = [];
    if (period === "woche") {
      const daysToMon = today.getDay() === 0 ? 6 : today.getDay() - 1;
      const weekMonday = new Date(today.getTime() + (offset * 7 - daysToMon) * 86400000);
      for (let i = 0; i < 7; i++) {
        const d = new Date(weekMonday.getTime() + i * 86400000);
        const start = d.getTime() / 1000;
        buckets.push({ start, end: start + 86400, label: d.toLocaleDateString("de-DE", { weekday: "short" }).replace(".", "") });
      }
    } else if (period === "monat") {
      const base = new Date(now.getFullYear(), now.getMonth() + offset, 1);
      const year = base.getFullYear(), month = base.getMonth();
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      for (let d = 1; d <= daysInMonth; d++) {
        const start = new Date(year, month, d).getTime() / 1000;
        buckets.push({ start, end: start + 86400, label: (d === 1 || d % 5 === 0) ? String(d) : "" });
      }
    } else {
      const yr = now.getFullYear() + offset;
      for (let m = 0; m < 12; m++) {
        const d = new Date(yr, m, 1), end = new Date(yr, m + 1, 1);
        buckets.push({ start: d.getTime() / 1000, end: end.getTime() / 1000, label: d.toLocaleDateString("de-DE", { month: "short" }).replace(".", "") });
      }
    }
    return buckets;
  }

  _homeSessionsFiltered() {
    const raw = Array.isArray(this._homeSessions) ? this._homeSessions : [];
    const cfg = (this._vehicleConf().evcc_vehicle_name || "").toLowerCase();
    return raw.filter((s) => {
      if (cfg && typeof s.vehicle === "string" && s.vehicle && s.vehicle.toLowerCase() !== cfg) return false;
      if (!cfg && this._homeVehicleFilter && s.vehicle !== this._homeVehicleFilter) return false;
      return true;
    });
  }

  _extHist() {
    const eid = this._eid("last_cost");
    const st  = eid && this._hass ? this._hass.states[eid] : null;
    return (st && Array.isArray((st.attributes || {}).historie)) ? st.attributes.historie : [];
  }

  _svgBarChart(wrap, buckets, series, opts = {}) {
    if (!wrap) return;
    const svgW = 500, svgH = 170;
    const padL = 40, padR = 8, padT = 20, padB = 28;
    const chartW = svgW - padL - padR, chartH = svgH - padT - padB;
    const n = buckets.length, slotW = chartW / n, barW = Math.max(6, slotW * 0.55);
    const totalVal = (b) => series.reduce((s, {key}) => s + (b[key] || 0), 0);
    let roundedMax;
    if (opts.fixedMax != null) {
      roundedMax = opts.fixedMax;
    } else {
      const rawMax = Math.max(...buckets.map(totalVal), 0.1);
      const mag = Math.pow(10, Math.floor(Math.log10(rawMax)));
      const step = mag >= 10 ? mag : mag / 2;
      roundedMax = Math.ceil(rawMax / step) * step;
    }
    const toH = (v) => Math.max(0, (v / roundedMax) * chartH);
    let yAxis = "", grid = "";
    [0, 0.5, 1].forEach((f) => {
      const val = roundedMax * f;
      const yPos = padT + chartH - f * chartH;
      const lbl = opts.fmtAxis ? opts.fmtAxis(val) : (val >= 10 ? Math.round(val) : this._fmtNum(val, 1));
      yAxis += `<text x="${padL - 5}" y="${yPos + 4}" text-anchor="end" class="ca">${lbl}</text>`;
      if (f > 0) grid += `<line x1="${padL}" y1="${yPos}" x2="${svgW - padR}" y2="${yPos}" class="cg"/>`;
    });
    const fmtTip = opts.fmtVal || ((v) => v >= 10 ? this._fmtNum(v, 1) : this._fmtNum(v, 2));
    let bars = "", hits = "", xlabels = "";
    buckets.forEach((b, i) => {
      const xC = padL + slotW * i + slotW / 2, xL = xC - barW / 2, yBot = padT + chartH;
      let yTop = yBot;
      series.forEach(({key, color}) => {
        const h = toH(b[key] || 0);
        if (h > 0) { bars += `<rect x="${xL.toFixed(1)}" y="${(yTop-h).toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="${color}" rx="2"/>`; yTop -= h; }
      });
      const tot = totalVal(b);
      if (tot > 0) hits += `<rect class="ch" x="${xL.toFixed(1)}" y="${padT}" width="${barW.toFixed(1)}" height="${chartH}" fill="transparent" data-v="${fmtTip(tot)}" data-xc="${xC.toFixed(1)}" data-yt="${yTop.toFixed(1)}"/>`;
      xlabels += `<text x="${xC.toFixed(1)}" y="${svgH - 4}" text-anchor="middle" class="ca">${b.label}</text>`;
    });
    wrap.style.position = "relative";
    // tooltip div — create once, re-append after every innerHTML reset
    if (!wrap._tip) {
      const tip = document.createElement("div");
      tip.style.cssText = "position:absolute;display:none;pointer-events:none;background:var(--card-bg,#1e2024);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px;white-space:nowrap;z-index:10;transform:translateX(-50%)";
      wrap._tip = tip;
    }
    wrap.innerHTML = `<svg viewBox="0 0 ${svgW} ${svgH}" width="100%" style="display:block;overflow:visible">
      <style>.ca{font-size:11px;fill:var(--ink-dim);font-family:inherit}.cg{stroke:var(--line);stroke-width:1}.ch{cursor:default}</style>
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT+chartH}" stroke="var(--line-s)" stroke-width="1"/>
      ${grid}${yAxis}${bars}${hits}${xlabels}</svg>`;
    wrap.appendChild(wrap._tip);  // re-attach after innerHTML wipe
    const tip = wrap._tip;
    const svg = wrap.querySelector("svg");
    svg.onmouseover = (e) => {
      const el = e.target.closest(".ch");
      if (!el) { tip.style.display = "none"; return; }
      const svgRect = svg.getBoundingClientRect();
      const wrapRect = wrap.getBoundingClientRect();
      const scaleX = svgRect.width / svgW;
      const scaleY = svgRect.height / svgH;
      const xPx = parseFloat(el.dataset.xc) * scaleX + (svgRect.left - wrapRect.left);
      const yPx = parseFloat(el.dataset.yt) * scaleY + (svgRect.top - wrapRect.top);
      tip.textContent = el.dataset.v;
      tip.style.display = "block";
      tip.style.left = xPx + "px";
      tip.style.top = (yPx - tip.offsetHeight - 6) + "px";
    };
    svg.onmouseleave = () => { tip.style.display = "none"; };
  }

  _renderAllCharts() {
    this._renderChart();
    this._renderChartKosten();
    this._renderChartSolar();
  }

  _renderChart() {
    const buckets = this._buildBuckets().map(b => ({...b, home: 0, ext: 0}));
    this._homeSessionsFiltered().forEach((s) => {
      const ts = s.created ? Date.parse(s.created) / 1000 : null;
      const kwh = typeof s.chargedEnergy === "number" ? s.chargedEnergy : 0;
      if (ts != null && kwh > 0) buckets.forEach((b) => { if (ts >= b.start && ts < b.end) b.home += kwh; });
    });
    this._extHist().forEach((h) => {
      const ts = h.start_ts != null ? h.start_ts : h.erfasst_ts;
      const kwh = typeof h.kwh === "number" ? h.kwh : 0;
      if (ts != null && kwh > 0) buckets.forEach((b) => { if (ts >= b.start && ts < b.end) b.ext += kwh; });
    });
    this._svgBarChart(this._r && this._r.overviewChart, buckets,
      [{key: "home", color: "var(--c-home)"}, {key: "ext", color: "var(--c-ext)"}]);
  }

  _renderChartKosten() {
    const buckets = this._buildBuckets().map(b => ({...b, home: 0, ext: 0}));
    this._homeSessionsFiltered().forEach((s) => {
      const ts   = s.created ? Date.parse(s.created) / 1000 : null;
      const cost = typeof s.price === "number" ? s.price : 0;
      if (ts != null && cost > 0) buckets.forEach((b) => { if (ts >= b.start && ts < b.end) b.home += cost; });
    });
    this._extHist().forEach((h) => {
      const ts   = h.start_ts != null ? h.start_ts : h.erfasst_ts;
      const cost = typeof h.kosten === "number" ? h.kosten : 0;
      if (ts != null && cost > 0) buckets.forEach((b) => { if (ts >= b.start && ts < b.end) b.ext += cost; });
    });
    this._svgBarChart(this._r && this._r.kostenChart, buckets,
      [{key: "home", color: "var(--c-home)"}, {key: "ext", color: "var(--c-ext)"}],
      {});
  }

  _renderChartSolar() {
    const buckets = this._buildBuckets().map(b => ({...b, solar: 0, _kwh: 0, _skwh: 0}));
    this._homeSessionsFiltered().forEach((s) => {
      const ts  = s.created ? Date.parse(s.created) / 1000 : null;
      const kwh = typeof s.chargedEnergy === "number" ? s.chargedEnergy : 0;
      const pct = typeof s.solarPercentage === "number" ? s.solarPercentage : null;
      if (ts != null && kwh > 0 && pct != null) {
        buckets.forEach((b) => { if (ts >= b.start && ts < b.end) { b._kwh += kwh; b._skwh += kwh * pct; } });
      }
    });
    buckets.forEach((b) => { b.solar = b._kwh > 0 ? b._skwh / b._kwh : 0; });
    this._svgBarChart(this._r && this._r.solarChart, buckets,
      [{key: "solar", color: "var(--c-solar)"}],
      {fixedMax: 100, fmtAxis: (v) => Math.round(v), fmtVal: (v) => Math.round(v) + " %"});
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
      .app {
        display: flex; flex-direction: column; height: 100%;
        container-type: inline-size; container-name: panel;
      }

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
      .vt-bar {
        display: flex; align-items: center; padding: 10px 30px;
        border-bottom: 1px solid var(--line); flex-shrink: 0;
        overflow-x: auto; scrollbar-width: none;
      }
      .vt-bar::-webkit-scrollbar { display: none; }

      /* Main scroll area */
      .main { flex: 1; overflow-y: auto; padding: 24px 28px 40px; overscroll-behavior: contain; }
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
      /* Media-Query-Fallback fuer Browser ohne Container-Query-Unterstuetzung
         (z.B. aeltere Handy-Browser) -- reagiert auf die Viewport-Breite. */
      @media (max-width: 1080px) { .resumen-lower { grid-template-columns: 1fr; } }
      @media (max-width: 720px)  { .charts-2x2 { grid-template-columns: 1fr; grid-template-rows: none; } }
      /* Container-Query-Verbesserung: reagiert auf den tatsaechlich
         verfuegbaren Platz des Panels selbst (z.B. bei auf-/zugeklappter
         Sidebar), nicht nur auf die Bildschirmbreite. Ueberschreibt die
         Media-Query-Fallbacks oben in unterstuetzenden Browsern. */
      @container panel (max-width: 1080px) { .resumen-lower { grid-template-columns: 1fr; } }
      @container panel (max-width: 720px)  { .charts-2x2 { grid-template-columns: 1fr; grid-template-rows: none; } }

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
      @container panel (max-width: 860px) {
        .soc-inner { flex-direction: column; align-items: center; gap: 20px; }
        .soc-diag { align-self: stretch; border-left: none; padding-left: 0; border-top: 1px solid var(--line); padding-top: 18px; }
      }
      @container panel (max-width: 560px) { .diag-grid { grid-template-columns: 1fr; } }

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

      /* Ladeübersicht Chart */
      .card-head-charts { align-items: flex-start; }
      .charts-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; margin-top: 10px; }
      .chart-col { padding: 0 var(--gap); }
      .chart-col:first-child { padding-left: 0; }
      .chart-col:last-child  { padding-right: 0; }
      .chart-col + .chart-col { border-left: 1px solid var(--line); }
      .chart-col-title { font-size: 0.78rem; font-weight: 500; color: var(--ink-mid); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.04em; }
      .chart-controls { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; margin-left: auto; }
      .chart-pills { display: flex; gap: 4px; }
      .chart-pills .pill {
        padding: 4px 12px; border-radius: 20px;
        border: 1px solid var(--line-s); background: transparent;
        color: var(--ink-mid); font-size: 0.8rem; cursor: pointer;
        font-family: inherit; transition: background 0.15s, color 0.15s;
      }
      .chart-pills .pill:hover { background: var(--bg-0); color: var(--ink); }
      .chart-pills .pill.active { background: var(--accent); color: #fff; border-color: transparent; }
      .chart-nav { display: none; align-items: center; justify-content: flex-end; gap: 8px; }
      .nav-label { font-size: 0.85rem; font-weight: 500; color: var(--ink); min-width: 100px; text-align: center; }
      .nav-arrow { background: none; border: 1px solid var(--line-s); border-radius: 50%; width: 26px; height: 26px; display: grid; place-items: center; cursor: pointer; color: var(--ink-mid); font-size: 1.1rem; line-height: 1; transition: background 0.15s, color 0.15s; font-family: inherit; padding: 0; }
      .nav-arrow:hover:not(:disabled) { background: var(--bg-0); color: var(--ink); }
      .nav-arrow:disabled { opacity: 0.3; cursor: default; }
      .chart-legend { display: flex; gap: 14px; margin: 4px 0 10px; font-size: 0.82rem; color: var(--ink-mid); }
      @media (max-width: 600px) {
        .charts-grid { grid-template-columns: 1fr; }
        .chart-col { padding: var(--gap) 0; border-left: none !important; border-top: 1px solid var(--line); }
        .chart-col:first-child { padding-top: 0; border-top: none; }
        .card-head-charts { flex-wrap: wrap; gap: 10px; }
        .chart-controls { margin-left: 0; align-items: flex-start; width: 100%; }
        .chart-nav { justify-content: flex-start; }
      }
      .cleg { display: flex; align-items: center; gap: 5px; }
      .cleg-dot { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
      .cleg-dot.home  { background: var(--c-home); }
      .cleg-dot.ext   { background: var(--c-ext); }
      .cleg-dot.solar { background: var(--c-solar); }

      /* Fahrzeuge tab */
      .tab-wrap { display: flex; flex-direction: column; gap: var(--gap); }
      #vh-content { display: flex; flex-direction: column; gap: var(--gap); }
      .vh-3col { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--gap); align-items: start; }
      .vh-col  { display: flex; flex-direction: column; gap: var(--gap); }
      .vt-pills { display: flex; gap: 6px; flex-wrap: wrap; }
      .vt-pill {
        border: 1px solid var(--line-s); border-radius: 9999px; padding: 5px 16px;
        font-size: 12.5px; font-weight: 600; cursor: pointer;
        background: var(--bg-2); color: var(--ink-mid); transition: all 0.15s;
      }
      .vt-pill:hover { background: var(--bg-0); color: var(--ink); border-color: var(--accent); }
      .vt-pill.active { background: var(--accent); border-color: var(--accent); color: #fff; }
      .badge-row { display: flex; gap: 8px; flex-wrap: wrap; }
      .badge { display: flex; align-items: center; gap: 6px; font-size: 0.72rem; font-weight: 700; padding: 5px 12px; border-radius: 9999px; --mdc-icon-size: 14px; }
      .badge-ext  { background: #7c2d12; color: #fed7aa; border: 1px solid #9a3412; }
      .badge-trip { background: #1e3a5f; color: #bfdbfe; border: 1px solid #1d4ed8; }
      .kpi-row { display: flex; flex-wrap: wrap; gap: 12px 0; }
      .kpi     { flex: 1; min-width: 60px; text-align: center; }
      .kv      { font-size: 1.55rem; font-weight: 700; line-height: 1.1; }
      .kv-sm   { font-size: 0.9rem;  font-weight: 600; line-height: 1.3; color: var(--ink); }
      .kl      { font-size: 0.7rem; color: var(--ink-mid); margin-top: 2px; }
      .kv.green { color: #4ade80; }

      /* Nutzungsprofil-Tab */
      .profil-empty { color: var(--ink-dim); font-size: 0.85rem; line-height: 1.5; padding: 8px 0 4px; }
      .profil-recommend {
        display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 10px;
        background: var(--bg-0); border: 1px solid var(--line); margin-bottom: 14px;
      }
      .profil-recommend-icon { --mdc-icon-size: 28px; flex-shrink: 0; color: var(--ink-dim); }
      .profil-recommend-text { font-size: 0.88rem; font-weight: 600; line-height: 1.35; }
      .profil-recommend.rec-yes { background: rgba(245, 158, 11, 0.12); border-color: #f59e0b; }
      .profil-recommend.rec-yes .profil-recommend-icon { color: #f59e0b; }
      .profil-recommend.rec-no  { background: rgba(74, 222, 128, 0.10); border-color: #4ade80; }
      .profil-recommend.rec-no  .profil-recommend-icon { color: #4ade80; }
      .weekday-chart { display: flex; align-items: flex-end; gap: 6px; height: 130px; margin-top: 4px; }
      .wd-col { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; min-width: 0; }
      .wd-val { font-size: 0.68rem; color: var(--ink-mid); margin-bottom: 4px; }
      .wd-bar-track {
        flex: 1; width: 100%; max-width: 28px; display: flex; align-items: flex-end;
        background: var(--bg-0); border-radius: 5px; overflow: hidden;
      }
      .wd-bar { width: 100%; border-radius: 5px 5px 0 0; background: var(--line-s); transition: height 0.4s ease; }
      .wd-bar.today    { background: var(--accent); }
      .wd-bar.tomorrow { background: #4ade80; }
      .wd-label { font-size: 0.7rem; color: var(--ink-dim); margin-top: 6px; font-weight: 600; }

      /* Farbige Summary-Cards — HA Energiedashboard-Farben */
      :host { --c-home: #ff9800; --c-ext: #488fc2; --c-trip: #14b8a6; --c-solar: #4ade80; }

      /* Fahrzeug-Card Unterer Bereich: 3-Spalten-Grid (Kilometerleistung | Kosten | Verbrenner-Vergleich) */
      .vh-bottom-grid { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr; gap: 0; margin-top: 0; }
      .vh-bottom-col { min-width: 0; }
      .vh-bottom-divider { width: 1px; background: var(--line); margin: 0 16px; }
      .km-grid-1col { grid-template-columns: 1fr; }
      @media (max-width: 500px) {
        .vh-bottom-grid { grid-template-columns: 1fr; }
        .vh-bottom-divider { width: auto; height: 1px; margin: 12px 0; }
      }

      /* Kilometerleistungs-Grid */
      .km-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; margin-top: 8px; }
      .km-col { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
      .km-item { display: flex; align-items: baseline; gap: 5px; font-size: 0.82rem; min-width: 0; }
      .km-item--full { grid-column: 1 / -1; }
      .km-label { color: var(--ink-mid); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .km-val { font-weight: 700; color: var(--ink); }
      .km-unit { font-size: 0.72rem; color: var(--ink-dim); flex-shrink: 0; }
      .km-sep { height: 6px; }
      .sav-grid { display: flex; flex-direction: column; gap: 3px; margin-top: 8px; }

      /* Fahrzeug-Card */
      .card-vehicle { border-top: 3px solid var(--accent); }
      .card-vehicle .card-head .ic {
        width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
        background: color-mix(in oklab, var(--accent) 15%, transparent); color: var(--accent);
        --mdc-icon-size: 18px;
      }
      .veh-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
      .veh-name-block { flex: 1; min-width: 0; }
      .veh-name { font-size: 1.4rem; font-weight: 800; color: var(--ink); line-height: 1.1; }
      .veh-soc-block { display: flex; flex-direction: column; align-items: flex-end; gap: 5px; flex-shrink: 0; }
      .veh-soc-pct { font-size: 2.2rem; font-weight: 800; line-height: 1; color: var(--accent); font-variant-numeric: tabular-nums; }
      .veh-soc-pct small { font-size: 0.45em; font-weight: 600; color: var(--ink-mid); margin-left: 1px; }
      .veh-soc-bar-wrap { width: 120px; height: 7px; border-radius: 4px; background: var(--line); overflow: hidden; }
      .veh-soc-bar-fill { height: 100%; border-radius: 4px; background: var(--accent); transition: width 0.6s ease; width: 0; }
      .veh-soc-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.09em; color: var(--ink-dim); font-weight: 700; }

      /* Summary-Card Akzente */
      .card-home:not(.card-hist) { border-top: 3px solid var(--c-home); }
      .card-ext:not(.card-hist)  { border-top: 3px solid var(--c-ext); }
      .card-trip:not(.card-hist) { border-top: 3px solid var(--c-trip); }

      /* Icon-Hintergrund */
      .card-home .card-head .ic {
        width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
        background: color-mix(in oklab, var(--c-home) 15%, transparent); color: var(--c-home);
        --mdc-icon-size: 18px;
      }
      .card-ext .card-head .ic {
        width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
        background: color-mix(in oklab, var(--c-ext) 15%, transparent); color: var(--c-ext);
        --mdc-icon-size: 18px;
      }
      .card-trip .card-head .ic {
        width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
        background: color-mix(in oklab, var(--c-trip) 15%, transparent); color: var(--c-trip);
        --mdc-icon-size: 18px;
      }

      /* KPI-Werte in Spaltenfarbe, "Letzte"-Werte neutral kleiner */
      .card-home:not(.card-hist) .kpi-row:first-of-type .kv { color: var(--c-home); }
      .card-ext:not(.card-hist)  .kpi-row:first-of-type .kv { color: var(--c-ext); }
      .card-trip:not(.card-hist) .kpi-row:first-of-type .kv { color: var(--c-trip); }
      .letzte-section .kv { color: var(--ink) !important; font-size: 1.25rem; }

      /* KPI vertikale Trennlinie */
      .kpi:not(:last-child) { border-right: 1px solid var(--line); }

      /* "Letzte"-Sektion als getönter Block */
      .letzte-section {
        margin-top: 14px; background: var(--bg-2);
        border-radius: 10px; padding: 12px 14px;
      }
      .letzte-section .sub-head { margin-bottom: 10px; }
      .card-home .letzte-section .sub-head { color: var(--c-home); opacity: 0.8; }
      .card-ext  .letzte-section .sub-head { color: var(--c-ext);  opacity: 0.8; }
      .card-trip .letzte-section .sub-head { color: var(--c-trip); opacity: 0.8; }

      /* Historie-Sektion innerhalb der Karte */
      .hist-section { margin-top: 16px; border-top: 1px solid var(--line); padding-top: 14px; }
      .hist-section-head {
        display: flex; align-items: center; justify-content: space-between;
        margin-bottom: 10px;
      }
      .hist-section-head span {
        font-size: 11px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.06em; color: var(--ink-dim);
      }
      .card-home .hist-section-head span { color: var(--c-home); opacity: 0.7; }
      .card-ext  .hist-section-head span { color: var(--c-ext);  opacity: 0.7; }
      .card-trip .hist-section-head span { color: var(--c-trip); opacity: 0.7; }

      /* Hover auf History-Einträgen */
      .hist-card { transition: background 0.15s; }
      .hist-card:hover { background: var(--bg-0); }
      .hist-row  { transition: background 0.15s; border-radius: 6px; }
      .hist-row:hover { background: color-mix(in oklab, var(--ink) 4%, transparent); }

      /* SOC-Balken in Heimladen-Historie */
      .soc-bar-wrap { height: 3px; border-radius: 2px; background: var(--line); margin-top: 5px; position: relative; overflow: hidden; max-width: 100px; }
      .soc-bar-fill { position: absolute; height: 100%; border-radius: 2px; background: var(--c-home); left: 0; width: var(--soc-w); }
      .soc-bar-fill.ext { background: var(--c-ext); }
      .soc-bar-fill.trip { background: var(--c-trip); }
      .hist-route { font-size: 0.8rem; color: var(--ink-mid); margin-top: 4px; }

      /* Tab-Wechsel Fade-In */
      @keyframes vh-fadein { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
      .vh-fade { animation: vh-fadein 0.22s ease; }
      .est-card { border-color: rgba(251,146,60,0.25); }
      .est-list  { display: flex; flex-direction: column; gap: 8px; }
      .est-item  { display: flex; align-items: center; gap: 8px; font-size: 0.88rem; }
      .est-item strong { font-size: 1rem; font-weight: 700; }
      .ci { --mdc-icon-size: 18px; }
      .ci.orange { color: #fb923c; }
      .ci.blue   { color: #60a5fa; }

      /* Buttons */
      .btn {
        border: 1px solid var(--line-s); border-radius: 8px; padding: 7px 14px;
        font-size: 12.5px; font-weight: 600; cursor: pointer; background: var(--bg-2); color: var(--ink);
      }
      .btn:hover { filter: brightness(1.15); }
      .btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
      .btn-ghost   { background: transparent; }
      .btn-danger  { background: oklch(0.58 0.2 25); border-color: oklch(0.58 0.2 25); color: #fff; }
      .btn-icon {
        border: 1px solid var(--line-s); background: var(--bg-2); border-radius: 8px;
        width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center;
        cursor: pointer; color: var(--ink-mid); --mdc-icon-size: 16px;
      }
      .btn-icon:hover { color: var(--ink); }
      .btn-icon.confirm { background: oklch(0.7 0.18 25 / 0.15); border-color: oklch(0.7 0.18 25 / 0.5); color: oklch(0.7 0.18 25); }
      .btn-icon.sm { width: 26px; height: 26px; --mdc-icon-size: 14px; }

      /* Pending confirm/discard forms */
      .pend-list { display: flex; flex-direction: column; gap: 10px; }
      .pend-card {
        border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
        background: var(--bg-2); display: flex; flex-direction: column; gap: 12px;
      }
      .pend-top { display: flex; align-items: center; gap: 10px; }
      .pend-icon {
        display: flex; align-items: center; justify-content: center; flex-shrink: 0;
        width: 34px; height: 34px; border-radius: 9px;
        background: color-mix(in oklab, var(--accent) 16%, transparent);
        color: var(--accent); --mdc-icon-size: 18px;
      }
      .pend-top-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
      .pend-title { font-size: 13px; font-weight: 700; color: var(--ink); }
      .pend-meta { font-size: 11.5px; color: var(--ink-dim); }
      .pend-estimate { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
      .pend-estimate-val { font-size: 1.3rem; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
      .pend-estimate-val small { font-size: 0.6em; font-weight: 500; color: var(--ink-dim); margin-left: 4px; }
      .pend-estimate-sub { font-size: 12.5px; color: var(--ink-mid); font-variant-numeric: tabular-nums; }
      .pend-inputs { display: flex; align-items: flex-end; gap: 10px; flex-wrap: wrap; }
      .pend-inputs label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--ink-mid); flex: 1 1 110px; }
      .pend-inputs input {
        border: 1px solid var(--line-s); border-radius: 7px; padding: 7px 9px; font-size: 13.5px;
        background: var(--bg-0); color: var(--ink); width: 100%; box-sizing: border-box;
      }
      .pend-inputs input:focus { outline: none; border-color: var(--accent); }
      .pend-actions { display: flex; gap: 8px; justify-content: flex-end; }
      .btn:disabled { opacity: 0.4; cursor: not-allowed; }

      /* History lists */
      .hist-list { display: flex; flex-direction: column; gap: 8px; }
      .hist-scroll { display: flex; flex-direction: column; gap: 8px; }
      .hist-scroll.expanded {
        max-height: 420px; overflow-y: auto; padding-right: 4px;
        overscroll-behavior: contain; -webkit-overflow-scrolling: touch;
      }
      .hist-scroll.expanded::-webkit-scrollbar { width: 6px; }
      .hist-scroll.expanded::-webkit-scrollbar-thumb { background: var(--line-s); border-radius: 6px; }
      .hist-toggle {
        border: none; background: none; color: var(--accent); font-size: 12.5px; font-weight: 600;
        cursor: pointer; padding: 6px 2px; text-align: center; align-self: center;
      }
      .hist-toggle:hover { text-decoration: underline; }
      .hist-toolbar {
        display: flex; align-items: center; justify-content: space-between;
        gap: 10px; flex-wrap: wrap; margin-bottom: 10px;
      }
      .hist-summary { font-size: 12px; color: var(--ink-mid); }
      .hist-vehicle-select {
        border: 1px solid var(--line-s); border-radius: 7px; padding: 5px 8px; font-size: 12px;
        background: var(--bg-0); color: var(--ink);
      }
      .hist-row { border-bottom: 1px solid var(--line); padding-bottom: 8px; }
      .hist-row:last-child { border-bottom: none; padding-bottom: 0; }
      .hist-main { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 13px; }
      .hist-date { color: var(--ink-dim); min-width: 110px; }
      .hist-val { font-weight: 600; }
      .hist-val.dim { font-weight: 500; color: var(--ink-mid); }
      /* Fremdladung-Historie: eigene Karte pro Eintrag statt flacher Liste,
         mit klarer Hierarchie (Meta klein/dezent oben, Hauptzahlen betont
         in der Mitte, Aktionen kompakt unten). */
      .hist-card {
        border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px;
        background: var(--bg-2);
      }
      .hist-top {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; font-size: 11.5px; color: var(--ink-dim); flex-wrap: wrap;
        min-height: 26px;
      }
      .hist-top .hist-date { min-width: 0; }
      .hist-meta { color: var(--ink-dim); font-variant-numeric: tabular-nums; }
      .hist-figures {
        display: flex; align-items: baseline; justify-content: space-between;
        gap: 12px; margin-top: 4px;
      }
      .hist-figures-left { display: flex; align-items: baseline; gap: 10px; min-width: 0; flex-wrap: wrap; }
      .hist-figures-right { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
      .hist-soc { font-size: 12px; color: var(--ink-mid); white-space: nowrap; font-variant-numeric: tabular-nums; }
      .hist-solar { font-size: 12px; color: var(--ink-mid); white-space: nowrap; font-variant-numeric: tabular-nums; }
      .hist-kwh { font-size: 1.05rem; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
      .hist-kwh small { font-size: 0.68em; font-weight: 500; color: var(--ink-dim); margin-left: 3px; }
      .hist-power { font-size: 0.85rem; font-weight: 500; color: var(--ink-mid); font-variant-numeric: tabular-nums; }
      .hist-power small { font-size: 0.75em; font-weight: 400; color: var(--ink-dim); margin-left: 2px; }
      .hist-price { font-size: 12px; color: var(--ink-mid); white-space: nowrap; font-variant-numeric: tabular-nums; }
      .hist-fee   { font-size: 12px; color: var(--ink-dim); white-space: nowrap; font-variant-numeric: tabular-nums; }
      .hist-cost { font-size: 1.05rem; font-weight: 700; color: var(--ink); white-space: nowrap; font-variant-numeric: tabular-nums; }
      .hist-card .hist-actions { display: flex; gap: 4px; }
      .hist-row .hist-actions { display: flex; gap: 6px; margin-top: 6px; justify-content: flex-end; }
      .hist-edit-form { display: flex; align-items: flex-end; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
      .hist-edit-form label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--ink-mid); }
      .hist-edit-form input {
        border: 1px solid var(--line-s); border-radius: 7px; padding: 6px 9px; font-size: 13px;
        background: var(--bg-0); color: var(--ink); width: 110px;
      }
      .hist-edit-form input[type="text"] { width: 140px; }
      .hist-delete-confirm {
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 10px;
      }
      .hist-delete-text { font-size: 12px; color: var(--ink-mid); }

      @media (max-width: 700px) {
        .vh-3col { grid-template-columns: 1fr; }
      }
      @media (max-width: 500px) {
        .appbar { padding: 0 14px; gap: 12px; }
        .brand .btext { display: none; }
        .tab { padding: 0 12px; }
        .vt-bar { padding: 8px 14px; }
        .main { padding: 16px 14px 30px; }
        .kv { font-size: 1.3rem; }
        .kpi-row { gap: 10px 18px; }
        .pend-inputs label { flex: 1 1 90px; }
        .hist-date { min-width: 0; }
        .hist-main { gap: 8px 14px; }
      }
      @container panel (max-width: 700px) {
        .vh-3col { grid-template-columns: 1fr; }
      }
      @container panel (max-width: 500px) {
        .appbar { padding: 0 14px; gap: 12px; }
        .brand .btext { display: none; }
        .tab { padding: 0 12px; }
        .vt-bar { padding: 8px 14px; }
        .main { padding: 16px 14px 30px; }
        .kv { font-size: 1.3rem; }
        .kpi-row { gap: 10px 18px; }
        .pend-inputs label { flex: 1 1 90px; }
        .hist-date { min-width: 0; }
        .hist-main { gap: 8px 14px; }
      }
    `;
    return el;
  }
}

customElements.define("ev-assistant-panel", EVAssistantPanel);
