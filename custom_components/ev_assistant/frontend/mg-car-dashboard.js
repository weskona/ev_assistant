/*
 * mg-car-dashboard.js
 * Ablage:    /config/www/glow-dashboard/mg-car-dashboard.js
 * Ressource: /local/glow-dashboard/mg-car-dashboard.js?v=7  (Typ: JavaScript)
 * YAML:      type: custom:mg-car-dashboard
 */

window.customCards = window.customCards || [];
const VERSION = "3.1.0";
const FONT_URL = "https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap";

const WD = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const WD_LONG = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
const MON = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
const MON_LONG = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];

/* =====================================================================
 *  EINSTELLUNGEN – hier alle Sensoren, Pfade und Optionen anpassen.
 *  Jeder Wert kann zusätzlich per YAML überschrieben werden, z. B.
 *    type: custom:mg-car-dashboard
 *    car:
 *      soc: sensor.mein_auto_batterie
 *      image: /local/mein_auto.png
 * ===================================================================== */
const CAR_DEFAULTS = {
  fit_screen: true,   // Desktop/Laptop: Dashboard passt sich der Fensterhöhe an (kein Scrollen der Seite)
  debug: false,       // true = Diagnose-Meldungen in der Browser-Konsole

  // --- Energie (für Ladeleistung und Aufteilung Netz/PV im Verlauf) ---
  energy: {
    car_power: "sensor.shelly_wallbox_power",                       // Ladeleistung, falls car.evcc.power fehlt
    grid_import: "sensor.alpha_ess_netzbezug_leistung_vom_netz",     // Netzbezug (Leistung)
    home: "sensor.strom_leistung_haus_gesamt_inkl_bkw_und_marstek",  // Hausverbrauch inkl. Auto (Leistung)
  },

  car: {
    // --- Fahrzeug ---
    name: "Citroën ë-C3",
    image: "/local/auto.png",                       // Bild des Autos (leer = kein Bild)
    soc: "sensor.e_c3_batterie",                    // Ladestand in %
    range: "sensor.e_c3_reichweite",                // Reichweite in km
    status: "binary_sensor.e_c3_motor",             // on = fährt
    status_on: "Motor an",                          // Text bei status = on
    status_off: "Geparkt",                          // Text bei status = off
    cable: "binary_sensor.warp3_2ee3_cable",        // on = eingesteckt, off = abgesteckt

    // --- Wallbox / Lademodus ---
    limit: "number.wallbox_ladestrom",              // Ladestrom (A)
    mode: "select.evcc_warp3_mode",                 // evcc-Lademodus: Aus / Smart / Schnell
    always: "select.evcc_warp3_always_charge",      // nur bei Smart: Aus / Ein / Einmalig
    manual_mode: "input_select.evcc_lademodus_manuell",   // eigene Vorgabe (automatisch / manuell), leer lassen wenn nicht vorhanden

    // --- evcc (Ladepunkt) ---
    evcc: {
      charging: "binary_sensor.evcc_warp3_charging",
      connected: "binary_sensor.evcc_warp3_connected",
      power: "sensor.evcc_warp3_charge_power",
      session_energy: "sensor.evcc_warp3_session_energy",
      session_solar: "sensor.evcc_warp3_session_solar_percentage",
      session_price: "sensor.evcc_warp3_session_price",
      remaining: "sensor.evcc_warp3_charge_remaining_duration",
      duration: "sensor.evcc_warp3_charge_duration",
      finish: "sensor.e_c3_batterie_ladezeit_ende",
      limit_soc: "select.evcc_warp3_limit_soc",                 // Ladeziel (Auswahl + Markierung im Balken)
      min_soc: "input_number.evcc_auto_soc_schwelle_minpv",     // Markierung „bis hier immer laden“
      solar_total: "sensor.evcc_stat_total_solar_percentage",
      last_charge: "sensor.e_c3_letzte_ladung",
    },
    evcc_vehicle: "",                // nur Ladungen dieses evcc-Fahrzeugs in „Alle Ladungen“ (leer = alle)

    // --- ev_assistant ---
    // Die Entitäten werden automatisch gefunden. Einzelne lassen sich hier fest vorgeben, z. B.
    //   ev_assistant: { odo: "sensor.mein_km_stand", cost_year: "sensor.kosten_jahr" },
    // Verwendete Schlüssel: odo, odo_day_km, odo_week_km, odo_month_km, odo_year_km, odo_avg_day, odo_year_projected,
    //   trip_count, last_trip_km, vehicle_avg_consumption, trip_avg_consumption, range_estimate, available_kwh,
    //   battery_capacity, equivalent_full_cycles, measured_efficiency, cost_day, cost_week, cost_month, cost_year,
    //   kwh_month, kwh_year, home_kwh, total_kwh, savings, co2_savings, pending, trip_pending, wartung_faellig,
    //   evcc_charge_plan, evcc_mode_control, charge_before_pv_recommended
    ev_assistant: {},
    ev_assistant_entry: "",          // config_entry_id von ev_assistant (leer = automatisch suchen)
    stats: ["vehicle_avg_consumption", "odo", "cost_year", "savings"],   // Kennzahlen in der Auto-Kachel

    // --- Fahrtenbuch ---
    trips: "sensor.e_c3_fahrtenbuch_2",   // Sensor mit Attribut "trips"
    trips_visible: 5,                     // so viele Fahrten in der Kachel, wenn die Seite nicht an die Fensterhöhe angepasst ist
    trips_max: 100,                       // so viele Fahrten im Fenster „Alle Fahrten“

    // --- Verlauf: 5 Zeiträume zum Umschalten (Stunden, optional mit eigener Beschriftung) ---
    history_ranges: [
      { hours: 6,   label: "6 h" },
      { hours: 24,  label: "24 h" },
      { hours: 72,  label: "3 T" },
      { hours: 168, label: "7 T" },
      { hours: 720, label: "30 T" },
    ],
    history_hours: 24,                 // Zeitraum beim ersten Öffnen (einer der Werte oben)
    bars_from_hours: 0,                // ab diesem Zeitraum geladene kWh als Balken (Netz/PV) statt Linie (0 = immer Balken)
    bars_daily_from_hours: 72,         // ab diesem Zeitraum Tagesbalken (darunter stündlich), 72 = ab 3 Tagen
    bars_weekly_from_hours: 744,       // ab diesem Zeitraum Wochenbalken (Mo–So), 744 = ab 31 Tagen
    split_grid: null,                  // Netzbezug für die Aufteilung, Standard: energy.grid_import
    split_home: null,                  // Hausverbrauch inkl. Auto, Standard: energy.home
    session_days: 30,                  // „Letzte Ladung“: so viele Tage im Verlauf suchen
    session_stats_days: 120,           // … und so viele Tage in der Langzeitstatistik

    // --- Darstellung der Auswahlwerte (Groß-/Kleinschreibung egal, mehrere Schreibweisen mit |) ---
    mode_styles: {
      "aus|off":           { label: "Aus",     icon: "mdi:power-off",      color: "#8b91a1" },
      "smart|pv|minpv":    { label: "Smart",   icon: "mdi:solar-power",    color: "#34d399" },
      "schnell|fast|now":  { label: "Schnell", icon: "mdi:lightning-bolt", color: "#fb923c" },
    },
    always_when: "smart|pv|minpv",     // bei diesen Modi gibt es „Immer laden“ in der Smart-Kachel
    always_styles: {
      "aus|off|false":     { label: "Aus",      icon: "mdi:close",    color: "#8b91a1" },
      "ein|on|true":       { label: "Immer",    icon: "mdi:infinity", color: "#38bdf8" },
      "einmalig|once":     { label: "Einmalig", glyph: "1×",          color: "#a78bfa" },
    },
    manual_styles: {
      "automatisch|auto":        { label: "Auto",    icon: "mdi:robot-outline",      color: "#38bdf8" },
      "aus|off":                 { label: "Aus",     icon: "mdi:power-off",          color: "#8b91a1" },
      "pv":                      { label: "PV",      icon: "mdi:solar-power",        color: "#34d399" },
      "min + pv|min+pv|minpv":   { label: "Min+PV",  icon: "mdi:transmission-tower", color: "#f7b733" },
      "schnell|now|fast":        { label: "Schnell", icon: "mdi:lightning-bolt",     color: "#fb923c" },
    },
  },
};

const OFFLINE_HD = ["unavailable", "unknown", "none", ""];

/* ---------------- Helfer ---------------- */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const de = (v, d = 1) => Number(v).toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
const pad = (n) => String(n).padStart(2, "0");
const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
const merge = (a, b) => {
  const out = { ...a };
  for (const k of Object.keys(b || {})) out[k] = isObj(a?.[k]) && isObj(b[k]) ? merge(a[k], b[k]) : b[k];
  return out;
};
const icon = (i, cls = "") => `<ha-icon class="${cls}" icon="${esc(i)}"></ha-icon>`;

class MgCarDashboard extends HTMLElement {
  static getStubConfig() { return {}; }

  setConfig(config) {
    this._config = merge(CAR_DEFAULTS, config || {});
    if (this._built) { this._built = false; this._build(); if (this._hass) this._update(true); }
  }

