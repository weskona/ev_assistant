/*
 * mg-car-dashboard.js
 * Ablage:    /config/www/glow-dashboard/mg-car-dashboard.js
 * Ressource: /local/glow-dashboard/mg-car-dashboard.js?v=51  (Typ: JavaScript)
 * YAML:      type: custom:mg-car-dashboard
 */

window.customCards = window.customCards || [];
const VERSION = "3.6.6";
// Version der Datenschnittstelle zu ev_assistant (Panel-Konfiguration, Websocket-Befehle, evcc_live),
// die diese Karte erwartet. Meldet ev_assistant in der Panel-Konfiguration eine andere "api_version",
// warnt die Karte (Konsole + Hinweis). Ohne "api_version" (ältere ev_assistant-Versionen) keine Warnung.
const EVA_API_VERSION = 1;
const FONT_URL = "https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap";

const WD = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const WD_LONG = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
const MON = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
const PWD = [["montag", "Mo"], ["dienstag", "Di"], ["mittwoch", "Mi"], ["donnerstag", "Do"], ["freitag", "Fr"], ["samstag", "Sa"], ["sonntag", "So"]];
const PWD_LONG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
const MON_LONG = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];

/* =====================================================================
 *  EINSTELLUNGEN
 *  Die Karte holt sich alles, was möglich ist, aus ev_assistant (und den
 *  evcc-Live-Werten, die ev_assistant mitliefert). Werte mit "eva:" sind
 *  solche automatischen Quellen. Wer einen eigenen Sensor verwenden will,
 *  trägt stattdessen dessen Entity-ID ein – am besten per YAML, denn ein
 *  Update (z. B. über HACS) ersetzt diese Datei:
 *    type: custom:mg-car-dashboard
 *    car:
 *      image: /local/mein_auto.png
 *      soc: sensor.mein_auto_batterie
 *  Leer ("") = nicht verwenden, der Bereich wird ausgeblendet.
 * ===================================================================== */
