/*
 * EV Assistant — custom sidebar panel.
 *
 * Vanilla custom element, no build step, no external dependencies.
 * HA injects `hass`, `panel`, `narrow`, `route`.
 * Entity IDs arrive as panel.config.entities (key → entity_id map).
 *
 * Tabs:
 *   - Übersicht  (overview: totals, efficiency, savings)
 *   - Fahrzeuge  (vehicle detail: external charging, home charging, trip log)
 */

const ACCENT_H = 220; // blue hue for design tokens

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
  }

  // --- HA-injected properties -------------------------------------------------

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first || !this._built) {
      this._renderShell();
      this._built = true;
    }
    this._update();
  }
  get hass() { return this._hass; }

  set panel(panel) { this._config = (panel && panel.config) || {}; }
  set narrow(v)    { this._narrow = v; }
  set route(_v)    {}

  // --- Helpers ----------------------------------------------------------------

  _eid(key) { return (this._config.entities || {})[key]; }
  _title()  { return this._config.title || "EV Assistant"; }

  // Read by ev_assistant entity key
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

  // Read any entity directly by ID (for evcc entities not in config map)
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

  _rawOn(entityId) {
    if (!this._hass) return false;
    return (this._hass.states[entityId] || {}).state === "on";
  }

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
        <div class="bt-name">${this._title()}</div>
        <div class="bt-sub">EV Assistant</div>
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
    for (const [id, el] of Object.entries(this._tabs)) {
      el.classList.toggle("active", id === view);
    }
    if (!this._main) return;
    this._main.innerHTML = "";
    this._r = {};

    if (view === "uebersicht") {
      this._main.appendChild(this._buildOverview());
    } else if (view === "fahrzeuge") {
      this._main.appendChild(this._buildVehicle());
    }
    this._update();
  }

  // --- Tab: Overview ----------------------------------------------------------

  _buildOverview() {
    const wrap = document.createElement("div");
    wrap.className = "tab-wrap";
    wrap.innerHTML = `

      <!-- Status hero -->
      <div class="card status-card">
        <div class="status-top">
          <div class="status-left">
            <div class="status-title">WARP 3 Pro</div>
            <div class="status-conn" id="ov-conn-label">
              <span class="conn-dot" id="ov-conn-dot"></span>
              <span id="ov-conn-text">—</span>
            </div>
          </div>
          <div class="status-badges">
            <div class="mode-badge" id="ov-mode-badge">—</div>
            <div class="phase-badge" id="ov-phase-badge">—</div>
          </div>
        </div>

        <!-- SOC bar -->
        <div class="soc-wrap">
          <div class="soc-bar-track">
            <div class="soc-bar-fill" id="ov-soc-fill"></div>
            <div class="soc-bar-limit" id="ov-soc-limit"></div>
          </div>
          <div class="soc-labels">
            <span class="soc-val" id="ov-soc-val">—</span>
            <span class="soc-limit-lbl" id="ov-soc-limit-lbl"></span>
          </div>
        </div>

        <!-- Live KPIs -->
        <div class="kpi-row" style="margin-top:16px">
          <div class="kpi">
            <div class="kv accent" id="ov-charge-power">—</div>
            <div class="kl">kW Ladeleistung</div>
          </div>
          <div class="kpi">
            <div class="kv" id="ov-session-kwh">—</div>
            <div class="kl">kWh Session</div>
          </div>
          <div class="kpi">
            <div class="kv green" id="ov-solar-pct">—</div>
            <div class="kl">% Solar</div>
          </div>
          <div class="kpi">
            <div class="kv" id="ov-session-price">—</div>
            <div class="kl">EUR Session</div>
          </div>
          <div class="kpi">
            <div class="kv" id="ov-duration">—</div>
            <div class="kl">Dauer</div>
          </div>
        </div>
      </div>

      <!-- Tariff -->
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:cash-clock"></ha-icon></span>
          <h2>Aktueller Tarif</h2>
          <span class="pill-live"><span class="dot-live"></span>live</span>
        </div>
        <div class="kpi-row">
          <div class="kpi">
            <div class="kv" id="ov-tariff-grid">—</div>
            <div class="kl">EUR/kWh Netzbezug</div>
          </div>
          <div class="kpi">
            <div class="kv" id="ov-tariff-feedin">—</div>
            <div class="kl">EUR/kWh Einspeisung</div>
          </div>
        </div>
      </div>

      <!-- All-time stats -->
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:chart-bar"></ha-icon></span>
          <h2>Gesamtstatistik Wallbox</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi">
            <div class="kv" id="ov-total-kwh">—</div>
            <div class="kl">kWh gesamt</div>
          </div>
          <div class="kpi">
            <div class="kv green" id="ov-total-solar">—</div>
            <div class="kl">% Solar gesamt</div>
          </div>
          <div class="kpi">
            <div class="kv" id="ov-avg-price">—</div>
            <div class="kl">EUR/kWh Ø Preis</div>
          </div>
        </div>
      </div>

    `;

    const q = (s) => wrap.querySelector(s);
    this._r = {
      ovConnDot:      q("#ov-conn-dot"),
      ovConnText:     q("#ov-conn-text"),
      ovModeBadge:    q("#ov-mode-badge"),
      ovPhaseBadge:   q("#ov-phase-badge"),
      ovSocFill:      q("#ov-soc-fill"),
      ovSocLimit:     q("#ov-soc-limit"),
      ovSocVal:       q("#ov-soc-val"),
      ovSocLimitLbl:  q("#ov-soc-limit-lbl"),
      ovChargePower:  q("#ov-charge-power"),
      ovSessionKwh:   q("#ov-session-kwh"),
      ovSolarPct:     q("#ov-solar-pct"),
      ovSessionPrice: q("#ov-session-price"),
      ovDuration:     q("#ov-duration"),
      ovTariffGrid:   q("#ov-tariff-grid"),
      ovTariffFeedin: q("#ov-tariff-feedin"),
      ovTotalKwh:     q("#ov-total-kwh"),
      ovTotalSolar:   q("#ov-total-solar"),
      ovAvgPrice:     q("#ov-avg-price"),
    };
    return wrap;
  }

  // --- Tab: Vehicle -----------------------------------------------------------

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

      <!-- Running session estimate -->
      <div class="card est-card hidden" id="est-card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:motion-sensor"></ha-icon></span>
          <h2>Laufende Erfassung</h2>
        </div>
        <div class="est-list">
          <div class="est-item hidden" id="est-ext-item">
            <ha-icon icon="mdi:ev-station" class="ci orange"></ha-icon>
            <span>Fremdladung</span>
            <strong id="est-ext-val">—</strong>
            <span class="dim">kWh (Schätzung)</span>
          </div>
          <div class="est-item hidden" id="est-trip-item">
            <ha-icon icon="mdi:road-variant" class="ci blue"></ha-icon>
            <span>Fahrt</span>
            <strong id="est-trip-val">—</strong>
            <span class="dim">km (Schätzung)</span>
          </div>
        </div>
      </div>

      <!-- External charging -->
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:ev-station"></ha-icon></span>
          <h2>Fremdladung</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi">
            <div class="kv vh-ext-kwh-total">—</div>
            <div class="kl">kWh gesamt</div>
          </div>
          <div class="kpi">
            <div class="kv vh-ext-cost-total">—</div>
            <div class="kl">EUR gesamt</div>
          </div>
          <div class="kpi">
            <div class="kv vh-ext-count">—</div>
            <div class="kl">Ladevorgänge</div>
          </div>
        </div>
        <div class="divider"></div>
        <div class="sub-head">Letzte Fremdladung</div>
        <div class="kpi-row">
          <div class="kpi">
            <div class="kv vh-ext-kwh-last">—</div>
            <div class="kl">kWh</div>
          </div>
          <div class="kpi">
            <div class="kv vh-ext-cost-last">—</div>
            <div class="kl">EUR</div>
          </div>
          <div class="kpi">
            <div class="kv vh-ext-price-last">—</div>
            <div class="kl">EUR/kWh</div>
          </div>
          <div class="kpi">
            <div class="kv vh-ext-duration-last">—</div>
            <div class="kl">Dauer</div>
          </div>
        </div>
      </div>

      <!-- Home charging -->
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:home-lightning-bolt"></ha-icon></span>
          <h2>Heimladen</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi">
            <div class="kv vh-home-kwh">—</div>
            <div class="kl">kWh gesamt</div>
          </div>
          <div class="kpi">
            <div class="kv vh-home-cost">—</div>
            <div class="kl">EUR gesamt</div>
          </div>
        </div>
      </div>

      <!-- Trip log -->
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:book-open-page-variant"></ha-icon></span>
          <h2>Fahrtenbuch</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi">
            <div class="kv vh-trip-km-last">—</div>
            <div class="kl">km letzte Fahrt</div>
          </div>
          <div class="kpi">
            <div class="kv vh-trip-count">—</div>
            <div class="kl">Fahrten</div>
          </div>
          <div class="kpi">
            <div class="kv vh-trip-km-total">—</div>
            <div class="kl">km gesamt</div>
          </div>
        </div>
      </div>

      <!-- Vehicle info -->
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:car-info"></ha-icon></span>
          <h2>Fahrzeug</h2>
        </div>
        <div class="kpi-row">
          <div class="kpi">
            <div class="kv vh-odo">—</div>
            <div class="kl">km Kilometerstand</div>
          </div>
          <div class="kpi">
            <div class="kv vh-efficiency">—</div>
            <div class="kl">% Ladewirkungsgrad</div>
          </div>
          <div class="kpi">
            <div class="kv green vh-savings">—</div>
            <div class="kl">EUR Ersparnis ggü. Verbrenner</div>
          </div>
        </div>
      </div>

    `;

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

  // --- Update (patch-in-place) ------------------------------------------------

  _update() {
    if (!this._built || !this._hass) return;
    if (this._view === "uebersicht") this._updateOverview();
    else if (this._view === "fahrzeuge") this._updateVehicle();
  }

  _updateOverview() {
    const r = this._r;
    if (!r.ovConnText) return;

    const WB = "evcc_warp_3_pro";
    const charging   = this._rawOn(`binary_sensor.${WB}_charging`);
    const connected  = this._rawOn(`binary_sensor.${WB}_connected`);

    // Connection status
    const connState = charging ? "charging" : connected ? "connected" : "disconnected";
    const connLabel = { charging: "Lädt", connected: "Verbunden", disconnected: "Nicht verbunden" };
    const connColor = { charging: "#4ade80", connected: "#fbbf24", disconnected: "#6b7280" };
    r.ovConnDot.style.background  = connColor[connState];
    r.ovConnDot.style.boxShadow   = charging ? `0 0 8px ${connColor.charging}` : "none";
    r.ovConnText.textContent       = connLabel[connState];

    // Charge mode
    const MODE_LABEL = { now: "Sofort", minpv: "Min+PV", pv: "Nur PV", off: "Aus" };
    const mode = this._raw(`select.${WB}_mode`) || "";
    r.ovModeBadge.textContent = MODE_LABEL[mode] || mode || "—";

    // Phases
    const phases = this._raw(`sensor.${WB}_phases_active`);
    r.ovPhaseBadge.textContent = phases ? phases + "P" : "—";

    // SOC bar
    const soc      = parseFloat(this._raw(`sensor.${WB}_vehicle_soc`) ?? NaN);
    const socLimit = parseFloat(this._raw(`sensor.${WB}_effective_limit_soc`) ?? NaN);
    if (!isNaN(soc)) {
      r.ovSocFill.style.width = Math.min(soc, 100) + "%";
      r.ovSocVal.textContent  = Math.round(soc) + " %";
    } else {
      r.ovSocFill.style.width = "0%";
      r.ovSocVal.textContent  = "—";
    }
    if (!isNaN(socLimit) && socLimit < 100) {
      r.ovSocLimit.style.left    = Math.min(socLimit, 100) + "%";
      r.ovSocLimit.style.display = "block";
      r.ovSocLimitLbl.textContent = "Limit: " + Math.round(socLimit) + " %";
    } else {
      r.ovSocLimit.style.display = "none";
      r.ovSocLimitLbl.textContent = "";
    }

    // Live KPIs
    const power = parseFloat(this._raw(`sensor.${WB}_charge_power`) ?? NaN);
    r.ovChargePower.textContent  = isNaN(power) ? "—" : power.toFixed(1);
    r.ovSessionKwh.textContent   = this._rawNum(`sensor.${WB}_session_energy`, 2);
    r.ovSolarPct.textContent     = this._rawNum(`sensor.${WB}_session_solar_percentage`, 0);
    r.ovSessionPrice.textContent = this._rawNum(`sensor.${WB}_session_price`, 2);

    // Duration: sensor gives seconds
    const durSec = parseFloat(this._raw(`sensor.${WB}_charge_duration`) ?? NaN);
    if (!isNaN(durSec) && durSec > 0) {
      const min = Math.round(durSec / 60);
      r.ovDuration.textContent = min < 60 ? min + " min" : `${Math.floor(min/60)}h ${min%60}m`;
    } else {
      r.ovDuration.textContent = "—";
    }

    // Tariff
    r.ovTariffGrid.textContent   = this._rawNum("sensor.evcc_tariff_grid", 3);
    r.ovTariffFeedin.textContent = this._rawNum("sensor.evcc_tariff_feed_in", 3);

    // All-time stats
    r.ovTotalKwh.textContent   = this._rawNum("sensor.evcc_stat_total_charged_kwh", 1);
    r.ovTotalSolar.textContent = this._rawNum("sensor.evcc_stat_total_solar_percentage", 1);
    r.ovAvgPrice.textContent   = this._rawNum("sensor.evcc_stat_total_avg_price", 4);
  }

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
        display: block;
        height: 100%;
        --accent: #3b82f6;
        --bg-0: var(--primary-background-color, #0f172a);
        --bg-1: var(--card-background-color, #1e293b);
        --ink: var(--primary-text-color, #f1f5f9);
        --ink-mid: var(--secondary-text-color, #94a3b8);
        --ink-dim: var(--disabled-text-color, #64748b);
        --line: var(--divider-color, rgba(255,255,255,0.07));
        --line-s: rgba(255,255,255,0.13);
        --radius: 14px;
        --pad: 20px;
        --gap: 14px;
        font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        color: var(--ink);
        background: var(--bg-0);
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
        display: flex; align-items: center; gap: 8px;
        padding: 0 18px; height: 100%;
        border: none; background: none; cursor: pointer;
        color: var(--ink-mid); font-size: 14px; font-weight: 600;
        border-bottom: 2.5px solid transparent; transition: color 0.15s;
        white-space: nowrap; --mdc-icon-size: 18px;
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

      /* Tab content */
      .tab-wrap { display: flex; flex-direction: column; gap: var(--gap); }

      /* Status badges */
      .badge-row { display: flex; gap: 8px; flex-wrap: wrap; min-height: 0; }
      .badge-row:empty { display: none; }
      .badge {
        display: flex; align-items: center; gap: 6px;
        font-size: 0.72rem; font-weight: 700;
        padding: 5px 12px; border-radius: 9999px;
        --mdc-icon-size: 14px;
      }
      .badge-ext  { background: #7c2d12; color: #fed7aa; border: 1px solid #9a3412; }
      .badge-trip { background: #1e3a5f; color: #bfdbfe; border: 1px solid #1d4ed8; }

      /* Cards */
      .card {
        background: var(--bg-1);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: var(--pad);
      }
      .card-head {
        display: flex; align-items: center; gap: 9px;
        margin-bottom: 16px; --mdc-icon-size: 17px;
      }
      .card-head h2 {
        font-size: 12px; font-weight: 700;
        letter-spacing: 0.07em; text-transform: uppercase;
        color: var(--ink-mid); margin: 0;
      }
      .card-head .ic { color: var(--ink-dim); display: grid; place-items: center; }
      .divider { height: 1px; background: var(--line); margin: 14px 0; }
      .sub-head {
        font-size: 11px; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.06em;
        color: var(--ink-dim); margin-bottom: 10px;
      }

      /* KPI grid */
      .kpi-row { display: flex; flex-wrap: wrap; gap: 12px 28px; }
      .kpi     { min-width: 60px; }
      .kv      { font-size: 1.55rem; font-weight: 700; line-height: 1.1; }
      .kl      { font-size: 0.7rem; color: var(--ink-mid); margin-top: 2px; }
      .kv.green { color: #4ade80; }

      /* Running estimate card */
      .est-card { border-color: rgba(251, 146, 60, 0.25); }
      .est-list  { display: flex; flex-direction: column; gap: 8px; }
      .est-item  { display: flex; align-items: center; gap: 8px; font-size: 0.88rem; }
      .est-item strong { font-size: 1rem; font-weight: 700; }
      .ci       { --mdc-icon-size: 18px; }
      .ci.orange { color: #fb923c; }
      .ci.blue   { color: #60a5fa; }
      .dim       { color: var(--ink-dim); font-size: 0.78rem; }

      /* Status hero card */
      .status-card { padding-bottom: 18px; }
      .status-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px; gap: 12px; }
      .status-title { font-size: 13px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--ink-mid); }
      .status-conn { display: flex; align-items: center; gap: 8px; margin-top: 6px; font-size: 1rem; font-weight: 600; }
      .conn-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; transition: background 0.3s; }
      .status-badges { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
      .mode-badge, .phase-badge {
        font-size: 0.72rem; font-weight: 700; padding: 4px 10px;
        border-radius: 9999px; background: var(--bg-0); border: 1px solid var(--line-s);
        color: var(--ink-mid); white-space: nowrap;
      }

      /* SOC bar */
      .soc-wrap { margin-bottom: 4px; }
      .soc-bar-track {
        position: relative; height: 10px; border-radius: 9999px;
        background: var(--bg-0); border: 1px solid var(--line-s); overflow: visible;
      }
      .soc-bar-fill {
        height: 100%; border-radius: 9999px;
        background: linear-gradient(90deg, var(--accent), #34d399);
        transition: width 0.4s ease;
      }
      .soc-bar-limit {
        display: none; position: absolute; top: -3px;
        width: 2px; height: 16px; background: #f59e0b;
        border-radius: 2px; transform: translateX(-50%);
      }
      .soc-labels { display: flex; justify-content: space-between; margin-top: 6px; }
      .soc-val { font-size: 1.4rem; font-weight: 700; }
      .soc-limit-lbl { font-size: 0.72rem; color: #f59e0b; align-self: center; }

      /* Accent color for charge power */
      .kv.accent { color: var(--accent); }

      /* Live pill */
      .pill-live {
        display: inline-flex; align-items: center; gap: 6px;
        margin-left: auto; font-size: 11px; color: var(--ink-dim);
        padding: 4px 10px; border-radius: 999px;
        background: var(--bg-0); border: 1px solid var(--line);
      }
      .dot-live {
        width: 7px; height: 7px; border-radius: 50%; background: #4ade80;
        animation: pulse-dot 2.2s ease-in-out infinite;
      }
      @keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:.3} }

      .hidden { display: none !important; }

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