  getCardSize() { return 14; }
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (!this._built) this._build();
    if (first) { this._loadCarHist(); this._loadLastSession(); }
    this._update();
  }
  connectedCallback() {
    if (!this._onResize) {
      this._onResize = () => { cancelAnimationFrame(this._fitRaf); this._fitRaf = requestAnimationFrame(() => { this._fit(); this._render_trips(); }); };
      this._ro = new ResizeObserver(this._onResize);
    }
    window.addEventListener("resize", this._onResize);
    this._ro.observe(this); this._onResize();
    if (!this._histTimer) this._histTimer = setInterval(() => { this._loadCarHist(); this._loadLastSession(); }, 15 * 60000);
  }
  disconnectedCallback() {
    if (this._onResize) { window.removeEventListener("resize", this._onResize); this._ro.disconnect(); }
    clearInterval(this._histTimer); this._histTimer = null;
  }

  _build() {
    if (!document.querySelector(`link[href="${FONT_URL}"]`)) { const l = document.createElement("link"); l.rel = "stylesheet"; l.href = FONT_URL; document.head.appendChild(l); }
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (e) => this._click(e));
    }
    if (!this._pinBound) { this._pinBound = true; this.shadowRoot.addEventListener("change", (e) => { const t = e.composedPath()[0]; if (t?.classList?.contains("pin")) { this._planTime = t.value; t.blur(); } }); }
    if (!this._hoverBound) {
      this._hoverBound = true;
      this.shadowRoot.addEventListener("pointermove", (e) => this._barHover(e));
      this.shadowRoot.addEventListener("pointerdown", (e) => this._barHover(e));
      this.shadowRoot.addEventListener("pointerleave", () => { const t = this.shadowRoot.querySelector(".gtip"); if (t) t.hidden = true; this.shadowRoot.querySelector(".hl")?.setAttribute("width", 0); }, true);
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}${CAR_STYLE}</style>
      <div class="wrap carpage">
        <div class="grid">
          <div class="col"><section class="panel car" id="car"></section><section class="panel grow" id="trips"></section></div>
          <div class="col"><section class="panel" id="live"></section><section class="panel" id="mgmt"></section></div>
          <div class="col"><section class="panel grow" id="hist"></section></div>
        </div>
      </div><dialog class="dlg" id="cardlg"></dialog>`;
    this._built = true;
    requestAnimationFrame(() => { this._fit(); this._render_trips(); });
  }

  _update(force = false) {
    if (!this._hass || !this._built) return;
    const c = this._config.car, E = this._eva();
    const ids = [c.soc, c.range, c.status, c.cable, c.limit, c.mode, c.always, c.trips, c.manual_mode, this._config.energy.car_power,
      ...Object.values(c.evcc || {}), ...Object.values(E)].filter(Boolean);
    const sig = ids.map((id) => { const s = this._st(id); return s ? s.state + s.last_updated : "-"; }).join("|") + (this._carHist?.t || "") + Math.floor(Date.now() / 60000);
    if (!force && sig === this._sigCar) return;
    this._sigCar = sig;
    if (this._menu) return;   // Auswahlmenü offen: nicht neu zeichnen
    this._render_car();
    this._render_live();
    this._render_mgmt();
    this._render_trips();
    this._render_hist();
  }

  /* evcc setzt die Sitzungswerte nach dem Laden auf 0 → letzte echte Sitzung aus dem Verlauf holen */
  async _loadLastSession() {
    const ev = this._config.car.evcc || {}, eid = ev.session_energy;
    if (!eid || !this._st(eid) || !this._hass?.callApi) return;
    const ids = [eid, ev.session_solar, ev.session_price, ev.duration].filter((x) => x && this._st(x));
    const start = new Date(Date.now() - (this._config.car.session_days || 30) * 86400000).toISOString();
    try {
      const res = await this._hass.callApi("GET", `history/period/${start}?filter_entity_id=${ids.join(",")}&end_time=${encodeURIComponent(new Date().toISOString())}&minimal_response&no_attributes`);
      const hist = {};
      for (const l of res || []) if (l.length) hist[l[0].entity_id] = l.map((x) => [new Date(x.last_changed || x.last_updated).getTime(), parseFloat(x.state)]).filter((x) => !isNaN(x[1]));
      const en = hist[eid] || [];
      let end = null;
      for (let i = en.length - 1; i >= 0; i--) if (en[i][1] > 0) { end = en[i + 1]?.[0] ?? en[i][0]; break; }   // Zeitpunkt des Zurücksetzens = Sitzungsende
      if (end == null) {   // im Verlauf (Recorder, meist 10 Tage) nichts → Langzeitstatistik (Stundenmaxima) durchsuchen
        const st = await this._statsLastSession(ids);
        this._lastSess = st || { none: true, days: Math.round((Date.now() - new Date(start).getTime()) / 86400000) };
        this._log("letzte Ladung", this._lastSess);
        return this._update(true);
      }
      const vals = {};
      for (const id of ids) {
        const l = (hist[id] || []).filter((x) => x[0] < end);
        const v = l.length ? l[l.length - 1][1] : null;
        if (v != null) vals[id] = v;
      }
      this._lastSess = { end, vals, src: "history" };
    } catch (e) { this._lastSess = { err: true }; }
    this._log("letzte Ladung", this._lastSess);
    this._update(true);
  }

  async _statsLastSession(ids) {
    if (!this._hass.callWS) return null;
    const days = this._config.car.session_stats_days || 120;
    try {
      const st = await this._hass.callWS({ type: "recorder/statistics_during_period", start_time: new Date(Date.now() - days * 86400000).toISOString(),
        end_time: new Date().toISOString(), statistic_ids: ids, period: "hour", types: ["max", "mean", "state"] });
      const ts = (v) => (typeof v === "number" ? v : new Date(v).getTime());
      const val = (x) => x.max ?? x.state ?? x.mean;
      const en = st?.[ids[0]] || [];
      let k = -1;
      for (let i = en.length - 1; i >= 0; i--) if (val(en[i]) > 0) { k = i; break; }
      if (k < 0) return null;
      const end = ts(en[k].end ?? en[k].start + 3600000), hour = ts(en[k].start), vals = {};
      for (const id of ids) {
        const row = (st?.[id] || []).filter((x) => ts(x.start) <= hour && val(x) != null).pop();
        if (row) vals[id] = val(row);
      }
      return { end, vals, src: "stats" };
    } catch (e) { return null; }
  }

  /* --- Alle Ladungen (ev_assistant: evcc-Ladelogbuch + Fremdladungen) --- */
  _evaEntryId() {
    if (this._config.car.ev_assistant_entry) return this._config.car.ev_assistant_entry;
    if (this._evaEntryCache) return this._evaEntryCache;
    const reg = this._hass?.entities || {}, dev = this._hass?.devices || {};
    for (const id of Object.values(this._eva())) {
      const e = reg[id]; if (!e) continue;
      if (e.config_entry_id) { this._evaEntryCache = e.config_entry_id; return e.config_entry_id; }
      const d = dev[e.device_id]; if (d?.config_entries?.length) { this._evaEntryCache = d.config_entries[0]; return d.config_entries[0]; }
    }
    // Fallback: über alle Entitäten mit platform ev_assistant
    for (const e of Object.values(reg)) {
      if (e.platform === "ev_assistant" && e.config_entry_id) { this._evaEntryCache = e.config_entry_id; return e.config_entry_id; }
    }
    return null;
  }

  async _loadCharges(force) {
    if (!force && this._charges && Date.now() - this._charges.t < 5 * 60000) return;
    const id = this._evaEntryId(), out = { t: Date.now(), list: [], err: null };
    if (!id || !this._hass.callWS) { out.err = "ev_assistant nicht gefunden"; this._charges = out; return this._renderCharges(); }
    const [home, ext] = await Promise.all([
      this._hass.callWS({ type: "ev_assistant/evcc_sessions", config_entry_id: id }).catch((e) => ({ error: e })),
      this._hass.callWS({ type: "ev_assistant/charges", config_entry_id: id }).catch((e) => ({ error: e })),
    ]);
    const veh = (this._config.car.evcc_vehicle || "").toLowerCase();
    for (const x of home?.sessions || []) {
      if (veh && x.vehicle && String(x.vehicle).toLowerCase() !== veh) continue;
      const ts = x.created ? Date.parse(x.created) : null, te = x.finished ? Date.parse(x.finished) : null;
      if (!ts) continue;
      const dur = typeof x.chargeDuration === "number" && x.chargeDuration > 0 ? x.chargeDuration / 1e9 / 60 : te && te > ts ? (te - ts) / 60000 : null;
      out.list.push({ type: "home", ts, te, kwh: x.chargedEnergy ?? null, pv: x.solarPercentage ?? null, cost: x.price ?? null,
        per: x.pricePerKWh ?? null, dur, s0: x.socStart ?? null, s1: x.socEnd ?? null, who: x.vehicle || "" });
    }
    for (const x of ext?.charges || []) {
      const t = (x.start_ts || x.erfasst_ts) ? (x.start_ts || x.erfasst_ts) * 1000 : (x.datum ? Date.parse(x.datum) : null);
      if (!t) continue;
      out.list.push({ type: "ext", ts: t, te: null, kwh: x.kwh ?? null, pv: null, cost: x.kosten ?? null, per: x.preis_kwh ?? null,
        dur: x.dauer_min ?? null, s0: x.soc_start ?? null, s1: x.soc_end ?? null, who: x.anbieter || "Fremdladung", ac: x.ac_dc || x.typ || "" });
    }
    out.list.sort((a, b) => b.ts - a.ts);
    if (home?.error && ext?.error) out.err = "Abruf bei ev_assistant fehlgeschlagen";
    this._charges = out;
    this._renderCharges();
  }

  _openCharges() {
    this._openDlg("charges");
    this._renderCharges();
    this._loadCharges();
  }

  _renderCharges() {
    const d = this.shadowRoot.getElementById("cardlg");
    if (!d || this._dlg !== "charges") return;
    const C = this._charges, f = this._chFilter || "all";
    const all = C?.list || [], list = all.filter((x) => f === "all" || x.type === f);
    const sum = (arr, k) => arr.reduce((a, x) => a + (x[k] || 0), 0);
    const kwh = sum(list, "kwh"), cost = sum(list, "cost");
    const pvK = list.reduce((a, x) => a + (x.pv != null && x.kwh ? x.kwh * x.pv / 100 : 0), 0), pvBase = list.reduce((a, x) => a + (x.pv != null && x.kwh ? x.kwh : 0), 0);
    const nH = all.filter((x) => x.type === "home").length, nE = all.filter((x) => x.type === "ext").length;
    const seg = [["all", `Alle ${all.length}`], ["home", `Zuhause ${nH}`], ["ext", `Fremd ${nE}`]]
      .map(([k, l]) => `<button class="hseg ${f === k ? "sel" : ""}" data-act="chfilter" data-v="${k}">${l}</button>`).join("");
    let lastM = "";
    const rows = list.map((x) => {
      const dt = new Date(x.ts), m = `${MON_LONG[dt.getMonth()]} ${dt.getFullYear()}`;
      const mh = m !== lastM ? `<div class="chm">${m}</div>` : ""; lastM = m;
      const dur = x.dur == null ? "" : x.dur >= 60 ? `${Math.floor(x.dur / 60)}:${pad(Math.round(x.dur % 60))} h` : `${Math.round(x.dur)} min`;
      const per = x.per != null ? x.per : x.cost != null && x.kwh > 0.05 ? x.cost / x.kwh : null;
      const pv = x.pv != null ? Math.max(0, Math.min(100, x.pv)) : null;
      return `${mh}<div class="chr ${x.type}">
        <span class="chi">${icon(x.type === "home" ? "mdi:home-lightning-bolt" : "mdi:ev-station")}</span>
        <span class="chd"><b>${WD[dt.getDay()]} ${dt.getDate()}. ${MON[dt.getMonth()]}</b><small>${pad(dt.getHours())}:${pad(dt.getMinutes())} Uhr${dur ? ` · ${dur}` : ""}${x.type === "ext" ? ` · ${esc(x.who)}` : ""}</small></span>
        <span class="chpv">${pv != null ? `<i class="pvbar"><i style="width:${pv}%"></i></i><small>${Math.round(pv)} % PV</small>` : x.s0 != null && x.s1 != null ? `<small>${Math.round(x.s0)} → ${Math.round(x.s1)} %</small>` : ""}</span>
        <span class="chk"><b>${x.kwh == null ? "–" : de(x.kwh, 1)}</b><small>kWh</small></span>
        <span class="chc"><b>${x.cost == null ? "–" : de(x.cost, 2) + " €"}</b><small>${per != null ? `${de(per * 100, 1)} ct/kWh` : ""}</small></span>
      </div>`;
    }).join("");
    const body = !C ? `<div class="empty">Lädt …</div>` : C.err && !all.length ? `<div class="empty">${esc(C.err)}</div>`
      : !list.length ? `<div class="empty">Keine Ladungen</div>` : `<div class="chlist">${rows}</div>`;
    const sc = d.querySelector(".dbody")?.scrollTop || 0;
    d.innerHTML = `<div class="dpan chpan">
      <div class="dhd"><span class="dico">${icon("mdi:ev-station")}</span>
        <span class="rtx"><span class="rname">Alle Ladungen</span><span class="rsub">evcc-Ladelogbuch und Fremdladungen aus ev_assistant</span></span>
        <button class="dx" data-act="cardclose" aria-label="Schließen">${icon("mdi:close")}</button></div>
      <div class="chsum">
        <div><span>Ladungen</span><b>${list.length}</b></div>
        <div><span>Energie</span><b>${de(kwh, kwh >= 100 ? 0 : 1)}<small>kWh</small></b></div>
        <div><span>Kosten</span><b>${de(cost, 2)}<small>€</small></b></div>
        <div><span>Ø Preis</span><b>${kwh > 0.1 && cost ? de(cost / kwh * 100, 1) : "–"}<small>ct/kWh</small></b></div>
        <div class="pv"><span>PV-Anteil</span><b>${pvBase > 0.1 ? Math.round(pvK / pvBase * 100) : "–"}<small>%</small></b></div>
        <div class="hsegs">${seg}</div>
      </div>
      <div class="dbody">${body}</div></div>`;
    const b = d.querySelector(".dbody"); if (b) b.scrollTop = sc;
  }

  /* --- Lademanagement: Vorgabe, evcc-Modus (inkl. Immer laden), Ladestrom, Mindestladung, Ladeplan + Vollladung (ev_assistant) --- */
  _render_mgmt() {
    const el = this.shadowRoot.getElementById("mgmt"); if (!el) return;
    if (this.shadowRoot.activeElement?.classList?.contains("pin")) return;   // während der Eingabe nicht neu zeichnen
    const c = this._config.car, ev = c.evcc || {}, E = this._eva();
    const step = (lbl, ic, id, unit) => {
      const st = this._st(id); if (!st) return "";
      const a = st.attributes, pend = this._pendingNum?.[id], v = pend != null ? pend : parseFloat(st.state), u = unit ?? a.unit_of_measurement ?? "";
      return `<div class="mstep"><span class="msl">${icon(ic)}${lbl}</span>
        <div class="tgt"><button class="tb" data-act="mnum" data-entity="${esc(id)}" data-d="-1" aria-label="weniger">−</button>
        <span class="tv">${isNaN(v) ? "–" : de(v, (a.step || 1) < 1 ? 1 : 0)}<small> ${esc(u)}</small></span>
        <button class="tb" data-act="mnum" data-entity="${esc(id)}" data-d="1" aria-label="mehr">+</button></div></div>`;
    };
    const sw = (on, act, lbl, sub, ic, dis) => `<button class="mtog ${on ? "on" : ""} ${dis ? "dis" : ""}" data-act="${act}" data-v="${on ? "0" : "1"}">${icon(ic)}<span><b>${lbl}</b>${sub ? `<small>${sub}</small>` : ""}</span><i class="msw"><i></i></i></button>`;

    // Vorgabe (eigener Helfer)
    const manual = this._st(c.manual_mode), auto = manual && /^auto/i.test(manual.state);

    // evcc-Modus als Kacheln, „Immer laden“ als Auswahl in der Smart-Kachel
    const mst = this._st(c.mode), ast = this._st(c.always);
    // Modus-Zeile: [Vorgabe ▼] [Aus] [Smart ▼] [Schnell]
    const modeTiles = (() => {
      if (!mst) return "";
      const opts = mst.attributes.options || [], curM = mst.state;
      const tiles = [];
      // Vorgabe-Dropdown (manual_mode) – zeigt aktuellen Wert, rot wenn nicht Auto
      if (manual) {
        const curV = manual.state, isAuto = /^auto/i.test(curV);
        const vm = this._styleFor(c.manual_styles, curV);
        tiles.push(`<button class="mmode vorgabe ${isAuto ? "" : "manual"}" style="--cc:${isAuto ? "#38bdf8" : "#ef4444"}" data-act="vorgabemenu">
          <span class="mmh">${icon(vm.icon || "mdi:cog")}<b>${esc(this._label(vm, curV))}</b>${icon("mdi:chevron-down", "mchv")}</span></button>`);
      }
      // evcc-Modi: immer nach aktuellem evcc-State hervorgehoben
      for (const o of opts) {
        const m = this._styleFor(c.mode_styles || {}, o), sel = o === curM, smart = this._matches(o, c.always_when);
        if (smart && ast) {
          const am = this._styleFor(c.always_styles || {}, ast.state);
          const alwaysOff = /^aus$|^off$/i.test(ast.state);
          const smartIco = sel && !alwaysOff ? (am.glyph ? `<span class="glyph">${esc(am.glyph)}</span>` : icon(am.icon || m.icon || "mdi:ev-station")) : icon(m.icon || "mdi:ev-station");
          tiles.push(`<button class="mmode ${sel ? "sel" : ""}" style="--cc:${m.color || "var(--gold)"}" data-act="smartmenu" data-mode="${esc(o)}">
            <span class="mmh">${smartIco}<b>${esc(this._label(m, o))}</b>${sel ? icon("mdi:chevron-down", "mchv") : ""}</span></button>`);
        } else {
          tiles.push(`<button class="mmode ${sel ? "sel" : ""}" style="--cc:${m.color || "var(--gold)"}" data-act="msetmode" data-entity="${esc(c.mode)}" data-opt="${esc(o)}">
            <span class="mmh">${icon(m.icon || "mdi:ev-station")}<b>${esc(this._label(m, o))}</b></span></button>`);
        }
      }
      return `<div class="mmodes">${tiles.join("")}</div>`;
    })();

    // ev_assistant: Ladeplan, Vollladung, Pause
    const plan = this._st(E.evcc_charge_plan), pa = plan?.attributes || {}, mc = this._st(E.evcc_mode_control), ma = mc?.attributes || {};
    const planD = plan && !OFFLINE_HD.includes(plan.state) ? new Date(plan.state) : null, hasPlan = planD && !isNaN(planD);
    const fmtD = (d) => `${WD[d.getDay()]} ${d.getDate()}. ${MON[d.getMonth()]}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const entry = this._evaEntryId();
    let planHtml = "";
    if (entry || plan) {
      if (hasPlan) {
        const ps = pa.projected_start ? new Date(pa.projected_start) : null, pe = pa.projected_end ? new Date(pa.projected_end) : null;
        planHtml = `<div class="mplan act">
          <div class="mph">${icon("mdi:calendar-clock")}<span><b>${pa.target_soc != null ? `${Math.round(pa.target_soc)} %` : "Ladeplan"} bis ${fmtD(planD)}</b>
            ${ps && !isNaN(ps) ? `<small>Laden voraussichtlich ${pad(ps.getHours())}:${pad(ps.getMinutes())}${pe && !isNaN(pe) ? `–${pad(pe.getHours())}:${pad(pe.getMinutes())}` : ""} Uhr</small>` : ""}</span>
            <button class="qbtn ghost" data-act="mplanclear">${icon("mdi:delete-outline")}Löschen</button></div>
          ${pa.erwartung ? `<div class="mpe">${icon("mdi:information-outline")}${esc(pa.erwartung)}</div>` : ""}</div>`;
      } else {
        const def = new Date(); def.setDate(def.getDate() + 1); def.setHours(7, 0, 0, 0);
        const val = this._planTime || `${def.getFullYear()}-${pad(def.getMonth() + 1)}-${pad(def.getDate())}T07:00`;
        const soc = this._planSoc ?? 80;
        planHtml = `<div class="mplan">
          <div class="mph">${icon("mdi:calendar-plus")}<span><b>Ladeplan anlegen</b><small>evcc lädt bis zur Zielzeit auf den Ziel-Ladestand – PV-/tarifoptimiert</small></span></div>
          <div class="mpf">
            <label>Ziel<div class="tgt"><button class="tb" data-act="mplansoc" data-d="-5">−</button><span class="tv">${soc}<small> %</small></span><button class="tb" data-act="mplansoc" data-d="5">+</button></div></label>
            <label>bis<input class="pin" type="datetime-local" value="${esc(val)}" data-act="none"></label>
            <button class="qbtn" data-act="mplanset"${entry ? "" : " disabled"}>${icon("mdi:check")}Plan setzen</button>
          </div></div>`;
      }
    }
    const toggles = entry ? [
      ma.aktiv ? sw(!!ma.pausiert, "mpause", "Automatik pausieren", ma.pausiert ? "ev_assistant schreibt nichts nach evcc" : `Steuerung aktiv${mc?.state ? ` · ${mc.state}` : ""}`, "mdi:pause-circle-outline") : "",
    ].join("") : "";

    const rec = this._st(E.charge_before_pv_recommended);
    el.innerHTML = this._hd("Lademanagement", manual ? (auto ? `<span class="mauto">${icon("mdi:robot-outline")}Automatik</span>` : `<span class="mman">${icon("mdi:hand-back-right-outline")}Manuell</span>`) : "") + `
      ${modeTiles ? `<div class="mgrp"><span class="mgl">${manual ? "Lademodus" : "evcc-Modus"}</span>${modeTiles}</div>` : ""}
      <div class="msteps">${step("Ladestrom", "mdi:speedometer", c.limit)}</div>
      ${this._renderLimitRow(c, ev, E, ma)}
      ${planHtml || toggles ? `<div class="mgrp"><span class="mgl">ev_assistant</span>${planHtml}${toggles}</div>` : ""}
      ${rec?.state === "on" ? `<div class="lrows"><button class="lrow warn" data-act="more" data-entity="${esc(E.charge_before_pv_recommended)}">${icon("mdi:weather-cloudy-alert")}<span>Empfehlung</span><b>Laden vor PV sinnvoll</b></button></div>` : ""}`;
  }

  _renderLimitRow(c, ev, E, ma) {
    const entry = this._evaEntryId();
    // Ladeziel als Dropdown
    let limBtn = "";
    if (ev.limit_soc) {
      const limSt = this._st(ev.limit_soc);
      if (!limSt) this._log("limit_soc", ev.limit_soc, "nicht in hass.states gefunden");
      const v = limSt?.state;
      limBtn = `<button class="mbtn lim" data-act="limmenu" data-entity="${esc(ev.limit_soc)}">
        ${icon("mdi:battery-check-outline")}<div class="mtx"><b>${v != null && !OFFLINE_HD.includes(v) ? esc(String(v).replace(/ ?%$/, "")) + " %" : "–"}</b><span>Ladeziel</span></div>${icon("mdi:chevron-down", "mchv")}</button>`;
    }
    // Vollladung als Knopf
    if (this._balOptimistic != null && !!ma.balancing_enabled === this._balOptimistic) this._balOptimistic = null;   // bestätigt
    const balOptimistic = this._balOptimistic;
    const balOn = balOptimistic != null ? balOptimistic : !!ma.balancing_enabled;
    const balAkt = !!ma.balancing_aktiv, balF = !!ma.balancing_faellig;
    const nextFull = ma.naechste_vollladung_faellig_ts ? new Date(ma.naechste_vollladung_faellig_ts * (ma.naechste_vollladung_faellig_ts < 1e12 ? 1000 : 1)) : null;
    const balSub = balAkt ? "lädt auf 100 %" : balF ? "fällig" : nextFull && !isNaN(nextFull) ? `nächste ${WD[nextFull.getDay()]} ${nextFull.getDate()}.` : "";
    let balBtn = "";
    if (entry) {
      balBtn = `<button class="mbtn bal ${balOn ? "on" : ""} ${balAkt ? "act" : ""}" data-act="mbal" data-v="${balOn ? "0" : "1"}">
        ${icon(balAkt ? "mdi:battery-sync" : "mdi:battery-sync-outline")}<div class="mtx"><b>Vollladung</b><span>${balOn ? (balSub || "aktiv") : "aus"}</span></div></button>`;
    }
    if (!limBtn && !balBtn) return "";
    return `<div class="mbottom">${limBtn}${balBtn}</div>`;
  }

  _openLimMenu(anchor) {
    this._closeMenu();
    const id = anchor.dataset.entity, st = this._st(id);
    if (!st) return;
    const a = st.attributes, cur = st.state;
    const opts = a.options || [];
    const menu = document.createElement("div"); menu.className = "menu limm";
    if (opts.length) {
      menu.innerHTML = opts.map((v) => `<button class="mg-menu-item mi ${String(v) === String(cur) ? "cur" : ""}" data-act="limset" data-entity="${esc(id)}" data-v="${esc(v)}"><span>${esc(v)}</span>${String(v) === String(cur) ? icon("mdi:check", "ck") : ""}</button>`).join("");
    } else {
      const stp = Number(a.step) || 5, mn = Number(a.min) || 20, mx = Number(a.max) || 100;
      let numOpts = []; for (let v = mn; v <= mx; v += stp) numOpts.push(v);
      menu.innerHTML = numOpts.map((v) => `<button class="mg-menu-item mi ${v === parseFloat(cur) ? "cur" : ""}" data-act="limset" data-entity="${esc(id)}" data-v="${v}"><span>${v} %</span>${v === parseFloat(cur) ? icon("mdi:check", "ck") : ""}</button>`).join("");
    }
    this._openMenuAt(anchor, menu);
    const sel = menu.querySelector(".cur"); if (sel) sel.scrollIntoView({ block: "center" });
  }

  _evaCall(service, data) {
    const id = this._evaEntryId();
    if (!id) { console.warn("mg-car: ev_assistant config_entry_id nicht gefunden. Trage car.ev_assistant_entry ein."); return; }
    this._log("ev_assistant →", service, { config_entry_id: id, ...data });
    this._hass.callService("ev_assistant", service, { config_entry_id: id, ...data });
  }

  _mnum(el) {
    const id = el.dataset.entity, st = this._st(id); if (!st) return;
    const a = st.attributes, stp = Number(a.step) || 1;
    this._pendingNum = this._pendingNum || {}; this._numT = this._numT || {};
    const cur = this._pendingNum[id] ?? parseFloat(st.state);
    let v = Math.round((cur + Number(el.dataset.d) * stp) / stp) * stp;
    if (a.min != null) v = Math.max(Number(a.min), v); if (a.max != null) v = Math.min(Number(a.max), v);
    this._pendingNum[id] = v;
    clearTimeout(this._numT[id]);
    this._numT[id] = setTimeout(() => {
      this._hass.callService(id.split(".")[0], "set_value", { entity_id: id, value: v });
      setTimeout(() => { delete this._pendingNum[id]; this._render_mgmt(); }, 1500);
    }, 700);
    this._render_mgmt();
  }

  /* --- Laden: live oder letzte Ladung --- */
  _render_live() {
    const c = this._config.car, ev = c.evcc || {}, E = this._eva();
    const { charging, plugged, pw } = this._carState(), p = this._power(pw);
    if (this._wasCharging && !charging) setTimeout(() => this._loadLastSession(), 5000);   // gerade fertig geworden
    this._wasCharging = charging;
    const num = (id) => { const v = parseFloat(this._st(id)?.state); return isNaN(v) ? null : v; };
    const L = !charging && this._lastSess?.vals ? this._lastSess : null;
    const val = (id) => (charging ? num(id) : L?.vals?.[id] ?? null);
    const kwh = val(ev.session_energy), pvp = val(ev.session_solar), cost = val(ev.session_price), dur = val(ev.duration);
    const durU = (this._st(ev.duration)?.attributes?.unit_of_measurement || "min").toLowerCase();
    const durMin = dur == null ? null : durU === "h" ? dur * 60 : durU === "s" ? dur / 60 : dur;
    const durTxt = durMin == null ? "–" : durMin >= 60 ? `${Math.floor(durMin / 60)}:${pad(Math.round(durMin % 60))} h` : `${Math.round(durMin)} min`;
    const cur = this._st(ev.session_price)?.attributes?.unit_of_measurement || "€";

    // Kopf: Status
    const stTxt = charging ? "Lädt" : plugged ? "Bereit" : "Abgesteckt";
    const stCls = charging ? "on" : plugged ? "ready" : "";

    // links: große Zahl + Zeitangabe
    let kicker = "", when = "";
    if (charging) {
      kicker = `Lädt${durMin != null ? ` seit ${durTxt}` : ""}`;
      const fin = this._st(ev.finish), finD = fin && !OFFLINE_HD.includes(fin.state) ? new Date(fin.state) : null, rem = this._fmt(ev.remaining);
      when = `${icon("mdi:flash")}<b>${p.v} ${p.u}</b>${finD && !isNaN(finD) ? ` · fertig ${pad(finD.getHours())}:${pad(finD.getMinutes())} Uhr` : rem ? ` · noch ${rem.v} ${rem.u}` : ""}`;
    } else if (L) {
      const d = new Date(L.end);
      kicker = `Letzte Ladung · ${this._ago(d)}`;
      when = `${icon("mdi:calendar-clock")}${WD_LONG[d.getDay()]}, ${d.getDate()}. ${MON[d.getMonth()]} · ${pad(d.getHours())}:${pad(d.getMinutes())} Uhr`;
    } else kicker = this._lastSess?.none ? "Keine Ladung im gespeicherten Verlauf" : "Letzte Ladung";

    // rechts: PV-Ring
    const pvv = pvp == null ? null : Math.max(0, Math.min(100, pvp));
    const R = 34, C = 2 * Math.PI * R, arc = pvv == null ? 0 : (pvv / 100) * C;
    const ring = `<svg class="lring" viewBox="0 0 84 84"><circle cx="42" cy="42" r="${R}" class="rbg"/>
      <circle cx="42" cy="42" r="${R}" class="rgr" style="stroke-dasharray:${C - arc} ${C};stroke-dashoffset:${-arc}"/>
      <circle cx="42" cy="42" r="${R}" class="rpv" style="stroke-dasharray:${arc} ${C}"/></svg>
      <div class="lringt"><b>${pvv == null ? "–" : Math.round(pvv)}<small>%</small></b><span>PV</span></div>`;

    // Aufteilung PV/Netz in kWh
    const pvK = kwh != null && pvv != null ? kwh * pvv / 100 : null, grK = pvK != null ? kwh - pvK : null;
    const split = pvK != null && kwh > 0.01 ? `<div class="lsplit"><span class="pv" style="flex:${Math.max(pvK, 0.001)}"></span><span class="gr" style="flex:${Math.max(grK, 0.001)}"></span></div>
      <div class="lsplitl"><span class="pv">${icon("mdi:solar-power-variant")}PV <b>${de(pvK, 1)} kWh</b></span><span class="gr">${icon("mdi:transmission-tower")}Netz <b>${de(grK, 1)} kWh</b></span></div>` : "";

    // Kennzahlen
    const per = cost != null && kwh > 0.05 ? cost / kwh : null, avgP = kwh != null && durMin > 1 ? kwh / (durMin / 60) : null;
    const fact = (lbl, v) => `<div class="lfact"><span>${lbl}</span><b>${v}</b></div>`;
    const facts = [
      fact("Dauer", durTxt, ev.duration),
      fact("Kosten", cost == null ? "–" : `${de(cost, 2)} ${esc(cur)}`, ev.session_price),
      fact("Preis", per == null ? "–" : `${de(per * 100, 1)} ct/kWh`),
      fact("Ø Leistung", avgP == null ? "–" : `${de(avgP, 1)} kW`),
    ].join("");

    // Plan, Modus, Hinweise als schmale Zeilen
    const plan = this._st(E.evcc_charge_plan), mode = this._st(E.evcc_mode_control), rec = this._st(E.charge_before_pv_recommended), tot = this._fmt(ev.solar_total, 0);
    const row = (ic, lbl, v, id, cls = "") => `<button class="lrow ${cls}" data-act="more" data-entity="${esc(id)}">${icon(ic)}<span>${lbl}</span><b>${esc(v)}</b></button>`;
    const rows = [
      plan && !OFFLINE_HD.includes(plan.state) ? row("mdi:calendar-clock", "Ladeplan", plan.state, E.evcc_charge_plan) : "",
      mode && !OFFLINE_HD.includes(mode.state) ? row("mdi:robot-outline", "Steuerung", mode.state, E.evcc_mode_control) : "",
      rec?.state === "on" ? row("mdi:weather-cloudy-alert", "Empfehlung", "Laden vor PV sinnvoll", E.charge_before_pv_recommended, "warn") : "",
    ].join("");

    this.shadowRoot.getElementById("live").innerHTML = `
      <div class="hd"><span class="ttl">Laden</span><span class="lst ${stCls}">${icon(charging ? "mdi:lightning-bolt" : plugged ? "mdi:ev-plug-type2" : "mdi:power-plug-off-outline")}${stTxt}</span>
        <button class="arrow" data-act="charges" aria-label="Alle Ladungen" title="Alle Ladungen">${icon("mdi:format-list-bulleted")}</button></div>
      <div class="lclick" data-act="charges" title="Alle Ladungen anzeigen">
      <div class="lhero ${charging ? "chg" : ""}">
        <div class="lhl">
          <span class="lkick">${esc(kicker)}</span>
          <div class="lbig"><b>${kwh == null ? "–" : de(kwh, 1)}</b><small>kWh</small></div>
          ${when ? `<span class="lwhen">${when}</span>` : ""}
        </div>
        <div class="lringw">${ring}</div>
      </div>
      ${split}
      <div class="lfacts">${facts}</div></div>
`;
  }

  /* --- Fahrtenbuch --- */
  _tripList() {
    const c = this._config.car;
    let trips = this._st(c.trips)?.attributes?.trips || [];
    if (!Array.isArray(trips)) trips = [];
    const t0 = (x) => new Date(x.start).getTime() || 0;
    return trips.slice().sort((a, b) => t0(b) - t0(a)).slice(0, c.trips_max || 100);
  }

  _tripRows(list) {
    const dt = (v) => { const d = new Date(v); return isNaN(d) ? null : d; };
    const place = (x) => ({ home: "Zuhause", zuhause: "Zuhause", Home: "Zuhause", not_home: "unterwegs", "außerhalb": "unterwegs" }[x] || x || "?");
    let lastDay = "";
    return list.map((t) => {
      const s = dt(t.start), day = s ? `${WD[s.getDay()]}, ${s.getDate()}. ${MON[s.getMonth()]}${s.getFullYear() !== new Date().getFullYear() ? ` ${s.getFullYear()}` : ""}` : "";
      const head = day !== lastDay ? `<div class="tday">${esc(day)}</div>` : ""; lastDay = day;
      const km = parseFloat(t.strecke), kwh = parseFloat(t.verbrauch_kwh), avg = parseFloat(t.avg_verbrauch);
      return `${head}<div class="trip">
        <span class="ttime">${s ? `${pad(s.getHours())}:${pad(s.getMinutes())}` : ""}</span>
        <span class="troute"><b>${esc(place(t.start_ort))}</b>${icon("mdi:arrow-right")}<b>${esc(place(t.ziel_ort))}</b><small>${t.dauer != null ? `${esc(t.dauer)} min` : ""}${t.avg_speed ? ` · Ø ${de(parseFloat(t.avg_speed), 0)} km/h` : ""}</small></span>
        <span class="tkm"><b>${isNaN(km) ? "–" : de(km, 0)}</b><small>km</small></span>
        <span class="tkwh"><b>${isNaN(kwh) ? "–" : de(kwh, 1)}</b><small>kWh${!isNaN(avg) ? ` · ${de(avg, 1)}/100` : ""}</small></span>
      </div>`;
    }).join("");
  }

  _render_trips() {
    const c = this._config.car, el = this.shadowRoot?.getElementById("trips");
    if (!el || !this._hass) return;
    const all = this._tripList();
    const fit = this.shadowRoot.querySelector(".wrap")?.classList.contains("fit");
    // passt sich die Seite der Fensterhöhe an, kürzt _clipTrips() die Liste auf das, was in die Kachel passt
    const list = fit ? all : all.slice(0, c.trips_visible || 5);
    this._tripsAll = all.length;
    el.innerHTML = `<div class="hd"><span class="ttl">Fahrtenbuch</span><span class="lbl"></span>
        <button class="arrow" data-act="trips" aria-label="Alle Fahrten" title="Alle Fahrten">${icon("mdi:chevron-right")}</button></div>` +
      (list.length ? `<div class="tlist" data-act="trips" title="Alle Fahrten anzeigen">${this._tripRows(list)}</div>`
        : `<div class="empty">Keine Fahrten gefunden${c.trips ? ` (${esc(c.trips)})` : ""}</div>`);
    this._clipTrips();
    if (this._dlg === "trips") this._renderTripsDlg();
  }

  /* Fahrten ausblenden, die nicht mehr in die Kachel passen, und die Anzahl in die Kopfzeile schreiben */
  _clipTrips() {
    const el = this.shadowRoot?.getElementById("trips"), box = el?.querySelector(".tlist");
    const lbl = el?.querySelector(".hd .lbl");
    if (!lbl) return;
    let shown = box ? box.querySelectorAll(".trip").length : 0;
    if (box && this.shadowRoot.querySelector(".wrap")?.classList.contains("fit")) {
      const kids = [...box.children];
      kids.forEach((k) => (k.style.display = ""));
      const h = box.clientHeight;
      let cut = false;
      for (const k of kids) if (cut || k.offsetTop + k.offsetHeight > h + 1) { cut = true; k.style.display = "none"; }
      const vis = kids.filter((k) => k.style.display !== "none");
      while (vis.length && vis[vis.length - 1].classList.contains("tday")) vis.pop().style.display = "none";   // Tagesüberschrift ohne Fahrt
      if (!vis.some((k) => k.classList.contains("trip")) && kids.length) { kids[0].style.display = ""; kids[1] && (kids[1].style.display = ""); }   // mindestens eine Fahrt
      shown = kids.filter((k) => k.classList.contains("trip") && k.style.display !== "none").length;
    }
    const n = this._tripsAll || 0;
    lbl.textContent = !n ? "" : shown < n ? `${shown} von ${n} Fahrten` : `${n} Fahrten`;
  }

  _openTrips() { this._openDlg("trips"); this._renderTripsDlg(); }

  _renderTripsDlg() {
    const d = this.shadowRoot.getElementById("cardlg");
    if (!d || this._dlg !== "trips") return;
    const list = this._tripList(), num = (t, k) => parseFloat(t[k]) || 0;
    const km = list.reduce((a, t) => a + num(t, "strecke"), 0), kwh = list.reduce((a, t) => a + num(t, "verbrauch_kwh"), 0);
    const min = list.reduce((a, t) => a + num(t, "dauer"), 0);
    const sc = d.querySelector(".dbody")?.scrollTop || 0;
    d.innerHTML = `<div class="dpan chpan">
      <div class="dhd"><span class="dico">${icon("mdi:map-marker-path")}</span>
        <span class="rtx"><span class="rname">Alle Fahrten</span><span class="rsub">${esc(this._st(this._config.car.trips)?.attributes?.friendly_name || "Fahrtenbuch")}</span></span>
        <button class="dx" data-act="cardclose" aria-label="Schließen">${icon("mdi:close")}</button></div>
      <div class="chsum">
        <div><span>Fahrten</span><b>${list.length}</b></div>
        <div><span>Strecke</span><b>${de(km, 0)}<small>km</small></b></div>
        <div><span>Energie</span><b>${de(kwh, kwh >= 100 ? 0 : 1)}<small>kWh</small></b></div>
        <div><span>Ø Verbrauch</span><b>${km > 1 ? de(kwh / km * 100, 1) : "–"}<small>kWh/100</small></b></div>
        <div><span>Fahrzeit</span><b>${min >= 60 ? `${Math.floor(min / 60)}:${pad(Math.round(min % 60))}` : Math.round(min)}<small>${min >= 60 ? "h" : "min"}</small></b></div>
      </div>
      <div class="dbody">${list.length ? `<div class="tlist">${this._tripRows(list)}</div>` : `<div class="empty">Keine Fahrten gefunden</div>`}</div></div>`;
    const b = d.querySelector(".dbody"); if (b) b.scrollTop = sc;
  }

  /* gemeinsames Popup für „Alle Ladungen“ und „Alle Fahrten“ */
  _openDlg(mode) {
    const d = this.shadowRoot.getElementById("cardlg");
    this._dlg = mode;
    d.dataset.mode = mode;
    if (!d._bound) { d._bound = true; d.addEventListener("click", (ev) => { if (ev.target === d) d.close(); }); d.addEventListener("close", () => { this._dlg = null; }); }
    d.innerHTML = "";
    if (!d.open) try { d.showModal(); } catch (x) { d.setAttribute("open", ""); }
  }


  /* --- Verlauf bis jetzt: SoC + Ladeleistung, Zeitraum wählbar --- */
  /* Zeiträume aus history_ranges: Zahl (Stunden) oder { hours, label } */
  _ranges() {
    const l = (this._config.car.history_ranges || []).map((r) => {
      const h = Number(typeof r === "object" ? r?.hours : r);
      return h > 0 ? { h, label: (typeof r === "object" && r.label) || this._rangeLbl(h) } : null;
    }).filter(Boolean);
    return l.length ? l : [6, 24, 72, 168, 720].map((h) => ({ h, label: this._rangeLbl(h) }));
  }
  _histHours() {
    if (this._hh) return this._hh;
    const hs = this._ranges().map((r) => r.h);
    let v = null; try { v = Number(localStorage.getItem("mg-car-hist-hours")); } catch (e) {}
    const def = Number(this._config.car.history_hours);
    return (this._hh = hs.includes(v) ? v : hs.includes(def) ? def : hs[Math.min(1, hs.length - 1)]);
  }
  _rangeLbl(h) { return h < 48 ? `${h} h` : h % 24 === 0 ? `${h / 24} T` : `${h} h`; }

  async _loadCarHist() {
    const c = this._config.car, ev = c.evcc || {}, ids = [c.soc, ev.power || this._config.energy.car_power].filter((x) => x && this._st(x));
    if (!ids.length || !this._hass) return;
    const hrs = this._histHours(), req = (this._histReq = (this._histReq || 0) + 1);
    const t1 = Date.now(), t0 = t1 - hrs * 3600000, data = {}, src = {};
    const ts = (v) => (typeof v === "number" ? v : new Date(v).getTime());
    // 1) Langzeitstatistik (Stundenwerte, bleibt dauerhaft erhalten) – für längere Zeiträume
    if (hrs > 48 && this._hass.callWS) {
      try {
        const st = await this._hass.callWS({ type: "recorder/statistics_during_period", start_time: new Date(t0 - 3600000).toISOString(),
          end_time: new Date(t1).toISOString(), statistic_ids: ids, period: "hour", types: ["mean", "max"] });
        for (const id of ids) {
          const l = (st?.[id] || []).map((x) => [ts(x.start), x.mean ?? x.max]).filter((x) => x[1] != null && !isNaN(x[1]));
          if (l.length) { data[id] = l; src[id] = "Statistik"; }
        }
      } catch (e) { /* Statistik nicht verfügbar → Verlauf */ }
    }
    // 2) Zustandsverlauf (genau, aber nur so lange wie der Recorder speichert, Standard 10 Tage)
    const miss = ids.filter((id) => !data[id]);
    if (miss.length && this._hass.callApi) {
      try {
        const res = await this._hass.callApi("GET", `history/period/${new Date(t0).toISOString()}?filter_entity_id=${miss.join(",")}&end_time=${encodeURIComponent(new Date(t1).toISOString())}&minimal_response&no_attributes`);
        for (const l of res || []) if (l.length) {
          const pts = l.map((x) => [new Date(x.last_changed || x.last_updated).getTime(), parseFloat(x.state)]).filter((x) => !isNaN(x[1]) && !isNaN(x[0]));
          if (pts.length) { data[l[0].entity_id] = pts; src[l[0].entity_id] = "Verlauf"; }
        }
      } catch (e) {}
    }
    let bars = null;
    bars = await this._loadBars(t0, t1, hrs);
    if (req !== this._histReq) return;
    this._carHist = { t: Date.now(), hrs, data, src, ids, bars };
    this._update(true);
  }

  /* Stündlich geladene kWh, aufgeteilt nach Netz und PV/Speicher (aus Langzeitstatistik) */
  async _loadBars(t0, t1, hrs) {
    const c = this._config.car, ev = c.evcc || {}, e = this._config.energy;
    const pid = ev.power || e.car_power, gid = c.split_grid || e.grid_import, hid = c.split_home || e.home;
    if (!this._hass.callWS || !this._st(pid)) return null;
    const ids = [pid, gid, hid, c.soc].filter((x) => x && this._st(x));
    try {
      const st = await this._hass.callWS({ type: "recorder/statistics_during_period", start_time: new Date(t0).toISOString(),
        end_time: new Date(t1).toISOString(), statistic_ids: ids, period: "hour", types: ["mean"] });
      const ts = (v) => (typeof v === "number" ? v : new Date(v).getTime());
      const toKW = (id) => { const u = (this._st(id)?.attributes?.unit_of_measurement || "").toLowerCase(); return u === "kw" ? 1 : u === "mw" ? 1000 : 0.001; };
      const map = (id) => { const m = new Map(); for (const x of st?.[id] || []) if (x.mean != null) m.set(ts(x.start), x.mean); return m; };
      const P = map(pid), G = map(gid), Hm = map(hid), S = map(c.soc);
      const fp = toKW(pid), fg = toKW(gid), fh = toKW(hid);
      let rows = [];
      for (const [t, v] of P) {
        const kwh = Math.max(0, v * fp);
        const home = (Hm.get(t) ?? 0) * fh, grid = Math.max(0, (G.get(t) ?? 0) * fg);
        // Anteil Netz = Netzbezug / Gesamtverbrauch der Stunde (Auto im Hausverbrauch enthalten)
        const share = home > 0.01 ? Math.min(1, grid / Math.max(home, kwh)) : (G.has(t) ? 1 : 0);
        rows.push({ t, kwh, grid: kwh * share, pv: kwh * (1 - share), soc: S.get(t) });
      }
      rows.sort((a, b) => a.t - b.t);
      const unit = this._barUnit(hrs);
      if (unit !== "h") {   // Stundenwerte zu Tages- bzw. Wochensummen zusammenfassen
        const groups = new Map();
        for (const r of rows) {
          const d = new Date(r.t); d.setHours(0, 0, 0, 0);
          if (unit === "w") d.setDate(d.getDate() - ((d.getDay() + 6) % 7));   // Wochenbeginn Montag
          const k = d.getTime(), x = groups.get(k) || { t: k, kwh: 0, grid: 0, pv: 0, soc: null };
          x.kwh += r.kwh; x.grid += r.grid; x.pv += r.pv; if (r.soc != null) x.soc = r.soc;
          groups.set(k, x);
        }
        rows = [...groups.values()];
      }
      return { rows, unit, split: !!(gid && this._st(gid) && hid && this._st(hid)) };
    } catch (e) { return null; }
  }

  /* Balkenbreite je Zeitraum: "h" stündlich, "d" täglich, "w" wöchentlich */
  _barUnit(hrs) {
    const c = this._config.car;
    return hrs >= (c.bars_weekly_from_hours ?? 744) ? "w" : hrs >= (c.bars_daily_from_hours ?? 72) ? "d" : "h";
  }
  _stepMs(unit) { return unit === "w" ? 7 * 86400000 : unit === "d" ? 86400000 : 3600000; }
  _kw(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() + 3 - ((x.getDay() + 6) % 7)); const w1 = new Date(x.getFullYear(), 0, 4); return 1 + Math.round(((x - w1) / 86400000 - 3 + ((w1.getDay() + 6) % 7)) / 7); }

  _barsSvg(H, t0, t1, W, Ht, X, soc, nowS) {
    const B = H.bars, hrs = this._histHours(), step = this._stepMs(B.unit);
    const rows = B.rows.filter((r) => r.t + step > t0);
    const maxK = Math.max({ h: 1, d: 5, w: 20 }[B.unit] || 1, ...rows.map((r) => r.kwh));
    const Y = (v) => Ht - (v / maxK) * (Ht - 12);
    this._barRows = rows; this._barStep = step; this._barT = [t0, t1];
    const bars = rows.map((r, i) => {
      // angeschnittene Balken am Anfang (vor Zeitraumbeginn) und am Ende (laufende Stunde/Tag/Woche) nur so breit wie sichtbar
      const xa = X(Math.max(r.t, t0)), xb = X(Math.min(r.t + step, t1)), full = (step / (t1 - t0)) * W;
      const gap = full > 6 ? (B.unit === "h" ? 1 : 2) : 0.2;
      const x = xa + gap / 2, bw = Math.max(1, xb - xa - gap), yp = Y(r.pv), yg = Y(r.pv + r.grid);
      return r.kwh < 0.005 ? "" : `<g class="bar" data-i="${i}">
        <rect x="${x.toFixed(1)}" y="${yp.toFixed(1)}" width="${bw.toFixed(1)}" height="${(Ht - yp).toFixed(1)}" class="bpv"/>
        <rect x="${x.toFixed(1)}" y="${yg.toFixed(1)}" width="${bw.toFixed(1)}" height="${(yp - yg).toFixed(1)}" class="bgr"/></g>`;
    }).join("");
    // Ladestand als Linie darüber
    const S = (v) => (Ht - (v / 100) * (Ht - 10)).toFixed(1);
    const sp0 = soc.concat([[t1, nowS]]);
    let sp = ""; if (sp0.length > 1) { sp = `M${X(sp0[0][0]).toFixed(1)},${S(sp0[0][1])}`; for (const [t, v] of sp0.slice(1)) sp += `L${X(t).toFixed(1)},${S(v)}`; }
    const ticks = [];
    if (B.unit === "w") {
      const first = new Date(t0); first.setHours(0, 0, 0, 0); first.setDate(first.getDate() + ((8 - first.getDay()) % 7));   // erster Montag
      const every = Math.max(1, Math.ceil(hrs / 168 / 8));   // höchstens etwa 8 Beschriftungen
      for (let d = first, i = 0; d.getTime() <= t1; d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 7), i++)
        if (i % every === 0) ticks.push([X(d.getTime()) / W * 100, `KW ${this._kw(d)}`]);
    } else {
      let tstep = hrs <= 6 ? 1 : hrs <= 24 ? 3 : hrs <= 72 ? 12 : hrs <= 168 ? 24 : 24 * 5;
      if (B.unit === "d") tstep = Math.max(24, tstep);   // Tagesbalken: Tage beschriften
      const first = new Date(t0); first.setMinutes(0, 0, 0);
      if (tstep >= 24) first.setHours(0); else first.setHours(Math.ceil(first.getHours() / tstep) * tstep);
      for (let t = first.getTime(); t <= t1; t += tstep * 3600000) if (t >= t0) {
        const d = new Date(t);
        ticks.push([X(t) / W * 100, tstep >= 24 ? `${WD[d.getDay()]} ${d.getDate()}.` : tstep >= 12 && d.getHours() === 0 ? WD[d.getDay()] : `${pad(d.getHours())}:00`]);
      }
    }
    const grid = ticks.map(([x]) => `<line x1="${(x / 100) * W}" x2="${(x / 100) * W}" y1="0" y2="${Ht}" class="gl"/>`).join("");
    const sum = rows.reduce((a, r) => ({ k: a.k + r.kwh, g: a.g + r.grid, p: a.p + r.pv }), { k: 0, g: 0, p: 0 });
    return `<div class="chwrap bars">
        <svg class="chist" viewBox="0 0 ${W} ${Ht}" preserveAspectRatio="none">${grid}${bars}
          ${sp ? `<path d="${sp}" class="gs" vector-effect="non-scaling-stroke"/>` : ""}
          <line x1="${W}" x2="${W}" y1="0" y2="${Ht}" class="gnow"/><rect class="hl" x="0" y="0" width="0" height="${Ht}"/></svg>
        <div class="gax">${ticks.filter(([x]) => x < 90).map(([x, l]) => `<span class="${x < 4 ? "st" : ""}" style="left:${x}%">${l}</span>`).join("")}<span class="now" style="left:100%">jetzt</span></div>
        <div class="gtip" hidden></div>
        <span class="gmax">${de(maxK, 1)} kWh${{ h: "/h", d: "/Tag", w: "/Woche" }[B.unit]}</span></div>
      <div class="glg"><span class="pvl">PV/Speicher ${de(sum.p, 1)} kWh</span>${B.split ? `<span class="grl">Netz ${de(sum.g, 1)} kWh</span>` : ""}<span class="s">Ladestand ${Math.round(nowS)} %</span>
<span class="src">${{ h: "Stundenwerte", d: "Tageswerte", w: "Wochenwerte" }[B.unit]}</span></div>`;
  }

  /* Maus/Finger über den Balken: Werte anzeigen */
  _barHover(e) {
    const wrap = e.composedPath().find((n) => n.classList?.contains("chwrap") && n.classList.contains("bars"));
    const tip = this.shadowRoot.querySelector(".chwrap.bars .gtip"), hl = this.shadowRoot.querySelector(".chwrap.bars .hl");
    if (!wrap || !this._barRows) { if (tip) tip.hidden = true; if (hl) hl.setAttribute("width", 0); return; }
    const svg = wrap.querySelector("svg"), r = svg.getBoundingClientRect();
    const fx = (e.clientX - r.left) / r.width; if (fx < 0 || fx > 1) { tip.hidden = true; return; }
    const [t0, t1] = this._barT, t = t0 + fx * (t1 - t0), step = this._barStep;
    const row = this._barRows.find((x) => t >= x.t && t < x.t + step);
    if (!row) { tip.hidden = true; hl.setAttribute("width", 0); return; }
    const d = new Date(row.t), d2 = new Date(row.t + step);
    const de2 = new Date(row.t + step - 86400000);   // letzter Tag der Woche
    const when = step >= 7 * 86400000 ? `KW ${this._kw(d)} · ${d.getDate()}. ${d.getMonth() !== de2.getMonth() ? MON[d.getMonth()] + " " : ""}– ${de2.getDate()}. ${MON[de2.getMonth()]}`
      : step >= 86400000 ? `${WD_LONG[d.getDay()]}, ${d.getDate()}. ${MON[d.getMonth()]}` : `${WD[d.getDay()]} ${d.getDate()}. ${MON[d.getMonth()]} · ${pad(d.getHours())}–${pad(d2.getHours())} Uhr`;
    const pvp = row.kwh > 0 ? Math.round((row.pv / row.kwh) * 100) : 0;
    tip.innerHTML = `<b>${when}</b>
      <div><i class="pvd"></i>PV/Speicher<span>${de(row.pv, 2)} kWh</span></div>
      <div><i class="grd"></i>Netz<span>${de(row.grid, 2)} kWh</span></div>
      <div class="tot">Geladen<span>${de(row.kwh, 2)} kWh${row.kwh > 0.005 ? ` · ${pvp} % PV` : ""}</span></div>
      ${row.soc != null ? `<div class="tsoc">Ladestand<span>${Math.round(row.soc)} %</span></div>` : ""}`;
    tip.hidden = false;
    const W = 700, x0 = ((Math.max(row.t, t0) - t0) / (t1 - t0)) * W, x1 = ((Math.min(row.t + step, t1) - t0) / (t1 - t0)) * W;
    hl.setAttribute("x", x0); hl.setAttribute("width", Math.max(2, x1 - x0));
    const px = e.clientX - wrap.getBoundingClientRect().left, ww = wrap.clientWidth;
    tip.style.left = Math.min(Math.max(px - tip.offsetWidth / 2, 0), ww - tip.offsetWidth) + "px";
  }

  _render_hist() {
    const c = this._config.car, ev = c.evcc || {}, el = this.shadowRoot.getElementById("hist");
    const hrs = this._histHours(), H = this._carHist?.hrs === hrs ? this._carHist : null;
    const W = 700, Ht = 150, t1 = Date.now(), t0 = t1 - hrs * 3600000;
    const X = (t) => ((Math.max(t, t0) - t0) / (t1 - t0)) * W;
    const pid = ev.power || this._config.energy.car_power;
    // nur den Zeitraum zeigen: letzter Wert vor Beginn wird zum Startwert
    const clip = (arr) => { const pre = arr.filter((p) => p[0] <= t0).pop(); return (pre ? [[t0, pre[1]]] : []).concat(arr.filter((p) => p[0] > t0)); };
    const soc = clip(H?.data?.[c.soc] || []), pw = clip(H?.data?.[pid] || []);
    const kw = this._st(pid)?.attributes?.unit_of_measurement?.toLowerCase() === "kw" ? 1 : 0.001;
    // aktuellen Wert bis "jetzt" fortschreiben
    const nowP = this._w(pid) / 1000, nowS = this._num(c.soc);
    const seg = this._ranges().map((r) =>
      `<button class="hseg ${r.h === hrs ? "sel" : ""}" data-act="hrange" data-h="${r.h}">${esc(r.label)}</button>`).join("");
    let body;
    if (!H) body = `<div class="empty">Lädt …</div>`;
    else if (H.bars?.rows?.length && hrs >= (c.bars_from_hours ?? 0)) body = this._barsSvg(H, t0, t1, W, Ht, X, soc, nowS);
    else if (!(H.data?.[c.soc]?.length) && !(H.data?.[pid]?.length)) body = `<div class="empty hdiag">Keine Verlaufsdaten für ${(H.ids || []).map((x) => `<code>${esc(x)}</code>`).join(" und ")} im Zeitraum.<br>
      Für lange Zeiträume braucht der Sensor <code>state_class: measurement</code> (Langzeitstatistik), sonst speichert der Recorder standardmäßig nur 10 Tage.</div>`;
    else {
      const pts = pw.map((x) => [x[0], x[1] * kw]).concat([[t1, nowP]]);
      const maxP = Math.max(3.7, ...pts.map((x) => x[1]));
      const Y = (v) => (Ht - (v / maxP) * (Ht - 10)).toFixed(1);
      // Wert vor Fensterbeginn als Startwert
      let ap = `M0,${Ht}V${Y(pts[0][0] <= t0 ? pts[0][1] : 0)}`;
      for (const [t, v] of pts) ap += `H${X(t).toFixed(1)}V${Y(v)}`;
      ap += `H${W}V${Ht}Z`;
      const sp0 = soc.concat([[t1, nowS]]);
      const S = (v) => (Ht - (v / 100) * (Ht - 10)).toFixed(1);
      let sp = `M${X(sp0[0][0]).toFixed(1)},${S(sp0[0][1])}`;
      for (const [t, v] of sp0.slice(1)) sp += `L${X(t).toFixed(1)},${S(v)}`;
      // Zeitachse: Stunden bei kurzen, Tage bei langen Zeiträumen
      const ticks = [], step = hrs <= 6 ? 1 : hrs <= 24 ? 3 : hrs <= 72 ? 12 : hrs <= 168 ? 24 : 24 * 5;
      const first = new Date(t0); first.setMinutes(0, 0, 0);
      if (step >= 24) first.setHours(0); else first.setHours(Math.ceil(first.getHours() / step) * step);
      for (let t = first.getTime(); t <= t1; t += step * 3600000) if (t >= t0) {
        const d = new Date(t);
        ticks.push([X(t) / W * 100, step >= 24 ? `${WD[d.getDay()]} ${d.getDate()}.` : step >= 12 && d.getHours() === 0 ? `${WD[d.getDay()]}` : `${pad(d.getHours())}:00`]);
      }
      const grid = ticks.map(([x]) => `<line x1="${(x / 100) * W}" x2="${(x / 100) * W}" y1="0" y2="${Ht}" class="gl"/>`).join("");
      const kwh = pw.length ? (() => { let e = 0; for (let i = 0; i < pts.length - 1; i++) { const a = Math.max(pts[i][0], t0), b = pts[i + 1][0]; if (b > a) e += pts[i][1] * (b - a) / 3600000; } return e; })() : 0;
      body = `<div class="chwrap"><svg class="chist" viewBox="0 0 ${W} ${Ht}" preserveAspectRatio="none">${grid}
          <path d="${ap}" class="gp"/><path d="${sp}" class="gs" vector-effect="non-scaling-stroke"/>
          <line x1="${W}" x2="${W}" y1="0" y2="${Ht}" class="gnow"/></svg>
        <div class="gax">${ticks.filter(([x]) => x < 90).map(([x, l]) => `<span class="${x < 4 ? "st" : ""}" style="left:${x}%">${l}</span>`).join("")}<span class="now" style="left:100%">jetzt</span></div></div>
        <div class="glg"><span class="s">Ladestand ${Math.round(nowS)} %</span><span class="p">Ladeleistung (max ${de(maxP, 1)} kW)</span>${Object.values(H.src || {}).includes("Statistik") ? `<span class="src">Stundenmittel</span>` : ""}</div>`;
    }
    // Summe und gemessener PV-Anteil des Zeitraums in die Kopfzeile
    let head = "";
    if (H) {
      const rows = (H.bars?.rows || []).filter((r) => r.t + this._stepMs(H.bars.unit) > t0);
      let k = rows.reduce((a, r) => a + r.kwh, 0), pv = rows.reduce((a, r) => a + r.pv, 0);
      if (!rows.length && pw.length) {   // keine Statistik: Energie aus der Leistungskurve
        const pts = pw.map((x) => [x[0], x[1] * kw]).concat([[t1, nowP]]);
        k = 0; for (let i = 0; i < pts.length - 1; i++) k += pts[i][1] * (pts[i + 1][0] - Math.max(pts[i][0], t0)) / 3600000;
        pv = null;
      }
      if (k > 0.05) head = `<span class="hsum"><b>${de(k, 1)}</b> kWh${pv != null && H.bars?.split ? `<span class="hpv">${icon("mdi:solar-power-variant")}${Math.round((pv / k) * 100)} % PV</span>` : ""}</span>`;
      else head = `<span class="hsum dim">nicht geladen</span>`;
    }
    el.innerHTML = `<div class="hd"><span class="ttl">Verlauf</span>${head}<div class="hsegs">${seg}</div></div>` + body;
  }


  /* ---------- Werte ---------- */
  _log(...a) { if (this._config?.debug) console.info("mg-car:", ...a); }
  /* Zustand einer Entität. Ist sie nur kurz nicht verfügbar (z. B. während ev_assistant nach einer
     Einstellungsänderung neu lädt), wird bis zu 60 s der letzte gültige Zustand weiterverwendet,
     damit die Kacheln nicht kurz leer werden und springen. */
  _st(id) {
    if (!id) return undefined;
    const s = this._hass?.states[id], now = Date.now(), lg = (this._good = this._good || {});
    if (s && !OFFLINE_HD.includes(s.state)) { lg[id] = { s, t: now }; return s; }
    const g = lg[id];
    return g && now - g.t < 60000 ? g.s : s;
  }
  _num(id) { const s = this._st(id); const v = s ? parseFloat(s.state) : NaN; return isNaN(v) ? 0 : v; }
  _w(id) { const s = this._st(id); if (!s) return 0; const u = (s.attributes.unit_of_measurement || "").toLowerCase(); return this._num(id) * (u === "kw" ? 1000 : 1); }
  _power(w) { w = Math.abs(w); return w >= 1000 ? { v: de(w / 1000, 1), u: "kW" } : { v: String(Math.round(w)), u: "W" }; }

  /* Bildschirm-Anpassung: auf breiten Bildschirmen genau Fensterhöhe, Inhalte skalieren/scrollen innen */
  _fit() {
    const wrap = this.shadowRoot?.querySelector(".wrap");
    if (!wrap) return;
    const on = this._config?.fit_screen !== false && this.clientWidth > 1180;
    if (!on) { wrap.classList.remove("fit"); return; }
    const top = this.getBoundingClientRect().top + window.scrollY;
    const h = Math.max(560, Math.floor(window.innerHeight - top));
    wrap.style.setProperty("--fit-h", h + "px");
    wrap.classList.add("fit");
    wrap.classList.toggle("compact", h < 860);   // niedrige Fenster: alles etwas kompakter
  }

  _hd(title, label = "", entity = null, labelCls = "") {
    return `<div class="hd"><span class="ttl">${esc(title)}</span><span class="lbl ${labelCls}">${label}</span>
      ${entity ? `<button class="arrow" data-act="more" data-entity="${esc(entity)}">${icon("mdi:chevron-right")}</button>` : ""}</div>`;
  }

  /* ---------- Auto ---------- */
  /* ev_assistant-Entitäten finden (Integration „ev_assistant“, über translation_key) */
  _eva() {
    const cfg = this._config.car.ev_assistant, fixed = cfg && typeof cfg === "object" ? cfg : {};
    const reg = this._hass?.entities;
    if (!reg) return { ...fixed };
    if (this._evaCache?.ref === reg) return this._evaCache.map;
    // bisher gefundene Entitäten behalten: beim Neuladen der Integration fehlen sie sonst kurz
    const map = { ...(this._evaCache?.map || {}) };
    for (const e of Object.values(reg)) if (e.platform === "ev_assistant" && e.translation_key) map[e.translation_key] = e.entity_id;
    Object.assign(map, fixed);
    this._evaCache = { ref: reg, map };
    return map;
  }

  /* Wert mit Einheit hübsch formatieren */
  _fmt(id, dec, raw) {
    const s = this._st(id);
    if (!s || (raw == null && OFFLINE_HD.includes(s.state))) return null;
    const u = s.attributes.unit_of_measurement || "", v = parseFloat(raw ?? s.state);
    if (isNaN(v)) return { v: s.state, u: "" };
    if (s.attributes.device_class === "duration" || ["h", "min", "s"].includes(u)) {
      const m = u === "h" ? v * 60 : u === "s" ? v / 60 : v;
      return { v: m >= 60 ? `${Math.floor(m / 60)}:${pad(Math.round(m % 60))}` : `${Math.round(m)}`, u: m >= 60 ? "h" : "min" };
    }
    const d = dec ?? (Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2);
    return { v: de(v, Math.min(d, 2)).replace(/,0+$/, ""), u };
  }

  _carState() {
    const c = this._config.car, ev = c.evcc || {};
    const pw = ev.power ? this._w(ev.power) : this._w(this._config.energy.car_power);
    const charging = this._st(ev.charging)?.state === "on" || pw > 50;
    const plugged = this._st(ev.connected)?.state === "on" || this._st(c.cable)?.state === "on";
    const driving = this._st(c.status)?.state === "on";
    return { charging, plugged, driving, pw };
  }

  _render_car() {
    const c = this._config.car, ev = c.evcc || {}, E = this._eva();
    const soc = Math.max(0, Math.min(100, this._num(c.soc)));
    const { charging, plugged, driving, pw } = this._carState();
    const range = this._st(c.range), rEst = this._fmt(E.range_estimate, 0);
    const status = charging ? "Lädt" : driving ? (c.status_on || "Unterwegs") : plugged ? "Angesteckt" : (c.status_off || "Geparkt");

    // Markierungen im Balken: Ladeziel (evcc) und Mindest-SoC (immer laden bis …)
    const lim = ev.limit_soc && this._st(ev.limit_soc) ? this._num(ev.limit_soc) : null;
    const min = ev.min_soc && this._st(ev.min_soc) ? this._num(ev.min_soc) : null;
    const marks = [min != null && min > 0 && min < 100 ? `<i class="bm min" style="left:${min}%" title="Mindestladung ${Math.round(min)} %"></i>` : "",
      lim != null && lim > 0 && lim < 100 ? `<i class="bm lim" style="left:${lim}%" title="Ladeziel ${Math.round(lim)} %"></i>` : ""].join("");

    // Infozeile: beim Laden Leistung/Energie/PV/Fertig, sonst letzte Fahrt bzw. letzte Ladung
    let line = "";
    if (charging) {
      const p = this._power(pw), se = this._fmt(ev.session_energy, 1), sp = this._fmt(ev.session_solar, 0), rem = this._fmt(ev.remaining);
      const fin = this._st(ev.finish), finD = fin && !OFFLINE_HD.includes(fin.state) ? new Date(fin.state) : null;
      line = `<div class="cline charge">
        <span>${icon("mdi:flash")}<b>${p.v}</b> ${p.u}</span>
        ${se ? `<span>${icon("mdi:battery-plus-variant")}<b>${se.v}</b> ${se.u || "kWh"}</span>` : ""}
        ${sp ? `<span class="pv">${icon("mdi:solar-power-variant")}<b>${sp.v}</b> %</span>` : ""}
        ${finD && !isNaN(finD) ? `<span>${icon("mdi:flag-checkered")}<b>${pad(finD.getHours())}:${pad(finD.getMinutes())}</b></span>` : rem ? `<span>${icon("mdi:timer-sand")}<b>${rem.v}</b> ${rem.u}</span>` : ""}
      </div>`;
    } else {
      const lt = this._fmt(E.last_trip_km, 0), lc = this._st(ev.last_charge);
      const lcD = lc && !OFFLINE_HD.includes(lc.state) ? new Date(lc.state) : null;
      const parts = [];
      if (lt) parts.push(`<span>${icon("mdi:map-marker-path")}Letzte Fahrt <b>${lt.v}</b> km</span>`);
      if (lcD && !isNaN(lcD)) parts.push(`<span>${icon("mdi:ev-station")}Geladen <b>${this._ago(lcD)}</b></span>`);
      if (parts.length) line = `<div class="cline">${parts.join("")}</div>`;
    }

    // drei Kennzahlen aus ev_assistant
    const LBL = { vehicle_avg_consumption: "Ø Verbrauch", trip_avg_consumption: "Ø Fahrten", odo_month_km: "km Monat", odo_day_km: "km heute",
      odo_week_km: "km Woche", odo_year_km: "km Jahr", cost_month: "Kosten Monat", cost_year: "Kosten Jahr", cost_week: "Kosten Woche",
      savings: "Ersparnis gesamt", kwh_month: "kWh Monat", odo_avg_day: "Ø km/Tag", odo: "km-Stand", range_estimate: "Reichweite",
      total_trip_km: "km gesamt" };
    const stats = (c.stats || []).map((k) => {
      const id = E[k] || (k.includes(".") ? k : null), f = this._fmt(id);
      if (!f) return "";
      return `<button class="cstat" data-act="more" data-entity="${esc(id)}"><span>${esc(LBL[k] || this._st(id)?.attributes?.friendly_name || k)}</span><b>${esc(f.v)}<small>${esc(f.u.replace("kWh/100km", "kWh/100"))}</small></b></button>`;
    }).join("");

    // Hinweise von ev_assistant (Fremdladung/Fahrt erfassen, Wartung)
    const flags = [];
    if (this._st(E.pending)?.state === "on") flags.push(["mdi:ev-station", "Fremdladung erfassen", E.pending]);
    if (this._st(E.trip_pending)?.state === "on") flags.push(["mdi:map-marker-question", "Fahrt erfassen", E.trip_pending]);
    const wf = this._st(E.wartung_faellig);
    if (wf && ["on", "true", "ja", "fällig"].includes(String(wf.state).toLowerCase())) flags.push(["mdi:wrench", "Wartung fällig", E.wartung_faellig]);

    const html = `
      <div class="hd"><span class="ttl">${esc(c.name)}</span><span class="lbl ${charging ? "chg" : ""}">${charging ? `${icon("mdi:lightning-bolt")} ` : ""}${esc(status)}</span>
        <button class="arrow" data-act="cardetail" aria-label="Details">${icon("mdi:chevron-right")}</button></div>
      <div class="carbody" data-act="cardetail">
        <div><div class="soc">${Math.round(soc)}<sup>%</sup></div>
          <div class="range">${range ? `${Math.round(this._num(c.range))} km` : rEst ? `${rEst.v} km` : ""}${range && rEst ? `<small> · real ≈ ${rEst.v} km</small>` : ""}</div></div>
        ${c.image ? `<img class="carimg" src="${esc(c.image)}" alt="" onerror="this.style.display='none'">` : ""}
      </div>
      <div class="bar">${marks}<span style="width:${soc}%" class="${charging ? "charging" : ""}"></span></div>
      ${line}
      ${flags.length ? `<div class="cflags">${flags.map(([i, t, id]) => `<button class="chip warn" data-act="more" data-entity="${esc(id)}">${icon(i)}${t}</button>`).join("")}</div>` : ""}
      ${stats ? `<div class="cstats">${stats}</div>` : ""}`;
    // nur bei Änderungen neu aufbauen (sonst lädt z. B. das Bild jedes Mal neu)
    const el = this.shadowRoot.getElementById("car");
    if (el._html !== html) { el.innerHTML = html; el._html = html; }
    if (this._menu && !this.shadowRoot.contains(this._menu.anchorEl)) this._closeMenu();
  }

  _ago(d) {
    const m = Math.round((Date.now() - d.getTime()) / 60000);
    if (m < 60) return `vor ${Math.max(1, m)} min`;
    if (m < 24 * 60) return `vor ${Math.round(m / 60)} h`;
    const days = Math.round(m / 1440);
    return days === 1 ? "gestern" : `vor ${days} Tagen`;
  }

  /* Wert gegen "a|b|c" prüfen, ohne Groß-/Kleinschreibung */
  _matches(v, keys) { return v != null && String(keys || "").toLowerCase().split("|").map((k) => k.trim()).includes(String(v).toLowerCase()); }
  _styleFor(styles, v) {
    for (const [k, m] of Object.entries(styles || {})) if (this._matches(v, k)) return m;
    return {};
  }
  _label(m, v) { return m.label || (v ? String(v).charAt(0).toUpperCase() + String(v).slice(1) : ""); }

  _openMenuAt(anchor, menu) {
    this._closeMenu();
    // An body anhängen damit kein overflow:hidden abschneidet
    // Styles inline setzen da das Element außerhalb des Shadow-DOM ist
    document.body.appendChild(menu);
    if (!document.getElementById("mg-menu-styles")) {
      const st = document.createElement("style");
      st.id = "mg-menu-styles";
      st.textContent = `.mg-menu-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:12px;cursor:pointer;font-size:14px;font-weight:500;color:#94a3b8;background:none;border:0;width:100%;text-align:left;white-space:nowrap}.mg-menu-item:hover{background:rgba(255,255,255,.06);color:#e2e8f0}.mg-menu-item.cur{background:rgba(255,255,255,.08);color:#e2e8f0}.mg-menu-item ha-icon{--mdc-icon-size:17px}.mg-menu-item .glyph{font-size:15px}.mg-menu-item .ck{margin-left:auto;--mdc-icon-size:16px;color:#34d399}`;
      document.head.appendChild(st);
    }
    Object.assign(menu.style, {
      position: "fixed", zIndex: "99999",
      background: "#1c2029", border: "1px solid rgba(255,255,255,.1)",
      borderRadius: "16px", padding: "6px",
      boxShadow: "0 16px 40px rgba(0,0,0,.55)",
      display: "flex", flexDirection: "column", gap: "2px",
      fontFamily: "inherit", fontSize: "14px", color: "#e2e8f0"
    });
    const ar = anchor.getBoundingClientRect();
    const mw = Math.max(ar.width, 160);
    menu.style.minWidth = mw + "px";
    // Horizontal: links am Anker, aber nicht über Bildschirmrand
    let left = ar.left;
    if (left + mw > window.innerWidth - 8) left = window.innerWidth - mw - 8;
    menu.style.left = Math.max(8, left) + "px";
    // Vertikal: unterhalb wenn Platz, sonst oberhalb
    const spaceBelow = window.innerHeight - ar.bottom - 6;
    const spaceAbove = ar.top - 6;
    const mh = Math.min(menu.scrollHeight, Math.max(spaceBelow, spaceAbove, 120));
    menu.style.maxHeight = mh + "px";
    menu.style.overflowY = "auto";
    // Immer nach unten öffnen, außer unten zu wenig Platz
    const below = spaceBelow >= Math.min(mh, 120) || spaceBelow >= spaceAbove;
    menu.style.top = (below ? ar.bottom + 4 : ar.top - mh - 4) + "px";
    // Aktuellen Wert in Sicht scrollen
    const cur = menu.querySelector(".cur");
    if (cur) setTimeout(() => cur.scrollIntoView({ block: "nearest" }), 0);
    menu.anchorEl = anchor; this._menu = menu;
    this._menuClose = (e) => { if (!e.composedPath().includes(menu) && !e.composedPath().includes(anchor)) this._closeMenu(); };
    setTimeout(() => window.addEventListener("click", this._menuClose), 0);
  }

  _closeMenu() {
    if (this._menuClose) window.removeEventListener("click", this._menuClose);
    this._menu?.remove(); this._menu = null; this._menuClose = null;
  }

  /* ---------- Klicks ---------- */
  _click(e) {
    const el = e.composedPath().find((n) => n.dataset && n.dataset.act);
    if (!el) return;
    e.stopPropagation();
    const { act, entity } = el.dataset;
    if (act === "charges") { this._openCharges(); return; }
    if (act === "trips") { this._openTrips(); return; }
    if (act === "mset") {
      this._closeMenu();
      const id = el.dataset.entity;
      if (this._st(id)?.state !== el.dataset.opt) this._hass.callService(id.split(".")[0], "select_option", { entity_id: id, option: el.dataset.opt });
      return;
    }
    if (act === "mnum") { this._mnum(el); return; }
    if (act === "malways") {
      this._closeMenu();
      const c = this._config.car;
      if (this._st(c.mode)?.state !== el.dataset.mode) this._hass.callService(c.mode.split(".")[0], "select_option", { entity_id: c.mode, option: el.dataset.mode });
      if (this._st(c.always)?.state !== el.dataset.opt) this._hass.callService(c.always.split(".")[0], "select_option", { entity_id: c.always, option: el.dataset.opt });
      // manual_mode von Auto weg
      if (c.manual_mode && this._st(c.manual_mode) && /^auto/i.test(this._st(c.manual_mode).state)) {
        const opts = this._st(c.manual_mode).attributes.options || [];
        const t = opts.find((o) => /^pv$|^min/i.test(o)) || opts.find((o) => !/^auto/i.test(o));
        if (t) this._hass.callService(c.manual_mode.split(".")[0], "select_option", { entity_id: c.manual_mode, option: t });
      }
      return;
    }
    if (act === "limmenu") { this._openLimMenu(el); return; }
    if (act === "limset") {
      this._closeMenu();
      const id = el.dataset.entity, v = el.dataset.v, dom = id.split(".")[0];
      if (dom === "select" || dom === "input_select") this._hass.callService(dom, "select_option", { entity_id: id, option: String(v) });
      else this._hass.callService(dom, "set_value", { entity_id: id, value: Number(v) });
      return;
    }
    if (act === "vorgabemenu") {
      this._closeMenu();
      const c = this._config.car, st = this._st(c.manual_mode);
      if (!st) return;
        const menu = document.createElement("div"); menu.className = "menu";
      menu.innerHTML = (st.attributes.options || []).map((o) => {
        const m = this._styleFor(c.manual_styles, o), cur = o === st.state;
        return `<button class="mg-menu-item mi ${cur ? "cur" : ""}" style="--cc:${m.color || "var(--text)"}" data-act="mset" data-entity="${esc(c.manual_mode)}" data-opt="${esc(o)}">
          ${icon(m.icon || "mdi:circle-small")}<span>${esc(this._label(m, o))}</span>${cur ? icon("mdi:check", "ck") : ""}</button>`;
      }).join("");
      this._openMenuAt(el, menu);
      return;
    }
    if (act === "msetmode") {
      const c = this._config.car, id = el.dataset.entity;
      if (this._st(id)?.state !== el.dataset.opt) this._hass.callService(id.split(".")[0], "select_option", { entity_id: id, option: el.dataset.opt });
      // manual_mode von Auto wegnehmen, damit der Modus nicht überschrieben wird
      if (c.manual_mode && this._st(c.manual_mode)) {
        const opts = this._st(c.manual_mode).attributes.options || [], cur = this._st(c.manual_mode).state;
        if (/^auto/i.test(cur)) {
          // Passendes Pendant suchen (aus→aus, smart→pv, schnell→schnell)
          const map = {"off":"aus","pv":"pv","now":"schnell"};
          const target = opts.find((o) => o.toLowerCase() === (map[el.dataset.opt] || el.dataset.opt).toLowerCase()) || opts.find((o) => !/^auto/i.test(o));
          if (target) this._hass.callService(c.manual_mode.split(".")[0], "select_option", { entity_id: c.manual_mode, option: target });
        }
      }
      return;
    }
    if (act === "smartmenu") {
      this._closeMenu();
      const c = this._config.car, ast = this._st(c.always), mst = this._st(c.mode);
      if (!ast || !mst) return;
      const mode = el.dataset.mode;
      const menu = document.createElement("div"); menu.className = "menu";
      menu.innerHTML = (ast.attributes.options || []).map((ao) => {
        const am = this._styleFor(c.always_styles || {}, ao);
        const mLabel = this._styleFor(c.mode_styles || {}, mode);
        const cur = mst.state === mode && ast.state === ao;
        return `<button class="mg-menu-item mi ${cur ? "cur" : ""}" style="--cc:${am.color || "var(--cyan)"}" data-act="malways" data-mode="${esc(mode)}" data-opt="${esc(ao)}">
          ${am.glyph ? `<span class="glyph">${esc(am.glyph)}</span>` : icon(am.icon || "mdi:circle-small")}<span>${esc(this._label(mLabel, mode))} · ${esc(this._label(am, ao))}</span>${cur ? icon("mdi:check", "ck") : ""}</button>`;
      }).join("");
      this._openMenuAt(el, menu);
      return;
    }
    if (act === "mbal") {
      // Optimistisches Update: sofort in UI anzeigen, dann Service aufrufen
      const enable = el.dataset.v === "1";
      this._balOptimistic = enable;
      this._render_mgmt();
      this._evaCall("set_weekly_full_charge_enabled", { enabled: enable });
      // bis die Integration den neuen Wert meldet (spätestens nach 30 s wieder echten Wert zeigen)
      clearTimeout(this._balTimer);
      this._balTimer = setTimeout(() => { this._balOptimistic = null; this._render_mgmt(); }, 30000);
      return;
    }
    if (act === "mpause") { this._evaCall("set_evcc_mode_control_pause", { paused: el.dataset.v === "1" }); return; }
    if (act === "mplanclear") { if (window.confirm("Ladeplan löschen?")) this._evaCall("clear_evcc_charge_plan", {}); return; }
    if (act === "mplansoc") { this._planSoc = Math.max(10, Math.min(100, (this._planSoc ?? 80) + Number(el.dataset.d))); this._planTime = this.shadowRoot.querySelector("#mgmt .pin")?.value; this._render_mgmt(); return; }
    if (act === "mplanset") {
      const v = this.shadowRoot.querySelector("#mgmt .pin")?.value, t = v ? new Date(v).getTime() : NaN;
      if (isNaN(t) || t < Date.now() + 10 * 60000) { window.alert("Bitte eine Zielzeit in der Zukunft wählen."); return; }
      this._evaCall("set_evcc_charge_plan", { target_soc: this._planSoc ?? 80, target_time: Math.round(t / 1000) });
      this._planTime = null; return;
    }
    if (act === "none") return;
    if (act === "chfilter") { this._chFilter = el.dataset.v; this._renderCharges(); this.shadowRoot.querySelector("#cardlg .dbody")?.scrollTo(0, 0); return; }
    if (act === "hrange") {
      this._hh = Number(el.dataset.h);
      try { localStorage.setItem("mg-car-hist-hours", String(this._hh)); } catch (x) {}
      this._carHist = null; this._update(true); this._loadCarHist(); return;
    }
    if (act === "cardetail") {
      const ev = new Event("hass-more-info", { bubbles: true, composed: true }); ev.detail = { entityId: this._config.car.soc }; this.dispatchEvent(ev); return;
    }
    if (act === "cardclose") { this.shadowRoot.getElementById("cardlg")?.close(); return; }
    if (!entity) return;
    if (act === "more") {
      const ev = new Event("hass-more-info", { bubbles: true, composed: true });
      ev.detail = { entityId: entity }; this.dispatchEvent(ev);
    }
  }
}