const CAR_DEFAULTS = {
  fit_screen: true,   // Desktop/Laptop: Dashboard passt sich der Fensterhöhe an (kein Scrollen der Seite)
  debug: false,       // true = Diagnose-Meldungen in der Browser-Konsole (u. a. welche Quelle für welchen Wert)
  // Panel-Konfiguration von ev_assistant. Setzt das ev_assistant-Panel selbst, wenn es die Karte einbettet;
  // als eigenständige Karte leer lassen – dann liest die Karte sie über "get_panels".
  ev_assistant_panel: null,
  // Mehrere Autos: die Karte bietet alle Fahrzeuge aus ev_assistant zur Auswahl an (Pfeil neben dem Namen).
  // Hier lassen sich je Auto eigene Werte setzen – Schlüssel ist der Fahrzeugname oder die config_entry_id, z. B.
  //   vehicles:
  //     "Citroën ë-C3": { image: /local/c3.png }
  //     "Renault Zoe":  { image: /local/zoe.png, evcc_loadpoint: carport }
  vehicles: {},

  // --- Energie (Verlauf) ---
  // Geladene kWh je Stunde kommen aus der Ladeleistung (Standard: „Wallbox Ladeleistung“ aus ev_assistant ab 0.99.34),
  // ohne Ladeleistung aus dem evcc-Ladelogbuch. Den PV-Anteil liefert evcc je Ladesitzung.
  energy: {
    car_power: "",      // eigener Ladeleistungs-Sensor mit Langzeitstatistik (leer = aus ev_assistant)
    grid_import: "",    // nur ohne evcc: Netzbezug (Leistung) für die Aufteilung Netz/PV
    home: "",           // nur ohne evcc: Hausverbrauch inkl. Auto (Leistung)
  },

  car: {
    // --- Fahrzeug ---
    name: "",                         // leer = Fahrzeugname aus ev_assistant
    image: "",                        // Bild des Autos, z. B. "/local/auto.png" (leer = Fahrzeugbild aus ev_assistant ab 0.99.45, sonst kein Bild)
    soc: "eva:soc",                   // Ladestand: SoC-Sensor aus ev_assistant, sonst evcc
    range: "eva:range",               // Reichweite: ev_assistant „Reichweite (real)“
    status: "eva:motor",              // fährt: Motor-Sensor aus ev_assistant (sofern dort freigegeben)
    status_on: "Motor an",            // Text, wenn das Auto fährt
    status_off: "Geparkt",            // Text, wenn das Auto steht
    cable: "eva:plug",                // eingesteckt: Stecker-Sensor aus ev_assistant, sonst evcc „verbunden“

    // --- Lademodus ---
    // Ohne eigene Auswahl-Entitäten schaltet die Karte den evcc-Modus über ev_assistant
    // (Auto = ev_assistant steuert, Smart, Smart + Immer laden, Schnell).
    mode: "",                         // evcc-Lademodus als select-Entität (z. B. aus der evcc-Integration)
    always: "",                       // „Immer laden“ als select-Entität (nur zusammen mit mode)
    manual_mode: "",                  // eigene Vorgabe (input_select automatisch / manuell)
    limit: "",                        // Ladestrom (A) einstellbar anzeigen: "eva:max_current" = Select der evcc-Integration, oder eigene number-/select-Entität (leer = aus)

    // --- evcc (Ladepunkt) – Standard: Live-Werte aus ev_assistant ---
    evcc: {
      charging: "eva:charging",
      connected: "eva:connected",
      power: "eva:charge_power",
      session_energy: "eva:session_energy",
      session_solar: "eva:session_solar",
      session_price: "eva:session_price",
      duration: "eva:duration",
      currents: "eva:currents",       // Ladestrom je Phase: evcc „chargeCurrents“ über ev_assistant, sonst „Ladestrom P1–P3“ der evcc-Integration; oder Liste eigener Sensoren
      remaining: "",                  // Restladezeit (Sensor; leer = „Laderestzeit“ der evcc-Integration)
      finish: "",                     // voraussichtliches Ladeende (Sensor mit Zeitstempel)
      limit_soc: "eva:limit_soc",     // Ladeziel: automatisch das Select der evcc-Integration (auswählbar), sonst evcc-Live-Wert (nur Anzeige)
      min_soc: "eva:min_soc",         // Markierung „bis hier immer laden“
      solar_total: "eva:solar_total",
      last_charge: "eva:last_charge",
    },
    evcc_vehicle: "",                // nur Ladungen dieses evcc-Fahrzeugs in „Alle Ladungen“ (leer = aus ev_assistant)
    evcc_loadpoint: "",              // bei mehreren Ladepunkten in der evcc-Integration: Teil der Entity-ID, z. B. "warp3"

    // --- ev_assistant ---
    // Die Entitäten werden automatisch gefunden. Einzelne lassen sich hier fest vorgeben, z. B.
    //   ev_assistant: { odo: "sensor.mein_km_stand", cost_year: "sensor.kosten_jahr" },
    // Verwendete Schlüssel: odo, odo_day_km, odo_week_km, odo_month_km, odo_year_km, odo_avg_day, odo_year_projected,
    //   trip_count, last_trip_km, vehicle_avg_consumption, trip_avg_consumption, range_estimate, available_kwh,
    //   battery_capacity, equivalent_full_cycles, measured_efficiency, cost_day, cost_week, cost_month, cost_year,
    //   kwh_month, kwh_year, home_kwh, total_kwh, savings, co2_savings, pending, trip_pending, wartung_faellig,
    //   evcc_charge_plan, evcc_mode_control, charge_before_pv_recommended
    ev_assistant: {},
    ev_assistant_entry: "",          // config_entry_id von ev_assistant (leer = automatisch, bei mehreren Fahrzeugen das erste)
    stats: ["vehicle_avg_consumption", "odo", "cost_year", "savings"],   // Kennzahlen in der Auto-Kachel
    // Leasing-Kilometerbudget: Sensor „km vor Rücklauf“ aus ev_assistant (alle Vertrags- und Hochrechnungswerte
    // stehen in seinen Attributen). Eigene Entity-ID möglich, "" = Kachel aus. Ohne Leasing-Vertrag bleibt sie ausgeblendet.
    leasing: "eva:leasing_km_vor_ruecklauf",
    // Nutzungs-Kachel (km/kWh/Kosten je Zeitraum, Durchschnitte, Ladeorte aus ev_assistant). Mit Leasing-Vertrag
    // lässt sich im Kachelkopf zwischen Leasing und Nutzung umschalten, sonst wird nur die Nutzung gezeigt. false = aus
    usage: true,

    // --- Fahrtenbuch ---
    trips: "eva:trips",                   // Fahrtenbuch aus ev_assistant (oder ein Sensor mit Attribut "trips")
    urlaub_entity: "",                    // Urlaubsmodus: die „Urlaubs-Entität“ aus den ev_assistant-Optionen (leer = automatisch suchen)
    trips_visible: 5,                     // so viele Fahrten in der Kachel, wenn die Seite nicht an die Fensterhöhe angepasst ist
    trips_max: 0,                         // höchstens so viele Fahrten berücksichtigen (0 = alle)
    list_page: 30,                        // Fenster „Alle Fahrten“ / „Alle Ladungen“: so viele Einträge zuerst, beim Scrollen weitere

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

/* evcc-Lademodus über ev_assistant (Services set_evcc_manual_mode / clear_evcc_manual_mode).
   Kacheln: Auto | Smart ▼ | Schnell. Smart hat die evcc-Einstellung „immer laden“ (alwaysCharge) als Auswahl:
   aus (nur PV), immer, 1x (einmalig – nur über die evcc-Integration, ev_assistant kennt nur pv/minpv/now) */
const EVA_AUTO  = { v: "auto",  label: "Auto",    icon: "mdi:robot-outline",  color: "#38bdf8", title: "ev_assistant steuert den Lademodus" };
const EVA_SMART = { label: "Smart",   color: "#34d399", title: "PV-optimiert laden" };
const EVA_NOW   = { v: "now",   label: "Schnell", icon: "mdi:lightning-bolt", color: "#f87171", title: "sofort mit voller Leistung laden" };
const EVA_SMART_OPTS = [
  { ac: "off",  mode: "pv",    label: "aus",   sub: "PV",     long: "nur PV-Überschuss",             icon: "mdi:solar-power" },
  { ac: "on",   mode: "minpv", label: "immer", sub: "immer",  long: "immer laden (Mindestleistung)", icon: "mdi:infinity" },
  { ac: "once", mode: "minpv", label: "1x",    sub: "einmal", long: "einmal laden (Mindestleistung)", glyph: "1x" },
];
// manuelle Modi in der Auswahl der zweiten Kachel (v wie die Auswahl-Logik in _render_mgmt_eva: off/pv/once/minpv/now)
const EVA_MANUAL = [
  { v: "off",   act: "evamode2", dv: "off",  label: "Aus",           short: "Aus",       icon: "mdi:power-off",      color: "#8b91a1", sub: "nicht laden", needs: "mode" },
  { v: "pv",    act: "evasmart", dv: "off",  label: "Smart · aus",   short: "Smart",     icon: "mdi:solar-power",    color: "#34d399", sub: "nur PV-Überschuss" },
  { v: "once",  act: "evasmart", dv: "once", label: "Smart · 1x",    short: "Smart · 1x", glyph: "1x",               color: "#34d399", sub: "einmal mit Mindestleistung", needs: "alwayscharge" },
  { v: "minpv", act: "evasmart", dv: "on",   label: "Smart · immer", short: "Smart · immer", icon: "mdi:infinity",   color: "#34d399", sub: "immer mit Mindestleistung" },
  { v: "now",   act: "evamode2", dv: "now",  label: "Schnell",       short: "Schnell",   icon: "mdi:lightning-bolt", color: "#f87171", sub: "sofort mit voller Leistung" },
];
const EVA_MODES = [EVA_AUTO, { v: "pv", label: "Smart" }, { v: "minpv", label: "Smart · immer" }, EVA_NOW];   // Beschriftung „evcc: …“

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
    const prevPanel = this._config?.ev_assistant_panel;
    this._rawConfig = config || {};
    this._config = merge(CAR_DEFAULTS, this._rawConfig);
    if (this._evaPanel) this._applyVehicle();
    if (this._config.ev_assistant_panel !== prevPanel) { this._evaPanelReq = false; if (this._hass) this._loadEvaPanel(); }
    if (this._built) { this._built = false; this._build(); if (this._hass) this._update(true); }
  }

  getCardSize() { return 14; }
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (!this._built) this._build();
    if (first) { this._loadEvaPanel(); this._loadCarHist(); this._loadLastSession(); this._loadTrips(); }
    this._update();
  }
  connectedCallback() {
    if (!this._onResize) {
      this._onResize = () => { cancelAnimationFrame(this._fitRaf); this._fitRaf = requestAnimationFrame(() => { this._fit(); this._render_trips(); this._kFit(); }); };
      this._ro = new ResizeObserver(this._onResize);
    }
    window.addEventListener("resize", this._onResize);
    this._ro.observe(this); this._onResize();
    if (!this._histTimer) this._histTimer = setInterval(() => { this._loadCarHist(); this._loadLastSession(); this._loadTrips(); }, 15 * 60000);
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
      this.shadowRoot.addEventListener("error", (e) => { if (e.target?.classList?.contains("carimg")) this._carImageError(e.target); }, true);
    }
    if (!this._pinBound) { this._pinBound = true; this.shadowRoot.addEventListener("change", (e) => { const t = e.composedPath()[0]; if (t?.classList?.contains("pin")) { this._planTime = t.value; t.blur(); } }); }
    if (!this._setBound) {   // Eingaben der Einstellungen-Seite (Dateiauswahl, Filter, Vorlage im Formular)
      this._setBound = true;
      const on = (e) => {
        const t = e.composedPath()[0], c = t?.classList;
        if (!c) return;
        if (e.type === "change" && c.contains("simgfile")) { const f = t.files?.[0]; t.value = ""; this._uploadImg(f); }
        else if (e.type === "change" && c.contains("srestfile")) { const f = t.files?.[0]; t.value = ""; this._readRestore(f); }
        else if (e.type === "change" && c.contains("simpfile")) { const f = t.files?.[0]; t.value = ""; this._readTripImport(f); }
        else if (e.type === "change" && c.contains("fpreset")) this._wtPreset(t.value, true);
        else if (e.type === "change" && c.contains("pvminsel")) { t.blur(); this._setPvMin(t.value); }
        else if (e.type === "change" && c.contains("mbufsel")) { t.blur(); if (t.value !== "") this._setBuffer(Number(t.value)); }
        else if (e.type === "change" && c.contains("mptgt")) { if (t.dataset.u === "km") this._planKm = Number(t.value); else this._planSoc = Number(t.value); this._planTime = this.shadowRoot.querySelector("#mgmt .pin")?.value; t.blur(); this._render_mgmt(); }
        else if (e.type === "change" && c.contains("slogkat")) { this._logKat = t.value; this._renderLogList(); }
        else if (e.type === "input" && c.contains("slogq")) { this._logQ = t.value; this._renderLogList(); }
      };
      this.shadowRoot.addEventListener("change", on); this.shadowRoot.addEventListener("input", on);
    }
    if (!this._hoverBound) {
      this._hoverBound = true;
      this.shadowRoot.addEventListener("pointermove", (e) => this._barHover(e));
      this.shadowRoot.addEventListener("pointerdown", (e) => this._barHover(e));
      this.shadowRoot.addEventListener("pointerleave", () => { const t = this.shadowRoot.querySelector(".gtip"); if (t) t.hidden = true; this.shadowRoot.querySelector(".hl")?.setAttribute("width", 0); }, true);
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}${CAR_STYLE}</style>
      <div class="wrap carpage">
        <div class="apiwarn" id="apiwarn" hidden></div>
        <div class="pages"><div class="hsegs"><button class="hseg" data-act="page" data-p="main">Übersicht</button><button class="hseg" data-act="page" data-p="prof">Profil &amp; Analyse</button><button class="hseg" data-act="page" data-p="cost">Laden &amp; Kosten</button><button class="hseg" data-act="page" data-p="set">Einstellungen</button></div><div class="kper" id="kper" hidden></div></div>
        <div class="grid" id="pmain">
          <div class="col"><section class="panel car" id="car"></section><section class="panel grow" id="trips"></section></div>
          <div class="col"><section class="panel" id="live"></section><section class="panel" id="mgmt"></section></div>
          <div class="col"><section class="panel grow" id="hist"></section><section class="panel" id="lease" hidden></section><section class="panel" id="usage" hidden></section></div>
        </div>
        <div class="grid pgrid" id="pprof" hidden>
          <section class="panel" id="pweek"></section><section class="panel" id="pmorrow"></section>
          <section class="panel" id="pana"></section><section class="panel" id="pmisch"></section>
        </div>
        <div class="grid kgrid" id="pcost" hidden>
          <div class="col"><section class="panel" id="kgel"></section><section class="panel" id="klist"></section></div>
          <div class="col"><section class="panel" id="kauf"></section><section class="panel" id="kcmp"></section></div>
        </div>
        <div class="grid sgrid" id="pset" hidden>
          <div class="col"><section class="panel" id="swart"></section><section class="panel" id="slk"></section><section class="panel" id="slog"></section></div>
          <div class="col"><section class="panel" id="surl"></section><section class="panel" id="simg"></section><section class="panel" id="sdata"></section></div>
        </div>
      </div><dialog class="dlg" id="cardlg"></dialog>`;
    this._built = true;
    // nur bei geändertem HTML neu schreiben – sonst springt iOS (Companion-App) beim Scrollen alle paar Sekunden nach oben (#20)
    for (const id of ["live", "mgmt", "hist", "pweek", "pmorrow", "pana", "pmisch", "kper", "kgel", "klist", "kauf", "kcmp"]) this._guardHtml(this.shadowRoot.getElementById(id));
    this._showPage();
    requestAnimationFrame(() => { this._fit(); this._render_trips(); });
  }

  /* innerHTML eines Abschnitts: identisches HTML nicht erneut schreiben (DOM, Scroll-Position und Fokus bleiben) */
  _guardHtml(el) {
    if (!el || el._guardHtml) return;
    el._guardHtml = true;
    const d = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
    Object.defineProperty(el, "innerHTML", {
      configurable: true,
      get() { return d.get.call(this); },
      set(v) {
        const s = String(v);
        if (s !== "" && this._htmlG === s && this.firstChild) return;
        this._htmlG = s;
        d.set.call(this, s);
      },
    });
  }

  _update(force = false) {
    if (!this._hass || !this._built) return;
    const c = this._config.car, E = this._eva();
    const ids = [c.soc, c.range, c.status, c.cable, c.limit, c.mode, c.always, c.trips, c.manual_mode, this._config.energy.car_power,
      ...Object.values(c.evcc || {}).flat(), ...this._phaseIds(), ...Object.values(E)].filter((x) => typeof x === "string" && x);
    const tc = this._st(E.trip_count)?.state;
    if (tc != null && this._tripCount != null && tc !== this._tripCount) this._loadTrips(true);   // neue Fahrt erfasst
    this._tripCount = tc;
    const sig = ids.map((id) => { const s = this._st(id); return s ? s.state + s.last_updated : "-"; }).join("|") + (this._carHist?.t || "") + (this._evaTrips?.t || "") + Math.floor(Date.now() / 60000);
    if (!force && sig === this._sigCar) return;
    this._sigCar = sig;
    if (this._menu) return;   // Auswahlmenü offen: nicht neu zeichnen
    const aw = this.shadowRoot.getElementById("apiwarn");
    if (aw) { aw.hidden = !this._apiWarn; aw.textContent = this._apiWarn || ""; }
    this._render_car();
    this._render_live();
    this._render_mgmt();
    this._render_trips();
    this._render_hist();
    this._render_lease();
    this._render_usage();
    if (this._subPage() === "prof") this._render_prof();
    if (this._subPage() === "set") this._render_set();
    if (this._subPage() === "cost") this._render_cost();
    if (this._dlg === "ana") this._renderAnaDlg();
    if (this._dlg === "pend") this._renderPend();
  }

  /* evcc setzt die Sitzungswerte nach dem Laden auf 0 → letzte echte Sitzung aus dem Verlauf holen */
  async _loadLastSession() {
    const ev = this._config.car.evcc || {}, eid = ev.session_energy;
    if (eid && !this._real(eid)) return this._lastSessFromEva();
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
      if (this._evaEntryId()) {   // Start-/End-SoC kennt nur das evcc-Ladelogbuch: passende Sitzung (Ende ± 2 h) suchen
        const m = (await this._evccSessions()).filter((x) => x.finished && Math.abs(x.te - end) < 2 * 3600000).sort((a, b) => Math.abs(a.te - end) - Math.abs(b.te - end))[0];
        if (m) Object.assign(this._lastSess, { s0: m.s0, s1: m.s1, sessDur: m.dur });
      }
    } catch (e) { this._lastSess = { err: true }; }
    this._log("letzte Ladung", this._lastSess);
    this._update(true);
  }

  async _lastSessFromEva() {
    const ev = this._config.car.evcc || {};
    if (!this._evaEntryId() || !this._hass?.callWS) return;
    try {
      const x = (await this._evccSessions(true)).filter((s) => s.finished).sort((a, b) => b.te - a.te)[0];
      if (!x) { this._lastSess = { none: true }; return this._update(true); }
      const vals = {};
      if (ev.session_energy) vals[ev.session_energy] = x.kwh;
      if (ev.session_solar) vals[ev.session_solar] = x.pv;
      if (ev.session_price) vals[ev.session_price] = x.price;
      if (ev.duration) vals[ev.duration] = x.dur;
      this._lastSess = { end: x.te, vals, src: "evcc", kwh: x.kwh, durMin: x.dur ?? (x.te > x.ts ? (x.te - x.ts) / 60000 : null), s0: x.s0, s1: x.s1 };
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
    if (this._evaPanel?.config_entry_id) return this._evaPanel.config_entry_id;
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
    const veh = this._evccVehicle();
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
        dur: x.dauer_min ?? null, s0: x.soc_start ?? null, s1: x.soc_end ?? null, who: x.anbieter || "Fremdladung", ac: x.ac_dc || x.typ || "", raw: x });
    }
    out.list.sort((a, b) => b.ts - a.ts);
    if (home?.error && ext?.error) out.err = "Abruf bei ev_assistant fehlgeschlagen";
    this._charges = out;
    this._renderCharges();
    if (this._subPage() === "cost") this._render_cost();
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
    const rows = list.slice(0, this._dlgN).map((x) => {
      const dt = new Date(x.ts), m = `${MON_LONG[dt.getMonth()]} ${dt.getFullYear()}`;
      const mh = m !== lastM ? `<div class="chm">${m}</div>` : ""; lastM = m;
      const dur = x.dur == null ? "" : x.dur >= 60 ? `${Math.floor(x.dur / 60)}:${pad(Math.round(x.dur % 60))} h` : `${Math.round(x.dur)} min`;
      const per = x.per != null ? x.per : x.cost != null && x.kwh > 0.05 ? x.cost / x.kwh : null;
      const pv = x.pv != null ? Math.max(0, Math.min(100, x.pv)) : null;
      const avgP = x.kwh != null && x.dur > 1 ? x.kwh / (x.dur / 60) : null, soc = x.s0 != null && x.s1 != null ? `${Math.round(x.s0)} → ${Math.round(x.s1)} %` : null;
      const ed = x.type === "ext" && x.raw?.erfasst_ts != null;
      return `${mh}<div class="chr ${x.type}${ed ? " ted" : ""}"${ed ? ` data-act="set" data-k="ch-edit" data-id="${esc(x.raw.erfasst_ts)}" title="Fremdladung bearbeiten"` : ""}>
        <span class="chi">${icon(x.type === "home" ? "mdi:home-lightning-bolt" : "mdi:ev-station")}</span>
        <span class="chd"><b>${WD[dt.getDay()]} ${dt.getDate()}. ${MON[dt.getMonth()]}</b><small>${pad(dt.getHours())}:${pad(dt.getMinutes())} Uhr${dur ? ` · ${dur}` : ""}${x.type === "ext" ? ` · ${esc(x.who)}` : ""}</small>${soc || avgP != null ? `<small class="chsm">${[soc, avgP != null && `Ø ${de(avgP, 1)} kW`].filter(Boolean).join(" · ")}</small>` : ""}</span>
        <span class="chpv">${pv != null ? `<i class="pvbar"><i style="width:${pv}%"></i></i><small>${Math.round(pv)} % PV</small>` : ""}</span>
        <span class="chs"><b>${soc || "–"}</b><small>${avgP != null ? `Ø ${de(avgP, 1)} kW` : ""}</small></span>
        <span class="chk"><b>${x.kwh == null ? "–" : de(x.kwh, 1)}</b><small>kWh</small></span>
        <span class="chc"><b>${x.cost == null ? "–" : de(x.cost, 2) + " €"}</b><small>${per != null ? `${de(per * 100, 1)} ct/kWh` : ""}</small></span>
      </div>`;
    }).join("");
    const body = !C ? `<div class="empty">Lädt …</div>` : C.err && !all.length ? `<div class="empty">${esc(C.err)}</div>`
      : !list.length ? `<div class="empty">Keine Ladungen</div>` : `<div class="chlist">${rows}</div>${this._moreRow(Math.min(this._dlgN, list.length), list.length)}`;
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
    if (/\b(pin|pvminsel|mptgt|mbufsel)\b/.test(this.shadowRoot.activeElement?.className || "")) return;   // während der Eingabe nicht neu zeichnen
    const c = this._config.car, ev = c.evcc || {}, E = this._eva();
    const step = (lbl, ic, cfgId, unit) => {
      const id = this._real(cfgId), st = this._st(id); if (!st) return "";   // nur eine echte Entität lässt sich einstellen
      const a = st.attributes, pend = this._pendingNum?.[id], v = pend != null ? pend : parseFloat(st.state), u = unit ?? a.unit_of_measurement ?? "";
      return `<div class="mstep"><span class="msl">${icon(ic)}${lbl}</span>
        <div class="tgt"><button class="tb" data-act="mnum" data-entity="${esc(id)}" data-d="-1" aria-label="weniger">−</button>
        <span class="tv">${isNaN(v) ? "–" : de(v, (a.step || 1) < 1 ? 1 : 0)}<small> ${esc(u)}</small></span>
        <button class="tb" data-act="mnum" data-entity="${esc(id)}" data-d="1" aria-label="mehr">+</button></div></div>`;
    };

    // Vorgabe (eigener Helfer)
    const manual = this._st(c.manual_mode), auto = manual && /^auto/i.test(manual.state);

    // evcc-Modus als Kacheln, „Immer laden“ als Auswahl in der Smart-Kachel
    const mst = this._st(c.mode), ast = this._st(c.always);
    // Modus-Zeile: [Vorgabe ▼] [Aus] [Smart ▼] [Schnell]
    const evaCtl = !!(this._evaEntryId() && this._st(E.evcc_mode_control));
    if (evaCtl) return this._render_mgmt_eva(el);   // Lademodus immer über ev_assistant – auch wenn car.mode/manual_mode (alte Konfiguration) gesetzt sind
    const evaMode = !mst && this._evaEntryId() ? this._evaModeState() : null;
    const modeTiles = (() => {
      if (evaMode) {   // ohne eigene Auswahl-Entitäten: evcc-Modus über ev_assistant schalten
        // Auto blau, wenn ev_assistant steuert; zusätzlich leuchtet die Kachel des gerade wirksamen evcc-Modus
        const act = evaMode.cur !== "auto" ? evaMode.cur : evaMode.evcc;   // pv / minpv / now / off
        const smartOn = act === "pv" || act === "minpv" || act === "once", ac = this._evaAlways(act);
        const so = EVA_SMART_OPTS.find((o) => o.ac === ac) || EVA_SMART_OPTS[0];
        const ico = (o) => (o.glyph ? `<span class="glyph">${o.glyph}</span>` : icon(o.icon));
        const tile = (m, sel, act2, inner, extra = "") => `<button class="mmode ${sel ? "sel" : ""}" style="--cc:${m.color}" data-act="${act2}" ${extra} title="${esc(m.title)}"><span class="mmh">${inner}</span></button>`;
        return `<div class="mmodes">
          ${tile(EVA_AUTO, evaMode.cur === "auto", "evamode", `${icon(EVA_AUTO.icon)}<b>Auto</b>`, `data-v="auto"`)}
          ${tile(EVA_SMART, smartOn, "evasmartmenu", `${ico(so)}<b>Smart</b>${smartOn ? `<small class="msub">${so.sub}</small>` : ""}${icon("mdi:chevron-down", "mchv")}`)}
          ${tile(EVA_NOW, act === "now", "evamode", `${icon(EVA_NOW.icon)}<b>Schnell</b>`, `data-v="now"`)}</div>`;
      }
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
    const plan = this._planSt(), pa = plan?.attributes || {}, mc = this._st(E.evcc_mode_control), ma = mc?.attributes || {};
    const pi = this._planInfo(plan), hasPlan = !!pi;
    const fmtD = (d) => `${WD[d.getDay()]} ${d.getDate()}. ${MON[d.getMonth()]}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const entry = this._evaEntryId();
    if (hasPlan && this._planReq) { clearTimeout(this._planReq.timer); this._planReq = null; }   // Plan ist angekommen
    const pr = this._planReq;
    let planHtml = "";
    if (entry || plan) {
      if (hasPlan) {
        const ps = pa.projected_start ? new Date(pa.projected_start) : null, pe = pa.projected_end ? new Date(pa.projected_end) : null;
        const ttl = pi.date ? `${pi.soc != null ? `${Math.round(pi.soc)} %` : "Ladeplan"} bis ${fmtD(pi.date)}` : esc(plan.state);
        planHtml = `<div class="mplan act">
          <div class="mph">${icon("mdi:calendar-clock")}<span><b>${ttl}</b>
            ${ps && !isNaN(ps) ? `<small>Laden voraussichtlich ${pad(ps.getHours())}:${pad(ps.getMinutes())}${pe && !isNaN(pe) ? `–${pad(pe.getHours())}:${pad(pe.getMinutes())}` : ""} Uhr</small>` : ""}</span>
            <button class="qbtn ghost" data-act="mplanclear">${icon("mdi:delete-outline")}Löschen</button></div>
          ${pa.erwartung ? `<div class="mpe">${icon("mdi:information-outline")}${esc(pa.erwartung)}</div>` : ""}</div>`;
      } else {
        const def = new Date(); def.setDate(def.getDate() + 1); def.setHours(7, 0, 0, 0);
        const val = this._planTime || `${def.getFullYear()}-${pad(def.getMonth() + 1)}-${pad(def.getDate())}T07:00`;
        const soc = this._planSoc ?? 80;
        planHtml = `<div class="mplan">
          <div class="mph">${icon("mdi:calendar-plus")}<span><b>Ladeplan anlegen</b></span></div>
          <div class="mpf">
            <label>Ziel<div class="tgt"><button class="tb" data-act="mplansoc" data-d="-5">−</button><span class="tv">${soc}<small> %</small></span><button class="tb" data-act="mplansoc" data-d="5">+</button></div></label>
            <label>bis<input class="pin" type="datetime-local" value="${esc(val)}" data-act="none"></label>
            <button class="qbtn" data-act="mplanset"${entry && !pr?.busy ? "" : " disabled"}>${icon(pr?.busy ? "mdi:timer-sand" : "mdi:check")}${pr?.busy ? "Wird gesetzt …" : "Plan setzen"}</button>
          </div>
          ${pr?.err ? `<div class="mpe err">${icon("mdi:alert-circle-outline")}${esc(pr.err)}</div>` : pr?.info ? `<div class="mpe">${icon("mdi:information-outline")}${esc(pr.info)}</div>` : ""}</div>`;
      }
    }
    const rows = this._renderLimitRow(c, ev, E, ma, mc);

    const rec = this._st(E.charge_before_pv_recommended);
    const isAuto = evaMode ? evaMode.cur === "auto" : auto;
    const evccNow = evaMode?.evcc ? `<small>evcc: ${esc(EVA_MODES.find((m) => m.v === evaMode.evcc)?.label || (evaMode.evcc === "off" ? "Aus" : evaMode.evcc))}</small>` : "";
    const ladestrom = step("Ladestrom", "mdi:speedometer", c.limit, this._real(c.limit)?.startsWith("select.") ? "A" : undefined);
    el.innerHTML = this._hd("Lademanagement", manual || evaMode ? (isAuto ? `<span class="mauto">${icon("mdi:robot-outline")}Automatik</span>` : `<span class="mman">${icon("mdi:hand-back-right-outline")}Manuell</span>`) : "") + `
      ${modeTiles ? `<div class="mgrp"><span class="mgl">${manual || evaMode ? "Lademodus" : "evcc-Modus"} ${evccNow}</span>${modeTiles}</div>` : ""}
      ${ladestrom ? `<div class="msteps">${ladestrom}</div>` : ""}
      ${rows.top}
      ${planHtml || rows.bottom ? `<div class="mgrp"><span class="mgl">ev_assistant</span>${planHtml}${rows.bottom}</div>` : ""}
      ${rec?.state === "on" ? `<div class="lrows"><button class="lrow warn" data-act="more" data-entity="${esc(E.charge_before_pv_recommended)}">${icon("mdi:weather-cloudy-alert")}<span>Empfehlung</span><b>Laden vor PV sinnvoll</b></button></div>` : ""}`;
  }

  /* Lademanagement mit ev_assistant, zwei Bereiche:
     evcc         – was evcc gerade tut (nur Anzeige): Lademodus, Ladeziel, Ladeplan
     ev_assistant – Steuerung: Auto / manueller Modus, Ladeziel, Vollladung, Automatik pausieren, Ladeplan setzen */
  _render_mgmt_eva(el) {
    const E = this._eva(), L = this._live(), mc = this._st(E.evcc_mode_control), ma = mc?.attributes || {};
    const ms = this._evaModeState(), entry = this._evaEntryId();
    const acSel = this._evccEnt("alwayscharge");
    const acState = this._st(acSel)?.state;

    // --- evcc: Ist-Zustand ---
    const evM = L.mode, evAc = evM === "minpv" ? (acState === "once" ? "once" : "on") : evM === "pv" ? "off" : null;
    const so = EVA_SMART_OPTS.find((o) => o.ac === evAc);
    const ico = (o) => (o?.glyph ? `<span class="glyph">${o.glyph}</span>` : icon(o?.icon || "mdi:help"));
    const mInfo = evM === "now" ? { t: "Schnell", i: icon(EVA_NOW.icon), c: EVA_NOW.color }
      : evM === "off" ? { t: "Aus", i: icon("mdi:power-off"), c: "#8b91a1" }
      : so ? { t: `Smart · ${so.label === "aus" ? "PV" : so.label}`, i: so.glyph ? "" : ico(so), c: EVA_SMART.color } : { t: "–", i: icon("mdi:help"), c: "var(--muted)" };
    const plan = this._planSt(), pi = this._planInfo(plan);
    // Kopf: aktueller evcc-Lademodus oben rechts
    const head = `<div class="hd"><span class="ttl">Lademanagement</span>
      <span class="lbl mnow" style="--cc:${mInfo.c}" title="Lademodus in evcc">${mInfo.i}${esc(mInfo.t)}</span></div>`;

    // --- ev_assistant: Lademodus (Auto oder manuell) ---
    const o = this._evaSel && Date.now() - this._evaSel.t < 20000 ? this._evaSel.v : null;
    const po = this._opt?.pause, paused = po && Date.now() - po.t < 30000 ? po.v : !!ma.pausiert;
    // „Auto“ nur, solange ev_assistant wirklich steuert (nicht pausiert, kein manueller Modus) – sonst leuchtet
    // die Kachel des Modus, auf dem evcc gerade steht
    const evSel = evM === "off" ? "off" : evM === "now" ? "now" : evM === "minpv" ? (evAc === "once" ? "once" : "minpv") : evM === "pv" ? "pv" : ms.cur !== "auto" ? ms.cur : null;
    const sel = o || (ms.cur === "auto" && !paused ? "auto" : evSel);
    const tile = (m, on, act, inner, extra = "") => `<button class="mmode ${on ? "sel" : ""}" style="--cc:${m.color}" data-act="${act}" ${extra} title="${esc(m.title || "")}"><span class="mmh">${inner}</span></button>`;
    // zweite Kachel: alle manuellen Modi als Auswahl (Aus, Smart · aus/1x/immer, Schnell)
    const man = EVA_MANUAL.find((m) => m.v === sel);
    this._evaSelCur = man?.v || null;
    // oben: Automatik · Manuell · Vollladung
    const r = this._renderLimitRow(this._config.car, this._config.car.evcc || {}, E, ma, mc);
    const manBtn = `<button class="mbtn man ${man ? "on" : ""}" style="--cc:${(man || {}).color || "var(--muted)"}" data-act="evamanmenu" title="Lademodus manuell wählen (Aus, Smart, Schnell)">
        ${man ? (man.glyph ? `<span class="glyph">${man.glyph}</span>` : icon(man.icon)) : icon("mdi:hand-back-right-outline")}<div class="mtx"><b>${man ? esc(man.short) : "Manuell"}</b><span>${man ? "manuell" : "Lademodus"}</span></div>${icon("mdi:chevron-down", "mchv")}</button>`;
    const modes = `<div class="mbottom m3">${r.pause}${manBtn}${r.bal}</div>`;

    // unten: Ladeziel · PV-Anteil · Puffer
    const ctl = `<div class="mbottom m3">${r.lim}${this._pvMinTile(ma, "mbtn")}${this._bufTile()}</div>`;

    // --- ev_assistant: Ladeplan – aktiver Plan oder Formular (Ziel als SoC oder km, Zielzeit) ---
    const pr = this._planReq;
    if (pi?.date && pr?.target && Math.abs(pi.date.getTime() - pr.target) < 90000) { clearTimeout(pr.timer); this._planReq = null; this._planEdit = false; }
    const def = new Date(); def.setDate(def.getDate() + 1); def.setHours(7, 0, 0, 0);
    const dv = pi?.date && !isNaN(pi.date) ? pi.date : def;
    const val = this._planTime || `${dv.getFullYear()}-${pad(dv.getMonth() + 1)}-${pad(dv.getDate())}T${pad(dv.getHours())}:${pad(dv.getMinutes())}`;
    const soc = this._planSoc ?? (pi?.soc != null ? Math.round(pi.soc / 5) * 5 : 80);
    // Ziel wahlweise als SoC (direkt an evcc) oder als Reichweite in km (ev_assistant rechnet mit dem Verbrauch in SoC um)
    const kmOk = !!this._hass?.services?.ev_assistant?.set_evcc_charge_plan_range_km, unit = kmOk ? this._planUnitGet() : "soc";
    const kmPerPct = this._kmPerPct(), km = this._planKm ?? (kmPerPct ? Math.round((soc * kmPerPct) / 10) * 10 : 200);
    const reqMsg = pr?.err ? `<div class="mpe err">${icon("mdi:alert-circle-outline")}${esc(pr.err)}</div>` : pr?.info ? `<div class="mpe">${icon("mdi:information-outline")}${esc(pr.info)}</div>` : "";
    let planBox;
    if (pi && !this._planEdit && !pr?.busy) {
      const pa = plan?.attributes || {}, ps = pa.projected_start ? new Date(pa.projected_start) : null, pe = pa.projected_end ? new Date(pa.projected_end) : null;
      const hm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
      const when = pi.date ? `${pi.date.toDateString() === new Date().toDateString() ? "heute" : pi.date.toDateString() === new Date(Date.now() + 86400000).toDateString() ? "morgen" : `${WD[pi.date.getDay()]} ${pi.date.getDate()}.${pi.date.getMonth() + 1}.`} ${hm(pi.date)} Uhr` : esc(plan.state);
      const kmT = pi.soc != null && kmPerPct ? ` · ≈ ${de(Math.round((pi.soc * kmPerPct) / 10) * 10, 0)} km` : "";
      planBox = `<div class="mplan act"><div class="mpa">${icon("mdi:calendar-clock")}
          <span class="mpat"><small>Ladeplan${pa.aktiv ? ` <em class="mrun">läuft</em>` : ""}</small><b>${pi.soc != null ? `${Math.round(pi.soc)} %` : "Ziel"} bis ${when}</b>
            <small>${ps && !isNaN(ps) ? `Laden ${hm(ps)}${pe && !isNaN(pe) ? `–${hm(pe)}` : ""} Uhr` : ""}${kmT}</small></span>
          <span class="mpb"><button class="qbtn ghost" data-act="mplanedit">${icon("mdi:pencil")}Ändern</button><button class="qbtn ghost" data-act="mplanclear" title="Ladeplan löschen" aria-label="Ladeplan löschen">${icon("mdi:delete-outline")}</button></span></div>
        ${pa.erwartung ? `<div class="mpe">${icon("mdi:information-outline")}${esc(pa.erwartung)}</div>` : ""}${reqMsg}</div>`;
    } else {
      let opts = "";
      if (unit === "km") {
        const max = kmPerPct ? Math.max(100, Math.ceil((kmPerPct * 100) / 10) * 10) : 600, sel = Math.min(max, Math.round(km / 10) * 10);
        for (let v = 10; v <= max; v += 10) opts += `<option value="${v}"${v === sel ? " selected" : ""}>${v} km${kmPerPct ? ` (≈ ${Math.min(100, Math.round(v / kmPerPct))} %)` : ""}</option>`;
      } else for (let v = 10; v <= 100; v += 5) opts += `<option value="${v}"${v === soc ? " selected" : ""}>${v} %${kmPerPct ? ` (≈ ${de(Math.round((v * kmPerPct) / 10) * 10, 0)} km)` : ""}</option>`;
      const usw = kmOk ? `<span class="hsegs mpu"><button class="hseg ${unit === "soc" ? "sel" : ""}" data-act="planunit" data-v="soc" title="Ziel-SoC direkt an evcc">%</button><button class="hseg ${unit === "km" ? "sel" : ""}" data-act="planunit" data-v="km" title="Ziel-Reichweite – ev_assistant rechnet in SoC um">km</button></span>` : "";
      const setBtn = `<button class="qbtn" data-act="mplanset"${entry && !pr?.busy ? "" : " disabled"}>${icon(pr?.busy ? "mdi:timer-sand" : "mdi:check")}${pr?.busy ? "Wird gesetzt …" : "Plan setzen"}</button>`;
      planBox = `<div class="mplan"><div class="mphd mph3"><span class="mpl">${icon("mdi:calendar-plus")}${pi ? "Ändern" : "Ladeplan"}</span><span class="mpc">${setBtn}</span><span class="mpr">${usw}</span></div>
        <div class="mpg"><label><span>Ziel</span><select class="msel mptgt" data-u="${unit}" aria-label="Ziel">${opts}</select></label>
          <label><span>Bis</span><input class="pin" type="datetime-local" value="${esc(val)}" data-act="none" aria-label="Zielzeit"></label></div>
        ${pi ? `<div class="mpb end"><button class="qbtn ghost" data-act="mplancancel">Abbrechen</button></div>` : ""}
        ${reqMsg}</div>`;
    }
    const planForm = planBox;

    const rec = this._st(E.charge_before_pv_recommended);
    const err = this._mgmtErr ? `<div class="mpe err merr">${icon("mdi:alert-circle-outline")}<span>ev_assistant: ${esc(this._mgmtErr.msg)}</span></div>` : "";
    el.innerHTML = head + err + `
      <div class="mgrp">${modes}${ctl}${planForm}</div>
      ${rec?.state === "on" ? `<div class="lrows"><button class="lrow warn" data-act="more" data-entity="${esc(E.charge_before_pv_recommended)}">${icon("mdi:weather-cloudy-alert")}<span>Empfehlung</span><b>Laden vor PV sinnvoll</b></button></div>` : ""}`;
  }

  /* Mindest-PV-Anteil für den Netz-Zuschuss (ev_assistant ab 0.99.57: Dienst set_evcc_realtime_override_min_solar_share,
     Attribut pv_override_min_solar_share_pct). Unter der Mindestladeleistung der Wallbox wird nur dann Netzstrom
     dazugenommen, wenn mindestens dieser Anteil aus PV kommt. „aus“ = jeder PV-Überschuss wird mit Netzstrom ergänzt. */
  _pvMinCur(ma) {
    const has = Object.prototype.hasOwnProperty.call(ma, "pv_override_min_solar_share_pct"), raw = ma.pv_override_min_solar_share_pct;
    const real = typeof raw === "number" ? raw : null, o = this._pvMinSet;
    if (o && (Date.now() - o.t > 90000 || (has && real === o.v))) this._pvMinSet = null;
    return { has, v: this._pvMinSet ? this._pvMinSet.v : real };
  }
  _pvMinTile(ma, cls) {
    if (!this._hass?.services?.ev_assistant?.set_evcc_realtime_override_min_solar_share || !this._evaEntryId()) return "";
    const { v } = this._pvMinCur(ma), rv = v == null ? null : Math.round(v / 5) * 5;
    let opts = `<option value=""${v == null ? " selected" : ""}>aus</option>`;
    for (let x = 0; x <= 100; x += 5) opts += `<option value="${x}"${rv === x ? " selected" : ""}>${x} %</option>`;
    return `<label class="mbtn mpvmin mdrop${v != null ? " on" : ""}" title="Netzstrom nur dazunehmen, wenn mindestens dieser Anteil aus PV kommt">
      ${icon("mdi:solar-power-variant")}<div class="mtx"><b>${v == null ? "aus" : `ab ${de(v, 0)} %`}</b><span>PV-Anteil</span></div>${icon("mdi:chevron-down", "mchv")}
      <select class="pvminsel" aria-label="Laden ab PV-Anteil">${opts}</select></label>`;
  }
  /* Puffer für den Bedarf morgen (ev_assistant: set_usage_profile_buffer_km, 0–300 km) */
  _bufInfo() {
    const na = this._ea("usage_profile_tomorrow")?.attributes || {}, km = na.puffer_art === "km" && !isNaN(parseFloat(na.puffer_km));
    if (this._bufSet && (Date.now() - this._bufSet.t > 90000 || (km && parseFloat(na.puffer_km) === this._bufSet.v))) this._bufSet = null;
    return { cur: this._bufSet ? this._bufSet.v : km ? parseFloat(na.puffer_km) : null, pct: parseFloat(na.puffer_prozent), kwh: parseFloat(na.puffer_kwh), km };
  }
  _bufTile() {
    if (!this._hass?.services?.ev_assistant?.set_usage_profile_buffer_km || !this._evaEntryId()) return "";
    const B = this._bufInfo();
    let opts = B.cur == null ? `<option value="" selected>${isNaN(B.pct) ? "–" : `${de(B.pct, 0)} %`}</option>` : "";
    for (let v = 0; v <= 300; v += 5) opts += `<option value="${v}"${B.cur != null && Math.round(B.cur / 5) * 5 === v ? " selected" : ""}>${v} km</option>`;
    return `<label class="mbtn mbuf mdrop" title="Sicherheitspuffer auf den Bedarf für morgen">
      ${icon("mdi:shield-car")}<div class="mtx"><b>${B.cur != null ? `${de(B.cur, 0)} km` : isNaN(B.pct) ? "–" : `${de(B.pct, 0)} %`}</b><span>Puffer</span></div>${icon("mdi:chevron-down", "mchv")}
      <select class="mbufsel" aria-label="Puffer in km">${opts}</select></label>`;
  }
  _setBuffer(v) {
    const id = this._evaEntryId(); if (!id) return;
    this._bufSet = { v, t: Date.now() };
    Promise.resolve(this._hass.callService("ev_assistant", "set_usage_profile_buffer_km", { config_entry_id: id, buffer_km: v }))
      .catch((x) => { this._bufSet = null; this._render_mgmt(); this._render_morrow(); this._mgmtFail?.(x); });
    this._render_mgmt(); if (this._subPage() === "prof") this._render_morrow();
  }
  // dieselbe Einstellung als Auswahl in einer Kennzahl-Kachel (Netz-Zuschuss auf „Profil & Analyse“)
  _pvMinSel(ma) {
    if (!this._hass?.services?.ev_assistant?.set_evcc_realtime_override_min_solar_share || !this._evaEntryId()) return "";
    const { v } = this._pvMinCur(ma), rv = v == null ? null : Math.round(v / 5) * 5;
    let opts = `<option value=""${v == null ? " selected" : ""}>aus</option>`;
    for (let x = 0; x <= 100; x += 5) opts += `<option value="${x}"${rv === x ? " selected" : ""}>${x} %</option>`;
    return `<div class="pst pbuf"><span>Laden ab PV</span><select class="pbufsel pvminsel" aria-label="Laden ab PV-Anteil">${opts}</select></div>`;
  }
  _setPvMin(val) {
    const v = val === "" ? null : Number(val);
    this._pvMinSet = { v, t: Date.now() };
    this._evaCall("set_evcc_realtime_override_min_solar_share", v == null ? {} : { min_solar_share: v })
      .catch((x) => { this._pvMinSet = null; this._mgmtFail(x); });
    this._render_mgmt(); if (this._subPage() === "prof") this._render_misch();
  }

  /* Ladeplan-Sensor ohne Überbrückung: „unbekannt“ heißt hier „kein Plan“ (z. B. direkt nach dem Löschen) */
  _planSt() {
    const id = this._eva().evcc_charge_plan, s = id ? this._hass?.states[id] : null, c = this._planCleared;
    if (c && (Date.now() - c.t > 60000 || (s && s.state !== c.was))) this._planCleared = null;
    return this._planCleared ? undefined : s || undefined;
  }
  _planUnitGet() {
    if (this._planUnit) return this._planUnit;
    let v = null; try { v = localStorage.getItem("mg-car-plan-unit"); } catch (x) {}
    return (this._planUnit = v === "km" ? "km" : "soc");
  }
  // km je Prozent SoC aus Reichweite und Ladestand (für die Anzeige „≈ x %“ beim km-Ziel)
  _kmPerPct() {
    const c = this._config.car, soc = this._num(c.soc), E = this._eva();
    const r = parseFloat(this._st(E.range_estimate)?.state) || this._num(c.range);
    return soc > 5 && r > 0 ? r / soc : null;
  }

  /* Hinweis, wenn der Aufruf erfolgreich war, der Plan-Sensor den Plan aber (noch) nicht zeigt. Ältere ev_assistant-
     Versionen (vor 0.99.35) melden ein nicht gefundenes evcc-Fahrzeug nicht als Fehler – darauf nur als Möglichkeit hinweisen */
  _planSentText() {
    const name = this._config.car.evcc_vehicle || this._evaPanel?.evcc_vehicle_name;
    return `Plan an evcc gesendet, ev_assistant zeigt ihn noch nicht an. Bei ev_assistant vor 0.99.35 kann das auch heißen, dass das evcc-Fahrzeug${name ? ` „${name}“` : ""} nicht gefunden wurde.`;
  }

  /* Ladeplan aus der ev_assistant-Entität lesen: Zeitstempel als Zustand (ISO), in Attributen oder als
     Text („80 % bis 10.10.2026 07:00“). null = kein Plan. */
  _planInfo(plan) {
    const s = String(plan?.state ?? "").trim(), a = plan?.attributes || {};
    if (!plan || OFFLINE_HD.includes(s.toLowerCase()) || /^(aus|off|kein|inaktiv|inactive|false|nicht|0$|[-–—]$)/i.test(s)) return null;
    const toD = (v) => {
      if (v == null || v === "") return null;
      if (typeof v === "number" || /^\d{9,13}$/.test(String(v))) { const n = Number(v); return new Date(n < 1e12 ? n * 1000 : n); }
      const m = String(v).match(/(\d{1,2})\.(\d{1,2})\.(\d{4})(?:,?\s+(\d{1,2}):(\d{2}))?/);
      if (m) return new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0));
      return /^\d{4}-\d{2}-\d{2}/.test(String(v)) ? new Date(v) : null;
    };
    let date = null;
    for (const v of [a.target_time, a.zielzeit, a.plan_time, a.time, s]) { const d = toD(v); if (d && !isNaN(d)) { date = d; break; } }
    const sm = s.match(/(\d{1,3})\s*%/);
    const soc = a.target_soc ?? a.ziel_soc ?? a.soc ?? (sm ? Number(sm[1]) : null);
    if (!date && !/\d/.test(s)) return null;   // Text ohne Zeit/Ziel: kein Plan
    return { date, soc: soc != null && !isNaN(Number(soc)) ? Number(soc) : null };
  }

  /* Manueller Lademodus: Modus an evcc und Automatik pausieren, damit ev_assistant ihn nicht überschreibt */
  _evaManual(mode) {
    return this._evaCall("set_evcc_manual_mode", { mode }).then(() => this._evaCall("set_evcc_mode_control_pause", { paused: true }));
  }
  /* Zurück auf Auto: manuellen Modus beenden und Automatik fortsetzen */
  _evaAuto() {
    return Promise.all([this._evaCall("clear_evcc_manual_mode", {}), this._evaCall("set_evcc_mode_control_pause", { paused: false })]);
  }

  /* Fehler eines ev_assistant-Aufrufs im Lademanagement anzeigen (statt nur in der Konsole) und die
     vorab angezeigte Auswahl zurücknehmen */
  _mgmtFail(x) {
    const msg = x?.message || x?.error?.message || (typeof x === "string" ? x : "unbekannter Fehler");
    console.warn("mg-car:", x);
    this._mgmtErr = { msg, t: Date.now() };
    this._evaSel = this._evaModeOpt = this._evaSmartOpt = null; this._balOptimistic = null;
    if (this._opt) { delete this._opt.socmax; delete this._opt.pause; }
    clearTimeout(this._mgmtErrT); this._mgmtErrT = setTimeout(() => { this._mgmtErr = null; this._render_mgmt(); }, 15000);
    this._render_mgmt();
  }

  /* Zeilen im Lademanagement:
     oben  [Ladeziel (ev_assistant, einstellbar)] [Ziel, das ev_assistant gerade festlegt]
           – ohne aktive ev_assistant-Steuerung wie bisher das Ladeziel-Select der evcc-Integration
     unten [Vollladung] [Automatik pausieren] */
  _renderLimitRow(c, ev, E, ma, mc) {
    const entry = this._evaEntryId(), eva = !!(entry && ma.aktiv);
    const opt = (k, real) => {   // optimistische Anzeige nach dem Umschalten, bis ev_assistant den neuen Wert meldet
      const o = this._opt?.[k];
      if (!o || Date.now() - o.t > 30000 || o.v === real) { if (this._opt) delete this._opt[k]; return real; }
      return o.v;
    };
    let top = "", limBtn = "";
    if (eva) {
      const max = opt("socmax", ma.target_soc_max != null ? Number(ma.target_soc_max) : 80), cur = ma.target_soc != null ? Number(ma.target_soc) : null;
      const why = ma.balancing_aktiv ? "Vollladung" : ma.ueberschuss_ziel_erweitert_aktiv ? "PV-Überschuss" : "";
      limBtn = `<button class="mbtn lim" data-act="evalimmenu" title="Ladeziel in ev_assistant (höchstens so weit lädt die Automatik)">
          ${icon("mdi:battery-check-outline")}<div class="mtx"><b>${de(max, 0)} %</b><span>Ladeziel</span></div>${icon("mdi:chevron-down", "mchv")}</button>`;
      top = `<div class="mbottom">${limBtn}
        <div class="mbtn ro tnow" title="Ziel, das ev_assistant gerade an evcc gibt (aus Bedarf, PV-Überschuss und Vollladung)">
          ${icon("mdi:target")}<div class="mtx"><b>${cur != null && !isNaN(cur) ? `${de(cur, 0)} %` : "–"}</b><span>Ziel jetzt${why ? ` · ${why}` : ""}</span></div></div></div>`;
    } else if (ev.limit_soc) {
      const limSt = this._st(ev.limit_soc);
      if (!limSt) this._log("limit_soc", ev.limit_soc, "nicht in hass.states gefunden");
      let v = limSt?.state;
      const pick = !!this._real(ev.limit_soc);   // nur eine echte select-/number-Entität ist auswählbar
      // Ladeziel auf Fahrzeug-Ebene (evcc): das Select des Ladepunkts bleibt leer/0 → wirksames Ladeziel aus evcc anzeigen
      const eff = Number(this._live().limit_soc);
      if ((v == null || OFFLINE_HD.includes(v) || !parseFloat(v)) && eff > 0) v = String(eff);
      if (limSt) top = `<div class="mbottom"><button class="mbtn lim ${pick ? "" : "ro"}" ${pick ? `data-act="limmenu" data-entity="${esc(this._real(ev.limit_soc))}"` : `title="Ladeziel aus evcc"`}>
        ${icon("mdi:battery-check-outline")}<div class="mtx"><b>${v != null && !OFFLINE_HD.includes(v) ? esc(String(Math.round(parseFloat(v)) || v).replace(/ ?%$/, "")) + " %" : "–"}</b><span>Ladeziel</span></div>${pick ? icon("mdi:chevron-down", "mchv") : ""}</button></div>`;
    }
    // Vollladung
    if (this._balOptimistic != null && !!ma.balancing_enabled === this._balOptimistic) this._balOptimistic = null;   // bestätigt
    const balOptimistic = this._balOptimistic;
    const balOn = balOptimistic != null ? balOptimistic : !!ma.balancing_enabled;
    // „lädt auf 100 %“ und Blinken nur, wenn die Vollladung aktiv ist UND das Auto gerade wirklich lädt
    const balAkt = !!ma.balancing_aktiv && balOn && this._carState().charging, balF = !!ma.balancing_faellig;
    const nextFull = ma.naechste_vollladung_faellig_ts ? new Date(ma.naechste_vollladung_faellig_ts * (ma.naechste_vollladung_faellig_ts < 1e12 ? 1000 : 1)) : null;
    const balSub = balAkt ? "lädt auf 100 %" : balF ? "fällig" : nextFull && !isNaN(nextFull) ? `nächste ${WD[nextFull.getDay()]} ${nextFull.getDate()}.` : "";
    const btns = [];
    if (entry) btns.push(`<button class="mbtn bal ${balOn ? "on" : ""} ${balAkt ? "act" : ""}" data-act="mbal" data-v="${balOn ? "0" : "1"}">
        ${icon(balAkt ? "mdi:battery-sync" : "mdi:battery-sync-outline")}<div class="mtx"><b>Vollladung</b><span>${balOn ? (balSub || "aktiv") : "aus"}</span></div></button>`);
    // Automatik pausieren (gleiches Aussehen wie Vollladung)
    if (eva) {
      const paused = opt("pause", !!ma.pausiert);
      const run = !paused && this._evaModeState().cur === "auto";
      btns.push(`<button class="mbtn pause ${paused || !run ? "on" : "run"}" data-act="mpause" data-v="${paused ? "0" : "1"}" title="${paused ? "ev_assistant schreibt nichts nach evcc – tippen zum Fortsetzen" : "ev_assistant steuert evcc – tippen zum Pausieren"}">
        ${icon(paused ? "mdi:pause-circle" : run ? "mdi:robot-outline" : "mdi:hand-back-right-outline")}<div class="mtx"><b>Automatik</b><span>${paused ? "pausiert" : this._evaModeState().cur !== "auto" ? "manuell" : "läuft"}</span></div></button>`);
    }
    return { top, bottom: btns.length ? `<div class="mbottom mact">${btns.join("")}</div>` : "", bal: btns[0] || "", pause: btns[1] || "", lim: limBtn };
  }

  /* Ladeziel von ev_assistant (target_soc_max) auswählen */
  _openEvaLimMenu(anchor) {
    const ma = this._st(this._eva().evcc_mode_control)?.attributes || {};
    const cur = this._opt?.socmax?.v ?? (ma.target_soc_max != null ? Number(ma.target_soc_max) : 80);
    const opts = [50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100];
    if (!opts.includes(cur)) opts.push(cur), opts.sort((a, b) => a - b);
    const menu = document.createElement("div"); menu.className = "menu limm";
    menu.innerHTML = opts.map((v) => `<button class="mg-menu-item mi ${v === cur ? "cur" : ""}" data-act="evalimset" data-v="${v}"><span>${v} %</span>${v === cur ? icon("mdi:check", "ck") : ""}</button>`).join("");
    this._openMenuAt(anchor, menu);
  }

  _openLimMenu(anchor) {
    this._closeMenu();
    const id = anchor.dataset.entity, st = this._st(id);
    if (!st) return;
    const a = st.attributes, cur = st.state;
    const opts = a.options || [];
    const menu = document.createElement("div"); menu.className = "menu limm";
    if (opts.length) {
      menu.innerHTML = opts.map((v) => `<button class="mg-menu-item mi ${String(v) === String(cur) ? "cur" : ""}" data-act="limset" data-entity="${esc(id)}" data-v="${esc(v)}"><span>${isNaN(Number(v)) ? esc(v) : Number(v) === 0 ? "–" : `${esc(v)} %`}</span>${String(v) === String(cur) ? icon("mdi:check", "ck") : ""}</button>`).join("");
    } else {
      const stp = Number(a.step) || 5, mn = Number(a.min) || 20, mx = Number(a.max) || 100;
      let numOpts = []; for (let v = mn; v <= mx; v += stp) numOpts.push(v);
      menu.innerHTML = numOpts.map((v) => `<button class="mg-menu-item mi ${v === parseFloat(cur) ? "cur" : ""}" data-act="limset" data-entity="${esc(id)}" data-v="${v}"><span>${v} %</span>${v === parseFloat(cur) ? icon("mdi:check", "ck") : ""}</button>`).join("");
    }
    this._openMenuAt(anchor, menu);
  }

  _evaCall(service, data) {
    const id = this._evaEntryId();
    if (!id) { console.warn("mg-car: ev_assistant config_entry_id nicht gefunden. Trage car.ev_assistant_entry ein."); return Promise.reject(new Error("ev_assistant nicht gefunden")); }
    this._log("ev_assistant →", service, { config_entry_id: id, ...data });
    return Promise.resolve(this._hass.callService("ev_assistant", service, { config_entry_id: id, ...data }));
  }

  _mnum(el) {
    const id = el.dataset.entity, st = this._st(id); if (!st) return;
    const a = st.attributes, stp = Number(a.step) || 1, dom = id.split(".")[0], d = Number(el.dataset.d);
    this._pendingNum = this._pendingNum || {}; this._numT = this._numT || {};
    const cur = this._pendingNum[id] ?? parseFloat(st.state);
    let v;
    if (dom === "select" || dom === "input_select") {   // Auswahlliste (z. B. Ladestrom der evcc-Integration): nächster Wert
      const opts = (a.options || []).map(Number).filter((x) => !isNaN(x)).sort((x, y) => x - y);
      if (!opts.length) return;
      const i = opts.findIndex((x) => x >= cur);
      v = opts[Math.max(0, Math.min(opts.length - 1, (i < 0 ? opts.length - 1 : i) + (opts[i] === cur || i < 0 ? d : d > 0 ? 0 : -1)))];
    } else {
      v = Math.round((cur + d * stp) / stp) * stp;
      if (a.min != null) v = Math.max(Number(a.min), v); if (a.max != null) v = Math.min(Number(a.max), v);
    }
    this._pendingNum[id] = v;
    clearTimeout(this._numT[id]);
    this._numT[id] = setTimeout(() => {
      if (dom === "select" || dom === "input_select") {
        const opt = (a.options || []).find((o) => Number(o) === v);
        if (opt != null) this._hass.callService(dom, "select_option", { entity_id: id, option: opt });
      } else this._hass.callService(dom, "set_value", { entity_id: id, value: v });
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
    // Dauer der letzten Ladung aus dem evcc-Ladelogbuch ist schon in Minuten (die Einheit des Sensors gilt dafür nicht)
    const durMin = !charging && L?.durMin != null ? L.durMin : dur == null ? (!charging && L?.sessDur != null ? L.sessDur : null) : durU === "h" ? dur * 60 : durU === "s" ? dur / 60 : dur;
    const durTxt = durMin == null ? "–" : durMin >= 60 ? `${Math.floor(durMin / 60)}:${pad(Math.round(durMin % 60))} h` : `${Math.round(durMin)} min`;
    const cur = this._st(ev.session_price)?.attributes?.unit_of_measurement || "€";
    const avgP = kwh != null && durMin > 1 ? kwh / (durMin / 60) : null;   // Ø Ladeleistung der (letzten) Sitzung

    // Kopf: Status
    const stTxt = charging ? "Lädt" : plugged ? "Bereit" : "Abgesteckt";
    const stCls = charging ? "on" : plugged ? "ready" : "";

    // links: große Zahl + Zeitangabe
    let kicker = "", when = "", kickEnd = "";
    if (charging) {
      // Ladeende: eigener Sensor (finish), sonst jetzt + Restladezeit (eigener Sensor oder „Laderestzeit“ der evcc-Integration)
      const fin = this._st(ev.finish);
      let finD = fin && !OFFLINE_HD.includes(fin.state) ? new Date(fin.state) : null;
      if (!finD || isNaN(finD)) {
        const rs = this._st(ev.remaining || this._evccEnt("chargeremainingduration", true)), rv = parseFloat(rs?.state);
        const u = String(rs?.attributes?.unit_of_measurement || "s").toLowerCase();
        const sec = isNaN(rv) || rv <= 0 ? null : u === "h" ? rv * 3600 : u === "min" ? rv * 60 : u === "d" ? rv * 86400 : rv;
        finD = sec != null ? new Date(Date.now() + sec * 1000) : null;
      }
      const finTxt = finD && !isNaN(finD) ? `bis ${new Date(finD).toDateString() !== new Date().toDateString() ? `${WD[finD.getDay()]} ` : ""}${pad(finD.getHours())}:${pad(finD.getMinutes())} Uhr` : "";
      kicker = `Lädt${durMin != null ? ` seit ${durTxt}` : ""}`; kickEnd = finTxt;
      const amps = this._phaseCurrents();
      when = `${icon("mdi:flash")}<b>${p.v} ${p.u}</b>${avgP != null ? ` <span>(Ø ${de(avgP, 1)} kW)</span>` : ""}${amps ? `<span class="lamps">${amps}</span>` : ""}`;
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
    const per = cost != null && kwh > 0.05 ? cost / kwh : null;
    const fact = (lbl, v) => `<div class="lfact"><span>${lbl}</span><b>${v}</b></div>`;
    const facts = [
      fact("Dauer", durTxt, ev.duration),
      fact("Kosten", cost == null ? "–" : `${de(cost, 2)} ${esc(cur)}`, ev.session_price),
      fact("Preis", per == null ? "–" : `${de(per * 100, 1)} ct/kWh`),
    ].join("");

    // Plan, Modus, Hinweise als schmale Zeilen
    const plan = this._planSt(), mode = this._st(E.evcc_mode_control), rec = this._st(E.charge_before_pv_recommended), tot = this._fmt(ev.solar_total, 0);
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
          <span class="lkick">${esc(kicker)}${kickEnd ? `<span class="lend"><i> · </i>${esc(kickEnd)}</span>` : ""}</span>
          <div class="lbig"><b>${kwh == null ? "–" : de(kwh, 1)}</b><small>kWh</small>${!charging && avgP != null ? `<span class="lavg">Ø ${de(avgP, 1)} kW</span>` : ""}</div>
          ${when ? `<span class="lwhen">${when}</span>` : ""}
        </div>
        <div class="lringw">${ring}</div>
      </div>
      ${split}
      <div class="lfacts">${facts}</div></div>
`;
  }

  /* --- Leasing-Kilometerbudget (ev_assistant, Sensor „km vor Rücklauf“ mit allen Werten als Attribute) --- */
  _render_lease() {
    const el = this.shadowRoot.getElementById("lease"); if (!el) return;
    const cfg = this._config.car.leasing;
    const id = !cfg ? null : String(cfg).startsWith("eva:") ? this._eva()[String(cfg).slice(4)] : cfg;
    const st = this._st(id), a = st?.attributes || {}, km = parseFloat(st?.state);
    this._leaseOk = !!st && !OFFLINE_HD.includes(st.state) && !isNaN(km);   // false = kein Leasing-Vertrag eingerichtet
    el.hidden = !this._leaseOk || this._statView() === "usage";
    if (el.hidden) { if (el._html) { el.innerHTML = ""; el._html = ""; } return; }
    const n = (v) => typeof v === "number" && !isNaN(v);
    const f = (v, d = 0) => (n(v) ? de(v, d) : "–");
    const sg = (v, d = 0) => (n(v) ? `${v > 0 ? "+" : ""}${de(v, d)}` : "–");
    const dt = (iso) => { const d = iso ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso + "T00:00" : iso) : null; return d && !isNaN(d) ? `${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()}` : esc(iso || "–"); };
    const STATUS = { im_budget: ["Im Budget", "var(--green)"], knapp: ["Knapp", "var(--orange)"], ueber: ["Über Budget", "var(--red)"] };
    const [stTxt, stCol] = STATUS[a.status] || ["", "var(--green)"];

    // Kennzahlen
    const kpi = (lbl, v, u, cls = "") => `<div class="cstat ${cls}"><span>${lbl}</span><b>${v}${u ? `<small>${u}</small>` : ""}</b></div>`;
    const kpis = [
      kpi("vor Rücklauf", sg(km, 1), "km", km > 0 ? "neg" : "pos"),
      kpi("Tage bis Ende", f(a.verbleibende_tage), ""),
      kpi("Restbudget", f(a.verbleibendes_tagesbudget_km, 1), "km/Tag", n(a.verbleibendes_tagesbudget_km) && a.verbleibendes_tagesbudget_km < 0 ? "neg" : ""),
      kpi("Noch erlaubt", f(a.resterlaubte_km), "km", n(a.resterlaubte_km) && a.resterlaubte_km < 0 ? "neg" : ""),
    ].join("");

    // Balken: gefahren von inklusive; Skala bis Ende der Mehr-km-Toleranz, damit harte Grenze und Toleranzband sichtbar sind
    const inkl = a.vertrag_inkl_km, gef = a.gefahrene_vertrags_km, soll = a.soll_km_bis_heute;
    const tM = n(a.toleranz_mehr_km) ? a.toleranz_mehr_km : 0, tm = n(a.toleranz_minder_km) ? a.toleranz_minder_km : 0;
    const max = n(inkl) && inkl > 0 ? inkl + tM : 0, pos = (v) => Math.max(0, Math.min(100, v / max * 100));
    const tol = tM || tm ? (tM === tm ? `±${f(tM)}` : `−${f(tm)} / +${f(tM)}`) : "";
    const bar = !max || !n(gef) ? "" : `<div class="lscap"><span>${f(gef)} von ${f(inkl)} km</span><b>${de(gef / inkl * 100, 1)} %</b></div>
      <div class="bar">${tol ? `<i class="lzone" style="left:${pos(inkl - tm)}%" title="Toleranz ${tol} km"></i>` : ""}<span style="width:${pos(gef)}%;background:${stCol};box-shadow:none"></span>
        <i class="lhard" style="left:${pos(inkl)}%" title="Vertragsgrenze ${f(inkl)} km"></i>${n(soll) ? `<i class="bm soll" style="left:${pos(soll)}%" title="Soll heute ${f(soll)} km"></i>` : ""}</div>
      <div class="lsax"><span style="left:${pos(inkl)}%">${f(inkl)}</span></div>
      <div class="lsnote"><span><i class="ld soll"></i>Soll heute ${f(soll)}</span><span><i class="ld hard"></i>Grenze ${f(inkl)}</span>${tol ? `<span><i class="ld zone"></i>Toleranz ${tol}</span>` : ""}</div>`;

    const html = this._statHd("lease", stTxt ? `<span style="color:${stCol};font-weight:700">${stTxt}</span>` : "", id) + `
      <div class="cstats lstats">${kpis}</div>
      ${bar}`;
    if (el._html !== html) { el.innerHTML = html; el._html = html; }
  }

  /* Leasing / Nutzung: mit Leasing-Vertrag (und eingeschalteter Nutzung) per Umschalter im Kachelkopf wechseln */
  _statTabs() {
    const E = this._eva(), u = this._config.car.usage;
    return !!this._leaseOk && u !== false && u !== "" && ["odo_year_km", "kwh_year", "odo_avg_day", "cost_year"].some((k) => this._st(E[k]));
  }
  _statView() {
    if (!this._statTabs()) return "lease";
    if (!this._statTab) { try { this._statTab = localStorage.getItem("mg-car-stat-view"); } catch (e) {} }
    return this._statTab === "usage" ? "usage" : "lease";
  }
  _statHd(view, label, entity) {
    if (!this._statTabs()) return this._hd(view === "lease" ? "Leasing" : "Nutzung", label, entity);
    const seg = [["lease", "Leasing"], ["usage", "Nutzung"]].map(([v, l]) => `<button class="hseg ${v === view ? "sel" : ""}" data-act="statview" data-v="${v}">${l}</button>`).join("");
    return `<div class="hd stathd"><div class="hsegs">${seg}</div><span class="lbl">${label}</span>
      ${entity ? `<button class="arrow" data-act="more" data-entity="${esc(entity)}">${icon("mdi:chevron-right")}</button>` : ""}</div>`;
  }

  /* --- Nutzung (ev_assistant): Zeiträume, Durchschnitte, Ladeorte --- */
  _render_usage() {
    const el = this.shadowRoot.getElementById("usage"); if (!el) return;
    const cfg = this._config.car.usage, E = this._eva();
    const show = cfg !== false && cfg !== "" && (!this._leaseOk || this._statView() === "usage");
    const v = (k) => { const st = this._st(E[k]); const x = st ? parseFloat(st.state) : NaN; return isNaN(x) ? null : x; };
    const P = [["day", "Heute"], ["week", "Woche"], ["month", "Monat"], ["year", "Jahr"]];
    const loc = this._st(E.charging_location_breakdown)?.attributes || {};
    // Tabelle: gefahrene km je Zeitraum; Verbrauch (kWh) und Kosten daraus über Ø-Verbrauch bzw. € / 100 km
    // (ohne diese Werte: geladene kWh / Ladekosten aus ev_assistant)
    const cons = v("vehicle_avg_consumption"), e100 = Number(loc.eur_je_100km) > 0 ? Number(loc.eur_je_100km) : null;
    const km = (p) => v(`odo_${p}_km`);
    const R = [
      { l: "km", d: 0, u: "", val: km, id: () => E.odo },
      { l: "kWh", d: 1, u: "", val: (p) => (cons != null && km(p) != null ? km(p) * cons / 100 : v(`kwh_${p}`)), id: (p) => (cons != null ? E.vehicle_avg_consumption : E[`kwh_${p}`]) },
      { l: "Kosten", d: 2, u: " €", val: (p) => (e100 != null && km(p) != null ? km(p) * e100 / 100 : v(`cost_${p}`)), id: (p) => (e100 != null ? E.charging_location_breakdown : E[`cost_${p}`]) },
    ];
    const rows = R.filter((r) => P.some(([p]) => r.val(p) != null));
    const kp = [
      ["odo_avg_day", "Ø / Tag", 1, "km"],
      [null, "€ / 100 km", 2, "€", e100, E.charging_location_breakdown],
      ["co2_savings", "CO₂ gespart", 0, "kg"],
    ].map(([k, l, d, u, raw, id]) => {
      let x = raw ?? (k ? v(k) : null); if (x == null || isNaN(x)) return "";
      if (u === "kg" && x >= 1000) { x /= 1000; u = "t"; d = 1; }
      return `<button class="cstat" data-act="more" data-entity="${esc(id || E[k])}"><span>${l}</span><b>${de(x, d)}<small>${u}</small></b></button>`;
    }).join("");
    el.hidden = !show || (!rows.length && !kp);
    if (el.hidden) { if (el._html) { el.innerHTML = ""; el._html = ""; } return; }

    // Tabelle: Zeilen km / kWh / Kosten, Spalten Heute … Jahr; unter den Jahres-km die Prognose
    const prog = v("odo_year_projected");
    const cell = (r, p) => {
      const x = r.val(p); if (x == null) return `<b class="dim">–</b>`;
      const sub = r.l === "km" && p === "year" && prog != null ? `<em title="Prognose Jahr">≈ ${de(prog, 0)}</em>` : "";
      return `<b data-act="more" data-entity="${esc(r.id(p) || "")}">${de(x, Math.abs(x) >= 100 && r.d === 1 ? 0 : r.d)}${r.u ? `<small>${r.u}</small>` : ""}${sub}</b>`;
    };
    const calc = [cons != null && "kWh aus km × Ø Verbrauch", e100 != null && "Kosten aus km × € / 100 km"].filter(Boolean).join(", ");
    const table = rows.length ? `<div class="ustab"><span></span>${P.map(([, l]) => `<span class="h">${l}</span>`).join("")}
      ${rows.map((r) => `<span>${r.l}</span>${P.map(([p]) => cell(r, p)).join("")}`).join("")}</div>${calc ? `<div class="unote">${calc}</div>` : ""}` : "";

    // Ladeorte: Heim (davon PV) / unterwegs als Balken
    const h = loc.heim || {}, fr = loc.fremd || {};
    const hp = Number(h.kwh_anteil_pct) || 0, fp = Number(fr.kwh_anteil_pct) || 0, sp = hp * (Number(h.solar_pct) || 0) / 100;
    const kw = (x) => (x != null && !isNaN(x) ? ` · ${de(x, 0)} kWh` : "");
    const locs = hp + fp > 0 ? `<button class="uloc" data-act="more" data-entity="${esc(E.charging_location_breakdown)}">
      <span class="mgl">Geladen${loc.gesamt_autarkie_pct != null ? ` <small>· ${de(loc.gesamt_autarkie_pct, 0)} % aus PV</small>` : ""}</span>
      <span class="ubar">${sp > 0 ? `<i class="pv" style="width:${sp}%"></i>` : ""}<i class="home" style="width:${hp - sp}%"></i><i class="ext" style="width:${fp}%"></i></span>
      <span class="ulg"><span><i class="ld home"></i>Zuhause ${de(hp, 0)} %${kw(h.kwh)}</span>${sp > 0 ? `<span><i class="ld pv"></i>davon PV ${de(sp, 0)} %${kw(h.kwh != null ? h.kwh * (Number(h.solar_pct) || 0) / 100 : null)}</span>` : ""}${fp > 0 ? `<span><i class="ld ext"></i>Unterwegs ${de(fp, 0)} %${kw(fr.kwh)}</span>` : ""}</span></button>` : "";

    const odo = this._fmt(E.odo, 0);
    const html = this._statHd("usage", odo ? `${odo.v} km` : "", E.odo) + (kp ? `<div class="cstats ustats">${kp}</div>` : "") + table + locs;
    if (el._html !== html) { el.innerHTML = html; el._html = html; }
  }

  /* --- Fahrtenbuch --- */
  /* Fahrtenbuch über ev_assistant (Websocket „ev_assistant/trips“) */
  async _loadTrips(force) {
    if (!String(this._config.car.trips || "").startsWith("eva:")) return;
    if (!force && this._evaTrips && Date.now() - this._evaTrips.t < 5 * 60000) return;
    const id = this._evaEntryId();
    if (!id || !this._hass?.callWS) { setTimeout(() => !this._evaTrips && this._evaEntryId() && this._loadTrips(), 3000); return; }
    try {
      const res = await this._hass.callWS({ type: "ev_assistant/trips", config_entry_id: id });
      const ts = (v) => (v ? v * (v < 1e12 ? 1000 : 1) : null);
      const list = (res?.trips || []).map((r) => {
        const t0 = ts(r.start_ts || r.erfasst_ts), t1 = ts(r.end_ts), km = parseFloat(r.km), kwh = parseFloat(r.verbrauch_kwh);
        return { raw: r, start: t0 ? new Date(t0).toISOString() : r.datum, start_ort: r.start_ort, ziel_ort: r.end_ort, strecke: isNaN(km) ? null : km,
          verbrauch_kwh: isNaN(kwh) ? null : kwh, avg_verbrauch: km > 0.5 && !isNaN(kwh) ? kwh / km * 100 : null,
          dauer: t0 && t1 > t0 ? Math.round((t1 - t0) / 60000) : null, avg_speed: t0 && t1 > t0 && km > 0 ? km / ((t1 - t0) / 3600000) : null };
      });
      this._evaTrips = { t: Date.now(), list };
    } catch (e) { this._evaTrips = { t: Date.now(), list: [], err: true }; this._log("Fahrtenbuch nicht abrufbar", e); }
    this._update(true);
  }

  _tripList() {
    const c = this._config.car;
    let trips = String(c.trips || "").startsWith("eva:") ? this._evaTrips?.list || [] : this._st(c.trips)?.attributes?.trips || [];
    if (!Array.isArray(trips)) trips = [];
    const t0 = (x) => new Date(x.start).getTime() || 0;
    const l = trips.slice().sort((a, b) => t0(b) - t0(a));
    return c.trips_max > 0 ? l.slice(0, c.trips_max) : l;
  }

  _tripRows(list, edit = false) {
    const dt = (v) => { const d = new Date(v); return isNaN(d) ? null : d; };
    const place = (x) => ({ home: "Zuhause", zuhause: "Zuhause", Home: "Zuhause", not_home: "unterwegs", "außerhalb": "unterwegs" }[x] || x || "?");
    let lastDay = "";
    return list.map((t) => {
      const s = dt(t.start), day = s ? `${WD[s.getDay()]}, ${s.getDate()}. ${MON[s.getMonth()]}${s.getFullYear() !== new Date().getFullYear() ? ` ${s.getFullYear()}` : ""}` : "";
      const head = day !== lastDay ? `<div class="tday">${esc(day)}</div>` : ""; lastDay = day;
      const km = parseFloat(t.strecke), kwh = parseFloat(t.verbrauch_kwh), avg = parseFloat(t.avg_verbrauch);
      const ed = edit && t.raw?.erfasst_ts != null;
      return `${head}<div class="trip${ed ? " ted" : ""}"${ed ? ` data-act="set" data-k="trip-edit" data-id="${esc(t.raw.erfasst_ts)}" title="Fahrt bearbeiten"` : ""}>
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
    const html = `<div class="hd"><span class="ttl">Fahrtenbuch</span><span class="lbl"></span>
        <button class="arrow" data-act="trips" aria-label="Alle Fahrten" title="Alle Fahrten">${icon("mdi:chevron-right")}</button></div>` +
      (list.length ? `<div class="tlist" data-act="trips" title="Alle Fahrten anzeigen">${this._tripRows(list)}</div>`
        : `<div class="empty">${String(c.trips || "").startsWith("eva:") && !this._evaTrips ? "Lädt …" : `Keine Fahrten gefunden${c.trips && !c.trips.startsWith("eva:") ? ` (${esc(c.trips)})` : ""}`}</div>`);
    // nur bei Änderungen neu aufbauen – sonst verliert z. B. iOS beim Scrollen ans Seitenende (Größenänderung durch die Leisten) die Position
    if (el._html !== html) { el.innerHTML = html; el._html = html; }
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
  _page() { return Math.max(10, Number(this._config.car.list_page) || 30); }
  /* Fußzeile langer Listen: „30 von 350 – weiter scrollen“ */
  _moreRow(shown, total) {
    this._dlgMore = shown < total;
    return shown < total ? `<div class="dmore">${de(shown, 0)} von ${de(total, 0)} · zum Nachladen weiter scrollen</div>` : "";
  }

  _renderTripsDlg() {
    const d = this.shadowRoot.getElementById("cardlg");
    if (!d || this._dlg !== "trips") return;
    const list = this._tripList(), num = (t, k) => parseFloat(t[k]) || 0;
    const km = list.reduce((a, t) => a + num(t, "strecke"), 0), kwh = list.reduce((a, t) => a + num(t, "verbrauch_kwh"), 0);
    const min = list.reduce((a, t) => a + num(t, "dauer"), 0);
    const sc = d.querySelector(".dbody")?.scrollTop || 0;
    d.innerHTML = `<div class="dpan chpan">
      <div class="dhd"><span class="dico">${icon("mdi:map-marker-path")}</span>
        <span class="rtx"><span class="rname">Alle Fahrten</span><span class="rsub">${String(this._config.car.trips || "").startsWith("eva:") ? "Fahrtenbuch aus ev_assistant" : esc(this._st(this._config.car.trips)?.attributes?.friendly_name || "Fahrtenbuch")}</span></span>
        <button class="dx" data-act="cardclose" aria-label="Schließen">${icon("mdi:close")}</button></div>
      <div class="chsum">
        <div><span>Fahrten</span><b>${list.length}</b></div>
        <div><span>Strecke</span><b>${de(km, 0)}<small>km</small></b></div>
        <div><span>Energie</span><b>${de(kwh, kwh >= 100 ? 0 : 1)}<small>kWh</small></b></div>
        <div><span>Ø Verbrauch</span><b>${km > 1 ? de(kwh / km * 100, 1) : "–"}<small>kWh/100</small></b></div>
        <div><span>Fahrzeit</span><b>${min >= 60 ? `${Math.floor(min / 60)}:${pad(Math.round(min % 60))}` : Math.round(min)}<small>${min >= 60 ? "h" : "min"}</small></b></div>
      </div>
      <div class="dbody">${list.length ? `<div class="tlist">${this._tripRows(list.slice(0, this._dlgN), true)}</div>${this._moreRow(Math.min(this._dlgN, list.length), list.length)}` : `<div class="empty">Keine Fahrten gefunden</div>`}</div></div>`;
    const b = d.querySelector(".dbody"); if (b) b.scrollTop = sc;
  }

  /* gemeinsames Popup für „Alle Ladungen“ und „Alle Fahrten“ */
  _openDlg(mode) {
    const d = this.shadowRoot.getElementById("cardlg");
    this._dlg = mode; this._dlgN = this._page();
    d.dataset.mode = mode;
    if (!d._bound) {
      d._bound = true;
      d.addEventListener("click", (ev) => { if (ev.target === d) d.close(); });
      d.addEventListener("close", () => { if (!d.open) this._dlg = null; });   // „close“ kommt verzögert – nicht ein gerade neu geöffnetes Fenster abmelden
      // lange Listen: beim Scrollen ans Ende die nächsten Einträge anhängen
      d.addEventListener("scroll", (ev) => {
        const b = ev.target;
        if (!b.classList?.contains("dbody") || this._dlgMore !== true || b.scrollHeight - b.scrollTop - b.clientHeight > 400) return;
        this._dlgMore = false; this._dlgN += this._page();
        if (this._dlg === "trips") this._renderTripsDlg(); else if (this._dlg === "charges") this._renderCharges();
      }, true);
    }
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
    const c = this._config.car, hi = this._histIds(), ids = [hi.soc, hi.pw].filter(Boolean);
    if (!this._hass) return;
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

  /* Entitäten für den Verlauf: Ladestand und Ladeleistung (nur echte Sensoren haben Verlauf/Statistik) */
  _histIds() {
    const c = this._config.car, ev = c.evcc || {};
    return { soc: this._real(c.soc), pw: this._real(ev.power) || this._real(this._config.energy.car_power) };
  }

  /* evcc-Ladelogbuch über ev_assistant (für „Letzte Ladung“ und den PV-Anteil im Verlauf), 5 min zwischengespeichert */
  async _evccSessions(force) {
    if (!force && this._sess && Date.now() - this._sess.t < 5 * 60000) return this._sess.list;
    const id = this._evaEntryId();
    if (!id || !this._hass?.callWS) return [];
    try {
      const res = await this._hass.callWS({ type: "ev_assistant/evcc_sessions", config_entry_id: id });
      const veh = this._evccVehicle();
      const list = (res?.sessions || []).filter((x) => !veh || !x.vehicle || String(x.vehicle).toLowerCase() === veh).map((x) => {
        const ts = x.created ? Date.parse(x.created) : NaN, te = x.finished ? Date.parse(x.finished) : Date.now();
        return { ts, te, kwh: x.chargedEnergy ?? null, pv: x.solarPercentage ?? null, price: x.price ?? null,
          dur: typeof x.chargeDuration === "number" && x.chargeDuration > 0 ? x.chargeDuration / 1e9 / 60 : null, finished: !!x.finished,
          s0: typeof x.socStart === "number" ? x.socStart : null, s1: typeof x.socEnd === "number" ? x.socEnd : null };
      }).filter((x) => !isNaN(x.ts) && x.te > x.ts);
      this._sess = { t: Date.now(), list };
    } catch (e) { this._sess = { t: Date.now(), list: [] }; }
    return this._sess.list;
  }

  /* Geladene kWh je Stunde, aufgeteilt nach PV und Netz.
     - kWh: aus der Langzeitstatistik der Ladeleistung; ohne Ladeleistungs-Sensor aus dem evcc-Ladelogbuch
       (Energie jeder Sitzung gleichmäßig über ihre Dauer verteilt)
     - PV-Anteil: aus dem evcc-Ladelogbuch (PV-Anteil der Sitzung, in die die Stunde fällt); ohne evcc aus
       Netzbezug und Hausverbrauch (energy.grid_import / energy.home), sonst keine Aufteilung */
  async _loadBars(t0, t1, hrs) {
    const c = this._config.car, e = this._config.energy, H = 3600000;
    const hi = this._histIds(), pid = hi.pw, gid = this._real(c.split_grid || e.grid_import), hid = this._real(c.split_home || e.home), sid = hi.soc;
    if (!this._hass.callWS) return null;
    const sessions = (await this._evccSessions()).filter((x) => x.te > t0 - H && x.ts < t1);
    // Stunde → überwiegende Sitzung
    const sessAt = (t) => { let best = null, ov = 0; for (const x of sessions) { const o = Math.min(x.te, t + H) - Math.max(x.ts, t); if (o > ov) { ov = o; best = x; } } return best; };
    let rows = [], split = false, src = "";
    try {
      if (pid) {
        const ids = [pid, gid, hid, sid].filter(Boolean);
        const st = await this._hass.callWS({ type: "recorder/statistics_during_period", start_time: new Date(t0).toISOString(),
          end_time: new Date(t1).toISOString(), statistic_ids: ids, period: "hour", types: ["mean"] });
        const ts = (v) => (typeof v === "number" ? v : new Date(v).getTime());
        const toKW = (id) => { const u = (this._st(id)?.attributes?.unit_of_measurement || "").toLowerCase(); return u === "kw" ? 1 : u === "mw" ? 1000 : 0.001; };
        const map = (id) => { const m = new Map(); for (const x of st?.[id] || []) if (x.mean != null) m.set(ts(x.start), x.mean); return m; };
        const P = map(pid), G = map(gid), Hm = map(hid), S = map(sid), fp = toKW(pid), fg = toKW(gid), fh = toKW(hid);
        const useEvcc = sessions.length > 0, useSens = !useEvcc && !!(gid && hid);
        for (const [t, v] of P) {
          const kwh = Math.max(0, v * fp);
          let share = null;   // Netzanteil 0…1
          if (useEvcc) { const x = sessAt(t); if (x?.pv != null) share = 1 - Math.max(0, Math.min(100, x.pv)) / 100; }
          else if (useSens) {
            const home = (Hm.get(t) ?? 0) * fh, grid = Math.max(0, (G.get(t) ?? 0) * fg);
            // Anteil Netz = Netzbezug / Gesamtverbrauch der Stunde (Auto im Hausverbrauch enthalten)
            share = home > 0.01 ? Math.min(1, grid / Math.max(home, kwh)) : (G.has(t) ? 1 : 0);
          }
          // Stunde ohne zuordenbare Sitzung (z. B. Laden ohne evcc): ohne Aufteilung als Netz gezählt
          rows.push({ t, kwh, grid: kwh * (share ?? 1), pv: kwh * (1 - (share ?? 1)), soc: S.get(t) });
        }
        split = useEvcc || useSens; src = useEvcc ? "evcc" : useSens ? "sensor" : "";
      } else if (sessions.length) {
        // ohne Ladeleistungs-Sensor: Energie der Sitzungen gleichmäßig auf ihre Stunden verteilen
        const acc = new Map();
        for (const x of sessions) {
          if (!(x.kwh > 0)) continue;
          for (let t = Math.floor(x.ts / H) * H; t < x.te; t += H) {
            const f = (Math.min(x.te, t + H) - Math.max(x.ts, t)) / (x.te - x.ts);
            if (f <= 0 || t + H <= t0) continue;
            const r = acc.get(t) || { t, kwh: 0, grid: 0, pv: 0, soc: null }, k = x.kwh * f, pv = x.pv != null ? Math.max(0, Math.min(100, x.pv)) / 100 : 0;
            r.kwh += k; r.pv += k * pv; r.grid += k * (1 - pv);
            acc.set(t, r);
          }
        }
        rows = [...acc.values()]; split = true; src = "evcc-log";
      } else return null;
      if (!split) rows = rows.map((r) => ({ ...r, grid: 0, pv: 0 }));
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
      this._log("Verlauf-Balken", { unit, split, src, kwh: pid || "aus Ladelogbuch", sessions: sessions.length });
      return { rows, unit, split, src };
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
      if (!B.split) return r.kwh < 0.005 ? "" : `<g class="bar" data-i="${i}"><rect x="${x.toFixed(1)}" y="${Y(r.kwh).toFixed(1)}" width="${bw.toFixed(1)}" height="${(Ht - Y(r.kwh)).toFixed(1)}" class="bkw"/></g>`;
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
      <div class="glg">${B.split ? `<span class="pvl">PV/Speicher ${de(sum.p, 1)} kWh</span><span class="grl">Netz ${de(sum.g, 1)} kWh</span>` : `<span class="kwl">Geladen ${de(sum.k, 1)} kWh</span>`}<span class="s">Ladestand ${Math.round(nowS)} %</span>
<span class="src">${{ h: "Stundenwerte", d: "Tageswerte", w: "Wochenwerte" }[B.unit]}${B.src === "evcc-log" ? " aus dem evcc-Ladelogbuch" : B.src === "evcc" ? " · PV-Anteil aus evcc" : ""}</span></div>`;
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
    const split = this._carHist?.bars?.split;
    tip.innerHTML = `<b>${when}</b>
      ${split ? `<div><i class="pvd"></i>PV/Speicher<span>${de(row.pv, 2)} kWh</span></div>
      <div><i class="grd"></i>Netz<span>${de(row.grid, 2)} kWh</span></div>` : ""}
      <div class="tot">Geladen<span>${de(row.kwh, 2)} kWh${split && row.kwh > 0.005 ? ` · ${pvp} % PV` : ""}</span></div>
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
    const hi = this._histIds(), pid = hi.pw, sid = hi.soc, pnow = this._real(ev.power) ? ev.power : pid || ev.power;
    // nur den Zeitraum zeigen: letzter Wert vor Beginn wird zum Startwert
    const clip = (arr) => { const pre = arr.filter((p) => p[0] <= t0).pop(); return (pre ? [[t0, pre[1]]] : []).concat(arr.filter((p) => p[0] > t0)); };
    const soc = clip(H?.data?.[sid] || []), pw = clip(H?.data?.[pid] || []);
    const kw = this._st(pid)?.attributes?.unit_of_measurement?.toLowerCase() === "kw" ? 1 : 0.001;
    // aktuellen Wert bis "jetzt" fortschreiben
    const nowP = this._w(pnow) / 1000, nowS = this._num(c.soc);
    // das HTML hängt über Date.now() von der Uhrzeit ab – daher eigener Schlüssel: neu zeichnen nur bei anderem Zeitraum,
    // neuen Verlaufsdaten, geänderter Leistung (0,1 kW) oder Ladestand und alle 5 Minuten (iOS-Springen, #20)
    const hKey = [hrs, H?.t, Math.round(nowP * 10), Math.round(nowS), Math.floor(t1 / 300000)].join("|");
    if (el._hKey === hKey && el.firstChild) return;
    el._hKey = hKey;
    const seg = this._ranges().map((r) =>
      `<button class="hseg ${r.h === hrs ? "sel" : ""}" data-act="hrange" data-h="${r.h}">${esc(r.label)}</button>`).join("");
    let body;
    if (!H) body = `<div class="empty">Lädt …</div>`;
    else if (H.bars?.rows?.length && hrs >= (c.bars_from_hours ?? 0)) body = this._barsSvg(H, t0, t1, W, Ht, X, soc, nowS);
    else if (!pid && !sid) body = `<div class="empty hdiag">Für den Verlauf fehlt ein Sensor für Ladeleistung oder Ladestand mit Verlauf.<br>
      Ladeleistung per YAML angeben, z. B. <code>energy: { car_power: sensor.wallbox_leistung }</code>.</div>`;
    else if (!(H.data?.[sid]?.length) && !(H.data?.[pid]?.length)) body = `<div class="empty hdiag">Keine Verlaufsdaten für ${(H.ids || []).map((x) => `<code>${esc(x)}</code>`).join(" und ")} im Zeitraum.<br>
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
    if (H) el.style.minHeight = "";
  }


  /* ---------- Unterseite „Profil & Analyse“ (Daten aus ev_assistant) ---------- */
  _subPage() {
    if (this._pg) return this._pg;
    let v = null; try { v = localStorage.getItem("mg-car-page"); } catch (e) {}
    return (this._pg = ["prof", "set", "cost"].includes(v) ? v : "main");
  }
  _showPage() {
    const p = this._subPage(), sr = this.shadowRoot;
    sr.getElementById("pmain").hidden = p !== "main";
    sr.getElementById("pprof").hidden = p !== "prof";
    sr.getElementById("pset").hidden = p !== "set";
    sr.getElementById("pcost").hidden = p !== "cost"; sr.getElementById("kper").hidden = p !== "cost";
    sr.querySelectorAll('[data-act="page"]').forEach((b) => b.classList.toggle("sel", b.dataset.p === p));
  }
  _ea(key) { const id = this._eva()[key]; return id ? this._hass?.states[id] : null; }
  _wdIdx() { const t = new Date().getDay(), today = t === 0 ? 6 : t - 1; return { today, tomorrow: (today + 1) % 7 }; }
  _roundKm(km) { if (typeof km !== "number" || isNaN(km)) return null; km = Math.max(0, km); return km < 100 ? Math.round(km / 5) * 5 : Math.round(km / 10) * 10; }

  _render_prof() {
    this._render_week(); this._render_morrow(); this._render_ana(); this._render_misch();
  }

  _render_week() {
    const el = this.shadowRoot.getElementById("pweek");
    const P = this._ea("usage_profile")?.attributes || {}, Hs = this._ea("house_usage_profile")?.attributes || {};
    const Pl = this._ea("plug_window")?.attributes || {}, Dp = this._ea("morning_departure")?.attributes?.je_wochentag || null;
    const urlaub = !!this._ea("evcc_mode_control")?.attributes?.urlaub_aktiv;
    const head = this._hd("Deine Woche", urlaub ? `<span class="pchip">Urlaub</span>` : "");
    if (P.montag === undefined) { el.innerHTML = head + `<div class="empty">Noch nicht genug Fahrtenbuch-Historie (mindestens 7 Tage) für ein Nutzungsprofil.</div>`; return; }
    const km = P.km_je_wochentag, hasKm = !!km && PWD.every(([k]) => typeof km[k] === "number");
    const ev = PWD.map(([k]) => (hasKm ? km[k] : parseFloat(P[k]) || 0)), evMax = Math.max(0.1, ...ev);
    const hs = PWD.map(([k]) => (Hs[k] !== undefined ? parseFloat(Hs[k]) : null)), hsMax = Math.max(0.1, ...hs.filter((x) => x != null));
    const pl = PWD.map(([k]) => (Pl[k] !== undefined ? parseFloat(Pl[k]) : null));
    const minN = this._ea("morning_departure")?.attributes?.mindestanzahl || 4;
    const dep = (s) => !s ? "–" : s.status === "ok" && s.typisch ? s.typisch : s.status === "nicht_belastbar" ? `${s.n_gueltig}/${minN}` : s.status === "uneinheitlich" ? "?" : "–";
    const { today, tomorrow } = this._wdIdx(), showHs = Hs.konfiguriert === true && hs.some((x) => x != null);
    const days = PWD.map(([k, lbl], i) => {
      const cls = i === tomorrow ? "tm" : i === today ? "td" : "";
      return `<div class="pday ${cls}"><div class="pdn"><b>${lbl}</b>${i === tomorrow ? "<span>MORGEN</span>" : i === today ? "<span>HEUTE</span>" : ""}</div>
        <div class="pmt ev"><small>Auto${hasKm ? " (ca.)" : ""}</small><b>${hasKm ? this._roundKm(ev[i]) : de(ev[i], 1)}<em>${hasKm ? "km" : "kWh"}</em></b><div class="pbar"><i style="width:${(ev[i] / evMax) * 100}%"></i></div></div>
        ${showHs ? `<div class="pmt hs"><small>Haus</small><b>${hs[i] == null ? "–" : de(hs[i], 1)}<em>${hs[i] == null ? "" : "kWh"}</em></b><div class="pbar"><i style="width:${hs[i] == null ? 0 : (hs[i] / hsMax) * 100}%"></i></div></div>` : ""}
        ${pl.some((x) => x != null) ? `<div class="pmt pl"><small>Steckt</small><b>${pl[i] == null ? "–" : de(pl[i], pl[i] >= 10 ? 0 : 1)}<em>${pl[i] == null ? "" : "h"}</em></b></div>` : ""}
        ${Dp ? `<div class="pmt dp"><small>Abfahrt</small><b>${dep(Dp[k])}</b></div>` : ""}</div>`;
    }).join("");
    el.innerHTML = head + `<div class="pdays">${days}</div>`;
  }

  _render_morrow() {
    const el = this.shadowRoot.getElementById("pmorrow");
    if (this.shadowRoot.activeElement?.classList?.contains("pbufsel")) return;   // Auswahl offen: nicht neu zeichnen
    if (!this._bufBound) {
      this._bufBound = true;
      el.addEventListener("change", (e) => {
        const t = e.target; if (!t?.classList?.contains("pbufsel") || t.value === "") return;
        t.blur(); this._setBuffer(Number(t.value));
      });
    }
    const rec = this._ea("charge_before_pv_recommended"), ra = rec?.attributes || {};
    const ma = this._ea("evcc_mode_control")?.attributes || {}, need = this._ea("usage_profile_tomorrow"), na = need?.attributes || {};
    const avK = parseFloat(this._ea("available_kwh")?.state), needK = parseFloat(need?.state), pvK = parseFloat(ra.pv_prognose_morgen_kwh);
    const avKm = typeof ra.verfuegbare_km === "number" ? ra.verfuegbare_km : typeof ma.reichweite_km === "number" ? ma.reichweite_km : null;
    const st = (lbl, km, kwh, cls = "") => {
      const k = this._roundKm(km), hasW = !isNaN(kwh);
      return `<div class="pst ${cls}"><span>${lbl}</span><b>${k != null ? k : hasW ? de(kwh, 1) : "–"}<small>${k != null ? "km" : hasW ? "kWh" : ""}</small></b>${k != null && hasW ? `<em>${de(kwh, 1)} kWh</em>` : ""}</div>`;
    };
    const bufKm = na.puffer_art === "km" && !isNaN(parseFloat(na.puffer_km)), buf = bufKm ? parseFloat(na.puffer_km) : parseFloat(na.puffer_prozent);
    const on = rec?.state === "on", known = rec && !OFFLINE_HD.includes(rec.state);
    const hero = !known ? `<div class="phero"><div class="kick">Empfehlung</div><div class="pbig">Noch keine Empfehlung möglich</div></div>`
      : `<div class="phero ${on ? "yes" : "no"}"><div class="kick">Empfehlung</div><div class="pbig">${on ? "Laden empfehlenswert" : "Laden kann warten"}</div>
        <div class="psub">${on ? (isNaN(pvK) ? "Der Akku reicht laut Profil nicht sicher bis morgen." : "Akku plus PV-Prognose reichen laut Profil nicht sicher.") : (isNaN(pvK) ? "Akku reicht bis morgen – z. B. auf PV-Überschuss warten." : "Akku plus PV-Prognose decken den Bedarf.")}</div></div>`;
    // wie weit reicht der Akku laut Profil (Tage ab morgen)
    const P = this._ea("usage_profile")?.attributes || {}, kmD = P.km_je_wochentag;
    let reach = "";
    if (avKm != null && kmD) {
      const { tomorrow } = this._wdIdx(); let left = avKm, segs = [], until = null;
      for (let n = 0; n < 7; n++) {
        const [k, l] = PWD[(tomorrow + n) % 7], d = Math.max(0, kmD[k] || 0);
        const f = d > 0 ? Math.max(0, Math.min(1, left / d)) : 1; segs.push([l, f]); left -= d;
        if (left < 0) break; until = PWD[(tomorrow + n) % 7][1];
      }
      reach = `<div class="sl2">Reicht laut Profil ${until ? `bis <b>${PWD_LONG[PWD.findIndex((x) => x[1] === until)]}</b>` : "<b>nicht bis morgen</b>"}</div>
        <div class="preach">${segs.map(([l, f]) => `<span><i style="width:${f * 100}%"></i><small>${l}</small></span>`).join("")}</div>`;
    }
    // PV morgen abzüglich Hausverbrauch laut Hausprofil (was fürs Auto übrig bleibt)
    const Hs = this._ea("house_usage_profile")?.attributes || {}, hsK = Hs.konfiguriert === true ? parseFloat(Hs[PWD[this._wdIdx().tomorrow][0]]) : NaN;
    let pvTile = "";
    if (!isNaN(pvK)) {
      const net = isNaN(hsK) ? pvK : Math.max(0, pvK - hsK), kmPerKwh = pvK > 0 && typeof ra.pv_prognose_morgen_km === "number" ? ra.pv_prognose_morgen_km / pvK : null;
      const k = this._roundKm(kmPerKwh != null ? net * kmPerKwh : NaN);
      pvTile = `<div class="pst pv"><span>PV fürs Auto</span><b>${k != null ? k : de(net, 1)}<small>${k != null ? "km" : "kWh"}</small></b>
        <em>${isNaN(hsK) ? `${de(pvK, 1)} kWh · ohne Hausprofil` : `${de(pvK, 1)} − ${de(hsK, 1)} kWh Haus`}</em></div>`;
    }
    // Puffer in km einstellbar (ev_assistant-Dienst set_usage_profile_buffer_km, 0–300 km in 5er-Schritten)
    if (this._bufSet && (Date.now() - this._bufSet.t > 90000 || (bufKm && buf === this._bufSet.v))) this._bufSet = null;
    const bufCur = this._bufSet ? this._bufSet.v : bufKm ? buf : null;
    let opts = bufCur == null ? `<option value="" selected>${isNaN(buf) ? "–" : `${de(buf, 0)} %`}</option>` : "";
    for (let v = 0; v <= 300; v += 5) opts += `<option value="${v}"${bufCur != null && Math.round(bufCur / 5) * 5 === v ? " selected" : ""}>${v} km</option>`;
    const bufTile = this._evaEntryId() && this._hass?.services?.ev_assistant?.set_usage_profile_buffer_km
      ? `<div class="pst pbuf"><span>Puffer</span><select class="pbufsel" aria-label="Puffer in km">${opts}</select>${bufKm && !isNaN(parseFloat(na.puffer_kwh)) ? `<em>${de(parseFloat(na.puffer_kwh), 1)} kWh</em>` : ""}</div>`
      : `<div class="pst"><span>Puffer</span><b>${isNaN(buf) ? "–" : de(buf, 0)}<small>${bufKm ? "km" : "%"}</small></b></div>`;
    el.innerHTML = this._hd("Morgen", PWD_LONG[this._wdIdx().tomorrow]) + hero + `<div class="pstats">
      ${st("Verfügbar", avKm, avK)}${st("Bedarf morgen", na.benoetigt_km, needK)}
      ${bufTile}${pvTile}</div>${reach}`;
  }

  _anaData() {
    const L = this._ea("charging_location_breakdown")?.attributes || {}, R = this._ea("range_estimate")?.attributes || {};
    return { L, R, heim: L.heim || {}, fremd: L.fremd || {}, acdc: L.ac_dc || {}, anb: Object.entries(L.anbieter || {}) };
  }

  _render_ana() {
    const el = this.shadowRoot.getElementById("pana"), A = this._anaData(), num = (v, d) => (typeof v === "number" ? de(v, d) : "–");
    const cap = parseFloat(this._ea("battery_capacity")?.state), cyc = parseFloat(this._ea("equivalent_full_cycles")?.state);
    const bands = A.R.verbrauch_nach_temperatur || {}, band = A.R.temperaturband_aktuell, tNow = A.R.aussentemperatur;
    const bv = band && typeof bands[band] === "number" ? bands[band] : null, warm = bands[">20°C"];
    const anb = [...A.anb].sort((a, b) => (b[1].kwh ?? b[1].kosten ?? 0) - (a[1].kwh ?? a[1].kosten ?? 0));
    const tile = (k, lbl, val, unit, sub, extra = "") => `<button class="ptile" data-act="ana" data-k="${k}"><span>${lbl}</span><b>${val}<small>${unit}</small></b><p>${sub}</p>${extra}<i class="pchev">›</i></button>`;
    const tiles = [
      tile("bat", "Batterie", isNaN(cap) ? "–" : de(cap, 1), "kWh", isNaN(cyc) ? "geschätzte Kapazität" : `${de(cyc, 0)} Vollzyklen`),
      tile("temp", `Verbrauch${typeof tNow === "number" ? ` bei ${de(tNow, 0)} °C` : ""}`, bv != null ? de(bv, 1) : "–", "kWh/100km",
        bv != null && typeof warm === "number" && band !== ">20°C" && warm > 0 ? `${bv >= warm ? "+" : ""}${Math.round((bv / warm - 1) * 100)} % ggü. > 20 °C` : band ? `Band ${esc(band)}` : "noch keine Daten"),
      tile("cost", "Kosten", num(A.L.eur_je_100km, 2), "€/100km", `Heim ${num(A.heim.preis_je_kwh, 2)} · Fremd ${num(A.fremd.preis_je_kwh, 2)} €/kWh`),
      tile("loc", "Autarkie gesamt", num(A.L.gesamt_autarkie_pct, 0), "%", `Heim-Solaranteil ${num(A.heim.solar_pct, 0)} %`),
      tile("loc", "Ladeorte", num(A.heim.kwh_anteil_pct, 0), "% Heim", `${num(A.heim.kwh, 0)} / ${num(A.fremd.kwh, 0)} kWh`,
        `<div class="pbar two"><i style="width:${A.heim.kwh_anteil_pct || 0}%"></i><i class="o" style="width:${A.fremd.kwh_anteil_pct || 0}%"></i></div>`),
      A.acdc.dc || A.acdc.ac ? tile("acdc", "Schnellladen", num(A.acdc.dc?.anzahl, 0), "× DC", `${num(A.acdc.ac?.anzahl, 0)} × AC · DC Ø ${num(A.acdc.dc?.preis_je_kwh, 2)} €/kWh`) : "",
      anb.length ? tile("anb", "Top-Anbieter", esc(anb[0][0]), "", `${anb[0][1].kosten != null ? de(anb[0][1].kosten, 0) + " €" : ""}${anb[0][1].kwh != null ? ` · ${de(anb[0][1].kwh, 0)} kWh` : ""}`) : "",
    ].filter(Boolean);
    el.innerHTML = this._hd("Analyse", "Kachel antippen für Details") + `<div class="ptiles">${tiles.join("")}</div>`;
  }

  /* Wirtschaftlichkeit Netz-Zuschuss: Skala Einspeisevergütung → Netzpreis, Marker Schwelle und Mischpreis */
  _render_misch() {
    const el = this.shadowRoot.getElementById("pmisch"), lv = this._live();
    if (this.shadowRoot.activeElement?.classList?.contains("pvminsel")) return;   // Auswahl offen
    const fi = parseFloat(lv.tariff_feedin), gr = parseFloat(lv.tariff_grid);
    if (isNaN(fi) || isNaN(gr) || gr <= fi) { el.innerHTML = this._hd("Netz-Zuschuss") + `<div class="empty">evcc meldet keine Tarife (Netzpreis und Einspeisevergütung).</div>`; return; }
    const a = this._ea("evcc_mode_control")?.attributes || {};
    const sur = typeof a.pv_ueberschuss_w === "number" ? a.pv_ueberschuss_w : null, minP = typeof a.wallbox_min_power_w === "number" ? a.wallbox_min_power_w : null;
    const thr = typeof a.pv_override_max_mischpreis_kwh === "number" ? a.pv_override_max_mischpreis_kwh : null;
    let cur = null;
    if (sur != null && minP > 0) { const c = Math.max(0, Math.min(sur, minP)); cur = (c * fi + (minP - c) * gr) / minP; }
    const pct = (v) => Math.max(0, Math.min(100, ((v - fi) / (gr - fi)) * 100));
    const pm = this._pvMinCur(a), solarMin = pm.has || pm.v != null ? (pm.v == null ? null : Math.round(pm.v)) : thr != null ? Math.round((1 - pct(thr) / 100) * 100) : null;
    const note = cur == null ? "Noch keine Live-Daten von evcc." : thr == null ? "Kein Mindest-Solaranteil konfiguriert – PV-Überschuss unter der Mindestladeleistung wird mit Netzstrom ergänzt."
      : cur <= thr ? "Mischpreis innerhalb der Schwelle – ein Netz-Zuschuss würde genutzt." : "Mischpreis über der Schwelle – der Überschuss wird eingespeist statt teuren Netzstrom zuzukaufen.";
    el.innerHTML = this._hd("Netz-Zuschuss", solarMin != null ? `lohnt ab <b>${solarMin} % PV</b>` : "") + `
      <div class="mscale">${thr != null ? `<span class="ms" style="left:${pct(thr)}%"></span>` : ""}${cur != null ? `<span class="mc" style="left:${pct(cur)}%"></span>` : ""}</div>
      <div class="mlab"><span>Einspeisung ${de(fi, 3)} €</span><span>Netz ${de(gr, 3)} €</span></div>
      <div class="pstats two${this._pvMinSel(a) ? " three" : ""}"><div class="pst"><span>Mischpreis jetzt</span><b>${cur != null ? de(cur, 3) : "–"}<small>€/kWh</small></b></div>
        <div class="pst"><span>Schwelle</span><b>${thr != null ? de(thr, 3) : "–"}<small>€/kWh</small></b></div>${this._pvMinSel(a)}</div>
      <div class="pnote">${note}</div>`;
  }

  _openAna(k) { this._anaK = k; this._openDlg("ana"); this._renderAnaDlg(); }
  _renderAnaDlg() {
    const d = this.shadowRoot.getElementById("cardlg");
    if (!d || this._dlg !== "ana") return;
    const A = this._anaData(), k = this._anaK, num = (v, dd) => (typeof v === "number" ? de(v, dd) : "–");
    const col = (t, o, rows) => `<div class="pcol"><h4>${t}</h4>${rows.filter(Boolean).map(([l, v]) => `<p>${l}<b>${v}</b></p>`).join("")}</div>`;
    let title = "", sub = "", body = "";
    if (k === "temp") {
      title = "Verbrauch nach Temperatur"; sub = "Ø kWh/100 km je Temperaturband (mind. 3 Fahrten)";
      const B = A.R.verbrauch_nach_temperatur || {}, ks = ["<0°C", "0-10°C", "10-20°C", ">20°C"].filter((x) => B[x] !== undefined), mx = Math.max(0.1, ...ks.map((x) => B[x]));
      body = ks.length ? `<div class="pbands">${ks.map((x) => `<div class="${x === A.R.temperaturband_aktuell ? "cur" : ""}"><em>${de(B[x], 1)}</em><i style="height:${(B[x] / mx) * 100}%"></i><small>${esc(x)}</small></div>`).join("")}</div>`
        : `<div class="empty">Noch keine Außentemperatur konfiguriert oder zu wenige Fahrten je Temperaturband.</div>`;
    } else if (k === "bat") {
      title = "Batterie"; sub = "Geschätzte Kapazität und Vollzyklen";
      body = `<div class="pcols">${col("Kapazität", 0, [["geschätzt", `${num(parseFloat(this._ea("battery_capacity")?.state), 1)} kWh`], ["Vollzyklen", num(parseFloat(this._ea("equivalent_full_cycles")?.state), 1)]])}</div>
        <div class="pnote">Rollierender Schnitt aus Fremd- und Heimladungen mit großem SoC-Hub. Der Wert liegt meist über der echten Kapazität (Ladeverluste) – entscheidend ist der Trend über Monate. Vollzyklen aus Fahrtenbuch und Ladungen (0→100→0 = 1 Zyklus).</div>`;
    } else if (k === "anb") {
      title = "Verteilung nach Anbieter"; sub = "Nur tatsächliche Ladungskosten, ohne Grundgebühren";
      const l = [...A.anb].sort((a, b) => (b[1].kwh ?? b[1].kosten ?? 0) - (a[1].kwh ?? a[1].kosten ?? 0)), byK = l.some(([, v]) => typeof v.kwh === "number");
      const mx = Math.max(0.1, ...l.map(([, v]) => (byK ? v.kwh : v.kosten) || 0));
      body = `<div class="panb">${l.map(([n, v]) => `<div><p><b>${esc(n)}</b><span>${byK ? `${num(v.kwh, 1)} kWh` : `${num(v.kosten, 2)} €`}${typeof v.preis_je_kwh === "number" ? ` · Ø ${de(v.preis_je_kwh, 3)} €/kWh` : ""}</span></p><i><em style="width:${(((byK ? v.kwh : v.kosten) || 0) / mx) * 100}%"></em></i></div>`).join("")}</div>`;
    } else {
      title = "Ladeorte"; sub = "Heim und Fremd über alle Ladungen";
      const h = A.heim, f = A.fremd, ac = A.acdc.ac, dc = A.acdc.dc;
      body = `<div class="pcols">${col(`Heim · ${num(h.kwh_anteil_pct, 0)} %`, 0, [["Energie", `${num(h.kwh, 1)} kWh`], ["Kosten", `${num(h.kosten, 2)} €`], ["Ø Preis", `${num(h.preis_je_kwh, 3)} €/kWh`], ["Solaranteil", `${num(h.solar_pct, 1)} %`]])}
        ${col(`Fremd · ${num(f.kwh_anteil_pct, 0)} %`, 0, [["Energie", `${num(f.kwh, 1)} kWh`], ["Kosten", `${num(f.kosten, 2)} €`], ["Ø Preis", `${num(f.preis_je_kwh, 3)} €/kWh`]])}</div>
        <div class="pcols">${col("Gesamt", 0, [["€/100 km", num(A.L.eur_je_100km, 2)], ["Autarkie", `${num(A.L.gesamt_autarkie_pct, 1)} %`]])}
        ${ac || dc ? col("Fremd nach AC / DC", 0, [ac && ["AC", `${num(ac.anzahl, 0)} × · ${num(ac.kwh, 0)} kWh · Ø ${num(ac.preis_je_kwh, 2)} €`], dc && ["DC", `${num(dc.anzahl, 0)} × · ${num(dc.kwh, 0)} kWh · Ø ${num(dc.preis_je_kwh, 2)} €`]]) : ""}</div>
        <div class="pnote">Solaranteil nur für Heimladungen, die evcc gesteuert hat. Fremdladung zählt beim Autarkiegrad als 0 % Solar. AC/DC geschätzt aus der Ø Ladeleistung je Ladung.</div>`;
    }
    d.innerHTML = `<div class="dpan pdlg"><div class="dhd"><span class="dico">${icon("mdi:chart-box-outline")}</span>
      <span class="rtx"><span class="rname">${title}</span><span class="rsub">${sub}</span></span>
      <button class="dx" data-act="cardclose" aria-label="Schließen">${icon("mdi:close")}</button></div><div class="dbody">${body}</div></div>`;
  }

  /* ---------- Unterseite „Laden & Kosten“ (Ladungen, Fahrten und Verbrenner-Vergleich aus ev_assistant) ---------- */
  // Zeitraum: Tag / Woche / Monat / Jahr / Gesamt, mit Blättern (off = 0 aktuell, -1 davor …)
  _cpGet() {
    if (this._cp) return this._cp;
    let p = null; try { p = localStorage.getItem("mg-car-cost-period"); } catch (x) {}
    return (this._cp = { p: ["day", "week", "month", "year", "all"].includes(p) ? p : "month", off: 0 });
  }
  _cpRange(p = this._cpGet().p, off = this._cpGet().off) {
    const n = new Date();
    let a, b, unit, label;
    if (p === "day") { a = new Date(n.getFullYear(), n.getMonth(), n.getDate() + off); b = new Date(a); b.setDate(b.getDate() + 1); unit = "hour";
      label = off === 0 ? "Heute" : off === -1 ? "Gestern" : `${WD[a.getDay()]} ${a.getDate()}. ${MON[a.getMonth()]}${a.getFullYear() !== n.getFullYear() ? ` ${a.getFullYear()}` : ""}`; }
    else if (p === "week") { const d = (n.getDay() + 6) % 7; a = new Date(n.getFullYear(), n.getMonth(), n.getDate() - d + off * 7); b = new Date(a); b.setDate(b.getDate() + 7); unit = "day";
      const e = new Date(b - 86400000); label = `${a.getDate()}. ${MON[a.getMonth()]} – ${e.getDate()}. ${MON[e.getMonth()]}${e.getFullYear() !== n.getFullYear() ? ` ${e.getFullYear()}` : ""}`; }
    else if (p === "month") { a = new Date(n.getFullYear(), n.getMonth() + off, 1); b = new Date(a.getFullYear(), a.getMonth() + 1, 1); unit = "day"; label = `${MON_LONG[a.getMonth()]} ${a.getFullYear()}`; }
    else if (p === "year") { a = new Date(n.getFullYear() + off, 0, 1); b = new Date(a.getFullYear() + 1, 0, 1); unit = "month"; label = String(a.getFullYear()); }
    else {
      const first = Math.min(...[...(this._charges?.list || []).map((x) => x.ts), ...(this._evaTrips?.list || []).map((t) => new Date(t.start).getTime())].filter((x) => x > 0), n.getTime());
      const f = new Date(first); a = new Date(f.getFullYear(), f.getMonth(), 1); b = new Date(n.getFullYear(), n.getMonth() + 1, 1); unit = "month"; label = "Seit Beginn";
    }
    return { a: a.getTime(), b: b.getTime(), unit, label };
  }
  // Höhe der Ladungsliste: so groß, dass die linke Spalte bis zum Fensterrand reicht und die Seite nicht scrollt
  _kFit() {
    const box = this.shadowRoot.querySelector("#klist .klist"), col = this.shadowRoot.querySelector("#pcost");
    if (!box || !col || col.hidden) return;
    const narrow = col.getBoundingClientRect().width < 900;
    let h = narrow ? Math.round(window.innerHeight * 0.6) : Math.floor(window.innerHeight - box.getBoundingClientRect().top - 44);
    h = Math.max(220, h);
    if (box._h !== h) { box._h = h; box.style.maxHeight = h + "px"; }
  }
  _cpBuckets(R) {
    const out = [], d = new Date(R.a);
    while (d.getTime() < R.b && out.length < 400) {
      const s = d.getTime();
      if (R.unit === "hour") d.setHours(d.getHours() + 1); else if (R.unit === "day") d.setDate(d.getDate() + 1); else d.setMonth(d.getMonth() + 1);
      out.push([s, d.getTime()]);
    }
    return out;
  }
  // Ladekarten-Grundgebühren im Zeitraum (je Tag anteilig aus der jeweils gültigen Preisstufe)
  _cpFees(a, b) {
    const karten = this._ea("ladekarten_kosten")?.attributes?.karten || [];
    let sum = 0;
    const day = 86400000, end = Math.min(b, Date.now());
    for (const k of karten) {
      const st = [...(k.gebuehren || [])].sort((x, y) => (x.ab_datum < y.ab_datum ? -1 : 1));
      const k0 = k.start_datum ? new Date(k.start_datum).getTime() : -Infinity, k1 = k.end_datum ? new Date(k.end_datum).getTime() + day : Infinity;
      for (let t = Math.max(a, k0); t < Math.min(end, k1); t += day) {
        const iso = new Date(t).toISOString().slice(0, 10);
        const g = st.filter((s) => s.ab_datum <= iso).pop() || st[0];
        if (g) sum += (Number(g.gebuehr) || 0) * 12 / 365.25 * Math.min(1, (Math.min(end, k1, t + day) - t) / day);
      }
    }
    return sum;
  }
  // Ladung → Quelle: Heim PV/Netz (nach PV-Anteil) oder Fremd AC/DC
  _cpSplit(x, feedin) {
    if (x.type === "home") {
      const k = x.kwh || 0, pv = x.pv != null ? Math.max(0, Math.min(100, x.pv)) / 100 : 0, pvK = k * pv, grK = k - pvK;
      const pvC = x.cost != null && feedin != null ? Math.min(x.cost, pvK * feedin) : null;   // PV mit der entgangenen Einspeisevergütung bewertet
      return { pv: [pvK, pvC ?? 0], gr: [grK, x.cost != null ? x.cost - (pvC ?? 0) : 0] };
    }
    const dc = /dc/i.test(x.ac || "") || (!/ac/i.test(x.ac || "") && x.kwh > 0 && x.dur > 0 && x.kwh / (x.dur / 60) > 22);
    return { [dc ? "dc" : "ac"]: [x.kwh || 0, x.cost || 0] };
  }
  _cpSum(a, b) {
    const feedin = parseFloat(this._live().tariff_feedin), fi = isNaN(feedin) ? null : feedin;
    const S = { pv: [0, 0], gr: [0, 0], ac: [0, 0], dc: [0, 0], n: 0, km: 0, tk: 0, list: [] };
    for (const x of this._charges?.list || []) {
      if (!(x.ts >= a && x.ts < b)) continue;
      S.n++; S.list.push(x);
      for (const [k, v] of Object.entries(this._cpSplit(x, fi))) { S[k][0] += v[0]; S[k][1] += v[1]; }
    }
    for (const t of this._evaTrips?.list || []) {
      const ts = new Date(t.start).getTime();
      if (!(ts >= a && ts < b)) continue;
      S.km += parseFloat(t.strecke) || 0; if (parseFloat(t.verbrauch_kwh) > 0 && parseFloat(t.strecke) > 0) { S.tk += parseFloat(t.verbrauch_kwh); S.tkm = (S.tkm || 0) + parseFloat(t.strecke); }
    }
    S.kwh = S.pv[0] + S.gr[0] + S.ac[0] + S.dc[0];
    S.cost = S.pv[1] + S.gr[1] + S.ac[1] + S.dc[1];
    S.fees = this._cpFees(a, b);
    S.total = S.cost + S.fees;
    return S;
  }

  _render_cost() {
    const sr = this.shadowRoot;
    if (!this._charges || Date.now() - this._charges.t > 5 * 60000) this._loadCharges();
    if (!this._evaTrips) this._loadTrips();
    const cp = this._cpGet(), R = this._cpRange(), S = this._cpSum(R.a, R.b);
    const P = this._cpRange(cp.p, cp.off - 1), SP = cp.p === "all" ? null : this._cpSum(P.a, P.b);
    const loading = !this._charges;
    // Zeitraum-Leiste neben den Seiten-Tabs
    const per = [["day", "Tag"], ["week", "Woche"], ["month", "Monat"], ["year", "Jahr"], ["all", "Gesamt"]];
    sr.getElementById("kper").innerHTML = `<div class="hsegs">${per.map(([k, l]) => `<button class="hseg ${cp.p === k ? "sel" : ""}" data-act="cper" data-v="${k}">${l}</button>`).join("")}</div>
      <div class="knav">${cp.p !== "all" ? `<button class="sic" data-act="cnav" data-d="-1" aria-label="Zurück">${icon("mdi:chevron-left")}</button>` : ""}<b>${esc(R.label)}</b>${cp.p !== "all" ? `<button class="sic" data-act="cnav" data-d="1" aria-label="Weiter"${cp.off >= 0 ? " disabled" : ""}>${icon("mdi:chevron-right")}</button>` : ""}</div>`;

    // --- Geladen: Balken je Stunde/Tag/Monat, gestapelt nach Quelle ---
    const feedin = parseFloat(this._live().tariff_feedin), fi = isNaN(feedin) ? null : feedin;
    const B = this._cpBuckets(R).map(([s, e]) => {
      const v = { pv: 0, gr: 0, ac: 0, dc: 0, s, e };
      for (const x of S.list) if (x.ts >= s && x.ts < e) for (const [k, w] of Object.entries(this._cpSplit(x, fi))) v[k] += w[0];
      return v;
    });
    const mx = Math.max(0.1, ...B.map((v) => v.pv + v.gr + v.ac + v.dc));
    const lab = (s) => { const d = new Date(s); return R.unit === "hour" ? `${d.getHours()}` : R.unit === "day" ? (cp.p === "week" ? WD[d.getDay()] : `${d.getDate()}`) : cp.p === "all" ? `${MON[d.getMonth()]} ${String(d.getFullYear()).slice(2)}` : MON[d.getMonth()]; };
    const every = B.length > 24 ? Math.ceil(B.length / 12) : B.length > 14 ? 3 : 1;
    const tip = (v) => { const d = new Date(v.s), t = v.pv + v.gr + v.ac + v.dc;
      const when = R.unit === "hour" ? `${pad(d.getHours())}:00` : R.unit === "day" ? `${WD[d.getDay()]} ${d.getDate()}. ${MON[d.getMonth()]}` : `${MON_LONG[d.getMonth()]} ${d.getFullYear()}`;
      return `${when}: ${de(t, 1)} kWh${v.pv ? ` · PV ${de(v.pv, 1)}` : ""}${v.gr ? ` · Netz ${de(v.gr, 1)}` : ""}${v.ac ? ` · AC ${de(v.ac, 1)}` : ""}${v.dc ? ` · DC ${de(v.dc, 1)}` : ""}`; };
    const bars = B.map((v) => { const t = v.pv + v.gr + v.ac + v.dc;
      return `<div class="kc" style="height:${(t / mx) * 100}%" title="${esc(tip(v))}">${[["pv", "kpv"], ["gr", "kgr"], ["ac", "kac"], ["dc", "kdc"]].filter(([k]) => v[k] > 0).map(([k, c]) => `<i class="${c}" style="height:${(v[k] / t) * 100}%"></i>`).join("")}</div>`; }).join("");
    const ax = B.map((v, i) => `<span>${i % every === 0 ? lab(v.s) : ""}</span>`).join("");
    const pvPct = S.pv[0] + S.gr[0] > 0.05 ? Math.round((S.pv[0] / S.kwh) * 100) : null;
    const delta = (cur, prev) => { if (!SP || !(prev > 0.05)) return ""; const d = Math.round(((cur - prev) / prev) * 100); return `<em class="${d > 0 ? "up" : ""}">${d > 0 ? "+" : ""}${d} % ggü. ${cp.p === "month" ? MON[new Date(P.a).getMonth()] : cp.p === "year" ? P.label : cp.p === "week" ? "Vorwoche" : "Vortag"}</em>`; };
    const cons = S.tkm > 1 ? (S.tk / S.tkm) * 100 : null, per100 = S.km > 1 ? (S.total / S.km) * 100 : null;
    const kp = (l, v, u, ex = "") => `<div><span>${l}</span><b>${v}</b><small>${u}</small>${ex}</div>`;
    sr.getElementById("kgel").innerHTML = this._hd("Geladen", loading ? "Lädt …" : `<b>${de(S.kwh, 1)} kWh</b>${pvPct != null ? ` · ${pvPct} % PV` : ""}`)
      + `<div class="kchart">${bars}</div><div class="kax">${ax}</div>
      <div class="klg"><span><i class="kpv"></i>Heim PV</span><span><i class="kgr"></i>Heim Netz</span><span><i class="kac"></i>Fremd AC</span><span><i class="kdc"></i>Fremd DC</span></div>
      <div class="kkp">${kp("Energie", de(S.kwh, 1), "kWh", delta(S.kwh, SP?.kwh))}${kp("Kosten", de(S.total, 2), "€", delta(S.total, SP?.total))}${kp("Ø Preis", S.kwh > 0.1 ? de((S.cost / S.kwh) * 100, 1) : "–", "ct/kWh")}
        ${kp("Strecke", de(S.km, 0), "km")}${kp("Verbrauch", cons != null ? de(cons, 1) : "–", "kWh/100")}${kp("€ / 100 km", per100 != null ? de(per100, 2) : "–", "€")}</div>`;

    // --- Ladungen im Zeitraum: alle des Zeitraums in einer scrollbaren Liste, weitere werden beim Scrollen nachgeladen ---
    // Sortierung: Datum, kWh oder Kosten; erneutes Tippen dreht die Richtung um
    const so = this._kSort || (this._kSort = { k: "ts", d: -1 }), kKey = `${cp.p}|${cp.off}|${so.k}|${so.d}`;
    if (this._kKey !== kKey) { this._kKey = kKey; this._kN = 30; }
    const val = (x) => (so.k === "kwh" ? x.kwh : so.k === "cost" ? x.cost : x.ts) ?? -Infinity;
    const all = [...S.list].sort((x, y) => (val(x) - val(y)) * so.d || y.ts - x.ts), shown = Math.min(this._kN, all.length);
    this._kMore = shown < all.length;
    const rows = all.slice(0, shown).map((x) => {
      const d = new Date(x.ts), ed = x.type === "ext" && x.raw?.erfasst_ts != null;
      const sp = this._cpSplit(x, fi), what = x.type === "home" ? `Zuhause${x.pv != null ? ` · ${Math.round(x.pv)} % PV` : ""}` : `${esc(x.who)} · ${sp.dc ? "DC" : "AC"}`;
      return `<div class="krow${ed ? " ted" : ""}"${ed ? ` data-act="set" data-k="ch-edit" data-id="${esc(x.raw.erfasst_ts)}" title="Fremdladung bearbeiten"` : ""}>
        <span class="kri ${x.type}">${icon(x.type === "home" ? "mdi:home-lightning-bolt" : "mdi:ev-station")}</span>
        <span class="krt"><b>${WD[d.getDay()]} ${d.getDate()}. ${MON[d.getMonth()]}</b><small>${what}${x.s0 != null && x.s1 != null ? ` · ${Math.round(x.s0)} → ${Math.round(x.s1)} %` : ""}</small></span>
        <span class="krv"><b>${x.kwh != null ? de(x.kwh, 1) : "–"} kWh</b><small>${x.cost != null ? `${de(x.cost, 2)} €` : ""}</small></span></div>`;
    }).join("");
    const kl = sr.getElementById("klist"), oldBox = kl.querySelector(".klist"), keepTop = oldBox && this._kKeyShown === kKey ? oldBox.scrollTop : 0;
    const sb = (k, l) => `<button class="hseg ${so.k === k ? "sel" : ""}" data-act="ksort" data-v="${k}" title="${so.k === k ? (so.d < 0 ? "absteigend – erneut tippen für aufsteigend" : "aufsteigend – erneut tippen für absteigend") : `nach ${l} sortieren`}">${l}${so.k === k ? `<i class="kdir">${so.d < 0 ? "↓" : "↑"}</i>` : ""}</button>`;
    // Kopfzeile: links Überschrift, mittig Sortierung, rechts Anzahl
    kl.innerHTML = `<div class="hd khd"><span class="ttl">Ladungen im Zeitraum</span>${S.n > 1 ? `<div class="hsegs ksort">${sb("ts", "Datum")}${sb("kwh", "Menge")}${sb("cost", "Kosten")}</div>` : "<span></span>"}<span class="lbl">${S.n} Ladung${S.n === 1 ? "" : "en"}</span></div>`
      + (rows ? `<div class="klist">${rows}${this._kMore ? `<div class="kmore">${shown} von ${all.length} – weiter scrollen</div>` : ""}</div>` : `<div class="empty">${loading ? "Lädt …" : "Keine Ladungen in diesem Zeitraum."}</div>`);
    this._kKeyShown = kKey;
    const box = kl.querySelector(".klist");
    if (box) {
      if (box.scrollTop !== keepTop) box.scrollTop = keepTop;
      if (!box._sc) {   // beim Scrollen ans Ende die nächsten Ladungen anhängen
        box._sc = true;
        box.addEventListener("scroll", () => { if (this._kMore && box.scrollHeight - box.scrollTop - box.clientHeight < 300) { this._kMore = false; this._kN += 30; this._render_cost(); } }, { passive: true });
      }
      requestAnimationFrame(() => this._kFit());
    }

    // --- Aufschlüsselung ---
    const src = [["kpv", "Heim PV", S.pv], ["kgr", "Heim Netz", S.gr], ["kac", "Fremd AC", S.ac], ["kdc", "Fremd DC", S.dc]];
    const tot = Math.max(0.01, S.kwh);
    sr.getElementById("kauf").innerHTML = this._hd("Aufschlüsselung", esc(R.label))
      + `<div class="kbar">${src.map(([c, , v]) => (v[0] > 0 ? `<i class="${c}" style="width:${(v[0] / tot) * 100}%"></i>` : "")).join("")}</div>
      <div class="ksrc">${src.map(([c, l, v]) => `<div class="${v[0] > 0 ? "" : "z"}"><i class="${c}"></i><span>${l}</span><b>${de(v[0], 1)} kWh</b><small>${de(v[1], 2)} €${v[0] > 0.05 ? ` · ${de((v[1] / v[0]) * 100, 0)} ct` : ""}</small></div>`).join("")}
        ${S.fees > 0.005 ? `<div><i class="kfee"></i><span>Ladekarten-Gebühren</span><b></b><small>${de(S.fees, 2)} €</small></div>` : ""}</div>
      ${fi != null && S.pv[0] > 0 ? `<div class="pnote">Heim-PV ist mit der Einspeisevergütung (${de(fi * 100, 1)} ct) bewertet, der Rest der Heimkosten zählt als Netz.</div>` : ""}`;

    // --- Vergleich Verbrenner ---
    const sv = this._ea("savings"), sa = sv?.attributes || {}, vK = parseFloat(sa.kosten_verbrenner_geschaetzt), gk = parseFloat(sa.gefahrene_km);
    const rate = vK > 0 && gk > 0 ? vK / gk : null, fuel = parseFloat(this._ea("verbrenner_price_selected")?.state);
    const el = sr.getElementById("kcmp");
    if (rate == null) { el.innerHTML = this._hd("Vergleich Verbrenner") + `<div class="empty">ev_assistant hat noch keinen Verbrenner-Vergleich – dafür in den ev_assistant-Optionen (Schritt „Vergleich“) Verbrauch und Spritpreis des Verbrenners eintragen.</div>`; return; }
    const vC = S.km * rate, saved = vC - S.total, mxc = Math.max(0.01, vC, S.total);
    const lPer100 = !isNaN(fuel) && fuel > 0 ? (rate * 100) / fuel : null, liters = lPer100 != null ? (S.km * lPer100) / 100 : null;
    const co2 = parseFloat(this._ea("co2_savings")?.state), co2P = !isNaN(co2) && gk > 0 ? (co2 / gk) * S.km : null;
    const sinceAll = parseFloat(sv?.state);
    el.innerHTML = this._hd("Vergleich Verbrenner", lPer100 != null ? `${de(lPer100, 1)} l/100 · ${de(fuel, 2)} €/l` : "")
      + `<div class="ksave ${saved < 0 ? "neg" : ""}"><span>${saved >= 0 ? "Gespart" : "Mehrkosten"} · ${esc(R.label)}</span><div><b>${de(Math.abs(saved), 2)} €</b>${!isNaN(sinceAll) && cp.p !== "all" ? `<small> · seit Einrichtung ${de(sinceAll, 0)} €</small>` : ""}</div></div>
      <div class="kcb"><p>Elektro<b>${de(S.total, 2)} €</b></p><div class="kbar2"><i style="width:${(S.total / mxc) * 100}%;background:var(--green)"></i></div></div>
      <div class="kcb"><p>Verbrenner (geschätzt)<b>${de(vC, 2)} €</b></p><div class="kbar2"><i style="width:${(vC / mxc) * 100}%;background:#94a3b8"></i></div></div>
      <div class="kmini"><div><span>€ / 100 km</span><b>${per100 != null ? de(per100, 2) : "–"}</b><small>vs ${de(rate * 100, 2)}</small></div>
        <div><span>Liter</span><b>${liters != null ? de(liters, 0) : "–"}</b><small>gespart</small></div><div><span>CO₂</span><b>${co2P != null ? de(co2P, 0) : "–"}</b><small>kg weniger</small></div></div>
      <div class="pnote">Verbrenner: Kosten je km aus dem ev_assistant-Vergleich seit Einrichtung, mal den gefahrenen km im Zeitraum.</div>`;
  }

  /* ---------- Unterseite „Einstellungen“ (Wartung, Ladekarten, Einstellungen aus ev_assistant) ---------- */
  _render_set() {
    this._render_wart(); this._render_lk(); this._render_url(); this._render_img(); this._render_data(); this._render_log();
  }
  // nur neu zeichnen, wenn sich die Daten geändert haben (sonst gingen offene Datei-Auswahlen verloren)
  _setSig(el, sig) { if (el._sig === sig) return false; el._sig = sig; return true; }
  _fdate(iso) { if (!iso) return "–"; const d = new Date(iso); return isNaN(d) ? esc(iso) : d.toLocaleDateString("de-DE"); }
  _fmonth(iso) { if (!iso) return "–"; const d = new Date(iso); return isNaN(d) ? esc(iso) : d.toLocaleDateString("de-DE", { month: "2-digit", year: "numeric" }); }
  _toast(message) { this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true })); }
  // ev_assistant-Dienst für das gewählte Fahrzeug aufrufen; Fehler im offenen Formular bzw. als Hinweis zeigen
  _evaCall(service, data = {}) {
    const config_entry_id = this._evaEntryId();
    if (!config_entry_id) { this._toast("ev_assistant nicht gefunden"); return Promise.reject(new Error("ev_assistant nicht gefunden")); }
    return Promise.resolve(this._hass.callService("ev_assistant", service, { config_entry_id, ...data })).catch((x) => {
      const msg = x?.message || x?.error?.message || String(x);
      const err = this._dlg === "form" && this.shadowRoot.querySelector("#cardlg .ferr");
      if (err) err.textContent = msg; else this._toast(msg);
      throw x;
    });
  }

  /* Wartung */
  _wartData() {
    const a = this._ea("wartung_faellig")?.attributes || {};
    return { punkte: Array.isArray(a.punkte) ? a.punkte : [], presets: Array.isArray(a.presets) ? a.presets : [] };
  }
  // Dringlichkeit des nächsten Termins: gelb, ab 500 km / 4 Wochen orange, ab 100 km / 1 Woche (und überfällig) rot
  _wartLevel(p) {
    if (p.aktiv === false) return "off";
    const d = p.rest_tage, k = p.rest_km;
    if (d == null && k == null) return "unk";
    if ((d != null && d <= 7) || (k != null && k <= 100)) return "red";
    if ((d != null && d <= 28) || (k != null && k <= 500)) return "orange";
    return "yellow";
  }
  // warum ev_assistant (noch) keine Fälligkeit liefert – mit Hinweis, was fehlt
  _wartWhyNot(p) {
    const ld = p.last_done || {}, hasStart = ld.km != null || !!ld.datum;
    const kmI = p.km_intervall_wirksam ?? p.km_intervall, zI = p.zeit_intervall_wirksam ?? p.zeit_intervall_monate;
    let t = "noch nicht berechenbar", h = "";
    if (!hasStart && !p.festes_datum) { t = "Startpunkt fehlt"; h = "Bearbeiten → Letzter Service: Datum der Erstzulassung und 0 km eintragen – ab da zählt das Intervall."; }
    else if (kmI && ld.km != null && !(zI && ld.datum)) { t = "km-Stand unbekannt"; h = zI ? "Für die Zeit fehlt das Datum des letzten Service. Für die km meldet ev_assistant keinen aktuellen km-Stand." : "ev_assistant meldet keinen aktuellen km-Stand."; }
    else if (zI && !ld.datum && !kmI) { t = "Datum fehlt"; h = "Bearbeiten → Letzter Service: Datum eintragen."; }
    return `<b>${t}</b>${h ? `<button class="whint" data-act="set" data-k="wt-edit" data-id="${p.id}">${h}</button>` : ""}`;
  }
  _render_wart() {
    const el = this.shadowRoot.getElementById("swart"), { punkte } = this._wartData();
    if (!this._setSig(el, this._evaEntryId() + JSON.stringify(punkte) + new Date().toDateString())) return;
    const add = `<button class="sbt" data-act="set" data-k="wt-add">${icon("mdi:plus")}Anlegen</button>`;
    if (!punkte.length) { el.innerHTML = this._hd("Wartung", add) + `<div class="empty">Noch kein Wartungspunkt angelegt – z. B. HU oder Inspektion, fällig nach Kilometerstand, Zeit oder beidem (je nachdem, was zuerst kommt).</div>`; return; }
    const tage = (n) => { n = Math.abs(n); return n >= 60 ? `${Math.round(n / 30.44)} Monaten` : n >= 14 ? `${Math.round(n / 7)} Wochen` : `${n} Tag${n === 1 ? "" : "en"}`; };
    const items = punkte.map((p) => {
      const lv = this._wartLevel(p), over = (p.rest_tage != null && p.rest_tage < 0) || (p.rest_km != null && p.rest_km < 0) || p.status === "ueberfaellig";
      const kmI = p.km_intervall_wirksam ?? p.km_intervall, zI = p.zeit_intervall_wirksam ?? p.zeit_intervall_monate;
      // wie lange noch bis zum nächsten Termin (Zeit und km)
      const parts = [];
      if (p.rest_tage != null) parts.push(p.rest_tage >= 0 ? `in ${tage(p.rest_tage)}` : `seit ${tage(p.rest_tage)} überfällig`);
      if (p.rest_km != null) parts.push(p.rest_km >= 0 ? `noch ${de(p.rest_km, 0)} km` : `${de(-p.rest_km, 0)} km drüber`);
      const ziel = [p.faellig_datum && (p.naechste_quelle === "fest" ? this._fmonth(p.faellig_datum) : this._fdate(p.faellig_datum)),
        p.last_done?.km != null && kmI ? `bei ${de(p.last_done.km + kmI, 0)} km` : null].filter(Boolean).join(" · ");
      // Fortschritt seit dem letzten Termin (km oder Zeit, was weiter ist)
      let prog = null;
      if (kmI && p.rest_km != null) prog = (kmI - p.rest_km) / kmI;
      if (zI && p.last_done?.datum) {
        const a = new Date(p.last_done.datum), b = new Date(a); b.setMonth(b.getMonth() + Number(zI));
        const f = (Date.now() - a.getTime()) / Math.max(1, b.getTime() - a.getTime());
        prog = prog == null ? f : Math.max(prog, f);
      }
      const n = p.erledigt_anzahl != null ? p.erledigt_anzahl : p.last_done && (p.last_done.km != null || p.last_done.datum) ? 1 : 0;
      const first = p.intervall_phase === "erst";
      const done = n > 0 || p.last_done?.datum || p.last_done?.km != null
        ? `<span class="wdone">${icon("mdi:check-circle")}${n > 1 ? `${n}× erledigt · ` : ""}zuletzt ${[p.last_done?.km != null && `${de(p.last_done.km, 0)} km`, p.last_done?.datum && this._fdate(p.last_done.datum)].filter(Boolean).join(" · ") || "erledigt"}</span>` : "";
      const krit = [kmI && `alle ${de(kmI, 0)} km`, zI && `alle ${zI} Monate`, p.festes_datum && `fest ${this._fmonth(p.festes_datum)}`].filter(Boolean).join(" · ");
      const nach = first && (p.km_intervall || p.zeit_intervall_monate) ? ` · danach ${[p.km_intervall && `${de(p.km_intervall, 0)} km`, p.zeit_intervall_monate && `${p.zeit_intervall_monate} Monate`].filter(Boolean).join(" / ")}` : "";
      return `<div class="witem ${lv}${over ? " over" : ""}"><div class="stop"><b>${esc(p.name)}</b>${first ? `<span class="stag">1. Termin</span>` : ""}${p.aktiv === false ? `<span class="stag">pausiert</span>` : ""}
          <span class="sacts"><button class="sic" data-act="set" data-k="wt-done" data-id="${p.id}" title="Als erledigt markieren">${icon("mdi:check")}</button><button class="sic" data-act="set" data-k="wt-edit" data-id="${p.id}" title="Bearbeiten">${icon("mdi:pencil")}</button><button class="sic" data-act="set" data-k="wt-del" data-id="${p.id}" title="Löschen">${icon("mdi:delete-outline")}</button></span></div>
        <div class="wnext"><span class="wlbl">${over ? "Überfällig" : "Nächster Termin"}</span>${parts.length ? `<b>${parts.join(" · ")}</b>${ziel ? `<small>${ziel}</small>` : ""}` : this._wartWhyNot(p)}</div>
        ${prog != null ? `<div class="wbar"><i style="width:${Math.max(2, Math.min(100, prog * 100)).toFixed(1)}%"></i></div>` : ""}
        <div class="smeta">${done}<span>${krit || "kein Kriterium"}${nach}</span>${p.kosten != null ? `<span>${de(p.kosten, 2)} €</span>` : ""}</div></div>`;
    }).join("");
    // Kopf: der nächste fällige aktive Punkt
    const act = punkte.filter((p) => p.aktiv !== false && (p.rest_tage != null || p.rest_km != null));
    const key = (p) => (p.rest_tage != null ? p.rest_tage : p.rest_km / 50);
    const nx = act.sort((a, b) => key(a) - key(b))[0];
    const lbl = nx ? `<span class="wsum ${this._wartLevel(nx)}">${esc(nx.name)} ${nx.rest_tage != null ? (nx.rest_tage >= 0 ? `in ${tage(nx.rest_tage)}` : "überfällig") : nx.rest_km >= 0 ? `in ${de(nx.rest_km, 0)} km` : "überfällig"}</span>` : "";
    el.innerHTML = `<div class="hd"><span class="ttl">Wartung</span><span class="lbl">${lbl}</span>${add}</div><div class="slist">${items}</div>`;
  }

  /* Ladekarten */
  _render_lk() {
    const el = this.shadowRoot.getElementById("slk"), a = this._ea("ladekarten_kosten")?.attributes || {};
    const karten = Array.isArray(a.karten) ? a.karten : [];
    if (!this._setSig(el, this._evaEntryId() + JSON.stringify(karten) + a.gesamt)) return;
    const add = `<button class="sbt" data-act="set" data-k="lk-add">${icon("mdi:plus")}Anlegen</button>`;
    if (!karten.length) { el.innerHTML = this._hd("Ladekarten", add) + `<div class="empty">Noch keine Ladekarte angelegt – z. B. eine Abo-Karte mit monatlicher Grundgebühr. Die aufgelaufene Gebühr fließt in die Fremdlade-Kosten ein (Ersparnis, €/100 km), aber nicht in den Preis je kWh.</div>`; return; }
    const today = new Date().toISOString().slice(0, 10);
    const items = karten.map((k) => {
      const aktiv = !k.end_datum || k.end_datum >= today, st = [...(k.gebuehren || [])].sort((x, y) => (x.ab_datum < y.ab_datum ? -1 : 1));
      const stufen = st.map((s, i) => `<span class="schip">ab ${this._fdate(s.ab_datum)} · <b>${de(s.gebuehr, 2)} €</b>${i ? `<button class="sx" data-act="set" data-k="lk-sdel" data-id="${k.id}" data-ab="${esc(s.ab_datum)}" title="Preisstufe entfernen">${icon("mdi:close")}</button>` : ""}</span>`).join("");
      return `<div class="sitem${aktiv ? "" : " off"}"><div class="stop"><b>${esc(k.name)}</b>${aktiv ? "" : `<span class="stag">gekündigt</span>`}<span class="scost">${de(k.kosten ?? 0, 2)} €</span>
          <span class="sacts"><button class="sic" data-act="set" data-k="lk-edit" data-id="${k.id}" title="Bearbeiten">${icon("mdi:pencil")}</button><button class="sic" data-act="set" data-k="lk-del" data-id="${k.id}" title="Löschen">${icon("mdi:delete-outline")}</button></span></div>
        <div class="smeta"><span>${de(k.aktuelle_gebuehr ?? 0, 2)} €/Monat aktuell</span><span>seit ${this._fdate(k.start_datum)}${k.end_datum ? ` bis ${this._fdate(k.end_datum)}` : ""}</span></div>
        <div class="schips">${stufen}<button class="schip add" data-act="set" data-k="lk-stufe" data-id="${k.id}">${icon("mdi:plus")}Preisänderung</button></div></div>`;
    }).join("");
    el.innerHTML = this._hd("Ladekarten", add) + `<div class="skpi"><b>${de(a.gesamt ?? 0, 2)}<small>€</small></b><span>Grundgebühren aufgelaufen</span></div><div class="slist">${items}</div>`;
  }

  /* Fahrzeugbild */
  _render_img() {
    const el = this.shadowRoot.getElementById("simg"), st = this._ea("vehicle_image");
    const src = st && !OFFLINE_HD.includes(st.state) ? st.attributes?.entity_picture : null;
    if (!this._setSig(el, (src || "") + "|" + (this._imgStatus || "") + this._imgBusy)) return;
    el.innerHTML = this._hd("Fahrzeugbild") + `<div class="simgbox">${src ? `<img src="${esc(src)}" alt="Fahrzeugbild">` : `<span class="dim">Kein Bild gesetzt</span>`}</div>
      <div class="pnote">JPEG, PNG oder WebP bis 10 MB. ev_assistant verkleinert es und entfernt alle Metadaten (z. B. GPS); Transparenz bleibt erhalten.</div>
      <div class="srow"><label class="sbt${this._imgBusy ? " dis" : ""}">${icon("mdi:image-plus-outline")}Bild auswählen…<input type="file" class="simgfile" accept="image/jpeg,image/png,image/webp" hidden ${this._imgBusy ? "disabled" : ""}></label>
      ${src ? `<button class="sbt" data-act="set" data-k="img-clear" ${this._imgBusy ? "disabled" : ""}>${icon("mdi:delete-outline")}Entfernen</button>` : ""}</div>
      ${this._imgStatus ? `<div class="pnote">${esc(this._imgStatus)}</div>` : ""}`;
  }
  async _uploadImg(file) {
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) { this._imgStatus = "Dieses Dateiformat wird nicht unterstützt. Erlaubt sind JPEG, PNG und WebP."; return this._render_img(); }
    if (file.size > 10 * 1024 * 1024) { this._imgStatus = "Die Bilddatei ist zu groß (maximal 10 MB)."; return this._render_img(); }
    this._imgBusy = true; this._imgStatus = "Wird hochgeladen…"; this._render_img();
    try {
      const form = new FormData(); form.append("file", file);
      const resp = this._hass.fetchWithAuth ? await this._hass.fetchWithAuth("/api/file_upload", { method: "POST", body: form })
        : await fetch("/api/file_upload", { method: "POST", body: form, headers: { Authorization: `Bearer ${this._hass.auth?.data?.access_token}` } });
      if (!resp.ok) throw new Error(`Upload fehlgeschlagen (HTTP ${resp.status}).`);
      const { file_id } = await resp.json();
      await this._evaCall("set_vehicle_image", { file_id });
      this._imgStatus = "Bild gesetzt.";
    } catch (x) { this._imgStatus = x?.message || String(x); }
    this._imgBusy = false; this._render_img();
  }

  /* Kennzahlen und Datensicherung */
  _render_data() {
    const el = this.shadowRoot.getElementById("sdata");
    if (!this._setSig(el, "1" + (this._dataBusy || ""))) return;
    const b = this._dataBusy;
    el.innerHTML = this._hd("Daten") + `<div class="sblk"><h4>Datensicherung</h4><div class="pnote">Sichert Fahrtenbuch, Ladehistorie, Ladekarten, Wartungsplan, Kennzahlen und Ereignisprotokoll als Datei – ohne die Konfiguration (evcc-Host, Entitäten).</div>
        <div class="srow"><button class="sbt" data-act="set" data-k="backup" ${b ? "disabled" : ""}>${icon("mdi:database-arrow-down-outline")}${b === "backup" ? "Wird erstellt…" : "Backup erstellen"}</button>
        <label class="sbt">${icon("mdi:database-arrow-up-outline")}Wiederherstellen…<input type="file" class="srestfile" accept="application/json" hidden></label></div></div>
      <div class="sblk"><h4>Fahrtenbuch</h4><div class="pnote">Export: alle Fahrten als CSV (Datum, Start, Ziel, km-Stände, Strecke). Import: Fahrten aus einer anderen Fahrtenbuch-App (CSV oder JSON) – vor dem Import gibt es eine Vorschau, schon vorhandene Fahrten (gleiche Startzeit) überspringt ev_assistant.</div>
        <div class="srow"><button class="sbt" data-act="set" data-k="fb-export" ${b ? "disabled" : ""}>${icon("mdi:file-delimited-outline")}${b === "fb" ? "Wird erstellt…" : "Als CSV exportieren"}</button>
        <label class="sbt">${icon("mdi:file-import-outline")}Fahrten importieren…<input type="file" class="simpfile" accept=".csv,.txt,.json,text/csv,application/json" hidden></label></div></div>
      <div class="sblk"><h4>Kennzahlen seit Einrichtung</h4><div class="pnote">Setzt Verbrauch, Ersparnis und CO₂-Ersparnis auf einen neuen Startpunkt – z. B. wenn sie durch fehlerhafte Sensordaten kurz nach der Einrichtung verzerrt sind. Fahrtenbuch, Ladehistorie, Leasing und Wartung bleiben unverändert.</div>
        <div class="srow"><button class="sbt" data-act="set" data-k="reset">${icon("mdi:restart-alert")}Zurücksetzen…</button></div></div>`;
  }
  /* Urlaubsmodus: ev_assistant liest ihn aus einer Entität (Optionen → „Urlaubs-Entität“, z. B. input_boolean.urlaub).
     Die Karte schaltet diese Entität. Gefunden über car.urlaub_entity, die Panel-Konfiguration oder den Namen. */
  _urlEntity() {
    const c = this._config.car.urlaub_entity, pe = this._evaPanel?.entities?.urlaub_entity;
    if (c && this._hass?.states[c]) return c;
    if (pe && this._hass?.states[pe]) return pe;
    const st = this._hass?.states || {};
    return Object.keys(st).find((id) => /^(input_boolean|switch)\./.test(id) && /urlaub|vacation|holiday/i.test(id + " " + (st[id].attributes?.friendly_name || ""))) || null;
  }
  _render_url() {
    const el = this.shadowRoot.getElementById("surl"), id = this._urlEntity(), st = id ? this._hass.states[id] : null;
    const ma = this._ea("evcc_mode_control")?.attributes || {}, o = this._urlOpt && Date.now() - this._urlOpt.t < 15000 ? this._urlOpt.v : null;
    const on = o ?? (st ? st.state === "on" : !!ma.urlaub_aktiv);
    if (!this._setSig(el, `${id}|${on}|${st?.state}|${ma.urlaub_aktiv}`)) return;
    el.innerHTML = this._hd("Urlaub", on ? `<span class="urlon">${icon("mdi:bag-suitcase")}aktiv</span>` : "")
      + `<div class="pnote">Im Urlaub zählt ev_assistant die Tage nicht ins Nutzungsprofil und pausiert die evcc-Steuerung.</div>`
      + (id ? `<div class="srow"><button class="sbt ${on ? "pri red" : "pri"}" data-act="set" data-k="url-toggle">${icon(on ? "mdi:home-import-outline" : "mdi:bag-suitcase")}${on ? "Urlaub beenden" : "Urlaub starten"}</button>
          <button class="sbt" data-act="set" data-k="url-seit">${icon("mdi:history")}Rückwirkend…</button></div>
          <div class="pnote">Schaltet ${esc(st?.attributes?.friendly_name || id)} (${esc(id)}).</div>`
        : `<div class="pnote warn">Keine Urlaubs-Entität gefunden. In den ev_assistant-Optionen eine „Urlaubs-Entität“ eintragen (z. B. einen Helfer input_boolean.urlaub) und sie bei Bedarf in der Karte als car.urlaub_entity angeben.</div>`);
  }
  _urlToggle() {
    const id = this._urlEntity(); if (!id) return;
    const on = this._hass.states[id]?.state === "on", dom = id.split(".")[0];
    this._urlOpt = { v: !on, t: Date.now() }; this._render_url();
    Promise.resolve(this._hass.callService(dom, on ? "turn_off" : "turn_on", { entity_id: id })).catch((x) => { this._urlOpt = null; this._render_url(); this._toast(x?.message || String(x)); });
  }

  /* Fahrten-Import: CSV (Trennzeichen ; , oder Tab) oder JSON in das Format von ev_assistant.import_fahrtenbuch übersetzen */
  _readTripImport(file) {
    if (!file) return;
    const r = new FileReader();
    r.onload = () => { this._imp = { ...this._parseTrips(String(r.result)), name: file.name }; this._openForm("fb-import"); };
    r.readAsText(file);
  }
  _parseTrips(text) {
    const out = { trips: [], skip: 0, cols: "" };
    const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    const toDate = (v, timeV) => {
      v = String(v ?? "").trim(); timeV = String(timeV ?? "").trim();
      if (!v) return null;
      let m = v.match(/^(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?:[ ,T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?/), y, mo, d, h, mi, se, hasT;
      if (m) { d = +m[1]; mo = +m[2]; y = +m[3] < 100 ? 2000 + +m[3] : +m[3]; h = m[4]; mi = m[5]; se = m[6]; }
      else if ((m = v.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?/))) { y = +m[1]; mo = +m[2]; d = +m[3]; h = m[4]; mi = m[5]; se = m[6]; }
      else return null;
      if (h == null && timeV) { const t = timeV.match(/(\d{1,2}):(\d{2})(?::(\d{2}))?/); if (t) { h = t[1]; mi = t[2]; se = t[3]; } }
      hasT = h != null;
      const dt = new Date(y, mo - 1, d, +(h || 0), +(mi || 0), +(se || 0));
      return isNaN(dt) ? null : { dt, hasT };
    };
    const num = (v) => { if (v == null || v === "") return null; const n = parseFloat(String(v).replace(/\s/g, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".")); return isNaN(n) ? null : n; };
    let rows = [];
    const t = text.replace(/^\uFEFF/, "").trim();
    if (/^[\[{]/.test(t)) {
      try { const j = JSON.parse(t); rows = Array.isArray(j) ? j : Array.isArray(j?.trips) ? j.trips : []; } catch (x) { return out; }
    } else {
      const lines = t.split(/\r?\n/).filter((l) => l.trim());
      if (lines.length < 2) return out;
      const dl = [";", "\t", ","].map((c) => [c, lines[0].split(c).length]).sort((a, b) => b[1] - a[1])[0][0];
      const split = (l) => { const res = []; let cur = "", q = false; for (let i = 0; i < l.length; i++) { const ch = l[i]; if (ch === '"') { if (q && l[i + 1] === '"') { cur += '"'; i++; } else q = !q; } else if (ch === dl && !q) { res.push(cur); cur = ""; } else cur += ch; } res.push(cur); return res.map((x) => x.trim()); };
      const head = split(lines[0]);
      rows = lines.slice(1).map((l) => { const c = split(l), o = {}; head.forEach((h, i) => { o[h] = c[i]; }); return o; });
    }
    if (!rows.length) return out;
    const keys = Object.keys(rows[0]), norm = (k) => k.toLowerCase().replace(/[^a-zäöü0-9]/g, "");
    const pick = (...cands) => keys.find((k) => cands.includes(norm(k))) || keys.find((k) => cands.some((c) => norm(k).startsWith(c)));
    const K = {
      start: pick("start", "startzeit", "beginn", "abfahrt", "startdatum", "von_zeit", "datum", "date"),
      zeit: pick("uhrzeit", "zeit", "startuhrzeit", "time"),
      ende: pick("ende", "endzeit", "ankunft", "enddatum", "bis"),
      so: pick("startort", "start_ort", "startadresse", "von", "abfahrtsort", "from"),
      zo: pick("zielort", "ziel_ort", "ziel", "zieladresse", "nach", "ankunftsort", "to"),
      km: pick("strecke", "streckekm", "km", "distanz", "distanzkm", "kilometer", "distance"),
      kwh: pick("verbrauchkwh", "verbrauch_kwh", "kwh", "energie"),
      avg: pick("avgverbrauch", "avg_verbrauch", "verbrauch100km", "durchschnittsverbrauch"),
      spd: pick("avgspeed", "avg_speed", "durchschnittsgeschwindigkeit", "geschwindigkeit"),
    };
    // ev_assistant-Export: „Start“/„Ziel“ sind dort Orte, „Datum“ das Datum
    const kStart = keys.find((k) => norm(k) === "start");
    out.evaExport = keys.some((k) => norm(k) === "kmstart") && keys.some((k) => norm(k) === "kmende") && !!kStart;
    if (kStart && !toDate(rows[0][kStart])) { if (!K.so) K.so = kStart; if (K.start === kStart) K.start = keys.find((k) => norm(k) === "datum") || null; }
    out.cols = Object.entries(K).filter(([, v]) => v).map(([k, v]) => `${{ start: "Start", zeit: "Uhrzeit", ende: "Ende", so: "Startort", zo: "Zielort", km: "Strecke", kwh: "kWh", avg: "Ø Verbrauch", spd: "Ø km/h" }[k]} = „${v}“`).join(", ");
    const perDay = {};
    for (const r of rows) {
      const s = toDate(r[K.start], K.zeit ? r[K.zeit] : null), km = num(r[K.km]), so = String(r[K.so] ?? "").trim(), zo = String(r[K.zo] ?? "").trim();
      if (!s || km == null || !so || !zo) { out.skip++; continue; }
      if (!s.hasT) { const day = s.dt.toDateString(); perDay[day] = (perDay[day] || 0) + 1; s.dt.setMinutes(perDay[day] - 1); }
      const e = toDate(r[K.ende]);
      const ende = e && e.hasT && e.dt > s.dt ? e.dt : new Date(s.dt.getTime() + 60000);
      const trip = { start: fmt(s.dt), start_ort: so, ende: fmt(ende), ziel_ort: zo, strecke: km };
      for (const [k, f] of [["verbrauch_kwh", K.kwh], ["avg_verbrauch", K.avg], ["avg_speed", K.spd]]) { const v = f ? num(r[f]) : null; if (v != null) trip[k] = v; }
      if (!s.hasT) trip._noTime = true;
      out.trips.push(trip);
    }
    return out;
  }

  // Datei, die ev_assistant unter /config/www ablegt, herunterladen
  _download(name) {
    const a = document.createElement("a"); a.href = `/local/${name}?t=${Date.now()}`; a.download = name; a.target = "_blank";
    this.shadowRoot.appendChild(a); a.click(); a.remove();
  }
  _readRestore(file) {
    if (!file) return;
    const r = new FileReader();
    r.onload = () => {
      const text = String(r.result); let ok = false;
      try { const p = JSON.parse(text); ok = !!p && typeof p === "object" && "history" in p; } catch (x) {}
      if (!ok) { this._toast("Ungültige Datei – keine ev_assistant-Sicherung."); return; }
      this._restore = { text, name: file.name, kb: Math.round(file.size / 1024) };
      this._openForm("restore");
    };
    r.readAsText(file);
  }

  /* Ereignisprotokoll */
  async _loadLog(force) {
    const id = this._evaEntryId();
    if (!id || !this._hass?.callWS || this._logBusy) return;
    if (!force && this._log_?.entry === id && Date.now() - this._log_.t < 30000) return;
    this._logBusy = true;
    let list = [];
    try { const r = await this._hass.callWS({ type: "ev_assistant/event_log", config_entry_id: id }); list = Array.isArray(r?.event_log) ? r.event_log : []; } catch (x) {}
    this._logBusy = false; this._log_ = { entry: id, t: Date.now(), list };
    this._renderLogList();
  }
  _render_log() {
    const el = this.shadowRoot.getElementById("slog");
    if (!el.querySelector(".sloglist")) {
      el.innerHTML = this._hd("Ereignisprotokoll", `<button class="sbt" data-act="set" data-k="log-dl">${icon("mdi:file-download-outline")}Herunterladen</button>`)
        + `<div class="pnote">Die letzten ca. 14 Tage: Moduswechsel, erkannte Fremdladungen und Fahrten, Probleme.</div>
        <div class="srow"><select class="slogkat"><option value="alle">Alle Kategorien</option></select><input type="search" class="slogq" placeholder="Suchen…"></div><div class="sloglist"><div class="empty">Lädt…</div></div>`;
    }
    this._loadLog();
  }
  _renderLogList() {
    const el = this.shadowRoot.getElementById("slog"), box = el?.querySelector(".sloglist");
    if (!box) return;
    const list = this._log_?.list, sel = el.querySelector(".slogkat");
    if (!list) return;
    const kats = [...new Set(list.map((e) => e.kategorie))].sort(), cur = this._logKat || "alle";
    const ksig = kats.join("|");
    if (sel._k !== ksig) { sel._k = ksig; sel.innerHTML = `<option value="alle">Alle Kategorien</option>` + kats.map((k) => `<option value="${esc(k)}">${esc(k)}</option>`).join(""); }
    sel.value = kats.includes(cur) ? cur : "alle";
    const q = (this._logQ || "").trim().toLowerCase();
    const f = list.filter((e) => (sel.value === "alle" || e.kategorie === sel.value) && (!q || String(e.text).toLowerCase().includes(q) || String(e.kategorie).toLowerCase().includes(q))).sort((a, b) => b.ts - a.ts);
    const top = box.scrollTop < 4;
    box.innerHTML = !list.length ? `<div class="empty">Noch keine Einträge.</div>` : !f.length ? `<div class="empty">Keine Einträge für diesen Filter.</div>`
      : f.slice(0, 300).map((e) => { const d = new Date(e.ts * 1000); return `<div class="sline"><span>${d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })} ${d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}</span><em>${esc(e.kategorie)}</em><p>${esc(e.text)}</p></div>`; }).join("");
    if (top) box.scrollTop = 0;
  }

  /* Offene (erkannte, noch nicht bestätigte) Fremdladungen und Fahrten aus ev_assistant */
  _pendItems() {
    const pc = this._ea("pending"), pt = this._ea("trip_pending");
    const l = (st, k) => (st && st.state === "on" && Array.isArray(st.attributes?.[k]) ? st.attributes[k] : []);
    return { charges: l(pc, "offene_ladungen"), trips: l(pt, "offene_fahrten") };
  }
  _openPend() { this._pendSig = null; this._openDlg("pend"); this._renderPend(); }
  _renderPend() {
    const d = this.shadowRoot.getElementById("cardlg");
    if (!d || this._dlg !== "pend") return;
    const P = this._pendItems(), sig = P.charges.map((x) => x.start_ts).join() + "|" + P.trips.map((x) => x.start_ts).join();
    if (sig === this._pendSig) return;   // Eingaben nicht überschreiben – nur neu aufbauen, wenn Einträge dazukommen oder wegfallen
    this._pendSig = sig;
    if (!P.charges.length && !P.trips.length) { d.close(); return; }
    // bereits Eingetipptes über einen Neuaufbau retten
    const keep = {};
    d.querySelectorAll("form.pform").forEach((f) => { keep[f.dataset.key] = Object.fromEntries([...f.elements].filter((e) => e.name).map((e) => [e.name, e.value])); });
    const anb = this._ea("charging_location_breakdown")?.attributes?.bekannte_anbieter || [];
    const when = (ts, min) => `${ts ? new Date(ts * 1000).toLocaleString("de-DE", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}${min != null ? ` · ${min >= 60 ? `${Math.floor(min / 60)}:${pad(Math.round(min % 60))} h` : `${Math.round(min)} min`}` : ""}`;
    const inp = (key, lbl, name, val, attrs = 'inputmode="decimal"') => `<label class="sfld"><span>${lbl}</span><input name="${name}" type="text" ${attrs} value="${esc(keep[key]?.[name] ?? val ?? "")}"></label>`;
    const ch = P.charges.map((x) => {
      const key = `c${x.start_ts}`, kwh = x.energy_kwh != null ? String(Math.round(x.energy_kwh * 100) / 100).replace(".", ",") : "";
      return `<form class="pform sform" data-key="${key}" onsubmit="return false"><div class="ptop">${icon("mdi:ev-station")}<span><b>Fremdladung erkannt</b><small>${when(x.start_ts, x.duration_min)}</small></span>
        <em>${x.energy_kwh != null ? `${de(x.energy_kwh, 1)} kWh` : ""}${x.soc_start != null && x.soc_end != null ? `<small>${Math.round(x.soc_start)} → ${Math.round(x.soc_end)} %</small>` : ""}</em></div>
        <div class="sflds">${inp(key, "kWh (Beleg)", "kwh", kwh)}${inp(key, "€/kWh (Beleg)", "price", "", 'inputmode="decimal" placeholder="0,000"')}${inp(key, "Startgebühr €", "fee", "", 'inputmode="decimal" placeholder="0,00"')}
          ${inp(key, "Blockiergebühr €", "block", "", 'inputmode="decimal" placeholder="0,00"')}${inp(key, "Zeitgebühr €", "time", "", 'inputmode="decimal" placeholder="0,00"')}${inp(key, "Anbieter", "anbieter", "", 'list="panb" placeholder="z. B. EnBW"')}</div>
        <div class="ferr"></div><div class="srow end"><button type="button" class="sbt" data-act="set" data-k="pend-no" data-t="c" data-ts="${x.start_ts}">Verwerfen</button><button type="button" class="sbt pri" data-act="set" data-k="pend-ok" data-t="c" data-ts="${x.start_ts}">Bestätigen</button></div></form>`;
    }).join("");
    const tr = P.trips.map((x) => {
      const key = `t${x.start_ts}`;
      return `<form class="pform sform" data-key="${key}" onsubmit="return false"><div class="ptop">${icon("mdi:map-marker-question")}<span><b>Fahrt erkannt</b><small>${when(x.start_ts, x.duration_min)}</small></span><em>${x.km != null ? `${de(x.km, 1)} km` : ""}</em></div>
        <div class="sflds">${inp(key, "Startort", "start_ort", x.start_ort_vorschlag, "")}${inp(key, "Zielort", "end_ort", x.end_ort_vorschlag, "")}</div>
        <div class="ferr"></div><div class="srow end"><button type="button" class="sbt" data-act="set" data-k="pend-no" data-t="t" data-ts="${x.start_ts}">Verwerfen</button><button type="button" class="sbt pri" data-act="set" data-k="pend-ok" data-t="t" data-ts="${x.start_ts}">Bestätigen</button></div></form>`;
    }).join("");
    d.innerHTML = `<div class="dpan sdlg"><div class="dhd"><span class="dico">${icon("mdi:clipboard-check-outline")}</span>
      <span class="rtx"><span class="rname">Bestätigen</span><span class="rsub">Von ev_assistant erkannt, nicht automatisch übernommen</span></span>
      <button class="dx" data-act="cardclose" aria-label="Schließen">${icon("mdi:close")}</button></div>
      <div class="dbody">${ch}${tr}<datalist id="panb">${anb.map((a) => `<option value="${esc(a)}"></option>`).join("")}</datalist></div></div>`;
  }
  _pendAct(k, ds) {
    const f = ds.t && this.shadowRoot.querySelector(`#cardlg form.pform[data-key="${ds.t}${ds.ts}"]`);
    if (!f) return;
    const ts = Number(ds.ts), v = (x) => String(f.elements[x]?.value ?? "").trim(), num = (x) => { const r = v(x).replace(",", "."); return r === "" ? null : parseFloat(r); };
    const err = (m) => { f.querySelector(".ferr").textContent = m; };
    let svc, data;
    if (k === "pend-no") { svc = ds.t === "c" ? "discard_pending" : "discard_pending_trip"; data = { start_ts: ts }; }
    else if (ds.t === "c") {
      const kwh = num("kwh"), price = num("price");
      if (kwh == null || isNaN(kwh) || price == null || isNaN(price)) return err("Bitte kWh und Preis je kWh vom Beleg eintragen.");
      const fee = (x) => { const y = num(x); return y == null || isNaN(y) ? 0 : y; };
      svc = "log_charge"; data = { kwh, price_kwh: price, start_ts: ts, start_fee: fee("fee"), block_fee: fee("block"), time_fee: fee("time") };
      if (v("anbieter")) data.anbieter = v("anbieter");
    } else {
      if (!v("start_ort") || !v("end_ort")) return err("Bitte Start- und Zielort eintragen.");
      svc = "log_trip"; data = { start_ort: v("start_ort"), end_ort: v("end_ort"), start_ts: ts };
    }
    f.querySelectorAll("button").forEach((b) => { b.disabled = true; }); err("");
    this._evaCall(svc, data).then(() => {
      f.classList.add("done");
      if (ds.t === "t") this._loadTrips(true); else this._charges = null;
    }).catch((x) => { f.querySelectorAll("button").forEach((b) => { b.disabled = false; }); err(x?.message || String(x)); });
  }

  // Unix-Zeit (s) <-> <input type="datetime-local"> in Ortszeit
  _dtl(ts) { if (ts == null || ts === "") return ""; const d = new Date(ts * 1000); return isNaN(d) ? "" : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }
  _fromDtl(v) { if (!v) return null; const t = new Date(v).getTime(); return isNaN(t) ? null : t / 1000; }

  /* Formulare im Popup */
  _openForm(kind, id, extra = {}) {
    this._form = { kind, id, ...extra };
    this._openDlg("form");
    this._renderForm();
  }
  _renderForm() {
    const d = this.shadowRoot.getElementById("cardlg"), F = this._form, k = F.kind;
    const fld = (lbl, name, val = "", type = "text", attrs = "") => `<label class="sfld" data-f="${name}"><span>${lbl}</span><input name="${name}" type="${type}" ${type === "text" ? 'inputmode="decimal"' : ""} value="${esc(typeof val === "number" ? String(val).replace(".", ",") : val ?? "")}" ${attrs}></label>`;
    const txt = (lbl, name, val = "", ph = "") => `<label class="sfld" data-f="${name}"><span>${lbl}</span><input name="${name}" type="text" value="${esc(val ?? "")}" placeholder="${esc(ph)}"></label>`;
    const grp = (t, inner, cls = "") => `<div class="sgrp ${cls}">${t ? `<h4>${t}</h4>` : ""}<div class="sflds">${inner}</div></div>`;
    const W = this._wartData(), p = F.id != null ? W.punkte.find((x) => String(x.id) === String(F.id)) : null;
    const L = (this._ea("ladekarten_kosten")?.attributes?.karten || []), lk = F.id != null ? L.find((x) => String(x.id) === String(F.id)) : null;
    let title = "", sub = "", body = "", save = "Speichern", danger = false;
    if (k === "wt-add" || k === "wt-edit") {
      const e = k === "wt-edit", hu = e ? p?.typ === "tuev" : false;
      title = e ? "Wartungspunkt bearbeiten" : "Wartungspunkt anlegen"; sub = e ? esc(p?.name || "") : "Vorlage füllt die Felder vor – danach frei änderbar";
      const rm = p?.reminder_tage != null ? Math.round((p.reminder_tage / 30.44) * 10) / 10 : "";
      body = grp("", (e ? "" : `<label class="sfld" data-f="preset"><span>Vorlage</span><select name="preset" class="fpreset"><option value="">– eigene –</option>${W.presets.map((x) => `<option value="${esc(x.key)}">${esc(x.name)}</option>`).join("")}</select></label>`)
          + txt("Name", "name", p?.name, "z. B. Inspektion") + (e ? `<label class="sfld chk"><input type="checkbox" name="aktiv" ${p?.aktiv !== false ? "checked" : ""}><span>Aktiv</span></label>` : ""))
        + grp("Fälligkeit", (hu ? "" : fld("Kilometer-Intervall", "km_intervall", p?.km_intervall, "text", 'placeholder="z. B. 30000"')) + fld("Intervall (Monate)", "zeit_intervall_monate", p?.zeit_intervall_monate, "text", 'placeholder="z. B. 24"') + fld("Festes Datum (Monat)", "festes_datum", p?.festes_datum ? p.festes_datum.slice(0, 7) : "", "month"), "ffaell")
        + `<div class="pnote fhint">Mindestens ein Kriterium angeben. Bei mehreren gilt, was zuerst eintritt.</div>`
        + grp("Erster Termin abweichend (optional)", (hu ? "" : fld("Erstes km-Intervall", "erst_km_intervall", p?.erst_km_intervall, "text", 'placeholder="z. B. 12500"')) + fld("Erstes Intervall (Monate)", "erst_zeit_intervall_monate", p?.erst_zeit_intervall_monate, "text", 'placeholder="z. B. 12"')
          + (e ? fld("Schon erledigt (Anzahl)", "erledigt_anzahl", p?.erledigt_anzahl ?? "", "text", 'placeholder="0"') : ""), "ferst")
        + `<div class="pnote">Nur zusätzlich zum normalen Intervall unter „Fälligkeit“: gilt bis zum ersten „erledigt“, danach das normale. Beispiel: Fälligkeit 25.000 km / 24 Monate, erster Termin 12.500 km / 12 Monate (ev_assistant ab 0.99.57).</div>`
        + grp("Letzter Service", fld("Kilometerstand", "last_done_km", p?.last_done?.km) + fld("Datum", "last_done_datum", p?.last_done?.datum, "date"), "flast")
        + `<div class="pnote">Noch nie gemacht? Datum der Erstzulassung und 0 km eintragen – ab da zählt das (erste) Intervall.</div>`
        + grp("Erinnerung (leer = Standard)", fld("Vorwarnzeit (Monate)", "reminder_monate", rm) + fld("Vorwarnzeit (km)", "reminder_km", p?.reminder_km), "frem")
        + grp("", fld("Kosten €", "kosten", p?.kosten), "fkost");
    } else if (k === "wt-done") {
      title = "Als erledigt markieren"; sub = esc(p?.name || ""); save = "Erledigt";
      body = `<div class="pnote">Leer lassen = aktueller Kilometerstand und heute. Für einen Termin, der schon ein paar Tage her ist, Werte nachtragen.</div>` + grp("", fld("Kilometerstand", "km", "", "text", 'placeholder="aktuell"') + fld("Datum", "datum", "", "date"));
    } else if (k === "lk-add" || k === "lk-edit") {
      const e = k === "lk-edit", st = [...(lk?.gebuehren || [])].sort((a, b) => (a.ab_datum < b.ab_datum ? -1 : 1));
      title = e ? "Ladekarte bearbeiten" : "Ladekarte anlegen"; sub = e ? esc(lk?.name || "") : "Monatliche Grundgebühr einer Abo-Karte";
      body = grp("", txt("Name", "name", lk?.name, "z. B. ADAC e-Charge") + fld(e ? "Startgebühr € (früheste Stufe)" : "Monatliche Gebühr €", "monatliche_gebuehr", e ? st[0]?.gebuehr : "", "text", 'placeholder="0,00"')
        + fld("Startdatum", "start_datum", e ? lk?.start_datum : new Date().toISOString().slice(0, 10), "date") + fld("Enddatum (optional)", "end_datum", lk?.end_datum, "date"));
    } else if (k === "lk-stufe") {
      title = "Preisänderung"; sub = esc(lk?.name || ""); save = "Preisstufe speichern";
      body = `<div class="pnote">Neue Gebühr ab einem Datum, z. B. wenn ein Einführungspreis endet.</div>` + grp("", fld("Gültig ab", "ab_datum", "", "date") + fld("Monatliche Gebühr €", "gebuehr", "", "text", 'placeholder="0,00"'));
    } else if (k === "wt-del" || k === "lk-del") {
      title = k === "wt-del" ? "Wartungspunkt löschen" : "Ladekarte löschen"; sub = esc((k === "wt-del" ? p?.name : lk?.name) || ""); save = "Löschen"; danger = true;
      body = `<div class="pnote">Dauerhaft löschen? Das lässt sich nicht rückgängig machen.</div>`;
    } else if (k === "reset") {
      title = "Kennzahlen zurücksetzen"; sub = "Neuer Startpunkt für Verbrauch und Ersparnis"; save = "Zurücksetzen"; danger = true;
      body = grp("", fld("kWh seit Einrichtung", "home_kwh_since_setup", "", "text", 'placeholder="leer = 0"') + fld("Kosten € seit Einrichtung", "home_cost_since_setup", "", "text", 'placeholder="leer = 0"') + fld("km seit Einrichtung", "km_driven", "", "text", 'placeholder="leer = 0"'))
        + `<div class="pnote">Fahrtenbuch und Ladehistorie bleiben unverändert. Nicht rückgängig machbar.</div>`;
    } else if (k === "trip-edit") {
      const t = (this._evaTrips?.list || []).map((x) => x.raw).find((x) => x && String(x.erfasst_ts) === String(F.id)) || {};
      title = "Fahrt bearbeiten"; sub = `${esc(t.start_ort || "?")} → ${esc(t.end_ort || "?")}`;
      body = grp("", txt("Startort", "start_ort", t.start_ort) + txt("Zielort", "end_ort", t.end_ort))
        + grp("Zeit", fld("Start", "start_ts", this._dtl(t.start_ts), "datetime-local") + fld("Ende", "end_ts", this._dtl(t.end_ts), "datetime-local"))
        + grp("Strecke", fld("Strecke (km)", "km", t.km) + fld("km-Stand Start", "odo_start", t.odo_start) + fld("km-Stand Ende", "odo_end", t.odo_end))
        + grp("Akku", fld("SoC Start (%)", "soc_start", t.soc_start) + fld("SoC Ende (%)", "soc_end", t.soc_end) + fld("Verbrauch (kWh)", "verbrauch_kwh", t.verbrauch_kwh))
        + `<div class="srow"><button type="button" class="sbt red" data-act="set" data-k="trip-del" data-id="${esc(F.id)}">${icon("mdi:delete-outline")}Fahrt löschen</button></div>`;
    } else if (k === "ch-edit") {
      const h = (this._charges?.list || []).map((x) => x.raw).find((x) => x && String(x.erfasst_ts) === String(F.id)) || {};
      const karten = this._ea("ladekarten_kosten")?.attributes?.karten || [], anb = this._ea("charging_location_breakdown")?.attributes?.bekannte_anbieter || [];
      const end = h.start_ts != null && h.dauer_min != null ? h.start_ts + h.dauer_min * 60 : null;
      title = "Fremdladung bearbeiten"; sub = `${h.start_ts ? new Date(h.start_ts * 1000).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" }) : ""}${h.anbieter ? ` · ${esc(h.anbieter)}` : ""}`;
      body = grp("Beleg", fld("kWh", "kwh", h.kwh) + fld("€/kWh", "price_kwh", h.preis_kwh) + fld("Startgebühr €", "start_fee", h.startgebuehr || 0) + fld("Blockiergebühr €", "block_fee", h.blockiergebuehr || 0) + fld("Zeitgebühr €", "time_fee", h.zeitgebuehr || 0))
        + grp("Zeit und Akku", fld("Start", "start_ts", this._dtl(h.start_ts), "datetime-local") + fld("Ladeende", "end_ts", this._dtl(end), "datetime-local") + fld("SoC Start (%)", "soc_start", h.soc_start) + fld("SoC Ende (%)", "soc_end", h.soc_end))
        + grp("", `<label class="sfld" data-f="anbieter"><span>Anbieter</span><input name="anbieter" type="text" list="fanb" value="${esc(h.anbieter || "")}"></label><datalist id="fanb">${anb.map((a) => `<option value="${esc(a)}"></option>`).join("")}</datalist>`
          + (karten.length ? `<label class="sfld"><span>Ladekarte</span><select name="karte_id"><option value="">– keine –</option>${karten.map((x) => `<option value="${esc(x.id)}"${x.id === h.karte_id ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>` : ""))
        + `<div class="srow"><button type="button" class="sbt red" data-act="set" data-k="ch-del" data-id="${esc(F.id)}">${icon("mdi:delete-outline")}Fremdladung löschen</button></div>`;
    } else if (k === "trip-del" || k === "ch-del") {
      title = k === "trip-del" ? "Fahrt löschen" : "Fremdladung löschen"; save = "Löschen"; danger = true;
      body = `<div class="pnote">Diesen Eintrag dauerhaft löschen? Das lässt sich nicht rückgängig machen.</div>`;
    } else if (k === "fb-import") {
      const I = this._imp || { trips: [], skip: 0 }, n = I.trips.length, noTime = I.trips.filter((t) => t._noTime).length;
      title = "Fahrten importieren"; sub = `${esc(I.name || "")} · ${n} Fahrt${n === 1 ? "" : "en"} erkannt${I.skip ? ` · ${I.skip} Zeile${I.skip === 1 ? "" : "n"} übersprungen` : ""}`; save = `${n} importieren`;
      body = n ? `<div class="pnote">Spalten: ${esc(I.cols || "")}</div><div class="fbprev"><div class="fbh"><span>Start</span><span>Von → Nach</span><span>km</span></div>${I.trips.slice(0, 8).map((t) => `<div><span>${esc(t.start.slice(0, 16))}</span><span>${esc(t.start_ort)} → ${esc(t.ziel_ort)}</span><span>${de(t.strecke, 1)}</span></div>`).join("")}${n > 8 ? `<div class="fbmore">… und ${n - 8} weitere</div>` : ""}</div>
        ${I.evaExport ? `<div class="pnote err">${icon("mdi:alert-outline")} Diese Datei sieht aus wie ein Export von ev_assistant selbst. Die Fahrten stehen dann schon im Fahrtenbuch und würden doppelt angelegt (der Export enthält keine Uhrzeiten). Nur importieren, wenn das Fahrtenbuch leer ist, z. B. nach einer Neueinrichtung.</div>` : ""}
        ${noTime ? `<div class="pnote warn">${noTime} Fahrt${noTime === 1 ? "" : "en"} ohne Uhrzeit – Startzeit wird auf Mitternacht plus laufende Minute gesetzt (z. B. beim CSV-Export von ev_assistant, der nur das Datum enthält). Bei erneutem Import entstehen so keine Doppelten.</div>` : ""}`
        : `<div class="pnote warn">In der Datei wurden keine Fahrten erkannt. Nötig sind Spalten für Start (Datum und Uhrzeit), Startort, Zielort und Strecke in km – z. B. „start;start_ort;ende;ziel_ort;strecke“.</div>`;
    } else if (k === "url-seit") {
      const d = new Date(); d.setHours(d.getHours() - 24, 0, 0, 0);
      title = "Urlaub rückwirkend"; sub = "Fahrten seit dem Urlaubsbeginn aus den Profilen nehmen"; save = "Anwenden";
      body = `<div class="pnote">Für den Fall, dass der Urlaubsmodus erst nach der Abfahrt eingeschaltet wurde: Was ev_assistant seitdem als normalen Verbrauch gebucht hat, wird wieder aus dem Wochentags-Profil genommen. Wirkt nur auf die letzten Tage.</div>`
        + grp("", fld("Urlaub seit", "seit", this._dtl(d.getTime() / 1000), "datetime-local"));
    } else if (k === "restore") {
      const R = this._restore || {};
      title = "Backup wiederherstellen"; sub = `${esc(R.name || "")} (${R.kb ?? "?"} KB)`; save = "Wiederherstellen"; danger = true;
      body = `<div class="pnote">ALLE aktuellen Daten (Fahrtenbuch, Ladehistorie, Ladekarten, Wartungsplan, Kennzahlen) werden ersetzt. ev_assistant legt vorher automatisch ein Sicherheits-Backup des jetzigen Stands an.</div>`
        + grp("", txt("Zum Bestätigen WIEDERHERSTELLEN eintippen", "confirm", "", "WIEDERHERSTELLEN"));
    }
    d.innerHTML = `<div class="dpan sdlg"><div class="dhd"><span class="dico">${icon(k === "fb-import" ? "mdi:file-import-outline" : k === "url-seit" ? "mdi:bag-suitcase" : k.startsWith("wt") ? "mdi:wrench-clock" : k.startsWith("lk") ? "mdi:credit-card-multiple-outline" : k.startsWith("trip") ? "mdi:map-marker-path" : k.startsWith("ch") ? "mdi:ev-station" : "mdi:cog-outline")}</span>
      <span class="rtx"><span class="rname">${title}</span><span class="rsub">${sub}</span></span>
      <button class="dx" data-act="cardclose" aria-label="Schließen">${icon("mdi:close")}</button></div>
      <form class="dbody sform" onsubmit="return false">${body}<div class="ferr"></div>
      <div class="srow end"><button type="button" class="sbt" data-act="${F.back ? "set" : "cardclose"}" data-k="back">Abbrechen</button><button type="button" class="sbt pri${danger ? " red" : ""}" data-act="set" data-k="save">${save}</button></div></form></div>`;
    if (k === "wt-add") this._wtPreset("");
  }
  // Vorlage im Formular: Felder ein-/ausblenden (HU braucht kein km-Intervall) und leere Felder vorbelegen
  _wtPreset(key, fill) {
    const f = this.shadowRoot.querySelector("#cardlg .sform");
    if (!f) return;
    const hu = key === "tuev", insp = key === "inspektion";
    const hide = hu ? ["km_intervall", "erst_km_intervall", "last_done_km", "last_done_datum", "reminder_km", "kosten"] : insp ? ["festes_datum"] : [];
    f.querySelectorAll("[data-f]").forEach((x) => { const h = hide.includes(x.dataset.f); x.hidden = h; if (h) x.querySelector("input").value = ""; });
    f.querySelector(".flast").hidden = hu; f.querySelector(".fkost").hidden = hu;
    f.querySelector(".fhint").textContent = hu ? "Für die HU sind festes Datum und Intervall beide Pflicht." : "Mindestens ein Kriterium angeben. Bei mehreren gilt, was zuerst eintritt.";
    const P = fill && this._wartData().presets.find((x) => x.key === key);
    if (P) {
      const set = (n, v) => { const i = f.elements[n]; if (i && !i.value.trim() && v != null) i.value = v; };
      set("name", P.name); set("km_intervall", P.km_intervall); set("zeit_intervall_monate", P.zeit_intervall_monate);
    }
  }
  _saveForm() {
    const f = this.shadowRoot.querySelector("#cardlg .sform"), F = this._form, k = F?.kind;
    if (!f || !k) return;
    const v = (n) => (f.elements[n] ? String(f.elements[n].value ?? "").trim() : null);
    const n = (x) => { x = v(x); if (x == null || x === "") return x; const r = parseFloat(x.replace(",", ".")); return isNaN(r) ? NaN : r; };
    const err = (m) => { f.querySelector(".ferr").textContent = m; };
    const monthEnd = (m) => { const [y, mo] = m.split("-").map(Number); return `${m}-${String(new Date(y, mo, 0).getDate()).padStart(2, "0")}`; };
    const id = F.id != null ? Number(F.id) : null;
    let svc = null, data = {};
    if (k === "wt-add" || k === "wt-edit") {
      const e = k === "wt-edit", name = v("name"), km = n("km_intervall"), zeit = n("zeit_intervall_monate"), fest = v("festes_datum") || "";
      if (!name && !e) return err("Bitte einen Namen angeben.");
      for (const [x, l] of [[n("erst_km_intervall"), "Erstes km-Intervall"], [n("erst_zeit_intervall_monate"), "Erstes Intervall"], [n("erledigt_anzahl"), "Anzahl erledigt"], [km, "Kilometer-Intervall"], [zeit, "Intervall"], [n("kosten"), "Kosten"], [n("last_done_km"), "Kilometerstand"], [n("reminder_monate"), "Vorwarnzeit"], [n("reminder_km"), "Vorwarnzeit (km)"]]) if (Number.isNaN(x)) return err(`${l}: bitte eine Zahl eingeben.`);
      const hasKm = km != null && km !== "", hasZ = zeit != null && zeit !== "";
      const hu = e ? this._wartData().punkte.find((x) => x.id === id)?.typ === "tuev" : v("preset") === "tuev";
      const hasErst = !!(n("erst_km_intervall") || n("erst_zeit_intervall_monate"));
      if (!hu && hasErst && !(hasKm || hasZ || fest)) return err("Das erste Intervall gilt nur bis zum ersten Termin. Trag unter „Fälligkeit“ auch das normale Intervall ein (z. B. 25.000 km / 24 Monate) – das gilt danach.");
      if (hu ? !(fest && hasZ) : !(hasKm || hasZ || fest)) return err(hu ? "Für die HU sind festes Datum und Intervall beide Pflicht." : "Mindestens ein Kriterium angeben (km, Monate oder festes Datum).");
      if (hasErst && !v("last_done_datum") && (n("last_done_km") === "" || n("last_done_km") == null) && !(e && (this._wartData().punkte.find((x) => x.id === id)?.last_done))) return err("Ab wann zählt das erste Intervall? Trag unter „Letzter Service“ die Erstzulassung ein (Datum und 0 km).");
      if (e) {
        svc = "edit_maintenance"; data = { wartung_id: id, aktiv: !!f.elements.aktiv?.checked };
        if (name) data.name = name;
        // leer = Kriterium/Wert löschen (wie im ev_assistant-Panel), fehlendes Feld = unverändert
        if (f.elements.km_intervall) data.km_intervall = hasKm ? km : "";
        data.zeit_intervall_monate = hasZ ? Math.round(zeit) : "";
        data.festes_datum = fest ? monthEnd(fest) : "";
        const ko = n("kosten"); data.kosten = ko === "" ? "" : ko;
        const rm = n("reminder_monate"); data.reminder_monate = rm === "" ? "" : rm;
        const rk = n("reminder_km"); data.reminder_km = rk === "" ? "" : rk;
        // Erstintervall/Anzahl nur mitschicken, wenn gesetzt oder geändert (ältere ev_assistant-Versionen kennen die Felder nicht)
        const o = this._wartData().punkte.find((x) => x.id === id) || {};
        if (f.elements.erst_km_intervall) { const y = n("erst_km_intervall"); if (y !== "" || o.erst_km_intervall != null) data.erst_km_intervall = y === "" ? "" : y; }
        { const y = n("erst_zeit_intervall_monate"); if (y !== "" || o.erst_zeit_intervall_monate != null) data.erst_zeit_intervall_monate = y === "" ? "" : Math.round(y); }
        { const y = n("erledigt_anzahl"); if (y !== "" && y != null && Math.round(y) !== (o.erledigt_anzahl ?? null)) data.erledigt_anzahl = Math.max(0, Math.round(y)); }
      } else {
        svc = "add_maintenance"; data = { name };
        if (v("preset")) data.preset = v("preset");
        if (hasKm) data.km_intervall = km;
        if (hasZ) data.zeit_intervall_monate = Math.round(zeit);
        if (fest) data.festes_datum = monthEnd(fest);
        for (const x of ["kosten", "reminder_monate", "reminder_km", "erst_km_intervall"]) { const y = n(x); if (y !== "" && y != null) data[x] = y; }
        { const y = n("erst_zeit_intervall_monate"); if (y !== "" && y != null) data.erst_zeit_intervall_monate = Math.round(y); }
      }
      const lk = n("last_done_km"); if (lk !== "" && lk != null) data.last_done_km = lk;
      if (v("last_done_datum")) data.last_done_datum = v("last_done_datum");
    } else if (k === "wt-done") {
      const km = n("km"); if (Number.isNaN(km)) return err("Kilometerstand: bitte eine Zahl eingeben.");
      svc = "mark_maintenance_done"; data = { wartung_id: id };
      if (km !== "") data.km = km;
      if (v("datum")) data.datum = v("datum");
    } else if (k === "lk-add" || k === "lk-edit") {
      const e = k === "lk-edit", name = v("name"), g = n("monatliche_gebuehr"), start = v("start_datum"), end = v("end_datum");
      if (Number.isNaN(g)) return err("Gebühr: bitte eine Zahl eingeben.");
      if (!e && (!name || g === "" || !start)) return err("Name, Gebühr und Startdatum sind nötig.");
      if (e) { svc = "edit_ladekarte"; data = { karte_id: id, end_datum: end || "" }; if (name) data.name = name; if (g !== "") data.monatliche_gebuehr = g; if (start) data.start_datum = start; }
      else { svc = "add_ladekarte"; data = { name, monatliche_gebuehr: g, start_datum: start }; if (end) data.end_datum = end; }
    } else if (k === "lk-stufe") {
      const g = n("gebuehr"), ab = v("ab_datum");
      if (!ab || g === "" || Number.isNaN(g)) return err("Datum und Gebühr sind nötig.");
      svc = "add_ladekarte_preisstufe"; data = { karte_id: id, gebuehr: g, ab_datum: ab };
    } else if (k === "wt-del") { svc = "delete_maintenance"; data = { wartung_id: id }; }
    else if (k === "lk-del") { svc = "delete_ladekarte"; data = { karte_id: id }; }
    else if (k === "reset") {
      for (const x of ["home_kwh_since_setup", "home_cost_since_setup", "km_driven"]) { const y = n(x); if (Number.isNaN(y)) return err("Bitte nur Zahlen eingeben."); if (y !== "") data[x] = y; }
      svc = "reset_lifetime_kpis";
    } else if (k === "trip-edit") {
      const so = v("start_ort"), eo = v("end_ort");
      if (!so || !eo) return err("Start- und Zielort sind nötig.");
      svc = "edit_trip"; data = { erfasst_ts: Number(F.id), start_ort: so, end_ort: eo };
      for (const x of ["km", "odo_start", "odo_end", "soc_start", "soc_end", "verbrauch_kwh"]) { const y = n(x); if (Number.isNaN(y)) return err("Bitte nur Zahlen eingeben."); if (y !== "" && y != null) data[x] = y; }
      // Zeiten nur mitschicken, wenn geändert (das Feld kennt keine Sekunden)
      const o = (this._evaTrips?.list || []).map((x) => x.raw).find((x) => x && String(x.erfasst_ts) === String(F.id)) || {};
      for (const x of ["start_ts", "end_ts"]) { const y = this._fromDtl(v(x)); if (y != null && v(x) !== this._dtl(o[x])) data[x] = y; }
    } else if (k === "ch-edit") {
      svc = "edit_charge"; data = { erfasst_ts: Number(F.id) };
      for (const [x, key] of [["kwh", "kwh"], ["price_kwh", "price_kwh"], ["start_fee", "start_fee"], ["block_fee", "block_fee"], ["time_fee", "time_fee"], ["soc_start", "soc_start"], ["soc_end", "soc_end"]]) { const y = n(x); if (Number.isNaN(y)) return err("Bitte nur Zahlen eingeben."); if (y !== "" && y != null) data[key] = y; }
      const o = (this._charges?.list || []).map((x) => x.raw).find((x) => x && String(x.erfasst_ts) === String(F.id)) || {};
      const oEnd = o.start_ts != null && o.dauer_min != null ? o.start_ts + o.dauer_min * 60 : null;
      for (const [x, ov] of [["start_ts", o.start_ts], ["end_ts", oEnd]]) { const y = this._fromDtl(v(x)); if (y != null && v(x) !== this._dtl(ov)) data[x] = y; }
      if (f.elements.karte_id) data.karte_id = v("karte_id") === "" ? 0 : parseInt(v("karte_id"), 10);
      data.anbieter = v("anbieter") || "";
    } else if (k === "trip-del") { svc = "delete_trip"; data = { erfasst_ts: Number(F.id) }; }
    else if (k === "ch-del") { svc = "delete_charge"; data = { erfasst_ts: Number(F.id) }; }
    else if (k === "fb-import") {
      const T = (this._imp?.trips || []).map(({ _noTime, ...t }) => t);
      if (!T.length) return err("Keine Fahrten zum Importieren.");
      svc = "import_fahrtenbuch"; data = { trips: T };
    } else if (k === "url-seit") {
      const ts = this._fromDtl(v("seit"));
      if (ts == null || ts > Date.now() / 1000) return err("Bitte einen Zeitpunkt in der Vergangenheit wählen.");
      svc = "urlaub_seit"; data = { seit_ts: Math.round(ts) };
    }
    else if (k === "restore") {
      if (v("confirm") !== "WIEDERHERSTELLEN") return err("Bitte WIEDERHERSTELLEN eintippen.");
      svc = "restore_backup"; data = { backup_data: this._restore?.text };
    }
    if (!svc) return;
    const btn = f.querySelector('[data-k="save"]'); btn.disabled = true; err("");
    this._evaCall(svc, data).then(() => {
      if (k === "restore") this._restore = null;
      if (k.startsWith("trip")) { this._loadTrips(true); return this._openTrips(); }
      if (k.startsWith("ch-")) { this._charges = null; return this._openCharges(); }
      this.shadowRoot.getElementById("cardlg")?.close();
      if (k === "reset" || k === "restore") this._toast(k === "reset" ? "Kennzahlen zurückgesetzt." : "Backup wiederhergestellt.");
      if (k === "fb-import") { this._toast(`${data.trips.length} Fahrten an ev_assistant übergeben – bereits vorhandene werden übersprungen.`); this._imp = null; this._loadTrips(true); }
      if (k === "url-seit") this._toast("Urlaub rückwirkend angewendet.");
    }).catch(() => { btn.disabled = false; });
  }
  _setAct(k, ds) {
    if (["trip-edit", "trip-del"].includes(k)) return this._openForm(k, ds.id, { back: "trips" });
    if (["ch-edit", "ch-del"].includes(k)) return this._openForm(k, ds.id, { back: "charges" });
    if (k === "back") return this._form?.back === "trips" ? this._openTrips() : this._form?.back === "charges" ? this._openCharges() : this.shadowRoot.getElementById("cardlg")?.close();
    if (k === "pend-ok" || k === "pend-no") return this._pendAct(k, ds);
    if (["wt-add", "wt-edit", "wt-done", "wt-del", "lk-add", "lk-edit", "lk-del", "lk-stufe", "reset", "url-seit"].includes(k)) return this._openForm(k, ds.id);
    if (k === "save") return this._saveForm();
    if (k === "lk-sdel") return this._evaCall("delete_ladekarte_preisstufe", { karte_id: Number(ds.id), ab_datum: ds.ab }).catch(() => {});
    if (k === "img-clear") { this._imgBusy = true; this._render_img(); return this._evaCall("clear_vehicle_image").then(() => { this._imgStatus = "Bild entfernt."; }, (x) => { this._imgStatus = x?.message || String(x); }).finally(() => { this._imgBusy = false; this._render_img(); }); }
    const id = this._evaEntryId();
    if (k === "fb-export") { this._dataBusy = "fb"; this._render_data(); return this._evaCall("export_fahrtenbuch").then(() => this._download(`ev_assistant_fahrtenbuch_${id}.csv`), () => {}).finally(() => { this._dataBusy = null; this._render_data(); }); }
    if (k === "url-toggle") return this._urlToggle();
    if (k === "backup") { this._dataBusy = "backup"; this._render_data(); return this._evaCall("export_backup").then(() => this._download(`ev_assistant_backup_${id}.json`), () => {}).finally(() => { this._dataBusy = null; this._render_data(); }); }
    if (k === "log-dl") return this._evaCall("export_event_log").then(() => this._download(`ev_assistant_event_log_${id}.txt`), () => {});
  }

  /* ---------- Werte ---------- */
  _log(...a) { if (this._config?.debug) console.info("mg-car:", ...a); }
  /* Zustand einer Entität. Ist sie nur kurz nicht verfügbar (z. B. während ev_assistant nach einer
     Einstellungsänderung neu lädt), wird bis zu 60 s der letzte gültige Zustand weiterverwendet,
     damit die Kacheln nicht kurz leer werden und springen. */
  _st(id) {
    if (!id) return undefined;
    let s;
    if (id.startsWith("eva:")) { const r = this._resolve(id); if (r) return this._st(r); s = this._virtState(id.slice(4)); }
    else s = this._hass?.states[id];
    const now = Date.now(), lg = (this._good = this._good || {});
    if (s && !OFFLINE_HD.includes(s.state)) { lg[id] = { s, t: now }; return s; }
    const g = lg[id];
    return g && now - g.t < 60000 ? g.s : s;
  }
  /* ---------- ev_assistant als Quelle ("eva:…") ---------- */
  // Panel-Konfiguration von ev_assistant: Fahrzeugname, config_entry_id, evcc-Fahrzeug und die dort
  // konfigurierten Sensoren (bisher gibt ev_assistant davon nur den SoC-Sensor weiter)
  async _loadEvaPanel() {
    if (this._evaPanelReq || !this._hass) return;
    this._evaPanelReq = true;
    let cfg = this._config.ev_assistant_panel;   // vom ev_assistant-Panel übergeben
    if (!cfg && this._hass.callWS) {
      try {
        const panels = await this._hass.callWS({ type: "get_panels" });
        const names = ["ev-assistant-panel", "ev-assistant-glow-panel"];
        const l = Object.values(panels || {}).filter((x) => x?.config?.entities || x?.config?.vehicles);
        const p = l.find((x) => x.url_path === "ev-assistant") || l.find((x) => names.includes(x.config?._panel_custom?.name));
        cfg = p?.config || null;
      } catch (e) { cfg = null; }
    }
    cfg = cfg || {};
    this._evaPanelCfg = cfg;
    let vs = Array.isArray(cfg.vehicles) && cfg.vehicles.length ? cfg.vehicles : cfg.entities ? [cfg] : [];
    if (!vs.length) vs = this._evaDevices();   // ältere ev_assistant-Versionen: Fahrzeuge aus den Geräten
    this._evaVehicles = vs;
    let want = null; try { want = localStorage.getItem(this._vehKey()); } catch (e) {}
    if (!vs.some((v) => v.config_entry_id === want)) want = this._config.car.ev_assistant_entry;
    this._evaPanel = vs.find((v) => want && v.config_entry_id === want) || vs[0] || null;
    this._applyVehicle();
    // Schnittstellen-Version prüfen
    const api = cfg.api_version;
    this._apiWarn = api != null && Number(api) !== EVA_API_VERSION
      ? `ev_assistant meldet Schnittstellen-Version ${api}, diese Karte erwartet ${EVA_API_VERSION}. Einzelne Werte können fehlen – bitte Karte bzw. ev_assistant aktualisieren.` : "";
    if (this._apiWarn) console.warn("mg-car-dashboard:", this._apiWarn);
    this._log("ev_assistant-Fahrzeug", this._evaPanel);
    if (this._config.debug) {   // welche Quelle wird für welchen Wert verwendet
      const c = this._config.car, ev = c.evcc || {}, src = (id) => (!id ? "–" : id.startsWith("eva:") ? this._resolve(id) || `evcc-Live (${id})` : id);
      console.table(Object.fromEntries([["soc", c.soc], ["range", c.range], ["status", c.status], ["cable", c.cable], ...Object.entries(ev).map(([k, v]) => ["evcc." + k, v]),
        ["trips", c.trips]].map(([k, v]) => [k, { Quelle: src(v) }])));
    }
    this._loadCarHist(); this._loadLastSession(); this._loadTrips();
    this._update(true);
  }

  _vehKey() { return "mg-car-vehicle-" + (this._config?.quick_layout_key || "default"); }

  // Fahrzeuge ohne Panel-Konfiguration: je ev_assistant-Gerät (ein Gerät pro Fahrzeug bzw. config entry)
  _evaDevices() {
    const reg = this._hass?.entities || {}, dev = this._hass?.devices || {}, out = new Map();
    for (const e of Object.values(reg)) {
      if (e.platform !== "ev_assistant" || !e.device_id) continue;
      const d = dev[e.device_id], id = d?.config_entries?.[0];
      if (id && !out.has(id)) out.set(id, { config_entry_id: id, name: d.name_by_user || d.name || "Auto", entities: {} });
    }
    return [...out.values()];
  }

  // Konfiguration für das gewählte Fahrzeug: Grundkonfiguration + vehicles[Name oder config_entry_id]
  _applyVehicle() {
    const v = this._evaPanel, raw = JSON.parse(JSON.stringify(this._rawConfig || {})), vmap = raw.vehicles || {};   // Kopie: Kartenkonfiguration nicht verändern
    // Bettet das ev_assistant-Panel die Karte ein und übersetzt dabei die Werte des ersten Fahrzeugs in car-Optionen,
    // gelten diese bei mehreren Fahrzeugen nicht für die anderen – dann ignorieren (die Karte findet sie selbst).
    const P = this._evaPanelCfg || {}, E0 = P.entities || {};
    if (raw.ev_assistant_panel && (this._evaVehicles || []).length > 1 && raw.car) {
      const same = { name: P.name, ev_assistant_entry: P.config_entry_id, evcc_vehicle: P.evcc_vehicle_name, soc: E0.soc_entity, status: E0.motor_entity, cable: E0.plug_entity };
      for (const [k, val] of Object.entries(same)) if (val != null && raw.car[k] === val) delete raw.car[k];
      if (raw.energy && raw.energy.car_power === (E0.power_entity || E0.home_entity)) delete raw.energy.car_power;
    }
    const key = Object.keys(vmap).find((k) => v && (k === v.config_entry_id || k.toLowerCase() === String(v.name || "").toLowerCase()));
    const over = key ? vmap[key] : {};
    const { energy: oe, ...oc } = over || {};
    this._config = merge(CAR_DEFAULTS, merge(raw, { car: oc, ...(oe ? { energy: oe } : {}) }));
  }

  // anderes Fahrzeug gewählt: alles Fahrzeugbezogene verwerfen und neu laden
  _selectVehicle(entryId) {
    const v = (this._evaVehicles || []).find((x) => x.config_entry_id === entryId);
    if (!v || v === this._evaPanel) return;
    try { localStorage.setItem(this._vehKey(), entryId); } catch (e) {}
    this._evaPanel = v;
    this._applyVehicle();
    for (const k of ["_evaCache", "_evaEntryCache", "_sess", "_evaTrips", "_lastSess", "_carHist", "_charges", "_tripCount", "_wasCharging", "_balOptimistic", "_evaModeOpt", "_pendingNum"]) this[k] = null;
    this._good = {};
    const car = this.shadowRoot?.getElementById("car"); if (car) car._html = null;
    this._log("Fahrzeug gewechselt", v);
    this._loadCarHist(); this._loadLastSession(); this._loadTrips(true);
    this._update(true);
  }

  // evcc-Live-Werte, die ev_assistant als Attribut "evcc_live" am Sensor home_kwh mitliefert
  /* Ladestrom je Phase als „6 A | 0 A | 0 A“ (HTML, null wenn keine Werte) */
  _phaseIds() {
    const cfg = this._config.car.evcc?.currents;
    return Array.isArray(cfg) ? cfg : cfg === "eva:currents" ? [0, 1, 2].map((i) => this._evccEnt(`chargecurrents_${i}`, true)) : [];
  }
  _phaseCurrents() {
    const live = this._live().charge_currents;   // evcc /api/state „chargeCurrents“, von ev_assistant weitergereicht
    const v = this._config.car.evcc?.currents === "eva:currents" && Array.isArray(live) && live.length
      ? live.map((x) => (x == null || isNaN(Number(x)) ? null : Number(x)))
      : this._phaseIds().map((id) => { const x = parseFloat(this._st(id)?.state); return isNaN(x) ? null : x; });
    if (!v.some((x) => x != null)) return null;
    return v.map((x) => `<span>${x == null ? "–" : `${de(Math.round(x * 10) / 10, Math.round(x * 10) % 10 ? 1 : 0)}&nbsp;A`}</span>`).join(`<i>|</i>`);
  }

  _live() { return this._hass?.states[this._eva().home_kwh]?.attributes?.evcc_live || {}; }

  // "eva:…" → echte Entität, sofern ev_assistant eine liefert
  _resolve(id) {
    const k = id.slice(4), P = this._evaPanel?.entities || {}, E = this._eva();
    const real = { soc: P.soc_entity, range: E.range_estimate, motor: P.motor_entity, plug: P.plug_entity || P.wallbox_connected_entity,
      charging: P.wallbox_charging_entity, charge_power: P.home_entity || P.power_entity,
      limit_soc: this._evccEnt("limitsoc"), max_current: this._evccEnt("maxcurrent") }[k];
    return real && this._hass?.states[real] ? real : null;
  }

  // Entität der evcc-Integration (marq24/ha-evcc, Plattform "evcc_intg") anhand ihres translation_key,
  // z. B. "limitsoc" (Ladeziel) oder "maxcurrent" (Ladestrom). Select vor number, bei mehreren
  // Ladepunkten entscheidet car.evcc_loadpoint (Teil der Entity-ID).
  _evccEnt(key, sensor = false) {
    const reg = this._hass?.entities;
    if (!reg) return null;
    if (this._evccCache?.ref !== reg) {
      const m = {};
      for (const e of Object.values(reg)) if (e.platform === "evcc_intg" && e.translation_key && /^(select|number|sensor)\./.test(e.entity_id)) (m[e.translation_key] ||= []).push(e.entity_id);
      this._evccCache = { ref: reg, m };
    }
    const lp = String(this._config.car.evcc_loadpoint || "").toLowerCase();
    const l = (this._evccCache.m[key] || []).filter((id) => this._hass.states[id] && (!lp || id.includes(lp)) && id.startsWith("sensor.") === sensor)
      .sort((a, b) => (a.startsWith("select.") ? 0 : 1) - (b.startsWith("select.") ? 0 : 1) || a.localeCompare(b));
    return l[0] || null;
  }

  // echte Entität (für Verlauf/Statistik und Detailansicht) oder null
  _real(id) { return !id ? null : id.startsWith("eva:") ? this._resolve(id) : this._hass?.states[id] ? id : null; }

  // Wert aus den evcc-Live-Werten als Zustand im Format von hass.states
  _virtState(k) {
    const L = this._live(), t = this._hass?.states[this._eva().home_kwh]?.last_updated || "";
    const mk = (v, unit) => (v == null || v === "" ? undefined : { state: String(v), attributes: { unit_of_measurement: unit }, last_updated: t, virtual: true });
    const onoff = (v) => (v == null ? undefined : mk(v ? "on" : "off", ""));
    switch (k) {
      case "soc": return mk(L.vehicle_soc, "%");
      case "plug": case "connected": return onoff(L.connected);
      case "charging": return onoff(L.charging);
      case "charge_power": return mk(L.charge_power, "kW");
      case "session_energy": return mk(L.session_energy, "kWh");
      case "session_solar": return mk(L.session_solar_pct, "%");
      case "session_price": return mk(L.session_price, "€");
      case "duration": return L.charge_duration == null ? undefined : mk(L.charge_duration / 60, "min");   // s → min
      case "limit_soc": return mk(L.limit_soc, "%");
      case "min_soc": return mk(L.min_soc, "%");
      case "solar_total": return mk(L.stat_solar_pct, "%");
      case "last_charge": return this._lastSess?.end ? mk(new Date(this._lastSess.end).toISOString(), "") : undefined;
    }
    return undefined;
  }

  _evccVehicle() { return String(this._config.car.evcc_vehicle || this._evaPanel?.evcc_vehicle_name || "").toLowerCase(); }

  // aktueller Lademodus bei Steuerung über ev_assistant: "auto" oder der manuell gesetzte Modus
  /* evcc „immer laden“ (off/on/once) für Smart: aus der evcc-Integration (Select „alwayscharge“), sonst aus dem Modus */
  _evaAlways(mode) {
    if (this._evaSmartOpt && Date.now() - this._evaSmartOpt.t < 20000) return this._evaSmartOpt.ac;
    const st = this._st(this._evccEnt("alwayscharge"))?.state;
    if (["off", "on", "once"].includes(st) && (mode === "pv" || mode === "minpv")) return st;
    return mode === "minpv" ? "on" : "off";
  }

  _evaModeState() {
    const ma = this._st(this._eva().evcc_mode_control)?.attributes || {};
    let cur = ma.manueller_modus_aktiv && ma.manueller_modus ? ma.manueller_modus : "auto";
    if (this._evaModeOpt && Date.now() - this._evaModeOpt.t < 20000) { if (this._evaModeOpt.v === cur) this._evaModeOpt = null; else cur = this._evaModeOpt.v; }
    return { cur, evcc: this._live().mode };
  }

  _num(id) { const s = this._st(id); const v = s ? parseFloat(s.state) : NaN; return isNaN(v) ? 0 : v; }
  _w(id) { const s = this._st(id); if (!s) return 0; const u = (s.attributes.unit_of_measurement || "").toLowerCase(); return this._num(id) * (u === "kw" ? 1000 : 1); }
  _power(w) { w = Math.abs(w); return w >= 1000 ? { v: de(w / 1000, 1), u: "kW" } : { v: String(Math.round(w)), u: "W" }; }

  /* Bildschirm-Anpassung: auf breiten Bildschirmen genau Fensterhöhe, Inhalte skalieren/scrollen innen */
  _fit() {
    const wrap = this.shadowRoot?.querySelector(".wrap");
    if (!wrap) return;
    const top = this._docTop();
    wrap.classList.toggle("sat", top < 30);   // ganz oben (ohne HA-Kopfzeile): Abstand zur iPhone-Statusleiste
    const on = this._config?.fit_screen !== false && this.clientWidth > 1180;
    if (!on) { wrap.classList.remove("fit"); return; }
    const h = Math.max(560, Math.floor(window.innerHeight - top));
    wrap.style.setProperty("--fit-h", h + "px");
    wrap.classList.add("fit");
    wrap.classList.toggle("compact", h < 860);   // niedrige Fenster: alles etwas kompakter
  }

  /* Abstand der Karte zum Seitenanfang, unabhängig von der Scrollposition. HA (auch die Companion-App) scrollt in einem
     eigenen Container statt im Fenster – dessen scrollTop muss mitgezählt werden, sonst wirkt die Karte beim Scrollen
     „ganz oben“ (Safe-Area-Abstand springt an, die Seite verschiebt sich) */
  _docTop() {
    let y = this.getBoundingClientRect().top + window.scrollY;
    for (let n = this.parentNode || this.getRootNode()?.host; n && n !== document; n = n.parentNode || n.host) if (n.scrollTop) y += n.scrollTop;
    return y;
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
    const entry = this._evaPanel?.config_entry_id || this._config.car.ev_assistant_entry || null;
    if (this._evaCache?.ref === reg && this._evaCache.entry === entry) return this._evaCache.map;
    // bisher gefundene Entitäten behalten (beim Neuladen der Integration fehlen sie sonst kurz) – aber nur vom selben Fahrzeug
    const map = { ...(this._evaCache?.entry === entry ? this._evaCache.map : {}) }, dev = this._hass?.devices || {};
    // bei mehreren Fahrzeugen nur die Entitäten des gewählten (über das Gerät bzw. den config entry)
    const mine = (e) => !entry || e.config_entry_id === entry || (dev[e.device_id]?.config_entries || []).includes(entry);
    for (const e of Object.values(reg)) if (e.platform === "ev_assistant" && e.translation_key && mine(e)) map[e.translation_key] = e.entity_id;
    Object.assign(map, fixed);
    this._evaCache = { ref: reg, entry, map };
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

  /* Fahrzeugbild: eigenes car.image, sonst das Bild aus ev_assistant (Entität „Fahrzeugbild“, ab 0.99.45).
     Ohne Bild steht deren Zustand auf „unknown“ – dann kein Bild (image_proxy würde mit 500 antworten).
     Die URL enthält einen Token, der alle paar Minuten wechselt: sie wird nur bei geändertem Zustand
     (= neues Bild) übernommen, damit das Bild nicht ständig neu lädt; schlägt das Laden fehl, einmal mit
     frischer URL wiederholen. */
  _carImage() {
    const c = this._config.car;
    if (c.image) return c.image;
    const id = this._evaPanel?.entities?.vehicle_image || this._eva().vehicle_image, st = id && this._hass?.states[id];
    if (!st || OFFLINE_HD.includes(st.state) || !st.attributes?.entity_picture) { this._imgC = null; return ""; }
    if (this._imgC?.id !== id || this._imgC.v !== st.state) this._imgC = { id, v: st.state, url: st.attributes.entity_picture };
    return this._imgC.failed ? "" : this._imgC.url;
  }
  _carImageError(img) {
    const C = this._imgC, st = C && this._hass?.states[C.id];
    if (C && !C.retried && st?.attributes?.entity_picture) { C.retried = true; C.url = st.attributes.entity_picture; }   // frischer Token
    else if (C) C.failed = true;
    else { img.style.display = "none"; return; }
    const el = this.shadowRoot.getElementById("car"); if (el) el._html = null;
    this._render_car();
  }

  _render_car() {
    const img = this._carImage();
    const c = this._config.car, ev = c.evcc || {}, E = this._eva();
    const hasSoc = !!this._st(c.soc), soc = Math.max(0, Math.min(100, this._num(c.soc)));
    const { charging, plugged, driving, pw } = this._carState();
    const range = this._st(c.range), rEst = this._real(c.range) === E.range_estimate ? null : this._fmt(E.range_estimate, 0), name = c.name || this._evaPanel?.name || "Auto";
    const status = charging ? "Lädt" : driving ? (c.status_on || "Unterwegs") : plugged ? "Angesteckt" : (c.status_off || "Geparkt");

    // Markierungen im Balken: Ladeziel (evcc) und Mindest-SoC (immer laden bis …)
    const lim = ev.limit_soc && this._st(ev.limit_soc) ? this._num(ev.limit_soc) : null;
    const min = ev.min_soc && this._st(ev.min_soc) ? this._num(ev.min_soc) : null;
    const marks = [min != null && min > 0 && min < 100 ? `<i class="bm min" style="left:${min}%" title="Mindestladung ${Math.round(min)} %"></i>` : "",
      lim != null && lim > 0 && lim < 100 ? `<i class="bm lim" style="left:${lim}%" title="Ladeziel ${Math.round(lim)} %"></i>` : ""].join("");

    // Infozeile: letzte Fahrt und letzte Ladung (beim Laden „jetzt“ – Leistung, Energie und PV stehen in der Kachel „Laden“)
    let line = "";
    {
      const lt = this._fmt(E.last_trip_km, 0), lc = this._st(ev.last_charge);
      const lcD = lc && !OFFLINE_HD.includes(lc.state) ? new Date(lc.state) : null;
      const parts = [];
      if (lt) parts.push(`<span>${icon("mdi:map-marker-path")}Letzte Fahrt <b>${lt.v}</b> km</span>`);
      if (charging) parts.push(`<span class="now">${icon("mdi:ev-station")}Letzte Ladung <b>jetzt</b></span>`);
      else if (lcD && !isNaN(lcD)) parts.push(`<span>${icon("mdi:ev-station")}Letzte Ladung <b>${this._ago(lcD)}</b></span>`);
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
    // offene Fremdladungen/Fahrten (nicht automatisch übernommen): Hinweis oben rechts statt des Pfeils, öffnet „Bestätigen“
    const pend = this._pendItems(), nP = pend.charges.length + pend.trips.length;
    const pendBtn = nP ? `<button class="cpend" data-act="pendopen" title="Erkannte Fremdladungen und Fahrten bestätigen">${icon(pend.charges.length ? "mdi:ev-station" : "mdi:map-marker-question")}<b>${nP}</b><span>${nP === 1 ? (pend.charges.length ? "Ladung" : "Fahrt") : "offen"} bestätigen</span></button>` : "";
    const wf = this._st(E.wartung_faellig);
    if (wf && ["on", "true", "ja", "fällig"].includes(String(wf.state).toLowerCase())) flags.push(["mdi:wrench", "Wartung fällig", E.wartung_faellig]);

    const html = `
      <div class="hd">${(this._evaVehicles || []).length > 1
        ? `<button class="ttl vsel" data-act="vehmenu" title="Fahrzeug wählen">${esc(name)}${icon("mdi:chevron-down", "vchv")}</button>`
        : `<span class="ttl">${esc(name)}</span>`}<span class="lbl ${charging ? "chg" : ""}">${charging ? `${icon("mdi:lightning-bolt")} ` : ""}${esc(status)}</span>
        ${pendBtn}</div>
      <div class="carbody" data-act="cardetail">
        <div><div class="soc">${hasSoc ? Math.round(soc) : "–"}<sup>%</sup></div>
          <div class="range">${range ? `${Math.round(this._num(c.range))} km` : rEst ? `${rEst.v} km` : ""}${range && rEst ? `<small> · real ≈ ${rEst.v} km</small>` : ""}</div></div>
        ${img ? `<img class="carimg" src="${esc(img)}" alt="">` : ""}
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
    menu.addEventListener("click", (e) => this._click(e));   // liegt außerhalb der Karte: Klicks selbst weiterreichen
    if (!document.getElementById("mg-menu-styles")) {
      const st = document.createElement("style");
      st.id = "mg-menu-styles";
      st.textContent = `.mg-menu-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:12px;cursor:pointer;font-size:14px;font-weight:500;color:#94a3b8;background:none;border:0;width:100%;text-align:left;white-space:nowrap}.mg-menu-item:hover{background:rgba(255,255,255,.06);color:#e2e8f0}.mg-menu-item.cur{background:rgba(255,255,255,.08);color:#e2e8f0}.mg-menu-item ha-icon{--mdc-icon-size:17px}.mg-menu-item .glyph{font-size:15px}.mg-menu-item .ck{margin-left:auto;--mdc-icon-size:16px;color:#34d399}`;
      document.head.appendChild(st);
    }
    Object.assign(menu.style, {
      position: "fixed", zIndex: "99999", boxSizing: "border-box",
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
    // Vertikal: nach unten, wenn das Menü dort ganz hinpasst (oder unten mehr Platz ist), sonst nach oben –
    // die Höhe richtet sich nach dem Platz auf der gewählten Seite, der Rest ist im Menü scrollbar
    const pad = 8, full = menu.scrollHeight;
    const spaceBelow = window.innerHeight - ar.bottom - 4 - pad, spaceAbove = ar.top - 4 - pad;
    const below = spaceBelow >= full || spaceBelow >= spaceAbove;
    const mh = Math.max(80, Math.min(full, below ? spaceBelow : spaceAbove));
    menu.style.maxHeight = mh + "px";
    menu.style.overflowY = "auto";
    menu.style.overscrollBehavior = "contain";
    menu.style.top = Math.max(pad, below ? ar.bottom + 4 : ar.top - 4 - mh) + "px";
    // aktuellen Wert mittig ins Menü scrollen (nur das Menü, nicht die Seite)
    const cur = menu.querySelector(".cur");
    if (cur) menu.scrollTop = Math.max(0, cur.offsetTop - (mh - cur.offsetHeight) / 2);
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
    if (act === "pendopen") { this._openPend(); return; }
    if (act === "cper") { const cp = this._cpGet(); cp.p = el.dataset.v; cp.off = 0; try { localStorage.setItem("mg-car-cost-period", cp.p); } catch (x) {} this._render_cost(); return; }
    if (act === "ksort") { const so = this._kSort || { k: "ts", d: -1 }, v = el.dataset.v; this._kSort = so.k === v ? { k: v, d: -so.d } : { k: v, d: -1 }; const b = this.shadowRoot.querySelector("#klist .klist"); if (b) b.scrollTop = 0; this._render_cost(); return; }
    if (act === "cnav") { const cp = this._cpGet(); cp.off = Math.min(0, cp.off + Number(el.dataset.d)); this._render_cost(); return; }
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
    if (act === "evalimmenu") { this._openEvaLimMenu(el); return; }
    if (act === "evalimset") {
      this._closeMenu();
      const v = Number(el.dataset.v);
      (this._opt ||= {}).socmax = { v, t: Date.now() };
      this._evaCall("set_evcc_mode_control_target_soc_max", { target_soc_max: v }).catch((x) => this._mgmtFail(x));
      this._render_mgmt(); setTimeout(() => this._render_mgmt(), 30500);
      return;
    }
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
      this._evaCall("set_weekly_full_charge_enabled", { enabled: enable }).catch((x) => this._mgmtFail(x));
      // bis die Integration den neuen Wert meldet (spätestens nach 30 s wieder echten Wert zeigen)
      clearTimeout(this._balTimer);
      this._balTimer = setTimeout(() => { this._balOptimistic = null; this._render_mgmt(); }, 30000);
      return;
    }
    if (act === "vehmenu") {
      this._closeMenu();
      const cur = this._evaPanel?.config_entry_id, menu = document.createElement("div"); menu.className = "menu";
      menu.innerHTML = (this._evaVehicles || []).map((v) => `<button class="mg-menu-item mi ${v.config_entry_id === cur ? "cur" : ""}" data-act="vehset" data-v="${esc(v.config_entry_id)}">
        ${icon("mdi:car-electric")}<span>${esc(v.name || v.title || "Auto")}</span>${v.config_entry_id === cur ? icon("mdi:check", "ck") : ""}</button>`).join("");
      this._openMenuAt(el, menu);
      return;
    }
    if (act === "vehset") { this._closeMenu(); this._selectVehicle(el.dataset.v); return; }
    if (act === "evasmartmenu") {
      this._closeMenu();
      const ms = this._evaModeState(), cur = this._evaAlways(ms.cur !== "auto" ? ms.cur : ms.evcc), once = !!this._evccEnt("alwayscharge");
      const menu = document.createElement("div"); menu.className = "menu";
      menu.innerHTML = EVA_SMART_OPTS.filter((o) => o.ac !== "once" || once).map((o) => {
        const isCur = (ms.cur !== "auto" ? ms.cur : ms.evcc) !== "now" && o.ac === cur;
        return `<button class="mg-menu-item mi ${isCur ? "cur" : ""}" data-act="evasmart" data-v="${o.ac}">
          ${o.glyph ? `<span class="glyph">${o.glyph}</span>` : icon(o.icon)}<span>Smart · ${o.label}<small style="opacity:.6;margin-left:6px">${o.long}</small></span>${isCur ? icon("mdi:check", "ck") : ""}</button>`;
      }).join("");
      this._openMenuAt(el, menu);
      return;
    }
    if (act === "evamanmenu") {
      this._closeMenu();
      const menu = document.createElement("div"); menu.className = "menu";
      menu.innerHTML = EVA_MANUAL.filter((m) => !m.needs || this._evccEnt(m.needs)).map((m) => {
        const isCur = m.v === this._evaSelCur;
        return `<button class="mg-menu-item mi ${isCur ? "cur" : ""}" data-act="${m.act}" data-v="${m.dv}">${m.glyph ? `<span class="glyph">${m.glyph}</span>` : icon(m.icon)}<span>${m.label}<small style="opacity:.6;margin-left:6px">${m.sub}</small></span>${isCur ? icon("mdi:check", "ck") : ""}</button>`;
      }).join("");
      this._openMenuAt(el, menu);
      return;
    }
    if (act === "evamode2") {
      this._closeMenu();
      const v = el.dataset.v;
      this._evaSel = { v, t: Date.now() }; this._evaModeOpt = { v: v === "off" ? "pv" : v, t: Date.now() }; this._evaSmartOpt = null;
      (this._opt ||= {}).pause = { v: v !== "auto", t: Date.now() };
      // „Aus“ kennt ev_assistant nicht: manuell (ev_assistant schreibt dann nicht mehr) und evcc über die evcc-Integration ausschalten
      const ms = this._evccEnt("mode");
      (v === "auto" ? this._evaAuto() : this._evaManual(v === "off" ? "pv" : v))
        .then(() => { if (v === "off" && ms) setTimeout(() => Promise.resolve(this._hass.callService("select", "select_option", { entity_id: ms, option: "off" })).catch((x) => this._mgmtFail(x)), 3000); })
        .catch((x) => this._mgmtFail(x));
      this._render_mgmt(); setTimeout(() => this._render_mgmt(), 30500);
      return;
    }
    if (act === "evasmart") {
      this._closeMenu();
      const o = EVA_SMART_OPTS.find((x) => x.ac === el.dataset.v); if (!o) return;
      this._evaSel = { v: o.ac === "off" ? "pv" : o.ac === "on" ? "minpv" : "once", t: Date.now() };
      this._evaModeOpt = { v: o.mode, t: Date.now() }; this._evaSmartOpt = { ac: o.ac, t: Date.now() };
      // 1x gibt es nur über die evcc-Integration: nach dem Moduswechsel (ev_assistant schreibt „immer“) auf „einmalig“ stellen
      const sel = this._evccEnt("alwayscharge");
      (this._opt ||= {}).pause = { v: true, t: Date.now() };
      this._evaManual(o.mode)
        .then(() => { if (sel && o.ac === "once") setTimeout(() => Promise.resolve(this._hass.callService("select", "select_option", { entity_id: sel, option: "once" })).catch((x) => this._mgmtFail(x)), 3000); })
        .catch((x) => this._mgmtFail(x));
      this._render_mgmt();
      setTimeout(() => this._render_mgmt(), 30500);
      return;
    }
    if (act === "evamode") {
      const v = el.dataset.v;
      this._evaModeOpt = { v, t: Date.now() }; this._evaSmartOpt = null;
      (v === "auto" ? this._evaCall("clear_evcc_manual_mode", {}) : this._evaCall("set_evcc_manual_mode", { mode: v })).catch((x) => this._mgmtFail(x));
      this._render_mgmt();
      setTimeout(() => this._render_mgmt(), 20500);
      return;
    }
    if (act === "mpause") {
      const paused = el.dataset.v === "1";
      (this._opt ||= {}).pause = { v: paused, t: Date.now() };
      if (!paused) { this._evaSel = { v: "auto", t: Date.now() }; this._evaModeOpt = { v: "auto", t: Date.now() }; }
      (paused ? this._evaCall("set_evcc_mode_control_pause", { paused: true }) : this._evaAuto()).catch((x) => this._mgmtFail(x));
      this._render_mgmt(); setTimeout(() => this._render_mgmt(), 30500);
      return;
    }
    if (act === "mplanclear") {
      if (!window.confirm("Ladeplan löschen?")) return;
      // sofort als gelöscht anzeigen, bis ev_assistant das bestätigt (oder nach 60 s wieder den echten Stand)
      this._planCleared = { t: Date.now(), was: this._hass?.states[this._eva().evcc_charge_plan]?.state };
      this._planTime = null; this._render_mgmt(); this._render_live();
      this._evaCall("clear_evcc_charge_plan", {}).catch((x) => { this._planCleared = null; this._render_mgmt(); this._render_live(); window.alert(`Ladeplan konnte nicht gelöscht werden: ${x?.message || x}`); });
      return;
    }
    if (act === "mplanedit") { this._planEdit = true; this._planSoc = this._planKm = null; this._planTime = null; this._render_mgmt(); return; }
    if (act === "mplancancel") { this._planEdit = false; this._planReq = null; this._render_mgmt(); return; }
    if (act === "planunit") { this._planUnit = el.dataset.v; try { localStorage.setItem("mg-car-plan-unit", this._planUnit); } catch (x) {} this._planTime = this.shadowRoot.querySelector("#mgmt .pin")?.value; this._render_mgmt(); return; }
    if (act === "mplankm") { const kp = this._kmPerPct(), base = this._planKm ?? (kp ? Math.round(((this._planSoc ?? 80) * kp) / 10) * 10 : 200); this._planKm = Math.max(10, Math.min(1000, base + Number(el.dataset.d))); this._planTime = this.shadowRoot.querySelector("#mgmt .pin")?.value; this._render_mgmt(); return; }
    if (act === "mplansoc") { this._planSoc = Math.max(10, Math.min(100, (this._planSoc ?? 80) + Number(el.dataset.d))); this._planTime = this.shadowRoot.querySelector("#mgmt .pin")?.value; this._render_mgmt(); return; }
    if (act === "mplanset") {
      const v = this.shadowRoot.querySelector("#mgmt .pin")?.value, t = v ? new Date(v).getTime() : NaN;
      if (isNaN(t) || t < Date.now() + 10 * 60000) { window.alert("Bitte eine Zielzeit in der Zukunft wählen."); return; }
      // Rückmeldung: „Wird gesetzt …“; einen Fehler des Service (ev_assistant ab 0.99.35 nennt den Grund) sofort anzeigen.
      // Meldet der Plan-Sensor nach 12 s noch keinen Plan: war der Aufruf erfolgreich, nur ein neutraler Hinweis
      clearTimeout(this._planReq?.timer);
      const req = (this._planReq = { busy: true, err: "", info: "", sent: false, target: t });
      const done = (key, msg) => { if (this._planReq !== req) return; clearTimeout(req.timer); req.busy = false; req[key] = msg; this._planTime = v; this._render_mgmt(); };
      req.timer = setTimeout(() => (req.sent ? done("info", this._planSentText()) : done("err", "Keine Antwort von ev_assistant – Ladeplan vermutlich nicht gesetzt.")), 12000);
      // Ziel direkt aus der Auswahl lesen (zeigt immer den Wert, der auch gesendet wird)
      const sel = this.shadowRoot.querySelector("#mgmt .mptgt"), sv = Number(sel?.value);
      const byKm = sel?.dataset.u === "km" && !!this._hass?.services?.ev_assistant?.set_evcc_charge_plan_range_km;
      if (byKm) this._planKm = sv; else if (sv) this._planSoc = sv;
      (byKm ? this._evaCall("set_evcc_charge_plan_range_km", { target_range_km: sv, target_time: Math.round(t / 1000) })
        : this._evaCall("set_evcc_charge_plan", { target_soc: sv || 80, target_time: Math.round(t / 1000) }))
        .then(() => { req.sent = true; })
        .catch((x) => done("err", `Ladeplan konnte nicht gesetzt werden: ${x?.message || x?.error?.message || x}`));
      this._planTime = v; this._render_mgmt(); return;
    }
    if (act === "none") return;
    if (act === "chfilter") { this._chFilter = el.dataset.v; this._dlgN = this._page(); this._renderCharges(); this.shadowRoot.querySelector("#cardlg .dbody")?.scrollTo(0, 0); return; }
    if (act === "statview") {
      this._statTab = el.dataset.v;
      try { localStorage.setItem("mg-car-stat-view", this._statTab); } catch (x) {}
      this._render_lease(); this._render_usage(); return;
    }
    if (act === "hrange") {
      this._hh = Number(el.dataset.h);
      try { localStorage.setItem("mg-car-hist-hours", String(this._hh)); } catch (x) {}
      // Höhe halten, bis die neuen Daten da sind – sonst fällt die Seite kurz zusammen und springt nach oben (iOS)
      const hel = this.shadowRoot.getElementById("hist");
      if (hel) hel.style.minHeight = hel.offsetHeight + "px";
      this._carHist = null; this._render_hist(); this._loadCarHist(); return;
    }
    if (act === "cardetail") {
      const id = this._real(this._config.car.soc) || this._eva().home_kwh; if (!id) return;
      const ev = new Event("hass-more-info", { bubbles: true, composed: true }); ev.detail = { entityId: id }; this.dispatchEvent(ev); return;
    }
    if (act === "page") { this._pg = el.dataset.p; try { localStorage.setItem("mg-car-page", this._pg); } catch (x) {} this._showPage(); this._update(true); requestAnimationFrame(() => { this._fit(); this._render_trips(); }); return; }
    if (act === "ana") { this._openAna(el.dataset.k); return; }
    if (act === "set") { this._setAct(el.dataset.k, el.dataset); return; }
    if (act === "cardclose") { this.shadowRoot.getElementById("cardlg")?.close(); return; }
    if (!entity) return;
    if (act === "more") {
      const id = entity.startsWith("eva:") ? this._resolve(entity) || this._eva().home_kwh : entity;   // Live-Werte: Detailansicht von ev_assistant
      if (!id) return;
      const ev = new Event("hass-more-info", { bubbles: true, composed: true });
      ev.detail = { entityId: id }; this.dispatchEvent(ev);
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
.cline .now ha-icon,.cline .now b{color:var(--green)}
.cline.charge .pv ha-icon,.cline.charge .pv b{color:var(--e-solar)}
.cflags{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}
.chip.warn{color:var(--orange);background:rgba(251,146,60,.1);border-color:rgba(251,146,60,.3)}
.cstats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 14px}
.cstat{display:flex;flex-direction:column;gap:2px;padding:9px 11px;border-radius:15px;background:var(--tile);border:1px solid var(--tileb);min-width:0}
.cstat span{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cstat b{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.cstat small{font-size:11.5px;color:var(--muted);font-weight:500;margin-left:3px}
.stathd .hsegs{margin-left:0}
.stathd .hseg{padding:0 12px}
#usage .ustats{grid-template-columns:repeat(3,minmax(0,1fr));margin:0 0 14px}
#usage .ustats .cstat{padding:9px 10px}
#usage .ustats .cstat span{letter-spacing:.03em;text-overflow:clip}
@container (max-width:720px){#usage .ustats .cstat span{font-size:10.5px;letter-spacing:.01em}#usage .ustats .cstat b{font-size:16.5px}}
#usage .ustab em{display:block;font-style:normal;font-size:11px;font-weight:500;color:var(--dim)}
#usage .unote{font-size:11px;color:var(--dim);margin-top:6px}
#usage .ustab{display:grid;grid-template-columns:auto repeat(4,minmax(0,1fr));column-gap:10px;row-gap:8px;align-items:baseline;border-radius:16px;background:var(--tile);border:1px solid var(--tileb);padding:10px 14px;font-size:13.5px;color:var(--muted)}
#usage .ustab .h{font-size:11px;letter-spacing:.06em;text-transform:uppercase;font-weight:600;text-align:right}
#usage .ustab b{color:var(--text);font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right;cursor:pointer}
#usage .ustab b.dim{color:var(--dim);cursor:default}
#usage .ustab small{color:var(--muted);font-weight:500}
#usage .uloc{display:flex;flex-direction:column;gap:8px;width:100%;margin-top:14px}
#usage .uloc .mgl small{letter-spacing:0;text-transform:none}
#usage .ubar{display:flex;height:10px;border-radius:6px;overflow:hidden;background:rgba(255,255,255,.07)}
#usage .ubar i{display:block;height:100%}
#usage .pv{background:var(--e-solar)}#usage .home{background:var(--green)}#usage .ext{background:var(--e-grid-in)}
#usage .ulg{display:flex;flex-wrap:wrap;column-gap:12px;row-gap:2px;font-size:11.5px;color:var(--dim);font-variant-numeric:tabular-nums}
#usage .ulg>span{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
#usage .ld{display:inline-block;width:8px;height:8px;border-radius:2px}
#lease .lstats{grid-template-columns:repeat(2,minmax(0,1fr));margin:0 0 14px}
#lease .neg,#lease .cstat.neg b{color:var(--red)}
#lease .pos,#lease .cstat.pos b{color:var(--green)}
#lease .lscap{display:flex;justify-content:space-between;font-size:13px;color:var(--muted)}
#lease .lscap b{color:var(--text);font-variant-numeric:tabular-nums}
#lease .bar{margin:8px 0 4px;position:relative;overflow:visible}
#lease .bm.soll{background:#fff}
#lease .lsnote{display:flex;flex-wrap:wrap;align-items:center;column-gap:12px;row-gap:2px;font-size:11.5px;color:var(--dim);font-variant-numeric:tabular-nums}
#lease .lsnote span{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
#lease .ld{display:inline-block;width:3px;height:10px;border-radius:1px}
#lease .ld.soll{background:#fff}#lease .ld.hard{background:var(--red)}
#lease .ld.zone{width:12px;background:repeating-linear-gradient(135deg,rgba(247,183,51,.6) 0 3px,rgba(247,183,51,.15) 3px 6px)}
#lease .bar span{position:relative;z-index:1}
#lease .lzone{position:absolute;top:0;bottom:0;right:0;border-radius:0 6px 6px 0;z-index:2;background:repeating-linear-gradient(135deg,rgba(247,183,51,.45) 0 4px,rgba(247,183,51,.12) 4px 8px)}
#lease .lhard{position:absolute;top:-4px;width:2px;height:18px;margin-left:-1px;background:var(--red);z-index:3}
#lease .bm.soll{z-index:4}
#lease .lsax{position:relative;height:16px;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
#lease .lsax span{position:absolute;top:0;transform:translateX(-50%);white-space:nowrap}

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
@media (max-width:760px){.dlg{max-width:100vw;max-height:100vh;height:100%;margin:0}.dpan{height:100vh;height:100dvh;max-height:100vh;max-height:100dvh;border-radius:0;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}
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
.wrap.sat{padding-top:calc(18px + env(safe-area-inset-top,0px))}
.wrap.fit.sat{padding-top:calc(12px + env(safe-area-inset-top,0px))}
@container (max-width:720px){.wrap.sat{padding-top:calc(12px + env(safe-area-inset-top,0px))}}
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
.mmh .glyph{font-size:14px;font-weight:800;letter-spacing:-.02em;min-width:20px;text-align:center}
.mmh .msub{font-size:12px;font-weight:600;opacity:.75;white-space:nowrap}
.mmh b{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mphd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:space-between}.mphd .mpl ha-icon{--mdc-icon-size:18px;color:var(--cyan)}
.mpg{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.25fr);gap:10px}
.mpg label{display:flex;flex-direction:column;gap:5px;font-size:11.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);min-width:0}
.mpg .pin,.msel{width:100%;min-width:0;box-sizing:border-box;height:38px;border-radius:12px;border:1px solid var(--line);background:rgba(255,255,255,.05);color:var(--text);padding:0 10px;font:inherit;font-size:14px;font-weight:600;color-scheme:dark;letter-spacing:0;text-transform:none}
.msel option{color:#111;background:#fff;font-weight:500}
.mpb.end{justify-content:flex-end}
.mpa{display:flex;align-items:center;gap:12px}.mpa > ha-icon{--mdc-icon-size:24px;color:var(--cyan);flex:none}
.mpat{display:flex;flex-direction:column;min-width:0;flex:1}.mpat b{font-size:16px}.mpat small{font-size:12.5px;color:var(--muted)}
.mpat small:first-child{font-size:11.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase}
.mrun{font-style:normal;margin-left:6px;padding:1px 7px;border-radius:7px;background:rgba(52,211,153,.14);color:var(--green);letter-spacing:.04em}
@container (max-width:420px){.mpg{grid-template-columns:1fr}.mpa{flex-wrap:wrap}.mpa .mpb{width:100%;justify-content:flex-end}}.mphd .mpb{margin-left:auto}
.mphd .mpl{font-size:11.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.mpd{flex-direction:row!important;align-items:center;gap:8px!important}
.mpl{display:flex;align-items:center;gap:8px;min-height:24px}.mpu{display:inline-flex;margin:0;padding:2px}.mpu .hseg{padding:2px 10px;font-size:12px;min-height:0;letter-spacing:0}
.mpt{display:flex;align-items:center;gap:8px}.mpk{font-size:12.5px;color:var(--muted);white-space:nowrap}
.mpvmin{position:relative}.mpvmin select{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;font-size:16px}
.mpvmin:focus-within{border-color:rgba(255,255,255,.3)}
.mmode.vorgabe{flex:none;min-width:0}
.mmode.vorgabe.manual{background:linear-gradient(160deg,rgba(239,68,68,.18),rgba(239,68,68,.04));border-color:rgba(239,68,68,.55)}
.mmode.vorgabe.manual .mmh{color:#ef4444}
.mplan{display:flex;flex-direction:column;gap:10px;padding:12px 14px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb);margin-bottom:8px}
.mpe.err,.mpe.err ha-icon{color:var(--red)}
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
.mbtn.bal.on{border-color:rgba(52,211,153,.4);background:rgba(52,211,153,.1)}
.mbtn.bal.on ha-icon{color:var(--green)}
.mbtn.bal.on b{color:var(--green)}
.mbtn.bal.act{animation:mgpulse 1.4s ease-in-out infinite}
.mbtn.pause.on{border-color:rgba(251,146,60,.45);background:rgba(251,146,60,.1)}
.mbtn.pause.run{border-color:rgba(52,211,153,.4);background:rgba(52,211,153,.1)}.mbtn.pause.run ha-icon,.mbtn.pause.run b{color:var(--green)}
.mbtn.man.on{border-color:color-mix(in srgb,var(--cc) 45%,transparent);background:color-mix(in srgb,var(--cc) 10%,transparent)}.mbtn.man.on b,.mbtn.man.on > ha-icon:first-child,.mbtn.man.on .glyph{color:var(--cc)}
.mbtn .glyph{font-size:13px;font-weight:800;min-width:18px;text-align:center;color:var(--muted)}
.mbtn.mdrop{position:relative}.mbtn.mdrop select{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;font-size:16px}.mbtn.mdrop:focus-within{border-color:rgba(255,255,255,.3)}
.mbtn.mpvmin.on b,.mbtn.mpvmin.on > ha-icon:first-child{color:var(--e-solar,#ff9800)}.mbtn.mpvmin.on{border-color:rgba(255,152,0,.35)}
.mbtn.mbuf b,.mbtn.mbuf > ha-icon:first-child{color:var(--violet,#a78bfa)}
.mph3{display:grid!important;grid-template-columns:1fr auto 1fr}.mph3 .mpr{justify-self:end}.mph3 .mpc{justify-self:center}
.mbtn.pause.on ha-icon,.mbtn.pause.on b{color:var(--orange)}
.mbtn.tnow b{color:var(--text)}
.mbtn.tnow ha-icon:first-child{color:var(--muted)}
.mbottom.mact{margin:8px 0 0}
#mgmt .hd{margin-bottom:4px}
.lbl.mnow{display:inline-flex;align-items:center;gap:6px;color:var(--cc);font-weight:600}
.lbl.mnow ha-icon{--mdc-icon-size:18px}
.lbl.mnow .glyph{font-size:13px;font-weight:800;color:var(--cc)}
.mhint{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:4px 14px;margin:0 0 12px;font-size:12.5px;color:var(--dim);font-variant-numeric:tabular-nums}
.mhint b{color:var(--muted);font-weight:600}
.mhint .msrc{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);border:1px solid var(--line);border-radius:6px;padding:0 5px}
.mstats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
.mst{display:flex;flex-direction:column;gap:3px;padding:8px 12px;border-radius:14px;background:rgba(255,255,255,.02);border:1px dashed var(--tileb);min-width:0}
.mst span{font-size:10.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);white-space:nowrap}
.mst b{display:flex;align-items:center;gap:6px;font-size:14.5px;font-weight:700;color:var(--cc);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
.mst b ha-icon{--mdc-icon-size:17px;flex:none}
.mst b .glyph{font-size:13px;font-weight:800}
.mgl small{letter-spacing:0;text-transform:none;font-weight:500;color:var(--dim);margin-left:4px}
.mbottom.m3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:8px 0}
.mbottom.m3 .mbtn{padding:8px 10px;min-width:0}
.mbottom.m3 .mbtn span{overflow:hidden;text-overflow:ellipsis}
.mpb{display:flex;gap:6px;align-items:center}
.merr{margin:0 0 10px;padding:8px 12px;border-radius:12px;background:rgba(248,113,113,.08);border:1px solid rgba(248,113,113,.3)}
@container (max-width:420px){.mstats,.mbottom.m3,#mgmt .mmodes:not(.m3){display:grid;grid-template-columns:1fr 1fr}.mbottom.m3 .mbtn:first-child,.mst:last-child{grid-column:1 / -1}}
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
.chr{display:grid;grid-template-columns:40px minmax(0,1.4fr) minmax(0,1fr) 100px 80px 96px;align-items:center;gap:12px;padding:9px 14px 9px 10px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb)}
.chi{width:40px;height:40px;border-radius:13px;display:grid;place-items:center;background:rgba(52,211,153,.12);color:var(--green)}
.chr.ext .chi{background:color-mix(in srgb,var(--e-grid-in) 16%,transparent);color:var(--e-grid-in)}
.chi ha-icon{--mdc-icon-size:20px}
.chd{display:flex;flex-direction:column;min-width:0}
.chd b{font-size:15px;font-weight:600}
.chd small{font-size:12.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chpv{display:flex;flex-direction:column;gap:4px;min-width:0}
.chpv .pvbar{display:block;height:6px;border-radius:4px;background:var(--e-grid-in);overflow:hidden}
.chpv .pvbar i{display:block;height:100%;background:var(--e-solar)}
.chpv small{font-size:12px;color:var(--muted)}
.chs{display:flex;flex-direction:column;align-items:flex-end;font-variant-numeric:tabular-nums;white-space:nowrap}.chs b{font-size:14px;font-weight:600}.chs small{font-size:11.5px;color:var(--muted)}
.chk,.chc{display:flex;flex-direction:column;align-items:flex-end;font-variant-numeric:tabular-nums}
.chk b{font-size:17px;font-weight:700;color:var(--cyan)}
.chc b{font-size:15px;font-weight:700}
.chk small,.chc small{font-size:11.5px;color:var(--muted);white-space:nowrap}
.chsm{display:none}
@media (max-width:760px){.chr{grid-template-columns:36px minmax(0,1fr) 64px 78px}.chpv,.chs{display:none}.chd .chsm{display:block}.chsum .hsegs{width:100%;margin-left:0}}
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
.lkick .lend{color:var(--text)}
.lkick .lend i{font-style:normal;color:var(--muted)}
@container (max-width:460px){.lkick{white-space:normal}.lkick .lend{display:block}.lkick .lend i{display:none}}
.lbig{display:flex;align-items:baseline;gap:6px}
.lbig b{font-size:46px;font-weight:800;line-height:1.05;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.lhero.chg .lbig b{color:var(--green)}
.lbig small{font-size:16px;color:var(--muted);font-weight:600}
.lbig .lavg{margin-left:8px;font-size:14px;color:var(--muted);white-space:nowrap}
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
.dmore{padding:14px 0 6px;text-align:center;font-size:12.5px;color:var(--dim)}
.lamps{display:inline-flex;align-items:center;gap:7px;margin-left:6px;font-variant-numeric:tabular-nums;white-space:nowrap}
.lamps i{font-style:normal;color:var(--dim)}
.lsplit .pv{background:var(--e-solar)}.lsplit .gr{background:var(--e-grid-in)}
.lsplitl{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);margin:0 2px 12px}
.lsplitl span{display:inline-flex;align-items:center;gap:5px}
.lsplitl ha-icon{--mdc-icon-size:15px}
.lsplitl .pv ha-icon{color:var(--e-solar)}.lsplitl .gr ha-icon{color:var(--e-grid-in)}
.lsplitl b{color:var(--text);font-variant-numeric:tabular-nums}
.lfacts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:12px}
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
.glg .kwl::before{content:"";display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px;background:rgba(52,211,153,.75)}
.chist .bkw{fill:rgba(52,211,153,.75)}
.mbtn.ro{cursor:default}
.ttl.vsel{display:inline-flex;align-items:center;gap:6px;cursor:pointer;border-radius:10px;padding:2px 4px 2px 0}
.ttl.vsel:hover{color:var(--text)}
.ttl.vsel .vchv{--mdc-icon-size:20px;opacity:.75}
.apiwarn{margin:0 0 14px;padding:10px 14px;border-radius:14px;background:rgba(251,146,60,.1);border:1px solid rgba(251,146,60,.35);color:var(--orange);font-size:13.5px;font-weight:600}
.wrap.fit .apiwarn{flex:none}
.mbtn.ro:hover{border-color:var(--tileb)}
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

/* Unterseite Profil & Analyse */
[hidden]{display:none!important}
.pages{display:flex;margin:0 0 14px}
.wrap.fit .pgrid{grid-template-rows:none}
.wrap.fit .pages{flex:none}
.pgrid{grid-template-columns:2.1fr 1fr!important;align-content:start}
.wrap.fit .pgrid{overflow-y:auto;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.15) transparent}
.pchip{display:inline-flex;padding:4px 10px;border-radius:10px;font-size:12.5px;font-weight:600;background:rgba(251,146,60,.12);color:var(--orange)}
.pdays{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px}
.pday{padding:12px 12px 14px;border-radius:20px;background:var(--tile);border:1px solid var(--tileb);display:flex;flex-direction:column;gap:9px;min-width:0}
.pday.tm{border-color:rgba(52,211,153,.55);background:radial-gradient(120% 90% at 50% 0%,rgba(52,211,153,.14),transparent 70%),var(--tile)}
.pday.td{border-color:rgba(255,255,255,.18)}
.pdn{display:flex;align-items:baseline;justify-content:space-between;gap:4px}.pdn b{font-size:16px}.pdn span{font-size:10.5px;font-weight:700;letter-spacing:.08em;color:var(--green)}
.pday.td .pdn span{color:var(--muted)}
.pmt{display:flex;flex-direction:column;gap:3px}
.pmt small{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap}
.pmt b{font-size:17px;font-variant-numeric:tabular-nums;white-space:nowrap}.pmt b em{font-style:normal;font-size:11px;color:var(--muted);margin-left:2px}
.pbar{height:5px;border-radius:4px;background:rgba(255,255,255,.06);overflow:hidden;display:flex}.pbar i{display:block;height:100%}
.pmt.ev b{color:var(--cyan)}.pmt.ev .pbar i{background:var(--cyan)}.pday.tm .pmt.ev .pbar i{background:var(--green)}
.pmt.hs b{color:#c4b5fd}.pmt.hs .pbar i{background:var(--violet)}.pmt.dp b{color:var(--gold)}
.phero{padding:15px 17px;border-radius:22px;background:var(--tile);border:1px solid var(--tileb);margin-bottom:12px}
.phero.no{background:radial-gradient(120% 120% at 0% 0%,rgba(52,211,153,.14),transparent 60%),var(--tile);border-color:rgba(52,211,153,.35)}
.phero.yes{background:radial-gradient(120% 120% at 0% 0%,rgba(251,146,60,.14),transparent 60%),var(--tile);border-color:rgba(251,146,60,.4)}
.phero .kick{font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.pbig{font-size:22px;font-weight:700;margin:3px 0}.psub{font-size:13.5px;color:var(--muted)}
.pstats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.pst{padding:9px 11px;border-radius:15px;background:var(--tile);border:1px solid var(--tileb);min-width:0}
.pst span{display:block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap}
.pst b{font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}.pst b small{font-size:11.5px;color:var(--muted);margin-left:3px;font-weight:500}
.pst em{display:block;font-style:normal;font-size:11.5px;color:var(--muted)}.pst.pv b{color:var(--e-solar)}
.pst .pbufsel{display:block;margin-top:1px;max-width:100%;font:inherit;font-size:17px;font-weight:700;font-variant-numeric:tabular-nums;color:inherit;background:transparent;border:0;border-bottom:1px dashed var(--muted);padding:0 2px 1px 0;cursor:pointer;outline:none}
.pst .pbufsel:focus-visible{border-bottom-color:currentColor}.pst .pbufsel option{color:#111;background:#fff}
.sl2{font-size:13px;color:var(--muted);margin:2px 2px 7px}.sl2 b{color:var(--text)}
.preach{display:flex;gap:3px}
.preach span{flex:1;position:relative;display:flex;flex-direction:column;gap:4px}
.preach span::after{content:"";position:absolute;left:0;right:0;top:0;height:8px;border-radius:4px;background:rgba(255,255,255,.07)}
.preach span i{position:relative;z-index:1;display:block;height:8px;border-radius:4px;background:var(--green)}
.preach small{font-size:11px;color:var(--dim);text-align:center}
.ptiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.ptile{position:relative;padding:13px 14px;border-radius:20px;background:var(--tile);border:1px solid var(--tileb);min-width:0;transition:border-color .2s}
.ptile:hover{border-color:rgba(56,189,248,.45)}
.ptile > span{display:block;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:12px}
.ptile b{display:block;font-size:25px;font-weight:800;margin:4px 0 2px;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ptile b small{font-size:13px;color:var(--muted);font-weight:600;margin-left:3px}
.ptile p{margin:0;font-size:12.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ptile .pbar{margin:6px 0}.pbar.two i{background:var(--green)}.pbar.two i.o{background:var(--orange)}
.pchev{position:absolute;top:10px;right:13px;font-style:normal;color:var(--dim);font-size:18px}
.mscale{position:relative;height:12px;border-radius:7px;background:linear-gradient(90deg,var(--e-solar),var(--e-grid-in));margin:10px 2px 6px}
.mscale .ms,.mscale .mc{position:absolute;top:-5px;width:4px;height:22px;border-radius:2px;transform:translateX(-2px)}
.mscale .ms{background:var(--orange)}.mscale .mc{background:#fff}
.mlab{display:flex;justify-content:space-between;font-size:12px;color:var(--dim);margin-bottom:12px}
.pstats.two{margin-bottom:8px}.pstats.three{grid-template-columns:repeat(3,minmax(0,1fr))}
.pnote{font-size:12.5px;color:var(--dim);line-height:1.45}
.pdlg{max-width:720px}
.pcols{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.pcol{padding:12px 14px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb)}
.pcol h4{margin:0 0 6px;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.pcol p{margin:3px 0;display:flex;gap:10px;font-size:13.5px;color:var(--muted)}.pcol p b{margin-left:auto;color:var(--text);font-variant-numeric:tabular-nums;text-align:right}
.pbands{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;height:220px;align-items:end}
.pbands div{display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:6px;height:100%}
.pbands i{display:block;width:100%;border-radius:10px 10px 4px 4px;background:rgba(56,189,248,.55)}
.pbands .cur i{background:var(--green);box-shadow:0 0 14px rgba(52,211,153,.45)}.pbands .cur small{color:var(--green)}
.pbands em{font-style:normal;font-weight:700}.pbands small{font-size:12px;color:var(--dim);font-weight:600}
.panb{display:flex;flex-direction:column;gap:8px}.panb > div{padding:10px 14px;border-radius:14px;background:var(--tile);border:1px solid var(--tileb)}
.panb p{margin:0 0 6px;display:flex;gap:10px;font-size:14px}.panb p span{margin-left:auto;color:var(--muted);font-size:12.5px}
.panb i{display:block;height:5px;border-radius:3px;background:rgba(255,255,255,.06);overflow:hidden}.panb em{display:block;height:100%;background:var(--cyan)}
@container (max-width:1180px){.pgrid{grid-template-columns:1fr!important}.ptiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
@container (max-width:720px){.pdays{grid-template-columns:repeat(4,minmax(0,1fr))}.pcols{grid-template-columns:1fr}}
.sgrid{grid-template-columns:1.5fr 1fr!important;align-content:start}
.urlon{display:inline-flex;align-items:center;gap:6px;color:var(--cyan);font-weight:600}.urlon ha-icon{--mdc-icon-size:18px}
.pnote.warn{color:var(--orange)}.pnote.err{color:#f87171}.pnote.err ha-icon{--mdc-icon-size:16px;vertical-align:-3px}
.fbprev{display:flex;flex-direction:column;border:1px solid var(--tileb);border-radius:14px;overflow:hidden;font-size:13px}
.fbprev > div{display:grid;grid-template-columns:130px 1fr 60px;gap:10px;padding:6px 12px;border-top:1px solid var(--line)}.fbprev > div:first-child{border-top:0}
.fbprev .fbh{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;background:var(--tile)}
.fbprev > div span:last-child{text-align:right;font-variant-numeric:tabular-nums}.fbprev > div span:nth-child(2){overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fbprev .fbmore{display:block;color:var(--muted)}
.pages{display:grid!important;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px}.pages > .hsegs{grid-column:2}
.kper{grid-column:3;justify-self:end;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.knav{display:flex;align-items:center;gap:4px}.knav b{min-width:120px;text-align:center;font-size:15px}.knav .sic[disabled]{opacity:.3;pointer-events:none}
.kgrid{grid-template-columns:2fr 1fr!important;align-content:start}.wrap.fit .kgrid{grid-template-rows:none;overflow-y:auto;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.15) transparent}
.kpv{background:var(--e-solar,#ff9800)}.kgr{background:var(--e-grid-in,#488fc2)}.kac{background:#a78bfa}.kdc{background:#f472b6}.kfee{background:#64748b}
.kchart{display:flex;align-items:flex-end;gap:4px;height:190px;border-bottom:1px solid var(--line)}
.kc{flex:1;min-width:0;display:flex;flex-direction:column-reverse;border-radius:5px 5px 2px 2px;overflow:hidden;transition:filter .15s}.kc:hover{filter:brightness(1.25)}.kc i{display:block;width:100%}
.kax{display:flex;gap:4px;font-size:11px;color:var(--dim);margin-top:5px}.kax span{flex:1;min-width:0;text-align:center;white-space:nowrap;overflow:visible}
.klg{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12.5px;color:var(--muted);margin-top:10px}.klg span{display:inline-flex;align-items:center;gap:6px}.klg i,.ksrc i{width:10px;height:10px;border-radius:3px;display:inline-block;flex:none}
.kkp{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin-top:14px}
.kkp div{padding:9px 11px;border-radius:15px;background:var(--tile);border:1px solid var(--tileb);min-width:0}
.kkp span{display:block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap}
.kkp b{font-size:19px;font-variant-numeric:tabular-nums}.kkp small{font-size:11.5px;color:var(--muted);margin-left:3px}.kkp em{display:block;font-style:normal;font-size:11.5px;color:var(--green);white-space:nowrap}.kkp em.up{color:var(--orange)}
.klist{display:flex;flex-direction:column;gap:6px;max-height:420px;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.15) transparent;padding-right:4px;margin-right:-4px}
.khd{display:grid;grid-template-columns:1fr auto 1fr;align-items:center}.khd .ttl{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.khd .lbl{justify-self:end}.khd .ksort{justify-self:center;margin-left:0}
.ksort .hseg{padding:0 12px;font-size:13px}
@container (max-width:560px){.khd{grid-template-columns:1fr auto}.khd .ksort{grid-column:1 / -1;grid-row:2;justify-self:stretch;margin-left:0;width:100%}.khd .ksort .hseg{flex:1}}.kdir{font-style:normal;margin-left:4px;font-weight:700}
.kmore{text-align:center;font-size:12.5px;color:var(--dim);padding:6px 0}.krow:not(.ted){cursor:default}.krow:not(.ted):hover{border-color:var(--tileb)}
.krow{display:grid;grid-template-columns:34px 1fr auto;gap:10px;align-items:center;padding:8px 12px 8px 8px;border-radius:14px;background:var(--tile);border:1px solid var(--tileb);cursor:pointer}.krow:hover{border-color:rgba(255,255,255,.2)}
.kri{width:34px;height:34px;border-radius:11px;display:grid;place-items:center;background:color-mix(in srgb,var(--e-solar,#ff9800) 16%,transparent);color:var(--e-solar,#ff9800)}.kri.ext{background:rgba(244,114,182,.14);color:#f472b6}.kri ha-icon{--mdc-icon-size:18px}
.krt,.krv{display:flex;flex-direction:column;min-width:0}.krt small,.krv small{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.krv{align-items:flex-end;font-variant-numeric:tabular-nums}
.kall{margin-top:10px}
.kbar{display:flex;height:12px;border-radius:7px;overflow:hidden;background:rgba(255,255,255,.06);margin-bottom:12px}.kbar i{display:block;height:100%}
.ksrc{display:flex;flex-direction:column;gap:7px;margin-bottom:8px}
.ksrc div{display:grid;grid-template-columns:12px 1fr auto auto;gap:4px 12px;align-items:center;padding:9px 12px;border-radius:14px;background:var(--tile);border:1px solid var(--tileb);font-size:14px}.ksrc div.z{opacity:.5}
.ksrc b{font-variant-numeric:tabular-nums;text-align:right}.ksrc small{color:var(--muted);font-size:12px;text-align:right;min-width:84px}
.ksave{padding:14px 16px;border-radius:20px;background:radial-gradient(120% 120% at 0% 0%,rgba(52,211,153,.16),transparent 60%),var(--tile);border:1px solid rgba(52,211,153,.35);margin-bottom:12px}
.ksave span{font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}.ksave b{font-size:28px;color:var(--green);font-variant-numeric:tabular-nums}.ksave small{font-size:13.5px;color:var(--muted)}
.ksave.neg{border-color:rgba(251,146,60,.4);background:var(--tile)}.ksave.neg b{color:var(--orange)}
.kcb{display:flex;flex-direction:column;gap:5px;margin-bottom:10px}.kcb p{margin:0;display:flex;font-size:14px}.kcb p b{margin-left:auto;font-variant-numeric:tabular-nums}
.kbar2{height:12px;border-radius:7px;background:rgba(255,255,255,.06);overflow:hidden}.kbar2 i{display:block;height:100%;border-radius:7px}
.kmini{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:4px 0 10px}
.kmini div{padding:8px 10px;border-radius:13px;background:var(--tile);border:1px solid var(--tileb);min-width:0}.kmini span{display:block;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap}.kmini b{font-size:16px}.kmini small{font-size:11px;color:var(--muted);margin-left:3px}
@container (max-width:1180px){.kgrid{grid-template-columns:1fr!important}.kkp{grid-template-columns:repeat(3,minmax(0,1fr))}}
@container (max-width:520px){.pages > .hsegs{width:100%;overflow-x:auto;scrollbar-width:none}.pages > .hsegs .hseg{flex:1 0 auto;padding:0 9px;font-size:12.5px}}
@container (max-width:900px){.pages{grid-template-columns:1fr}.pages > .hsegs{grid-column:1;justify-self:center}.kper{grid-column:1;justify-self:stretch;justify-content:space-between}}
@container (max-width:720px){.kper{width:100%;margin-left:0;justify-content:space-between}.knav b{min-width:0}.kchart{height:150px;gap:2px}.kax{gap:2px}}
.cpend{display:inline-flex;align-items:center;gap:6px;flex:none;padding:7px 12px;border-radius:14px;background:rgba(249,115,22,.14);border:1px solid rgba(249,115,22,.45);color:var(--orange);font:inherit;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
.cpend ha-icon{--mdc-icon-size:17px}.cpend b{font-size:14px}.cpend:hover{background:rgba(249,115,22,.22)}
@container (max-width:420px){.cpend span{display:none}}
.pform{padding:14px;border-radius:18px;background:var(--tile);border:1px solid var(--tileb);display:flex;flex-direction:column;gap:12px}
.pform.done{opacity:.45;pointer-events:none}
.ptop{display:flex;align-items:center;gap:10px}.ptop ha-icon{--mdc-icon-size:22px;color:var(--orange)}
.ptop span{display:flex;flex-direction:column;min-width:0}.ptop span small{color:var(--muted);font-size:12.5px}
.ptop em{margin-left:auto;font-style:normal;font-weight:700;font-size:17px;text-align:right;display:flex;flex-direction:column;font-variant-numeric:tabular-nums}.ptop em small{font-size:12px;color:var(--muted);font-weight:500}
.trip.ted,.chr.ted{cursor:pointer;transition:border-color .2s}.trip.ted:hover,.chr.ted:hover{border-color:rgba(255,255,255,.22)}
.sbt.red{color:#f87171;border-color:rgba(239,68,68,.35)}
.wrap.fit .sgrid{grid-template-rows:none;overflow-y:auto;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.15) transparent}
.sbt{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:12px;background:var(--tile);border:1px solid var(--tileb);color:inherit;font:inherit;font-size:13.5px;font-weight:600;cursor:pointer;white-space:nowrap;transition:border-color .2s}
.sbt:hover{border-color:rgba(255,255,255,.22)}.sbt ha-icon{--mdc-icon-size:16px}.sbt[disabled],.sbt.dis{opacity:.5;pointer-events:none}
.sbt.pri{background:rgba(52,211,153,.16);border-color:rgba(52,211,153,.45);color:var(--green)}.sbt.pri.red{background:rgba(239,68,68,.14);border-color:rgba(239,68,68,.45);color:#f87171}
.hd .lbl .sbt{font-size:13px;padding:6px 11px}
.srow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}.srow.end{justify-content:flex-end;margin-top:4px}
.slist{display:flex;flex-direction:column;gap:8px}
.witem{--wc:#facc15;position:relative;padding:12px 14px 12px 16px;border-radius:16px;background:linear-gradient(90deg,color-mix(in srgb,var(--wc) 9%,transparent),transparent 60%),var(--tile);border:1px solid color-mix(in srgb,var(--wc) 30%,var(--tileb));display:flex;flex-direction:column;gap:6px;min-width:0;overflow:hidden}
.witem::before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:3px;border-radius:0 3px 3px 0;background:var(--wc);box-shadow:0 0 12px var(--wc)}
.witem.orange{--wc:var(--orange)}.witem.red{--wc:#f87171}.witem.unk,.witem.off{--wc:var(--dim)}.witem.off{opacity:.6}
.witem.red.over{animation:wpulse 2.4s ease-in-out infinite}
@keyframes wpulse{0%,100%{box-shadow:0 0 0 rgba(248,113,113,0)}50%{box-shadow:0 0 18px rgba(248,113,113,.35)}}
.wnext{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px}.wnext .wlbl{width:100%;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.wnext b{font-size:17px;color:var(--wc);font-variant-numeric:tabular-nums}.whint{width:100%;text-align:left;padding:0;border:0;background:none;font:inherit;font-size:12.5px;color:var(--muted);cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}.wnext small{font-size:12.5px;color:var(--muted)}
.wbar{height:5px;border-radius:3px;background:rgba(255,255,255,.06);overflow:hidden}.wbar i{display:block;height:100%;border-radius:3px;background:linear-gradient(90deg,color-mix(in srgb,var(--wc) 45%,transparent),var(--wc));box-shadow:0 0 10px var(--wc)}
.wdone{display:inline-flex;align-items:center;gap:5px;padding:2px 9px 2px 6px;border-radius:9px;color:var(--green);background:rgba(52,211,153,.1);border:1px solid rgba(52,211,153,.35);box-shadow:0 0 12px rgba(52,211,153,.18);position:relative;overflow:hidden}
.wdone ha-icon{--mdc-icon-size:15px}
.wdone::after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 30%,rgba(255,255,255,.18) 50%,transparent 70%);transform:translateX(-100%);animation:wshine 4s ease-in-out infinite}
@keyframes wshine{0%,60%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
@media (prefers-reduced-motion:reduce){.witem.red.over,.wdone::after{animation:none}}
.wsum{font-weight:600;color:#facc15}.wsum.orange{color:var(--orange)}.wsum.red{color:#f87171}.wsum.unk,.wsum.off{color:var(--muted)}
#swart .hd .lbl{font-size:13.5px}#swart .hd .sbt{margin-left:10px}
.sitem{--sc:var(--dim);padding:11px 14px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb);display:flex;flex-direction:column;gap:4px;min-width:0}
.sitem.ok{--sc:var(--green)}.sitem.soon{--sc:var(--orange)}.sitem.over{--sc:#f87171;border-color:rgba(239,68,68,.35)}.sitem.off{opacity:.62}
.stop{display:flex;align-items:center;gap:8px;min-width:0}.stop b{font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sdot{width:9px;height:9px;border-radius:50%;background:var(--sc);flex:none;box-shadow:0 0 10px var(--sc)}
.stag{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.scost{margin-left:auto;font-weight:700;font-variant-numeric:tabular-nums}.stop .scost + .sacts{margin-left:6px}
.sacts{margin-left:auto;display:flex;gap:4px;flex:none}
.sic{width:30px;height:30px;display:grid;place-items:center;border-radius:10px;background:transparent;border:1px solid transparent;color:var(--muted);cursor:pointer}
.sic:hover{background:rgba(255,255,255,.06);border-color:var(--tileb);color:inherit}.sic ha-icon{--mdc-icon-size:17px}
.sstat{font-size:13.5px;color:var(--sc)}.sstat b{font-weight:700}
.smeta{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;color:var(--muted)}
.snote{display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:10px;padding:8px 12px;border-radius:12px}.snote ha-icon{--mdc-icon-size:17px}
.snote.warn{color:var(--orange);background:rgba(249,115,22,.1);border:1px solid rgba(249,115,22,.3)}
.skpi{display:flex;align-items:baseline;gap:10px;margin-bottom:10px}.skpi b{font-size:24px;font-variant-numeric:tabular-nums}.skpi b small{font-size:13px;color:var(--muted);margin-left:3px}.skpi span{font-size:13px;color:var(--muted)}
.schips{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
.schip{display:inline-flex;align-items:center;gap:4px;padding:3px 6px 3px 10px;border-radius:10px;background:rgba(255,255,255,.04);border:1px solid var(--tileb);font-size:12px;color:var(--muted)}.schip b{color:var(--text,inherit)}
.schip.add{padding:3px 10px;cursor:pointer;font:inherit;font-size:12px;color:var(--muted);border-style:dashed}.schip.add:hover{color:inherit}.schip ha-icon{--mdc-icon-size:14px}
.sx{display:grid;place-items:center;width:20px;height:20px;border-radius:6px;border:0;background:transparent;color:var(--muted);cursor:pointer}.sx:hover{background:rgba(255,255,255,.08);color:inherit}
.simgbox{display:grid;place-items:center;min-height:110px;border-radius:16px;background:var(--tile);border:1px solid var(--tileb);padding:10px;margin-bottom:10px}
.simgbox img{max-width:100%;max-height:180px;object-fit:contain}
.sblk + .sblk{margin-top:16px;padding-top:14px;border-top:1px solid var(--line)}.sblk h4{margin:0 0 4px;font-size:14px}
#slog .srow{margin:8px 0 10px}#slog select,#slog input,.sfld input,.sfld select{font:inherit;font-size:14px;color:inherit;background:var(--tile);border:1px solid var(--tileb);border-radius:11px;padding:7px 10px;outline:none;color-scheme:dark;min-width:0}
#slog input{flex:1}#slog select:focus,#slog input:focus,.sfld input:focus,.sfld select:focus{border-color:rgba(255,255,255,.3)}
.sloglist{max-height:340px;overflow:auto;display:flex;flex-direction:column;gap:2px;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.15) transparent}
.sline{display:grid;grid-template-columns:auto auto 1fr;gap:4px 10px;padding:5px 2px;border-bottom:1px solid var(--line);font-size:12.5px;align-items:baseline}
.sline span{color:var(--dim);font-variant-numeric:tabular-nums;white-space:nowrap}.sline em{font-style:normal;color:var(--cyan);font-weight:600;white-space:nowrap}.sline p{margin:0;min-width:0;overflow-wrap:anywhere}
.sdlg{max-width:620px;margin:0 auto;width:100%}.sform{gap:12px}
.sgrp h4{margin:0 0 8px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.sflds{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.sfld{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--muted)}.sfld.chk{flex-direction:row;align-items:center;gap:8px;font-size:14px;color:inherit}
.sfld.chk input{width:18px;height:18px;accent-color:var(--green)}
.ferr{color:#f87171;font-size:13px;min-height:1px}.ferr:empty{display:none}
@container (max-width:1180px){.sgrid{grid-template-columns:1fr!important}}
@container (max-width:720px){.sline{grid-template-columns:auto 1fr}.sline p{grid-column:1 / -1}}
`;

if (!customElements.get("mg-car-dashboard")) customElements.define("mg-car-dashboard", MgCarDashboard);
if (!window.customCards.some((c) => c.type === "mg-car-dashboard"))
  window.customCards.push({ type: "mg-car-dashboard", name: "Glow Auto", description: "Auto-Seite mit evcc, ev_assistant und Fahrtenbuch im Glow-Stil" });

console.info(`%c GLOW AUTO (mg-car-dashboard) %c ${VERSION} `, "background:#f7b733;color:#111;font-weight:700", "background:#14171e;color:#f7b733");