/* ---------------- Styles ---------------- */
const STYLE = `
:host{
  --bg:#0b0d12; --panel:#14171e; --panel2:#11141a; --line:rgba(255,255,255,.065);
  --tile:rgba(255,255,255,.032); --tileb:rgba(255,255,255,.07);
  --text:#f3f5f9; --muted:#8b91a1; --dim:#5d6373;
  --e-grid-in:var(--energy-grid-consumption-color,#488fc2); --e-solar:var(--energy-solar-color,#ff9800);
  --gold:#f7b733; --cyan:#38bdf8; --green:#34d399; --violet:#a78bfa; --orange:#fb923c; --red:#f87171; --blue:#60a5fa;
  display:block; container-type:inline-size;
  font-family:'Outfit','Plus Jakarta Sans','Segoe UI',system-ui,sans-serif; color:var(--text);
  -webkit-font-smoothing:antialiased;
}
*{box-sizing:border-box}
button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer;text-align:left}
button:focus-visible{outline:2px solid var(--cyan);outline-offset:2px}
ha-icon{--mdc-icon-size:22px;display:inline-flex}
.wrap{background:var(--bg);padding:18px 22px 24px;min-height:100%;position:relative}
.grid{display:grid;grid-template-columns:1fr 1.32fr .96fr;gap:20px;align-items:stretch}
.col{display:flex;flex-direction:column;gap:20px;min-width:0}
.grow{flex:1}
.panel{background:linear-gradient(180deg,#161920,#12151b);border:1px solid var(--line);border-radius:30px;padding:20px 22px;position:relative;overflow:hidden}
.hd{display:flex;align-items:center;gap:12px;min-height:40px;margin-bottom:14px}
.ttl{font-size:15px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);white-space:nowrap}
.lbl{margin-left:auto;font-size:15px;color:rgba(243,245,249,.78);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lbl.warn{color:var(--orange);font-weight:600}
.arrow{width:42px;height:42px;border-radius:14px;background:rgba(255,255,255,.05);border:1px solid var(--line);display:grid;place-items:center;color:var(--text);flex:none}
.hd .lbl:empty + .arrow{margin-left:auto}
.empty{color:var(--dim);font-size:14px;padding:12px 2px}
.qbtn{display:inline-flex;align-items:center;gap:6px;height:38px;padding:0 13px;border-radius:13px;background:rgba(247,183,51,.14);border:1px solid rgba(247,183,51,.35);color:var(--gold);font-size:14px;font-weight:600;white-space:nowrap}
.qbtn ha-icon{--mdc-icon-size:18px}
.qbtn.ghost{background:rgba(255,255,255,.04);border-color:var(--line);color:var(--muted)}

/* Auto */
.panel.car .lbl.chg{color:var(--green);font-weight:600}
.panel.car .lbl ha-icon{--mdc-icon-size:16px;vertical-align:-2px}
.carbody{cursor:pointer}
.range small{color:var(--muted);font-size:.85em}
.bar{position:relative;overflow:visible}
.bar span{position:relative;z-index:1}
.bm{position:absolute;top:-4px;width:3px;height:18px;border-radius:2px;transform:translateX(-1px);z-index:2}
.bm.min{background:var(--orange)}
.bm.lim{background:#fff}
.cline{display:flex;flex-wrap:wrap;gap:6px 14px;margin:-4px 0 14px;font-size:14.5px;color:var(--muted)}
.cline span{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
.cline ha-icon{--mdc-icon-size:16px;color:var(--dim)}
.cline b{color:var(--text);font-weight:700;font-variant-numeric:tabular-nums}
.cline.charge ha-icon{color:var(--green)}
.cline.charge .pv ha-icon,.cline.charge .pv b{color:var(--e-solar)}
.cflags{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}
.chip.warn{color:var(--orange);background:rgba(251,146,60,.1);border-color:rgba(251,146,60,.3)}
.cstats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 14px}
.cstat{display:flex;flex-direction:column;gap:2px;padding:9px 11px;border-radius:15px;background:var(--tile);border:1px solid var(--tileb);min-width:0}
.cstat span{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cstat b{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.cstat small{font-size:11.5px;color:var(--muted);font-weight:500;margin-left:3px}
.wrap.compact .cline{font-size:13px;margin:-2px 0 10px}
.wrap.compact .cstats{margin-bottom:10px;gap:6px}
.wrap.compact .cstat{padding:6px 9px;border-radius:12px}
.wrap.compact .cstat b{font-size:15.5px}
.wrap.compact .cstat span{font-size:10.5px}

/* Detailfenster */
.dlg{outline:none;padding:0;border:0;background:transparent;max-width:min(980px,calc(100vw - 32px));width:100%;max-height:calc(100vh - 48px);overflow:visible;color:var(--text);font-family:inherit}
.dlg::backdrop{background:rgba(5,6,9,.62);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
.dpan{background:linear-gradient(180deg,#171a21,#111419);border:1px solid rgba(255,255,255,.09);border-radius:30px;box-shadow:0 30px 80px rgba(0,0,0,.6);display:flex;flex-direction:column;max-height:calc(100vh - 48px);overflow:hidden}
.dhd{display:flex;align-items:center;gap:14px;padding:18px 20px;border-bottom:1px solid var(--line)}
.dico{width:48px;height:48px;border-radius:16px;display:grid;place-items:center;background:rgba(52,211,153,.14);color:var(--green)}
.rtx{flex:1;min-width:0;display:flex;flex-direction:column}
.rname{font-size:20px;font-weight:600}
.rsub{font-size:13.5px;color:var(--muted)}
.dx{width:44px;height:44px;border-radius:15px;background:rgba(255,255,255,.06);border:1px solid var(--line);display:grid;place-items:center}
.dbody{overflow:auto;padding:16px 20px 22px;display:flex;flex-direction:column;gap:14px}
@media (max-width:760px){.dlg{max-width:100vw;max-height:100vh;height:100%;margin:0}.dpan{height:100vh;max-height:100vh;border-radius:0}}
.panel.car{display:flex;flex-direction:column}
.carbody{display:flex;align-items:center;justify-content:space-between;gap:10px}
.soc{font-size:64px;font-weight:800;line-height:1;letter-spacing:-.02em}
.soc sup{font-size:24px;font-weight:600;vertical-align:top;margin-left:2px}
.range{font-size:17px;color:rgba(243,245,249,.8);margin-top:6px}
.carimg{max-width:48%;max-height:96px;object-fit:contain;filter:drop-shadow(0 8px 14px rgba(0,0,0,.5))}
.bar{height:10px;border-radius:6px;background:rgba(255,255,255,.07);margin:18px 0 16px;overflow:hidden}
.bar span{display:block;height:100%;border-radius:6px;background:linear-gradient(90deg,#22c58f,#5eead4);box-shadow:0 0 12px rgba(52,211,153,.55)}
.bar span.charging{background:linear-gradient(90deg,#22c58f,#5eead4,#22c58f);background-size:200% 100%;animation:charge 2.4s linear infinite}
@keyframes charge{to{background-position:-200% 0}}
.chip{display:inline-flex;align-items:center;gap:8px;padding:9px 16px;border-radius:16px;background:rgba(255,255,255,.045);border:1px solid var(--line);font-size:16px;font-weight:600}
.chip ha-icon{--mdc-icon-size:18px}
.glyph{font-size:15px;font-weight:800;line-height:1;min-width:18px;text-align:center;color:var(--cc)}

/* Fensterhöhe (fit_screen) */
.wrap.fit{height:var(--fit-h);min-height:0;display:flex;flex-direction:column;overflow:hidden;padding-top:12px;padding-bottom:14px}
.wrap.fit .grid{flex:1;min-height:0;grid-template-rows:minmax(0,1fr)}
.wrap.fit .col{min-height:0}
.wrap.fit .panel{min-height:0;flex:none}

/* kompakt bei niedriger Fensterhöhe */
.wrap.compact .grid,.wrap.compact .col{gap:14px}
.wrap.compact .panel{padding:14px 16px;border-radius:24px}
.wrap.compact .hd{min-height:34px;margin-bottom:10px}
.wrap.compact .arrow{width:34px;height:34px;border-radius:11px}
.wrap.compact .ttl{font-size:13px}.wrap.compact .lbl{font-size:13.5px}
.wrap.compact .soc{font-size:48px}.wrap.compact .soc sup{font-size:18px}
.wrap.compact .range{font-size:14.5px;margin-top:2px}
.wrap.compact .carimg{max-height:70px}
.wrap.compact .bar{margin:10px 0}
.wrap.compact .chip{padding:6px 12px;font-size:14px}

/* Responsive */
@container (max-width:1180px){
  .grid{grid-template-columns:1fr 1fr}
  .col:nth-child(2){grid-column:1 / -1;order:-1}
}
@container (max-width:720px){
  .wrap{padding:12px}
  .grid{grid-template-columns:1fr;gap:14px}
  .col{gap:14px}
  .col:nth-child(2){grid-column:auto}
  .panel{border-radius:24px;padding:16px}
}
@media (prefers-reduced-motion:reduce){.bar span.charging{animation:none}}
`;

const CAR_STYLE = `
.wrap.carpage .grid{grid-template-columns:1fr 1.15fr 1.15fr}
#hist{display:flex;flex-direction:column;flex:none!important}
#hist .hd{flex-wrap:wrap;row-gap:10px}
#hist .hsegs{order:3;margin-left:0;width:100%}
#hist .hseg{flex:1;text-align:center}
#hist .chist{height:200px}
.wrap.carpage.fit #hist{flex:none;min-height:0}
.carpage .panel.car .carbody{cursor:default}
.carpage .soc{font-size:76px}
.carpage .carimg{max-height:120px}
/* Lademanagement */
.mauto,.mman{display:inline-flex;align-items:center;gap:6px;font-size:13.5px;font-weight:600}
.mauto{color:var(--cyan)}.mman{color:var(--orange)}
.mauto ha-icon,.mman ha-icon{--mdc-icon-size:16px}
.mgrp{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
.mgl{font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.mgl small{letter-spacing:0;text-transform:none;font-weight:500;color:var(--dim)}
.msteps{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;margin-bottom:12px}
.mstep{display:flex;flex-direction:column;gap:8px;padding:10px 12px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb)}
.msl{display:flex;align-items:center;gap:7px;font-size:12.5px;color:var(--muted);font-weight:600}
.msl ha-icon{--mdc-icon-size:16px;color:var(--dim)}
.mstep .tgt{display:flex;align-items:center;justify-content:space-between;gap:2px;background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:13px;padding:3px}
.mstep .tb{width:36px;height:34px;border-radius:10px;display:grid;place-items:center;font-size:20px;color:var(--muted);text-align:center}
.mstep .tb:hover{background:rgba(255,255,255,.07);color:var(--text)}
.mstep .tv{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.mstep .tv small{font-size:12px;color:var(--muted);font-weight:500}
#mgmt .lrows{margin-top:0}
.mmodes{display:flex;gap:6px}
.mmode{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px;padding:10px 12px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb);cursor:pointer;transition:all .2s}
.mmode:hover{border-color:rgba(255,255,255,.16)}
.mmh{display:flex;align-items:center;gap:8px;font-size:15px;color:var(--muted)}
.mmh ha-icon{--mdc-icon-size:20px}
.mmode.sel{background:linear-gradient(160deg,color-mix(in srgb,var(--cc) 20%,transparent),color-mix(in srgb,var(--cc) 4%,transparent));border-color:color-mix(in srgb,var(--cc) 60%,transparent)}
.mmode.sel .mmh{color:var(--cc)}
.mchv{--mdc-icon-size:18px;opacity:.6;margin-left:auto}
.mmode.vorgabe{flex:none;min-width:0}
.mmode.vorgabe.manual{background:linear-gradient(160deg,rgba(239,68,68,.18),rgba(239,68,68,.04));border-color:rgba(239,68,68,.55)}
.mmode.vorgabe.manual .mmh{color:#ef4444}
.mplan{display:flex;flex-direction:column;gap:10px;padding:12px 14px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb);margin-bottom:8px}
.mplan.act{border-color:rgba(56,189,248,.45);background:linear-gradient(160deg,rgba(56,189,248,.12),rgba(56,189,248,.02))}
.mph{display:flex;align-items:center;gap:10px}
.mph > ha-icon{--mdc-icon-size:22px;color:var(--cyan);flex:none}
.mph span{flex:1;min-width:0;display:flex;flex-direction:column}
.mph b{font-size:15px;font-weight:600}
.mph small{font-size:12.5px;color:var(--muted)}
.mpe{display:flex;gap:8px;font-size:13px;color:var(--muted);line-height:1.4}
.mpe ha-icon{--mdc-icon-size:16px;color:var(--dim);flex:none;margin-top:1px}
.mpf{display:flex;flex-wrap:wrap;align-items:flex-end;gap:10px}
.mpf label{display:flex;flex-direction:column;gap:5px;font-size:11.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.mpf .tgt{display:flex;align-items:center;gap:2px;background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:12px;padding:2px}
.mpf .tb{width:32px;height:32px;border-radius:9px;font-size:18px;color:var(--muted);text-align:center}
.mpf .tv{min-width:52px;text-align:center;font-size:16px;font-weight:700;letter-spacing:0;text-transform:none;color:var(--text)}
.pin{height:38px;border-radius:12px;border:1px solid var(--line);background:rgba(255,255,255,.05);color:var(--text);padding:0 10px;font:inherit;font-size:14px;color-scheme:dark}
.mpf .qbtn{margin-left:auto}
.qbtn[disabled]{opacity:.4;pointer-events:none}
.mtog{display:flex;align-items:center;gap:12px;width:100%;padding:11px 14px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb);margin-bottom:8px;text-align:left}
.mtog > ha-icon{--mdc-icon-size:21px;color:var(--muted);flex:none}
.mtog span{flex:1;min-width:0;display:flex;flex-direction:column}
.mtog b{font-size:15px;font-weight:600}
.mtog small{font-size:12.5px;color:var(--muted)}
.mtog.on{border-color:rgba(52,211,153,.4)}
.mtog.on > ha-icon{color:var(--green)}
.msw{width:44px;height:26px;border-radius:13px;background:rgba(255,255,255,.1);position:relative;flex:none;transition:background .2s}
.msw i{position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#c9ced8;transition:transform .2s}
.mtog.on .msw{background:#22a37a}
.mtog.on .msw i{transform:translateX(18px);background:#fff}
.mbottom{display:flex;gap:8px;margin-top:4px;margin-bottom:12px}
.mbtn{flex:1;display:flex;flex-direction:row;align-items:center;gap:8px;padding:8px 14px;border-radius:14px;background:var(--tile);border:1px solid var(--tileb);cursor:pointer;transition:border-color .2s}
.mbtn:hover{border-color:rgba(255,255,255,.16)}
.mbtn .mtx{display:flex;flex-direction:column;gap:1px;flex:1;min-width:0}
.mbtn ha-icon:first-child{--mdc-icon-size:18px;color:var(--muted);flex:none}
.mbtn b{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.mbtn span{font-size:10.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);white-space:nowrap}
.mbtn .mchv{--mdc-icon-size:14px;opacity:.4;margin-left:auto;flex:none}
.mbtn.lim b{color:var(--cyan)}
.mbtn.lim ha-icon:first-child{color:var(--cyan)}
.mbtn.bal.on{border-color:rgba(52,211,153,.4)}
.mbtn.bal.on ha-icon{color:var(--green)}
.mbtn.bal.on b{color:var(--green)}
.mbtn.bal.act{animation:mgpulse 1.4s ease-in-out infinite}
.limm{scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.15) transparent}
/* Laden */
.lclick{cursor:pointer;border-radius:22px}
.lclick:hover .lhero{border-color:rgba(255,255,255,.16)}
#live .hd .arrow{margin-left:10px}
/* Alle Ladungen */
.chpan{max-width:980px}
.chsum{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:14px 20px;border-bottom:1px solid var(--line)}
.chsum > div:not(.hsegs){display:flex;flex-direction:column;padding:8px 14px;border-radius:14px;background:var(--tile);border:1px solid var(--tileb);min-width:92px}
.chsum span{font-size:11.5px;color:var(--muted);font-weight:600;letter-spacing:.06em;text-transform:uppercase}
.chsum b{font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}
.chsum b small{font-size:12px;color:var(--muted);font-weight:500;margin-left:3px}
.chsum .pv b{color:var(--e-solar)}
.chsum .hsegs{margin-left:auto}
.chlist{display:flex;flex-direction:column;gap:6px}
.chm{font-size:12px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin:10px 4px 2px}
.chm:first-child{margin-top:0}
.chr{display:grid;grid-template-columns:40px minmax(0,1.4fr) minmax(0,1fr) 80px 96px;align-items:center;gap:12px;padding:9px 14px 9px 10px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb)}
.chi{width:40px;height:40px;border-radius:13px;display:grid;place-items:center;background:rgba(52,211,153,.12);color:var(--green)}
.chr.ext .chi{background:rgba(251,146,60,.13);color:var(--orange)}
.chi ha-icon{--mdc-icon-size:20px}
.chd{display:flex;flex-direction:column;min-width:0}
.chd b{font-size:15px;font-weight:600}
.chd small{font-size:12.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chpv{display:flex;flex-direction:column;gap:4px;min-width:0}
.chpv .pvbar{display:block;height:6px;border-radius:4px;background:var(--e-grid-in);overflow:hidden}
.chpv .pvbar i{display:block;height:100%;background:var(--e-solar)}
.chpv small{font-size:12px;color:var(--muted)}
.chk,.chc{display:flex;flex-direction:column;align-items:flex-end;font-variant-numeric:tabular-nums}
.chk b{font-size:17px;font-weight:700;color:var(--cyan)}
.chc b{font-size:15px;font-weight:700}
.chk small,.chc small{font-size:11.5px;color:var(--muted);white-space:nowrap}
@media (max-width:760px){.chr{grid-template-columns:36px minmax(0,1fr) 64px 78px}.chpv{display:none}.chsum .hsegs{width:100%;margin-left:0}}
.lst{margin-left:auto;display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:12px;font-size:13.5px;font-weight:600;background:rgba(255,255,255,.05);color:var(--muted)}
.lst ha-icon{--mdc-icon-size:16px}
.lst.on{background:rgba(52,211,153,.14);color:var(--green)}
.lst.on ha-icon{animation:mgpulse 1.4s ease-in-out infinite}
.lst.ready{background:rgba(56,189,248,.12);color:var(--cyan)}
@keyframes mgpulse{50%{opacity:.4}}
.lhero{display:flex;align-items:center;gap:16px;padding:16px 18px;border-radius:22px;background:var(--tile);border:1px solid var(--tileb);margin-bottom:12px}
.lhero.chg{background:radial-gradient(120% 120% at 0% 0%,rgba(52,211,153,.16),transparent 60%),var(--tile);border-color:rgba(52,211,153,.4)}
.lhl{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}
.lkick{font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lbig{display:flex;align-items:baseline;gap:6px}
.lbig b{font-size:46px;font-weight:800;line-height:1.05;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.lhero.chg .lbig b{color:var(--green)}
.lbig small{font-size:16px;color:var(--muted);font-weight:600}
.lwhen{display:flex;align-items:center;gap:6px;font-size:14px;color:var(--muted);flex-wrap:wrap}
.lwhen ha-icon{--mdc-icon-size:16px;color:var(--dim)}
.lwhen b{color:var(--text)}
.lhero.chg .lwhen ha-icon{color:var(--green)}
.lringw{position:relative;width:96px;height:96px;flex:none}
.lring{width:100%;height:100%;transform:rotate(-90deg)}
.lring circle{fill:none;stroke-width:9;stroke-linecap:butt}
.lring .rbg{stroke:rgba(255,255,255,.06)}
.lring .rpv{stroke:var(--e-solar);filter:drop-shadow(0 0 5px color-mix(in srgb,var(--e-solar) 50%,transparent))}
.lring .rgr{stroke:var(--e-grid-in)}
.lringt{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1}
.lringt b{font-size:22px;font-weight:800;color:var(--e-solar)}
.lringt small{font-size:12px;font-weight:600;margin-left:1px}
.lringt span{font-size:11px;font-weight:700;letter-spacing:.12em;color:var(--muted);margin-top:3px}
.lsplit{display:flex;height:10px;border-radius:6px;overflow:hidden;gap:2px;margin:0 2px 6px}
.lsplit .pv{background:var(--e-solar)}.lsplit .gr{background:var(--e-grid-in)}
.lsplitl{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);margin:0 2px 12px}
.lsplitl span{display:inline-flex;align-items:center;gap:5px}
.lsplitl ha-icon{--mdc-icon-size:15px}
.lsplitl .pv ha-icon{color:var(--e-solar)}.lsplitl .gr ha-icon{color:var(--e-grid-in)}
.lsplitl b{color:var(--text);font-variant-numeric:tabular-nums}
.lfacts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:12px}
.lfact{display:flex;flex-direction:column;gap:2px;padding:9px 11px;border-radius:14px;background:var(--tile);border:1px solid var(--tileb);min-width:0}
.lfact span{font-size:11.5px;color:var(--muted);font-weight:600;white-space:nowrap}
.lfact b{font-size:15.5px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lrows{display:flex;flex-direction:column;border-radius:16px;background:var(--tile);border:1px solid var(--tileb);overflow:hidden}
.lrow{display:flex;align-items:center;gap:10px;padding:10px 14px;font-size:14px;color:var(--muted)}
.lrow + .lrow{border-top:1px solid var(--line)}
.lrow ha-icon{--mdc-icon-size:18px;color:var(--cyan)}
.lrow b{margin-left:auto;color:var(--text);font-weight:600;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lrow.warn ha-icon,.lrow.warn b{color:var(--orange)}
.wrap.compact .lbig b{font-size:36px}.wrap.compact .lringw{width:80px;height:80px}.wrap.compact .lhero{padding:12px 14px}
@container (max-width:720px){.lfacts{grid-template-columns:repeat(2,minmax(0,1fr))}}
.carpage .cstats{grid-template-columns:repeat(2,minmax(0,1fr))}
#trips{display:flex;flex-direction:column}
.tlist{display:flex;flex-direction:column;gap:6px}
.tday{font-size:12px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin:8px 4px 2px}
.tday:first-child{margin-top:0}
.trip{display:grid;grid-template-columns:52px 1fr auto auto;align-items:center;gap:12px;padding:10px 14px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb)}
.ttime{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums;color:rgba(243,245,249,.85)}
.troute{display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px;min-width:0;font-size:15px}
.troute b{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:140px}
.troute ha-icon{--mdc-icon-size:15px;color:var(--dim)}
.troute small{width:100%;font-size:12.5px;color:var(--muted)}
.tkm,.tkwh{display:flex;flex-direction:column;align-items:flex-end;font-variant-numeric:tabular-nums;min-width:56px}
.tkm b,.tkwh b{font-size:17px;font-weight:700}
.tkwh b{color:var(--cyan)}
.tkm small,.tkwh small{font-size:11.5px;color:var(--muted);white-space:nowrap}
.chwrap{position:relative;padding-bottom:20px}
.glg .src{margin-left:auto;color:var(--dim)}
.glg .src::before{display:none}
.hdiag{line-height:1.5}
.hdiag code{font-size:12px;background:rgba(255,255,255,.06);padding:1px 6px;border-radius:6px;color:var(--text)}
.chist{width:100%;height:170px;display:block;overflow:visible}
.chist .gnow{stroke:rgba(255,255,255,.35);stroke-width:1;stroke-dasharray:3 3}
.gax{position:absolute;left:0;right:0;bottom:0;height:16px}
.gax span{position:absolute;transform:translateX(-50%);font-size:11.5px;color:var(--dim);white-space:nowrap;font-variant-numeric:tabular-nums}
.gax span.st{transform:none}
.gax span.now{transform:translateX(-100%);color:var(--muted);font-weight:600}
.hsegs{margin-left:auto;display:flex;background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:12px;padding:3px}
.hseg{height:30px;padding:0 8px;border-radius:9px;font-size:13px;font-weight:600;color:var(--muted);white-space:nowrap}
.hseg.sel{background:rgba(255,255,255,.09);color:var(--text)}
.glg .e{color:var(--green);font-weight:600}
.hsum{display:inline-flex;align-items:center;gap:10px;font-size:14.5px;color:var(--muted);white-space:nowrap;margin-left:4px}
.hsum b{color:var(--green);font-size:17px;font-variant-numeric:tabular-nums}
.hsum.dim{color:var(--dim)}
.hpv{display:inline-flex;align-items:center;gap:4px;color:var(--e-solar);font-weight:700;padding:3px 9px;border-radius:10px;background:color-mix(in srgb,var(--e-solar) 12%,transparent)}
.hpv ha-icon{--mdc-icon-size:15px}
@container (max-width:720px){#hist .hd{flex-wrap:wrap}#hist .hsegs{width:100%;margin-left:0}}
.chist .bpv{fill:rgba(255,152,0,.85)}
.chist .bgr{fill:rgba(72,143,194,.9)}
.chist .hl{fill:rgba(255,255,255,.08);pointer-events:none}
.chwrap.bars{cursor:crosshair;touch-action:pan-y}
.gmax{position:absolute;top:-2px;left:4px;font-size:11px;color:var(--dim);pointer-events:none}
.glg .pvl::before{background:rgba(255,152,0,.85)!important}
.glg .grl::before{background:rgba(72,143,194,.9)!important}
.glg .pvl,.glg .grl{}
.glg .pvl::before,.glg .grl::before{content:"";display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.gtip{position:absolute;top:6px;z-index:5;min-width:190px;max-width:240px;background:#1c2029;border:1px solid rgba(255,255,255,.12);border-radius:13px;padding:9px 12px;font-size:12.5px;color:var(--muted);box-shadow:0 10px 26px rgba(0,0,0,.5);pointer-events:none}
.gtip b{display:block;color:var(--text);font-size:13px;margin-bottom:5px}
.gtip div{display:flex;align-items:center;gap:6px;line-height:1.6}
.gtip div span{margin-left:auto;color:var(--text);font-weight:600;font-variant-numeric:tabular-nums;padding-left:12px}
.gtip i{width:9px;height:9px;border-radius:3px;display:inline-block}
.gtip .pvd{background:rgba(255,152,0,.9)}.gtip .grd{background:rgba(72,143,194,.95)}
.gtip .tot{border-top:1px solid var(--line);margin-top:4px;padding-top:4px}
.gtip .tot span{color:var(--green)}
.glg .e::before{display:none}
.chist .gl{stroke:rgba(255,255,255,.06);stroke-width:1}
.chist .gt{fill:var(--dim);font-size:12px;font-family:inherit}
.chist .gp{fill:rgba(52,211,153,.22);stroke:rgba(52,211,153,.7);stroke-width:1}
.chist .gs{fill:none;stroke:#38bdf8;stroke-width:2.2}
.glg{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12.5px;color:var(--muted);margin-top:6px}
.glg span{white-space:nowrap}
.glg span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.glg .s::before{background:#38bdf8}.glg .p::before{background:rgba(52,211,153,.6)}
.wrap.carpage.fit .col{overflow-y:auto;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.15) transparent;padding-right:2px}
.wrap.carpage.fit .panel{flex:none}
.wrap.carpage.fit #trips{flex:1 1 0;min-height:260px}
.wrap.carpage.fit #trips .tlist{flex:1;min-height:0;overflow:hidden;position:relative}
#trips .tlist{cursor:pointer}
#trips .tlist:hover .trip{border-color:rgba(255,255,255,.12)}
@container (max-width:1180px){.wrap.carpage .grid{grid-template-columns:1fr 1fr}.wrap.carpage .col:nth-child(2){grid-column:1 / -1;order:1}}
@container (max-width:720px){.wrap.carpage .grid{grid-template-columns:1fr}.carpage .soc{font-size:60px}.trip{grid-template-columns:44px 1fr auto;}.tkwh{display:none}.cstats{grid-template-columns:repeat(2,minmax(0,1fr))}}
`;

if (!customElements.get("mg-car-dashboard")) customElements.define("mg-car-dashboard", MgCarDashboard);
if (!window.customCards.some((c) => c.type === "mg-car-dashboard"))
  window.customCards.push({ type: "mg-car-dashboard", name: "MG Auto", description: "Auto-Seite mit evcc, ev_assistant und Fahrtenbuch im Glow-Stil" });

console.info(`%c MG-CAR-DASHBOARD %c ${VERSION} `, "background:#f7b733;color:#111;font-weight:700", "background:#14171e;color:#f7b733");
