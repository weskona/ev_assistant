/*
 * EV Assistant — custom sidebar panel.
 * Übersicht modelled after the omnibattery Resumen layout:
 *   top: full-width status card (ring + diagnostics grid)
 *   lower: energy-flow diagram (left) + 2×2 bar-chart cards (right)
 * Fahrzeuge tab unchanged.
 */

const ACCENT_H = 127;

class EVAssistantPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._built = false;
    this._view = "uebersicht_beta";
    this._tabs = {};
    this._r = {};
    // Eigener, von _switchView()s "this._r = {}"-Reset UNBERUEHRTER Ref-
    // Speicher fuer das Ladeplan-Popup (siehe _buildLadeplanModal()) --
    // analog zu den direkten this._pendingModalXxx-Properties des Fahrten/
    // Fremdladungen-Popups. Bug 2026-09-23: die Modal-Refs lagen zuerst in
    // this._r, das aber bei JEDEM Tab-Wechsel (auch dem impliziten direkt
    // nach dem ersten Rendern) geleert wird -- das Popup selbst wird aber
    // nur EINMAL gebaut, also gingen alle seine Referenzen sofort verloren
    // und jede dynamische Aktualisierung (Slider-Minimum, "Jetzt"-Marke)
    // griff seitdem ins Leere, ohne Fehler (nur stille `if (!x) return`-Guards).
    this._lp = {};
    // Ref-Speicher fuer das "Panel anpassen"-Popup (siehe
    // _buildPanelLayoutModal()) -- aus demselben Grund wie this._lp NICHT
    // in this._r.
    this._pl = {};
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

  // Live-evcc-Werte direkt vom evcc-Addon (siehe coordinator.py::
  // evcc_live_attrs()) -- als Attribut auf der home_kwh-Entity mitgeliefert,
  // kein eigener Entity/Netzwerkweg mehr pro Feld (ersetzt die fruehere
  // evcc_intg-Entity-fuer-Entity-Zuordnung).
  _evccLive() {
    const eid = this._eid("home_kwh");
    const s = eid && this._hass ? this._hass.states[eid] : null;
    return (s && s.attributes && s.attributes.evcc_live) || {};
  }

  // Lade-Modus (siehe const.py::resolve_lade_modus()) -- als Attribut am
  // "count"-Sensor mitgeliefert (coordinator.py::lade_modus(), sensor.py::
  // CountSensor.extra_state_attributes), kein eigener Netzwerkweg/Sensor
  // dafuer noetig. Steuert NUR Sichtbarkeit, siehe z.B. _buildUebersichtBeta()
  // -- bewusst als eigene Methode, damit weitere Tabs denselben Modus ohne
  // Zusatzaufwand abfragen koennen.
  _ladeModus() {
    const eid = this._eid("count");
    const s = eid && this._hass ? this._hass.states[eid] : null;
    return (s && s.attributes && s.attributes.lade_modus) || "gemischt";
  }

  // Vom Nutzer im "Panel anpassen"-Popup gewaehlte Sichtbarkeit/Reihenfolge
  // der Beta-Panel-Karten (Nutzerwunsch 2026-09-23: "der nutzer bekommt
  // eine auswahl von karten, die er selber im panel anordnen oder auch
  // auswaehlen kann") -- als Attribut am "count"-Sensor mitgeliefert
  // (coordinator.py::panel_layout(), analog _ladeModus() oben). []
  // (unbekannt/leer) faellt in _panelLayoutOrder() auf die Standard-
  // reihenfolge zurueck. this._panelLayoutOverride: optimistisches lokales
  // Update direkt nach dem Speichern (siehe _openPanelLayoutModal()), noch
  // bevor der Server-Roundtrip die Live-Attribute aktualisiert hat --
  // einmalig konsumiert, danach zaehlt wieder die Live-Entitaet.
  _panelLayout() {
    if (this._panelLayoutOverride) {
      const ov = this._panelLayoutOverride;
      this._panelLayoutOverride = null;
      return ov;
    }
    const eid = this._eid("count");
    const s = eid && this._hass ? this._hass.states[eid] : null;
    const raw = s && s.attributes && s.attributes.panel_layout;
    return Array.isArray(raw) ? raw : [];
  }

  // Gemeinsames Label/Farbe fuer einen evcc-Lademodus-String -- verwendet
  // fuer den LIVE-Modus (evcc_live_attrs().mode, direkt von evccs Loadpoint,
  // kann zusaetzlich "off" sein wenn nichts angesteckt ist) UND fuer den
  // von ev_assistant EMPFOHLENEN Modus (_evcc_mode_targets().modus, siehe
  // EvccModeControlSensor -- nie "off", da die Steuerung selbst nur
  // pv/minpv/now schreibt). EINE Quelle statt zweier Kopien, damit beide
  // Anzeigen (Wallbox-Karte Aufgabe 3.3, evcc-Steuerung-Karte Aufgabe 3.7)
  // konsistent beschriften.
  _evccModeLabel(mode) {
    // Beschriftung an evccs "Mode Redesign" (0.316.0, 2026-09-22, PR #32490)
    // angepasst: "pv" heisst dort jetzt "Smart", "minpv" ist keine eigene
    // Stufe mehr, sondern "Smart" + Always-Charge-Zusatzoption -- intern
    // bleiben unsere Werte unveraendert pv/minpv/now (siehe coordinator.py::
    // normalize_evcc_mode()), nur die Anzeige zieht nach.
    const LABELS = {
      pv: "Smart", minpv: "Smart + Immer laden", now: "Schnell", off: "Aus",
    };
    return LABELS[mode] || mode || "—";
  }

  _evccModeColor(mode) {
    const COLORS = {
      pv: "#4ade80", minpv: "#f97316", now: "#ef4444", off: "var(--ink-dim)",
    };
    return COLORS[mode] || "var(--ink-dim)";
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
    app.appendChild(this._buildPendingModal());
    app.appendChild(this._buildLadeplanModal());
    app.appendChild(this._buildPanelLayoutModal());
    this.shadowRoot.appendChild(app);
    this._switchView(this._view);
  }

  // --- Popup: offene Fahrten/Fremdladungen bestaetigen -------------------------
  //
  // Unabhaengig vom Tab-Wechsel (ausserhalb von this._main aufgebaut, siehe
  // _renderShell()), damit die blinkende Pill der Uebersicht (Beta) (siehe
  // _buildUebersichtBeta()) es jederzeit oeffnen kann, ohne den Tab zu
  // verlassen. Der Inhalt selbst ist keine neue Komponente, sondern
  // dieselben _renderPendingCharges()/_renderPendingTrips()-Karten wie im
  // "Laufende Erfassung"-Bereich des Fahrzeuge-Tabs, hier nur in eigene
  // Container statt #est-ext-item/#est-trip-item gerendert.
  _buildPendingModal() {
    const overlay = document.createElement("div");
    overlay.className = "pending-modal-overlay hidden";
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) this._closePendingModal();
    });
    const modal = document.createElement("div");
    modal.className = "pending-modal";
    modal.innerHTML = `
      <div class="pending-modal-head">
        <span class="ic"><ha-icon icon="mdi:motion-sensor"></ha-icon></span>
        <h2 id="pending-modal-title">Offene Fahrten &amp; Fremdladungen</h2>
        <button type="button" class="pending-modal-close" aria-label="Schließen"><ha-icon icon="mdi:close"></ha-icon></button>
      </div>
      <div class="pending-modal-body">
        <div class="pend-list hidden" id="pending-modal-charges"></div>
        <div class="pend-list hidden" id="pending-modal-trips"></div>
      </div>`;
    modal.querySelector(".pending-modal-close").addEventListener("click", () => this._closePendingModal());
    overlay.appendChild(modal);
    this._pendingModalEl = overlay;
    this._pendingModalTitle = modal.querySelector("#pending-modal-title");
    this._pendingModalCharges = modal.querySelector("#pending-modal-charges");
    this._pendingModalTrips = modal.querySelector("#pending-modal-trips");
    return overlay;
  }

  // Zeigt NUR die Art, deren Pill angeklickt wurde (Nutzerwunsch 2026-09-23:
  // "in den jeweiligen popups sind fahrten und fremdladungen zu sehen. nicht
  // nur jeweils das, auf dessen pill man geklickt hat") -- vorher blendete
  // _updateUebersichtBeta() beide Listen ein, sobald beide Arten gleichzeitig
  // offen waren, unabhaengig davon, welche Pill gedrueckt wurde. Wird sowohl
  // beim Oeffnen (_openPendingModal()) als auch bei jedem Update waehrend das
  // Popup offen ist (_updateUebersichtBeta()) angewendet, damit ein
  // zwischenzeitliches Bestaetigen/Verwerfen die Filterung nicht aufhebt.
  _applyPendingModalFilter(pendingCharges, pendingTrips) {
    const focus = this._pendingModalFocus;
    const showCharges = focus === "trips" ? false : pendingCharges.length > 0;
    const showTrips = focus === "charges" ? false : pendingTrips.length > 0;
    this._pendingModalCharges.classList.toggle("hidden", !showCharges);
    this._pendingModalTrips.classList.toggle("hidden", !showTrips);
    return { showCharges, showTrips };
  }

  // `focusSection` ("charges"/"trips") legt fest, welche der beiden Listen
  // gezeigt wird (siehe _applyPendingModalFilter()) -- exklusiv, nicht nur
  // ein Scroll-Ziel bei ansonsten weiterhin beiden sichtbaren Listen.
  _openPendingModal(focusSection) {
    if (!this._pendingModalEl) return;
    this._pendingModalFocus = focusSection;
    this._pendingModalTitle.textContent = focusSection === "trips"
      ? "Offene Fahrten"
      : focusSection === "charges"
        ? "Offene Fremdladungen"
        : "Offene Fahrten & Fremdladungen";
    const pendingCharges = this._pendingList("pending", "offene_ladungen");
    const pendingTrips = this._pendingList("trip_pending", "offene_fahrten");
    this._applyPendingModalFilter(pendingCharges, pendingTrips);
    this._pendingModalEl.classList.remove("hidden");
  }

  _closePendingModal() {
    if (this._pendingModalEl) this._pendingModalEl.classList.add("hidden");
    this._pendingModalFocus = null;
  }

  _buildAppbar() {
    const bar = document.createElement("div");
    bar.className = "appbar";
    const brand = document.createElement("div");
    brand.className = "brand";
    brand.innerHTML = `
      <div class="logo"><ha-icon icon="mdi:ev-station"></ha-icon></div>
      <div class="btext">
        <div class="bt-name">EV Assistant</div>
      </div>`;
    brand.querySelector(".logo").addEventListener("click", () =>
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }))
    );
    const tabBar = document.createElement("div");
    tabBar.className = "tabs";
    const TAB_DEFS = [
      ["uebersicht_beta", "mdi:flask-outline",          "Übersicht (Beta)"],
      ["fahrzeuge",  "mdi:car-electric",           "Fahrzeug"],
      ["profil",     "mdi:calendar-week",          "Nutzungsprofil"],
      ["analyse",    "mdi:chart-line",             "Analyse"],
      ["leasing",    "mdi:file-document-outline",  "Leasing"],
      ["ladekarten", "mdi:credit-card-multiple-outline", "Ladekarten"],
      ["wartung",    "mdi:wrench-clock",           "Wartung"],
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
    bar.appendChild(this._buildScrollWrap(tabBar, "tabs-wrap"));
    return bar;
  }

  // Baut einen horizontal scrollbaren Container mit Pfeil-Buttons an den
  // Enden -- eine reine overflow-x:auto-Leiste mit ausgeblendetem
  // Scrollbalken ist am Desktop mit der Maus sonst kaum bedienbar (Mausrad
  // per _wireHorizontalWheelScroll geht zwar, wirkt aber nicht wie eine
  // "richtige" Bedienung). Die Pfeile blenden sich per scroll-/resize-
  // getriebenem updateArrows() automatisch aus, sobald in ihre Richtung
  // nichts mehr zu scrollen ist (oder gar kein Overflow besteht).
  _buildScrollWrap(scrollEl, extraClass) {
    const wrap = document.createElement("div");
    wrap.className = "scroll-wrap" + (extraClass ? " " + extraClass : "");
    const prevBtn = document.createElement("button");
    prevBtn.className = "scroll-arrow hidden";
    prevBtn.innerHTML = `<ha-icon icon="mdi:chevron-left"></ha-icon>`;
    const nextBtn = document.createElement("button");
    nextBtn.className = "scroll-arrow hidden";
    nextBtn.innerHTML = `<ha-icon icon="mdi:chevron-right"></ha-icon>`;

    const scrollByChunk = (dir) => {
      scrollEl.scrollBy({ left: dir * Math.round(scrollEl.clientWidth * 0.7), behavior: "smooth" });
    };
    prevBtn.addEventListener("click", () => scrollByChunk(-1));
    nextBtn.addEventListener("click", () => scrollByChunk(1));

    const updateArrows = () => {
      const overflow = scrollEl.scrollWidth > scrollEl.clientWidth + 1;
      prevBtn.classList.toggle("hidden", !overflow || scrollEl.scrollLeft <= 0);
      nextBtn.classList.toggle("hidden",
        !overflow || scrollEl.scrollLeft >= scrollEl.scrollWidth - scrollEl.clientWidth - 1);
    };
    scrollEl.addEventListener("scroll", updateArrows, { passive: true });
    new ResizeObserver(updateArrows).observe(scrollEl);
    this._wireHorizontalWheelScroll(scrollEl);

    wrap.appendChild(prevBtn);
    wrap.appendChild(scrollEl);
    wrap.appendChild(nextBtn);
    return wrap;
  }

  // Desktop-Mäuse liefern nur vertikales Wheel-Delta -- ohne diese
  // Übersetzung ist eine per overflow-x:auto scrollbare Leiste (Tabs,
  // Fahrzeug-Umschalter) am Desktop faktisch nicht bedienbar, da der
  // native Scrollbalken bewusst ausgeblendet ist (schmaleres Design).
  _wireHorizontalWheelScroll(el) {
    el.addEventListener("wheel", (e) => {
      if (el.scrollWidth <= el.clientWidth) return;
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    }, { passive: false });
  }

  // Eigene Zeile unter der App-Bar, nur wenn mehr als ein Fahrzeug konfiguriert
  // ist -- wirkt global auf ALLE Tabs (siehe _switchVehicle()).
  _buildVehicleBar() {
    const vehicles = this._config.vehicles;
    this._vtBtns = [];
    if (!vehicles || vehicles.length < 2) return null;

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
    const scroll = document.createElement("div");
    scroll.className = "vt-bar-scroll";
    scroll.appendChild(pills);

    const row = document.createElement("div");
    row.className = "vt-bar";
    row.appendChild(this._buildScrollWrap(scroll));
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
    if (view === "uebersicht_beta") this._main.appendChild(this._buildUebersichtBeta());
    else if (view === "fahrzeuge") this._main.appendChild(this._buildVehicle());
    else if (view === "profil") this._main.appendChild(this._buildProfil());
    else if (view === "analyse") this._main.appendChild(this._buildAnalyse());
    else if (view === "leasing") this._main.appendChild(this._buildLeasing());
    else if (view === "ladekarten") this._main.appendChild(this._buildLadekarten());
    else if (view === "wartung") this._main.appendChild(this._buildWartung());
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
    // Lade-Modus (siehe _ladeModus()): Heim- bzw. Fremd-spezifische Elemente
    // dieser Karte gaenzlich weglassen statt leer/als 0 zu zeigen -- ein
    // reiner Heim- bzw. Fremdlader hat vom jeweils anderen konzeptionell
    // keine Daten. "gemischt" (Default) zeigt beides, exakt wie vor dieser
    // Aenderung.
    const modus = this._ladeModus();
    const showHome = modus !== "nur_auswaerts";
    const showExt = modus !== "nur_zuhause";
    // Legende fuer "Ladeuebersicht"/"Kostenuebersicht": im Einmodus nur die
    // tatsaechlich vorhandene Reihe zeigen (siehe _renderChart()/
    // _renderChartKosten() fuer den dazugehoerigen series-Filter), sonst
    // (gemischt) beide wie bisher.
    const chargeLegend = showHome && showExt
      ? `<span class="cleg"><span class="cleg-dot home"></span>Heimladen</span>
         <span class="cleg"><span class="cleg-dot ext"></span>Fremdladung</span>`
      : showHome
        ? `<span class="cleg"><span class="cleg-dot home"></span>Heimladen</span>`
        : `<span class="cleg"><span class="cleg-dot ext"></span>Fremdladung</span>`;
    // "Solaranteil" ist rein heim-basiert (Solarbezug gibt es nur an der
    // eigenen Wallbox, nie an fremden Ladepunkten) -- in "nur_auswaerts"
    // ganz weglassen statt eine bedeutungslose 0%-Spalte zu zeigen.
    const solarColHtml = showHome ? `
          <div class="chart-col">
            <div class="chart-col-title">Solaranteil</div>
            <div class="chart-legend">
              <span class="cleg"><span class="cleg-dot solar"></span>Solar Ø</span>
            </div>
            <div id="solar-chart"></div>
          </div>` : "";
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
              <span class="ic"><ha-icon icon="mdi:ev-station"></ha-icon></span><h2>Fahrzeug</h2>
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
            <div class="sub-head">Kosten &amp; kWh</div>
            <div class="km-grid">
              <div class="km-col">
                <div class="km-item"><span class="km-label">Heute</span><span class="km-val vh-cost-day">—</span><span class="km-unit">EUR</span></div>
                <div class="km-item"><span class="km-label">Woche</span><span class="km-val vh-cost-week">—</span><span class="km-unit">EUR</span></div>
                <div class="km-item"><span class="km-label">Monat</span><span class="km-val vh-cost-month">—</span><span class="km-unit">EUR</span></div>
                <div class="km-item"><span class="km-label">Jahr</span><span class="km-val vh-cost-year">—</span><span class="km-unit">EUR</span></div>
              </div>
              <div class="km-col">
                <div class="km-item"><span class="km-label">Heute</span><span class="km-val vh-kwh-day">—</span><span class="km-unit">kWh</span></div>
                <div class="km-item"><span class="km-label">Woche</span><span class="km-val vh-kwh-week">—</span><span class="km-unit">kWh</span></div>
                <div class="km-item"><span class="km-label">Monat</span><span class="km-val vh-kwh-month">—</span><span class="km-unit">kWh</span></div>
                <div class="km-item"><span class="km-label">Jahr</span><span class="km-val vh-kwh-year">—</span><span class="km-unit">kWh</span></div>
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
              ${chargeLegend}
            </div>
            <div id="overview-chart"></div>
          </div>
          <div class="chart-col">
            <div class="chart-col-title">Kostenübersicht</div>
            <div class="chart-legend">
              ${chargeLegend}
            </div>
            <div id="kosten-chart"></div>
          </div>${solarColHtml}
        </div>
      </div>

      <div class="vh-3col">${showHome ? `
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
        </div>` : ""}${showExt ? `
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
                <label>Ladeende (optional, nicht Abstecken)<input type="datetime-local" class="em-end-ts"></label>
                <label>kWh<input type="text" inputmode="decimal" class="em-kwh" placeholder="0,0"></label>
                <label>EUR/kWh<input type="text" inputmode="decimal" class="em-price" placeholder="0,000"></label>
                <label>SoC Start % (optional)<input type="text" inputmode="decimal" class="em-soc-start" placeholder="0"></label>
                <label>SoC Ende % (optional)<input type="text" inputmode="decimal" class="em-soc-end" placeholder="0"></label>
                <label>Startgebühr € (optional)<input type="text" inputmode="decimal" class="em-fee" placeholder="0,00"></label>
                <label>Blockiergebühr € (optional)<input type="text" inputmode="decimal" class="em-block-fee" placeholder="0,00"></label>
                <label>Zeitgebühr € (optional)<input type="text" inputmode="decimal" class="em-time-fee" placeholder="0,00"></label>
                <label class="em-karte-label hidden">Ladekarte (optional)<select class="em-karte"></select></label>
                <label>Anbieter (optional)<input type="text" class="em-anbieter" list="em-anbieter-list" placeholder="z.B. EnBW"></label>
                <datalist id="em-anbieter-list"></datalist>
                <button class="btn btn-primary em-save" disabled>Speichern</button>
                <button class="btn btn-ghost em-cancel">Abbrechen</button>
              </div>
              <div class="hist-list" id="hist-charge-list"></div>
            </div>
          </div>
        </div>` : ""}
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

    // Grid-Spaltenzahl an tatsaechlich vorhandene Karten/Spalten anpassen
    // (siehe .charts-grid/.vh-3col: repeat(var(--...-cols, 3), 1fr) in den
    // Stilen weiter unten) -- ohne das bliebe bei einer weggelassenen
    // Spalte eine leere Luecke im festen 3-Spalten-Raster stehen. Nur bei
    // tatsaechlich fehlender Spalte gesetzt; ohne Wert greift der Default
    // (3), optisch identisch zu vorher.
    if (!showHome) {
      const chartsGrid = container.querySelector(".charts-grid");
      if (chartsGrid) chartsGrid.style.setProperty("--charts-cols", "2");
    }
    if (modus !== "gemischt") {
      const vh3col = container.querySelector(".vh-3col");
      if (vh3col) vh3col.style.setProperty("--vh3-cols", "2");
    }

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
      vhKwhDay:       q(".vh-kwh-day"),
      vhKwhWeek:      q(".vh-kwh-week"),
      vhKwhMonth:     q(".vh-kwh-month"),
      vhKwhYear:      q(".vh-kwh-year"),

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
    const karteLabel    = form.querySelector(".em-karte-label");
    const karteSelect   = form.querySelector(".em-karte");
    const anbieterInput = form.querySelector(".em-anbieter");
    const anbieterList  = form.querySelector("#em-anbieter-list");
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
        const karten = this._ladekartenList();
        karteLabel.classList.toggle("hidden", karten.length === 0);
        karteSelect.innerHTML = this._karteOptionsHtml(null);
        anbieterInput.value = "";
        anbieterList.innerHTML = this._anbieterOptionsHtml();
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
      if (!karteLabel.classList.contains("hidden") && karteSelect.value !== "") {
        payload.karte_id = parseInt(karteSelect.value, 10);
      }
      if (anbieterInput.value.trim()) payload.anbieter = anbieterInput.value.trim();
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
          <span class="badge badge-urlaub hidden" id="profil-urlaub-badge" title="Urlaubsmodus aktiv — betroffene Tage werden aus den Profilen ausgeschlossen, die evcc-Steuerung pausiert">
            <ha-icon icon="mdi:bag-suitcase"></ha-icon>Urlaub
          </span>
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
      </div>
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:home-clock"></ha-icon></span><h2>Hausnutzungsprofil</h2>
        </div>
        <div class="profil-empty hidden" id="house-profil-empty">—</div>
        <div class="hidden" id="house-profil-content">
          <div class="sub-head" id="house-profil-subhead">Ø kWh-Verbrauch pro Wochentag</div>
          <div class="weekday-chart" id="house-profil-weekday-chart"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:ev-plug-type2"></ha-icon></span><h2>Steckerprofil</h2>
        </div>
        <div class="profil-empty hidden" id="plug-profil-empty">—</div>
        <div class="hidden" id="plug-profil-content">
          <div class="sub-head">Ø Steckdauer pro Wochentag (Std.)</div>
          <div class="weekday-chart" id="plug-profil-weekday-chart"></div>
        </div>
      </div>`;

    const q = (s) => wrap.querySelector(s);
    this._r = {
      profilEmpty:        q("#profil-empty"),
      profilContent:       q("#profil-content"),
      profilUrlaubBadge:  q("#profil-urlaub-badge"),
      profilRecommendIcon: q("#profil-recommend-icon"),
      profilRecommendText: q("#profil-recommend-text"),
      profilAvailable:     q("#profil-available"),
      profilNeedTomorrow:  q("#profil-need-tomorrow"),
      profilBuffer:        q("#profil-buffer"),
      profilPvForecastKpi: q("#profil-pv-forecast-kpi"),
      profilPvForecast:    q("#profil-pv-forecast"),
      profilWeekdayChart:  q("#profil-weekday-chart"),
      houseProfilEmpty:        q("#house-profil-empty"),
      houseProfilContent:      q("#house-profil-content"),
      houseProfilSubhead:      q("#house-profil-subhead"),
      houseProfilWeekdayChart: q("#house-profil-weekday-chart"),
      plugProfilEmpty:        q("#plug-profil-empty"),
      plugProfilContent:      q("#plug-profil-content"),
      plugProfilWeekdayChart: q("#plug-profil-weekday-chart"),
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
          <div class="kpi"><div class="kv" id="analyse-loc-gesamt-autarkie">—</div><div class="kl">Gesamt-Autarkiegrad (Heim + Fremd)</div></div>
        </div>
        <div class="profil-empty">
          Solaranteil nur für Heimladungen, die evcc gesteuert hat. EUR/100km und Gesamt-Autarkiegrad sind
          fahrzeugweit über die Gesamtladung — Fremdladung zählt beim Autarkiegrad als 0% Solar, da der
          Strommix an fremden Ladesäulen unbekannt ist. km lassen sich keinem einzelnen Ladeort zuordnen.
        </div>
        <div class="divider hidden" id="analyse-acdc-divider"></div>
        <div class="sub-head hidden" id="analyse-acdc-head" title="Geschätzt aus Ø-Ladeleistung (kWh/Ladedauer), keine direkte AC/DC-Messung.">Fremdladung nach AC/DC ⓘ</div>
        <div class="km-grid hidden" id="analyse-acdc-grid">
          <div class="km-col hidden" id="analyse-acdc-ac-col">
            <div class="sub-head">AC</div>
            <div class="km-item"><span class="km-label">kWh</span><span class="km-val" id="analyse-acdc-ac-kwh">—</span><span class="km-unit">kWh</span></div>
            <div class="km-item"><span class="km-label">Kosten</span><span class="km-val" id="analyse-acdc-ac-cost">—</span><span class="km-unit">EUR</span></div>
            <div class="km-item"><span class="km-label">Anteil</span><span class="km-val" id="analyse-acdc-ac-pct">—</span><span class="km-unit">%</span></div>
            <div class="km-item"><span class="km-label">Ø Preis</span><span class="km-val" id="analyse-acdc-ac-price">—</span><span class="km-unit">EUR/kWh</span></div>
            <div class="km-item"><span class="km-label">Ladungen</span><span class="km-val" id="analyse-acdc-ac-count">—</span><span class="km-unit"></span></div>
          </div>
          <div class="km-col hidden" id="analyse-acdc-dc-col">
            <div class="sub-head">DC</div>
            <div class="km-item"><span class="km-label">kWh</span><span class="km-val" id="analyse-acdc-dc-kwh">—</span><span class="km-unit">kWh</span></div>
            <div class="km-item"><span class="km-label">Kosten</span><span class="km-val" id="analyse-acdc-dc-cost">—</span><span class="km-unit">EUR</span></div>
            <div class="km-item"><span class="km-label">Anteil</span><span class="km-val" id="analyse-acdc-dc-pct">—</span><span class="km-unit">%</span></div>
            <div class="km-item"><span class="km-label">Ø Preis</span><span class="km-val" id="analyse-acdc-dc-price">—</span><span class="km-unit">EUR/kWh</span></div>
            <div class="km-item"><span class="km-label">Ladungen</span><span class="km-val" id="analyse-acdc-dc-count">—</span><span class="km-unit"></span></div>
          </div>
        </div>
        <div class="profil-empty hidden" id="analyse-acdc-note" style="padding:4px 0 0;font-size:0.72rem">
          Geschätzt aus der Durchschnittsleistung je Ladung (kWh ÷ Ladedauer) gegen eine 22-kW-Schwelle — keine
          direkte AC/DC-Messung. Grenzfälle möglich, insbesondere bei abgeregelten Schnellladungen.
        </div>
      </div>
      <div class="card hidden" id="analyse-mischpreis-card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:cash-sync"></ha-icon></span><h2>Wirtschaftlichkeit Netz-Zuschuss</h2>
        </div>
        <div class="mischpreis-scale-wrap">
          <div class="mischpreis-scale" id="analyse-mischpreis-scale">
            <div class="mischpreis-marker mischpreis-marker-schwelle hidden" id="analyse-mischpreis-schwelle-marker" title="Konfigurierte Schwelle (Mindest-Solaranteil)"></div>
            <div class="mischpreis-marker mischpreis-marker-aktuell hidden" id="analyse-mischpreis-aktuell-marker" title="Aktueller Mischpreis"></div>
          </div>
          <div class="mischpreis-scale-labels">
            <span id="analyse-mischpreis-feedin-label">—</span>
            <span id="analyse-mischpreis-grid-label">—</span>
          </div>
        </div>
        <div class="kpi-row">
          <div class="kpi"><div class="kv" id="analyse-mischpreis-aktuell">—</div><div class="kl">EUR/kWh aktueller Mischpreis</div></div>
          <div class="kpi"><div class="kv" id="analyse-mischpreis-schwelle">—</div><div class="kl">EUR/kWh Schwelle (Mindest-Solaranteil)</div></div>
        </div>
        <div class="profil-empty" id="analyse-mischpreis-note">—</div>
      </div>
      <div class="card hidden" id="analyse-anbieter-card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:map-marker-radius"></ha-icon></span><h2>Verteilung nach Anbieter</h2>
        </div>
        <div id="analyse-anbieter-list"></div>
        <div class="profil-empty" style="padding-top:4px">
          Nur tatsächliche Ladungskosten je Anbieter (WO geladen wurde) — Ladekarten-Grundgebühren gehören
          keinem einzelnen Anbieter zu und fließen hier nicht ein.
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
      analyseLocGesamtAutarkie: q("#analyse-loc-gesamt-autarkie"),
      analyseAcdcDivider: q("#analyse-acdc-divider"),
      analyseAcdcHead:    q("#analyse-acdc-head"),
      analyseAcdcGrid:    q("#analyse-acdc-grid"),
      analyseAcdcAcCol:   q("#analyse-acdc-ac-col"),
      analyseAcdcAcKwh:   q("#analyse-acdc-ac-kwh"),
      analyseAcdcAcCost:  q("#analyse-acdc-ac-cost"),
      analyseAcdcAcPct:   q("#analyse-acdc-ac-pct"),
      analyseAcdcAcPrice: q("#analyse-acdc-ac-price"),
      analyseAcdcAcCount: q("#analyse-acdc-ac-count"),
      analyseAcdcDcCol:   q("#analyse-acdc-dc-col"),
      analyseAcdcDcKwh:   q("#analyse-acdc-dc-kwh"),
      analyseAcdcDcCost:  q("#analyse-acdc-dc-cost"),
      analyseAcdcDcPct:   q("#analyse-acdc-dc-pct"),
      analyseAcdcDcPrice: q("#analyse-acdc-dc-price"),
      analyseAcdcDcCount: q("#analyse-acdc-dc-count"),
      analyseAcdcNote:    q("#analyse-acdc-note"),
      analyseAnbieterCard: q("#analyse-anbieter-card"),
      analyseAnbieterList: q("#analyse-anbieter-list"),
      analyseMischpreisCard:      q("#analyse-mischpreis-card"),
      analyseMischpreisSchwelleMarker: q("#analyse-mischpreis-schwelle-marker"),
      analyseMischpreisAktuellMarker:  q("#analyse-mischpreis-aktuell-marker"),
      analyseMischpreisFeedinLabel:    q("#analyse-mischpreis-feedin-label"),
      analyseMischpreisGridLabel:      q("#analyse-mischpreis-grid-label"),
      analyseMischpreisAktuell:  q("#analyse-mischpreis-aktuell"),
      analyseMischpreisSchwelle: q("#analyse-mischpreis-schwelle"),
      analyseMischpreisNote:     q("#analyse-mischpreis-note"),
    };
    return wrap;
  }

  _updateProfil() {
    const r = this._r;
    if (!r.profilRecommendText) return;

    const modeCtrlEid = this._eid("evcc_mode_control");
    const modeCtrlState = modeCtrlEid ? this._hass.states[modeCtrlEid] : null;
    const urlaubAktiv = !!(modeCtrlState && modeCtrlState.attributes && modeCtrlState.attributes.urlaub_aktiv);
    if (r.profilUrlaubBadge) r.profilUrlaubBadge.classList.toggle("hidden", !urlaubAktiv);

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

    this._updateHouseProfil();
    this._updatePlugProfil();
  }

  // Haus-Nutzungsprofil (siehe coordinator.py::house_usage_profile(), fuer
  // die evcc-Modus-/SoC-Steuerung) -- eigene Karte unter dem Fahrzeugprofil
  // oben, bewusst ohne KPI-Zeile/Empfehlung (keine Verfuegbare-kWh- oder
  // PV-Entsprechung fuers Haus als Ganzes), nur der Wochentags-Chart.
  // Anders als beim Fahrzeug-Profil koennen einzelne Wochentage fehlen
  // (house_usage_profile() liefert nur tatsaechlich beobachtete Tage) --
  // "noch keine Daten" wird als eigener Balken-Zustand dargestellt statt
  // faelschlich als 0 kWh.
  _updateHouseProfil() {
    const r = this._r;
    if (!r.houseProfilEmpty) return;
    const eid = this._eid("house_usage_profile");
    const state = eid ? this._hass.states[eid] : null;
    const attrs = state ? state.attributes || {} : {};
    const WEEKDAYS = [
      ["montag", "Mo"], ["dienstag", "Di"], ["mittwoch", "Mi"], ["donnerstag", "Do"],
      ["freitag", "Fr"], ["samstag", "Sa"], ["sonntag", "So"],
    ];
    const konfiguriert = attrs.konfiguriert === true;
    const hasAnyDay = WEEKDAYS.some(([key]) => attrs[key] !== undefined);

    if (!konfiguriert || !hasAnyDay) {
      r.houseProfilEmpty.textContent = !konfiguriert
        ? "Kein Hausverbrauchszähler konfiguriert (Einstellungen → evcc & Wallbox → evcc-Modus-/SoC-Steuerung) — optional, fürs Hausnutzungsprofil und die evcc-Steuerung."
        : "Noch keine Tage gesammelt. Das Profil füllt sich automatisch über die nächsten Tage.";
      r.houseProfilEmpty.classList.remove("hidden");
      r.houseProfilContent.classList.add("hidden");
      return;
    }
    r.houseProfilEmpty.classList.add("hidden");
    r.houseProfilContent.classList.remove("hidden");

    r.houseProfilSubhead.textContent = attrs.speicher_enthalten
      ? "Ø kWh-Verbrauch pro Wochentag (inkl. Speicherladung)"
      : "Ø kWh-Verbrauch pro Wochentag";

    const values = WEEKDAYS.map(([key]) => (attrs[key] !== undefined ? parseFloat(attrs[key]) : null));
    const maxVal = Math.max(...values.filter((v) => v !== null), 0.1);
    const todayWd = new Date().getDay();
    const todayIdx = todayWd === 0 ? 6 : todayWd - 1;
    const tomorrowIdx = (todayIdx + 1) % 7;

    r.houseProfilWeekdayChart.innerHTML = WEEKDAYS.map(([, label], i) => {
      const v = values[i];
      const noData = v === null;
      const pct = noData ? 2 : Math.max(2, Math.round((v / maxVal) * 100));
      let cls = noData ? "wd-bar no-data" : "wd-bar";
      if (!noData) cls += i === tomorrowIdx ? " tomorrow" : (i === todayIdx ? " today" : "");
      return `
        <div class="wd-col">
          <div class="wd-val">${noData ? "–" : this._fmtNum(v, 1)}</div>
          <div class="wd-bar-track"><div class="${cls}" style="height:${pct}%"></div></div>
          <div class="wd-label">${label}</div>
        </div>`;
    }).join("");
  }

  // Steckerprofil (siehe coordinator.py::plug_window_profile(), rein
  // informatives Beobachtungsfeature -- Nutzerwunsch 2026-09-23: "wann und
  // wie lange am tag das auto angeschlossen ist ... um zu erkennen wie das
  // auto zuhause ist und wann fenster zum laden entstehen"). Analog
  // _updateHouseProfil(): eigene Karte, gleicher Wochentags-Chart, einzelne
  // fehlende Wochentage als "noch keine Daten" statt 0 Std. Beeinflusst
  // (noch) NICHT die Modus-/SoC-Steuerung, rein zur Beobachtung.
  _updatePlugProfil() {
    const r = this._r;
    if (!r.plugProfilEmpty) return;
    const eid = this._eid("plug_window");
    const state = eid ? this._hass.states[eid] : null;
    const attrs = state ? state.attributes || {} : {};
    const WEEKDAYS = [
      ["montag", "Mo"], ["dienstag", "Di"], ["mittwoch", "Mi"], ["donnerstag", "Do"],
      ["freitag", "Fr"], ["samstag", "Sa"], ["sonntag", "So"],
    ];
    const hasAnyDay = WEEKDAYS.some(([key]) => attrs[key] !== undefined);

    if (!eid || !hasAnyDay) {
      r.plugProfilEmpty.textContent = "Noch keine Tage gesammelt. Das Profil füllt sich automatisch über die nächsten Tage.";
      r.plugProfilEmpty.classList.remove("hidden");
      r.plugProfilContent.classList.add("hidden");
      return;
    }
    r.plugProfilEmpty.classList.add("hidden");
    r.plugProfilContent.classList.remove("hidden");

    const values = WEEKDAYS.map(([key]) => (attrs[key] !== undefined ? parseFloat(attrs[key]) : null));
    const maxVal = Math.max(...values.filter((v) => v !== null), 0.1);
    const todayWd = new Date().getDay();
    const todayIdx = todayWd === 0 ? 6 : todayWd - 1;
    const tomorrowIdx = (todayIdx + 1) % 7;

    r.plugProfilWeekdayChart.innerHTML = WEEKDAYS.map(([, label], i) => {
      const v = values[i];
      const noData = v === null;
      const pct = noData ? 2 : Math.max(2, Math.round((v / maxVal) * 100));
      let cls = noData ? "wd-bar no-data" : "wd-bar";
      if (!noData) cls += i === tomorrowIdx ? " tomorrow" : (i === todayIdx ? " today" : "");
      return `
        <div class="wd-col">
          <div class="wd-val">${noData ? "–" : this._fmtNum(v, 1)}</div>
          <div class="wd-bar-track"><div class="${cls}" style="height:${pct}%"></div></div>
          <div class="wd-label">${label}</div>
        </div>`;
    }).join("");
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
    r.analyseLocGesamtAutarkie.textContent = typeof locAttrs.gesamt_autarkie_pct === "number"
      ? `${this._fmtNum(locAttrs.gesamt_autarkie_pct, 1)} %` : "—";

    const acDc = locAttrs.ac_dc || {};
    const hasAcDc = !!(acDc.ac || acDc.dc);
    r.analyseAcdcDivider.classList.toggle("hidden", !hasAcDc);
    r.analyseAcdcHead.classList.toggle("hidden", !hasAcDc);
    r.analyseAcdcGrid.classList.toggle("hidden", !hasAcDc);
    r.analyseAcdcNote.classList.toggle("hidden", !hasAcDc);
    r.analyseAcdcAcCol.classList.toggle("hidden", !acDc.ac);
    if (acDc.ac) {
      r.analyseAcdcAcKwh.textContent = fmt(acDc.ac.kwh, 1);
      r.analyseAcdcAcCost.textContent = fmt(acDc.ac.kosten, 2);
      r.analyseAcdcAcPct.textContent = fmt(acDc.ac.kwh_anteil_pct, 1);
      r.analyseAcdcAcPrice.textContent = fmt(acDc.ac.preis_je_kwh, 3);
      r.analyseAcdcAcCount.textContent = fmt(acDc.ac.anzahl, 0);
    }
    r.analyseAcdcDcCol.classList.toggle("hidden", !acDc.dc);
    if (acDc.dc) {
      r.analyseAcdcDcKwh.textContent = fmt(acDc.dc.kwh, 1);
      r.analyseAcdcDcCost.textContent = fmt(acDc.dc.kosten, 2);
      r.analyseAcdcDcPct.textContent = fmt(acDc.dc.kwh_anteil_pct, 1);
      r.analyseAcdcDcPrice.textContent = fmt(acDc.dc.preis_je_kwh, 3);
      r.analyseAcdcDcCount.textContent = fmt(acDc.dc.anzahl, 0);
    }

    // Verteilung nach Anbieter (WO geladen wurde -- siehe engine.py::
    // anbieter_breakdown(), NICHT zu verwechseln mit Ladekarten). In
    // "nur_zuhause" faellt keine Fremdladung an, die Karte waere dort
    // immer leer -- daher ausgeblendet statt eine leere Karte zu zeigen.
    // Ebenso ausgeblendet bei <=1 Anbieter-Bucket (z.B. alles unter
    // "Unbekannt"), da eine Verteilung mit nur einem Balken nichts aussagt.
    const anbieter = locAttrs.anbieter || {};
    const anbieterEntries = Object.entries(anbieter);
    const showAnbieter = anbieterEntries.length > 1 && this._ladeModus() !== "nur_zuhause";
    r.analyseAnbieterCard.classList.toggle("hidden", !showAnbieter);
    if (showAnbieter) {
      const byKwh = anbieterEntries.some(([, v]) => typeof v.kwh === "number");
      anbieterEntries.sort((a, b) => {
        const va = byKwh ? (a[1].kwh || 0) : (a[1].kosten || 0);
        const vb = byKwh ? (b[1].kwh || 0) : (b[1].kosten || 0);
        return vb - va;
      });
      const maxVal = Math.max(...anbieterEntries.map(([, v]) => (byKwh ? v.kwh : v.kosten) || 0), 0.1);
      r.analyseAnbieterList.innerHTML = anbieterEntries.map(([label, v]) => {
        const val = (byKwh ? v.kwh : v.kosten) || 0;
        const pct = Math.max(2, Math.round((val / maxVal) * 100));
        const valText = byKwh ? `${this._fmtNum(val, 1)} kWh` : `${this._fmtNum(val, 2)} EUR`;
        // Anteil an der Gesamtsumme und Ø Preis/kWh -- beide bereits aus
        // engine.anbieter_breakdown(), nur angezeigt wenn die zugrunde-
        // liegenden Werte tatsaechlich bekannt sind (preis_je_kwh fehlt
        // z.B. ganz ohne kwh-Angabe).
        const sharePct = byKwh ? v.kwh_anteil_pct : v.kosten_anteil_pct;
        const pctText = typeof sharePct === "number" ? `${this._fmtNum(sharePct, 1)}%` : "—";
        const subParts = [valText];
        if (typeof v.preis_je_kwh === "number") subParts.push(`Ø ${this._fmtNum(v.preis_je_kwh, 3)} €/kWh`);
        return `
          <div class="anbieter-bar-row">
            <div class="anbieter-bar-top">
              <div class="anbieter-bar-label" title="${label}">${label}</div>
              <div class="anbieter-bar-val">
                <div class="anbieter-bar-val-main">${pctText}</div>
                <div class="anbieter-bar-val-sub">${subParts.join(" · ")}</div>
              </div>
            </div>
            <div class="veh-soc-bar-wrap"><div class="veh-soc-bar-fill" style="width:${pct}%"></div></div>
          </div>`;
      }).join("");
    }

    this._updateAnalyseMischpreis();

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

  // Wirtschaftlichkeit Netz-Zuschuss (Analyse-Tab, Nutzerwunsch 2026-09-24:
  // "stelle das auch grafisch im analysetab dar", zur wirtschaftlichen
  // Kappung der Echtzeit-PV-Uebersteuerung, siehe coordinator.py::
  // _evcc_mode_targets()/engine.blended_charge_price()). Skala von der
  // Einspeiseverguetung (guenstig) bis zum Netzpreis (teuer), mit Markern
  // fuer die konfigurierte Schwelle (Mindest-Solaranteil) und den gerade
  // aktuellen Mischpreis. Nur sichtbar, wenn evcc ueberhaupt Tarife meldet
  // -- ohne die ist weder eine Skala noch ein Mischpreis moeglich.
  //
  // Der "aktuell"-Marker wird bewusst NICHT aus "pv_override_mischpreis_
  // kwh" abgeleitet (Nutzerbeobachtung 2026-09-24: "daten werden gezeigt,
  // und dann wieder nicht, dann wieder ... marker bleibt nicht auf der
  // skala sichtbar") -- dieses Attribut ist serverseitig bewusst nur
  // innerhalb des schmalen 0 < Ueberschuss < Mindestleistung-Fensters
  // gesetzt (siehe coordinator.py-Docstring), verschwindet also bei jedem
  // kurzen Ueber-/Unterschreiten der Schwelle (Wolken, Verbraucher-
  // Spitzen) komplett. Stattdessen wird der Mischpreis HIER selbst
  // kontinuierlich aus dem immer vorhandenen "pv_ueberschuss_w" und
  // "wallbox_min_power_w" nachgerechnet (identische Formel wie engine.
  // blended_charge_price(), Ueberschuss auf [0, Mindestleistung]
  // geklemmt) -- der Marker gleitet dadurch stetig ueber die Skala statt
  // zu blinken, auch ausserhalb des schmalen Kandidaten-Fensters (dort
  // zeigt er dann einfach reinen Netz- bzw. reinen Einspeisepreis).
  _updateAnalyseMischpreis() {
    const r = this._r;
    if (!r.analyseMischpreisCard) return;
    const live = this._evccLive();
    const feedin = parseFloat(live.tariff_feedin);
    const grid = parseFloat(live.tariff_grid);
    const hasTariffs = !isNaN(feedin) && !isNaN(grid) && grid > feedin;
    r.analyseMischpreisCard.classList.toggle("hidden", !hasTariffs);
    if (!hasTariffs) return;

    const modeCtrlEid = this._eid("evcc_mode_control");
    const modeCtrlState = modeCtrlEid ? this._hass.states[modeCtrlEid] : null;
    const a = (modeCtrlState && modeCtrlState.attributes) || {};
    const surplus = typeof a.pv_ueberschuss_w === "number" ? a.pv_ueberschuss_w : null;
    const minPower = typeof a.wallbox_min_power_w === "number" ? a.wallbox_min_power_w : null;
    const schwelle = typeof a.pv_override_max_mischpreis_kwh === "number" ? a.pv_override_max_mischpreis_kwh : null;
    let aktuell = null;
    if (surplus !== null && minPower !== null && minPower > 0) {
      const clamped = Math.max(0, Math.min(surplus, minPower));
      const gridTopupW = minPower - clamped;
      aktuell = (clamped * feedin + gridTopupW * grid) / minPower;
    }
    const pct = (v) => Math.max(0, Math.min(100, ((v - feedin) / (grid - feedin)) * 100));

    r.analyseMischpreisFeedinLabel.textContent = `${this._fmtNum(feedin, 3)} €/kWh Einspeisung`;
    r.analyseMischpreisGridLabel.textContent = `${this._fmtNum(grid, 3)} €/kWh Netz`;

    r.analyseMischpreisSchwelleMarker.classList.toggle("hidden", schwelle === null);
    if (schwelle !== null) r.analyseMischpreisSchwelleMarker.style.left = `${pct(schwelle)}%`;

    r.analyseMischpreisAktuellMarker.classList.toggle("hidden", aktuell === null);
    if (aktuell !== null) r.analyseMischpreisAktuellMarker.style.left = `${pct(aktuell)}%`;

    r.analyseMischpreisAktuell.textContent = aktuell !== null ? this._fmtNum(aktuell, 3) : "—";
    r.analyseMischpreisSchwelle.textContent = schwelle !== null ? this._fmtNum(schwelle, 3) : "—";

    if (aktuell === null) {
      r.analyseMischpreisNote.textContent = "Noch keine Live-Daten von evcc.";
    } else if (schwelle === null) {
      r.analyseMischpreisNote.textContent = "Kein Mindest-Solaranteil konfiguriert (Einstellungen → evcc & Wallbox) — jeder PV-Überschuss unter der Mindestladeleistung wird derzeit durch Netzstrom ergänzt.";
    } else if (aktuell <= schwelle) {
      r.analyseMischpreisNote.textContent = "Aktueller Mischpreis liegt innerhalb der Schwelle — ein Netz-Zuschuss würde genutzt.";
    } else {
      r.analyseMischpreisNote.textContent = "Aktueller Mischpreis liegt über der Schwelle — ein Überschuss wird stattdessen eingespeist statt teuren Netzstrom zuzukaufen.";
    }
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

  // --- Tab: Ladekarten ---------------------------------------------------------
  //
  // Reine Kostenposten (monatliche Grundgebuehren, siehe coordinator.py::
  // ladekarten_stats()) -- unabhaengig von einzelnen Fremdladungen, deren
  // optionale Zuordnung (siehe _karteOptionsHtml()) rein informativ ist.
  // Analog zum Leasing-Tab: eigener, immer sichtbarer Tab, aber ohne
  // Inhalt/Rauschen, solange keine Karte angelegt ist.

  _buildLadekarten() {
    const wrap = document.createElement("div");
    wrap.className = "tab-wrap";
    wrap.innerHTML = `
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:credit-card-multiple-outline"></ha-icon></span><h2>Ladekarten</h2>
          <button class="btn btn-ghost lk-add-toggle" style="margin-left:auto">
            <ha-icon icon="mdi:plus" style="--mdc-icon-size:14px;vertical-align:-2px"></ha-icon> Karte anlegen
          </button>
        </div>
        <div class="hist-edit-form hidden" id="lk-add-form">
          <label>Name<input type="text" class="lk-name" placeholder="z.B. ADAC e-Charge"></label>
          <label>Monatliche Gebühr €<input type="text" inputmode="decimal" class="lk-gebuehr" placeholder="0,00"></label>
          <label>Startdatum<input type="date" class="lk-start"></label>
          <label>Enddatum (optional)<input type="date" class="lk-end"></label>
          <button class="btn btn-primary lk-save" disabled>Speichern</button>
          <button class="btn btn-ghost lk-cancel">Abbrechen</button>
        </div>
        <div class="profil-empty" id="lk-empty">
          Noch keine Ladekarte angelegt — z.B. eine Abo-Karte eines Fremdlade-Anbieters mit monatlicher
          Grundgebühr, unabhängig von einzelnen Ladungen. Die aufgelaufene Gebühr fließt automatisch in die
          Fremdladung-Gesamtkosten ein (Ersparnis, EUR/100km, Kosten-Perioden), aber nicht in den Preis je kWh.
        </div>
        <div class="hidden" id="lk-content">
          <div class="kpi-row">
            <div class="kpi"><div class="kv" id="lk-gesamt">—</div><div class="kl">EUR aufgelaufen gesamt</div></div>
          </div>
          <div class="divider"></div>
          <div class="hist-list" id="lk-list"></div>
        </div>
      </div>`;

    const q = (s) => wrap.querySelector(s);
    this._r.lkEmpty = q("#lk-empty");
    this._r.lkContent = q("#lk-content");
    this._r.lkGesamt = q("#lk-gesamt");
    this._r.lkList = q("#lk-list");

    this._wireLadekartenAddForm(wrap);
    return wrap;
  }

  _wireLadekartenAddForm(container) {
    const toggle = container.querySelector(".lk-add-toggle");
    const form = container.querySelector("#lk-add-form");
    if (!toggle || !form) return;
    const nameInput    = form.querySelector(".lk-name");
    const gebuehrInput = form.querySelector(".lk-gebuehr");
    const startInput   = form.querySelector(".lk-start");
    const endInput     = form.querySelector(".lk-end");
    const saveBtn      = form.querySelector(".lk-save");
    const cancelBtn    = form.querySelector(".lk-cancel");

    const updateValidity = () => {
      const gebuehr = parseFloat(gebuehrInput.value.replace(",", "."));
      saveBtn.disabled = !nameInput.value.trim() || isNaN(gebuehr) || !startInput.value;
    };
    nameInput.addEventListener("input", updateValidity);
    gebuehrInput.addEventListener("input", updateValidity);
    startInput.addEventListener("input", updateValidity);

    toggle.addEventListener("click", () => {
      const opening = form.classList.contains("hidden");
      form.classList.toggle("hidden");
      if (opening) {
        nameInput.value = "";
        gebuehrInput.value = "";
        startInput.value = new Date().toISOString().slice(0, 10);
        endInput.value = "";
        updateValidity();
      }
    });
    cancelBtn.addEventListener("click", () => form.classList.add("hidden"));
    saveBtn.addEventListener("click", () => {
      const name = nameInput.value.trim();
      const gebuehr = parseFloat(gebuehrInput.value.replace(",", "."));
      if (!name || isNaN(gebuehr) || !startInput.value) return;
      const payload = { name, monatliche_gebuehr: gebuehr, start_datum: startInput.value };
      if (endInput.value) payload.end_datum = endInput.value;
      this._call("add_ladekarte", payload);
      form.classList.add("hidden");
    });
  }

  _updateLadekarten() {
    const r = this._r;
    if (!r.lkContent) return;
    const eid = this._eid("ladekarten_kosten");
    const state = eid ? this._hass.states[eid] : null;
    const karten = (state && Array.isArray((state.attributes || {}).karten)) ? state.attributes.karten : [];
    const hasKarten = karten.length > 0;
    r.lkEmpty.classList.toggle("hidden", hasKarten);
    r.lkContent.classList.toggle("hidden", !hasKarten);
    if (!hasKarten) return;
    r.lkGesamt.textContent = this._fmtNum(state.attributes.gesamt, 2);
    this._renderLadekartenList(karten);
  }

  _renderLadekartenList(karten) {
    const list = this._r.lkList;
    if (!list) return;
    const sig = karten.map((k) => {
      const stufen = (k.gebuehren || []).map((s) => `${s.ab_datum}:${s.gebuehr}`).join(",");
      return `${k.id}:${k.name}:${k.start_datum}:${k.end_datum}:${stufen}`;
    }).join("|");
    if (sig === this._lkSig && list.dataset.built === "1") return;
    this._lkSig = sig;
    list.dataset.built = "1";
    list.innerHTML = "";
    const fmtDate = (iso) => {
      if (!iso) return "—";
      const d = new Date(iso);
      return isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-DE");
    };
    karten.forEach((k) => {
      const row = document.createElement("div");
      row.className = "hist-card";
      const aktiv = !k.end_datum || k.end_datum >= new Date().toISOString().slice(0, 10);
      const stufen = [...(k.gebuehren || [])].sort((a, b) => (a.ab_datum < b.ab_datum ? -1 : 1));
      const fruehesteAbDatum = stufen.length ? stufen[0].ab_datum : null;
      const stufenHtml = stufen.map((s) => {
        const kannLoeschen = s.ab_datum !== fruehesteAbDatum;
        return `
          <div class="km-item lk-stufe" data-ab="${s.ab_datum}">
            <span class="km-label">ab ${fmtDate(s.ab_datum)}</span>
            <span class="km-val">${this._fmtNum(s.gebuehr, 2)}</span>
            <span class="km-unit">EUR/Monat</span>
            ${kannLoeschen ? `<button class="btn-icon sm lk-stufe-delete" title="Preisstufe entfernen"><ha-icon icon="mdi:close"></ha-icon></button>` : ""}
          </div>`;
      }).join("");
      row.innerHTML = `
        <div class="hist-top">
          <span class="hist-date">${k.name}${aktiv ? "" : ` <span class="hist-meta">· gekündigt</span>`}</span>
          <div class="hist-actions">
            <button class="btn-icon sm lk-edit" title="Bearbeiten"><ha-icon icon="mdi:pencil"></ha-icon></button>
            <button class="btn-icon sm lk-delete" title="Löschen"><ha-icon icon="mdi:delete"></ha-icon></button>
          </div>
        </div>
        <div class="hist-figures">
          <div class="hist-figures-left">
            <span class="hist-price">${this._fmtNum(k.aktuelle_gebuehr, 2)} €/Monat (aktuell)</span>
            <span class="hist-fee">seit ${fmtDate(k.start_datum)}${k.end_datum ? ` bis ${fmtDate(k.end_datum)}` : ""}</span>
          </div>
          <span class="hist-cost">${this._fmtNum(k.kosten, 2)} €</span>
        </div>
        <div class="km-col lk-stufen">${stufenHtml}</div>
        <div class="hist-edit-form hidden lk-stufe-form">
          <label>Gültig ab<input type="date" class="lks-ab"></label>
          <label>Monatliche Gebühr €<input type="text" inputmode="decimal" class="lks-gebuehr" placeholder="0,00"></label>
          <button class="btn btn-primary lks-save" disabled>Preisstufe speichern</button>
          <button class="btn btn-ghost lks-cancel">Abbrechen</button>
        </div>
        <button class="btn btn-ghost sm lk-stufe-toggle">
          <ha-icon icon="mdi:plus" style="--mdc-icon-size:14px;vertical-align:-2px"></ha-icon> Preisänderung
        </button>
        <div class="hist-edit-form hidden">
          <label>Name<input type="text" class="lke-name" value="${k.name}"></label>
          <label>Startgebühr € (früheste Stufe)<input type="text" inputmode="decimal" class="lke-gebuehr" value="${stufen[0] ? stufen[0].gebuehr : ""}"></label>
          <label>Startdatum<input type="date" class="lke-start" value="${k.start_datum || ""}"></label>
          <label>Enddatum (optional)<input type="date" class="lke-end" value="${k.end_datum || ""}"></label>
          <button class="btn btn-primary lke-save">Speichern</button>
          <button class="btn btn-ghost lke-cancel">Abbrechen</button>
        </div>
        <div class="hist-delete-confirm hidden">
          <span class="hist-delete-text">Diese Ladekarte dauerhaft löschen?</span>
          <button class="btn btn-danger lkd-confirm">Löschen</button>
          <button class="btn btn-ghost lkd-cancel">Abbrechen</button>
        </div>`;
      const form = row.querySelector(".hist-edit-form:not(.lk-stufe-form)");
      const delConfirm = row.querySelector(".hist-delete-confirm");
      const stufeForm = row.querySelector(".lk-stufe-form");
      row.querySelector(".lk-edit").addEventListener("click", () => {
        delConfirm.classList.add("hidden");
        stufeForm.classList.add("hidden");
        form.classList.toggle("hidden");
      });
      row.querySelector(".lke-cancel").addEventListener("click", () => form.classList.add("hidden"));
      row.querySelector(".lke-save").addEventListener("click", () => {
        const name = row.querySelector(".lke-name").value.trim();
        const gebuehr = parseFloat(row.querySelector(".lke-gebuehr").value.replace(",", "."));
        const start = row.querySelector(".lke-start").value;
        const end = row.querySelector(".lke-end").value;
        const payload = { karte_id: k.id };
        if (name) payload.name = name;
        if (!isNaN(gebuehr)) payload.monatliche_gebuehr = gebuehr;
        if (start) payload.start_datum = start;
        // Leerer String loescht ein zuvor gesetztes Enddatum (siehe
        // coordinator.py::async_edit_ladekarte()) -- end ist hier bewusst
        // IMMER gesetzt (auch als ""), nicht nur wenn truthy.
        payload.end_datum = end;
        this._call("edit_ladekarte", payload);
        form.classList.add("hidden");
      });
      row.querySelector(".lk-delete").addEventListener("click", () => {
        form.classList.add("hidden");
        delConfirm.classList.toggle("hidden");
      });
      row.querySelector(".lkd-cancel").addEventListener("click", () => delConfirm.classList.add("hidden"));
      row.querySelector(".lkd-confirm").addEventListener("click", () => {
        this._call("delete_ladekarte", { karte_id: k.id });
        delConfirm.classList.add("hidden");
      });
      // Preisstufen: neue hinzufuegen (z.B. Ende eines Einfuehrungspreises)
      // oder eine bereits vorhandene (ausser der fruehesten, siehe
      // coordinator.py::async_delete_ladekarte_preisstufe()) entfernen.
      const stufeToggle = row.querySelector(".lk-stufe-toggle");
      const stufeAbInput = row.querySelector(".lks-ab");
      const stufeGebuehrInput = row.querySelector(".lks-gebuehr");
      const stufeSaveBtn = row.querySelector(".lks-save");
      const stufeUpdateValidity = () => {
        const gebuehr = parseFloat(stufeGebuehrInput.value.replace(",", "."));
        stufeSaveBtn.disabled = !stufeAbInput.value || isNaN(gebuehr);
      };
      stufeAbInput.addEventListener("input", stufeUpdateValidity);
      stufeGebuehrInput.addEventListener("input", stufeUpdateValidity);
      stufeToggle.addEventListener("click", () => {
        form.classList.add("hidden");
        const opening = stufeForm.classList.contains("hidden");
        stufeForm.classList.toggle("hidden");
        if (opening) {
          stufeAbInput.value = "";
          stufeGebuehrInput.value = "";
          stufeUpdateValidity();
        }
      });
      row.querySelector(".lks-cancel").addEventListener("click", () => stufeForm.classList.add("hidden"));
      stufeSaveBtn.addEventListener("click", () => {
        const gebuehr = parseFloat(stufeGebuehrInput.value.replace(",", "."));
        if (!stufeAbInput.value || isNaN(gebuehr)) return;
        this._call("add_ladekarte_preisstufe", { karte_id: k.id, gebuehr, ab_datum: stufeAbInput.value });
        stufeForm.classList.add("hidden");
      });
      row.querySelectorAll(".lk-stufe-delete").forEach((btn) => {
        btn.addEventListener("click", () => {
          const ab = btn.closest(".lk-stufe").dataset.ab;
          this._call("delete_ladekarte_preisstufe", { karte_id: k.id, ab_datum: ab });
        });
      });
      list.appendChild(row);
    });
  }

  // --- Tab: Wartung -------------------------------------------------------------

  _wartungPresets() {
    const eid = this._eid("wartung_faellig");
    const s = eid && this._hass ? this._hass.states[eid] : null;
    return (s && Array.isArray((s.attributes || {}).presets)) ? s.attributes.presets : [];
  }

  // Welche Feldgruppen eine Vorlage zeigt (siehe const.py::WARTUNG_PRESETS) --
  // HU/TÜV braucht kein km-/letzter-Service-/Kosten-Feld, Inspektion kein
  // festes Datum. "eigene" (kein Preset bzw. unbekannter Key) zeigt alles.
  // "pflicht" (nur HU) verschaerft die generische "mind. ein Kriterium"-Regel
  // auf "ALLE genannten Felder noetig" -- siehe updateValidity() in
  // _wireWartungAddForm().
  _wartungFeldSchema(presetKey) {
    const schema = {
      tuev: { sichtbar: ["fest", "zeit", "reminder-zeit"], pflicht: ["fest", "zeit"] },
      inspektion: {
        sichtbar: ["km", "zeit", "lastservice", "reminder-zeit", "reminder-km", "kosten"], pflicht: null,
      },
    };
    return schema[presetKey] || {
      sichtbar: ["km", "zeit", "fest", "lastservice", "reminder-zeit", "reminder-km", "kosten"], pflicht: null,
    };
  }

  // "YYYY-MM" (<input type="month">) -> ISO-Datum des LETZTEN Tages dieses
  // Monats. HU/TÜV ist "faellig bis Ende des Monats" -- engine.wartung_status()
  // nimmt festes_datum unveraendert als exakten Stichtag, daher muss hier
  // der MonatsLETZTE gespeichert werden, sonst waere der Punkt ab dem 1. des
  // Monats faelschlich schon ueberfaellig. new Date(jahr, monat, 0) liefert
  // den letzten Tag des VORHERIGEN Monatsindex, also genau den gesuchten.
  _wartungMonthToDate(monthStr) {
    if (!monthStr) return "";
    const [jahr, monat] = monthStr.split("-").map(Number);
    const letzterTag = new Date(jahr, monat, 0).getDate();
    return `${monthStr}-${String(letzterTag).padStart(2, "0")}`;
  }

  // ISO-Datum -> "YYYY-MM" fuers <input type="month">. Funktioniert
  // unveraendert auch fuer Alt-Eintraege mit vollem Tages-Datum (einfaches
  // Abschneiden) -- keine Migration noetig, siehe CHANGELOG.
  _wartungDateToMonth(iso) {
    return iso ? iso.substring(0, 7) : "";
  }

  _buildWartung() {
    const wrap = document.createElement("div");
    wrap.className = "tab-wrap";
    wrap.innerHTML = `
      <div class="card">
        <div class="card-head">
          <span class="ic"><ha-icon icon="mdi:wrench-clock"></ha-icon></span><h2>Wartung</h2>
          <button class="btn btn-ghost wt-add-toggle" style="margin-left:auto">
            <ha-icon icon="mdi:plus" style="--mdc-icon-size:14px;vertical-align:-2px"></ha-icon> Wartungspunkt anlegen
          </button>
        </div>
        <div class="hist-edit-form grouped hidden" id="wt-add-form">
          <div class="wt-group">
            <label>Vorlage (optional)<select class="wt-preset"><option value="">— eigene —</option></select></label>
            <label>Name<input type="text" class="wt-name" placeholder="z.B. Inspektion"></label>
          </div>
          <div class="dim wt-group-hint">Vorlage füllt die Felder unten vor — danach frei überschreibbar.</div>
          <div class="wt-group wt-group-faelligkeit">
            <div class="sub-head wt-group-title">Fälligkeit</div>
            <div class="dim wt-group-hint wt-faelligkeit-hint">Mindestens ein Kriterium angeben. Bei mehreren gilt, was zuerst eintritt.</div>
            <div class="wt-fld-km"><label>Kilometer-Intervall (optional)<input type="text" inputmode="decimal" class="wt-km-intervall" placeholder="z.B. 30000"></label></div>
            <div class="wt-fld-zeit"><label>Intervall (Monate, optional)<input type="text" inputmode="decimal" class="wt-zeit-intervall" placeholder="z.B. 24"></label></div>
            <div class="wt-fld-fest"><label>Festes Fälligkeitsdatum (optional)<input type="month" class="wt-festes-datum"></label></div>
          </div>
          <div class="wt-group wt-fld-lastservice">
            <div class="sub-head wt-group-title">Letzter Service (optional)</div>
            <label>Kilometerstand<input type="text" inputmode="decimal" class="wt-last-km" placeholder="optional"></label>
            <label>Datum<input type="date" class="wt-last-datum"></label>
          </div>
          <div class="wt-group">
            <div class="sub-head wt-group-title">Erinnerung (optional, sonst globaler Standard)</div>
            <div class="wt-fld-reminder-zeit"><label>Vorwarnzeit (Monate)<input type="text" inputmode="decimal" class="wt-reminder-monate" placeholder="Standard"></label></div>
            <div class="wt-fld-reminder-km"><label>Vorwarnzeit (km)<input type="text" inputmode="decimal" class="wt-reminder-km" placeholder="Standard"></label></div>
          </div>
          <div class="wt-fld-kosten"><label>Kosten € (optional)<input type="text" inputmode="decimal" class="wt-kosten" placeholder="0,00"></label></div>
          <div class="wt-group wt-group-actions">
            <button class="btn btn-primary wt-save" disabled>Speichern</button>
            <button class="btn btn-ghost wt-cancel">Abbrechen</button>
          </div>
        </div>
        <div class="profil-empty" id="wt-empty">
          Noch kein Wartungspunkt angelegt — z.B. HU oder Inspektion, fällig nach
          Kilometerstand, Zeit oder beidem ("je nachdem was zuerst kommt").
        </div>
        <div class="hidden" id="wt-content">
          <div class="hist-list" id="wt-list"></div>
        </div>
      </div>`;

    const q = (s) => wrap.querySelector(s);
    this._r.wtEmpty = q("#wt-empty");
    this._r.wtContent = q("#wt-content");
    this._r.wtList = q("#wt-list");
    this._r.wtPresetSelect = q(".wt-preset");

    this._wireWartungAddForm(wrap);
    return wrap;
  }

  _wireWartungAddForm(container) {
    const toggle = container.querySelector(".wt-add-toggle");
    const form = container.querySelector("#wt-add-form");
    if (!toggle || !form) return;
    const presetSelect = form.querySelector(".wt-preset");
    const nameInput = form.querySelector(".wt-name");
    const kmInput = form.querySelector(".wt-km-intervall");
    const zeitInput = form.querySelector(".wt-zeit-intervall");
    const festInput = form.querySelector(".wt-festes-datum");
    const kostenInput = form.querySelector(".wt-kosten");
    const lastKmInput = form.querySelector(".wt-last-km");
    const lastDatumInput = form.querySelector(".wt-last-datum");
    const reminderMonateInput = form.querySelector(".wt-reminder-monate");
    const reminderKmInput = form.querySelector(".wt-reminder-km");
    const saveBtn = form.querySelector(".wt-save");
    const cancelBtn = form.querySelector(".wt-cancel");
    const faelligkeitHint = form.querySelector(".wt-faelligkeit-hint");
    const fieldWraps = {
      km: form.querySelector(".wt-fld-km"),
      zeit: form.querySelector(".wt-fld-zeit"),
      fest: form.querySelector(".wt-fld-fest"),
      lastservice: form.querySelector(".wt-fld-lastservice"),
      "reminder-zeit": form.querySelector(".wt-fld-reminder-zeit"),
      "reminder-km": form.querySelector(".wt-fld-reminder-km"),
      kosten: form.querySelector(".wt-fld-kosten"),
    };
    const STANDARD_HINT = "Mindestens ein Kriterium angeben. Bei mehreren gilt, was zuerst eintritt.";
    const HU_HINT = "Festes Fälligkeitsdatum und Intervall sind für HU beide Pflicht.";

    // Bei HU/TÜV (schema.pflicht gesetzt) muessen ALLE genannten Felder
    // gefuellt sein statt nur irgendeines -- strenger als die generische
    // "mind. ein Kriterium"-Regel der anderen Vorlagen/"eigene".
    const updateValidity = () => {
      const schema = this._wartungFeldSchema(presetSelect.value);
      const werte = { fest: !!festInput.value, zeit: !!zeitInput.value.trim(), km: !!kmInput.value.trim() };
      const hatKriterium = schema.pflicht
        ? schema.pflicht.every((feld) => werte[feld])
        : werte.km || werte.zeit || werte.fest;
      saveBtn.disabled = !nameInput.value.trim() || !hatKriterium;
    };
    [nameInput, kmInput, zeitInput].forEach((el) => el.addEventListener("input", updateValidity));
    festInput.addEventListener("change", updateValidity);

    // Blendet Feldgruppen passend zur gewaehlten Vorlage ein/aus (siehe
    // _wartungFeldSchema()) und leert dabei ausgeblendete Felder -- sonst
    // wuerde ein beim vorherigen Preset befuellter, jetzt unsichtbarer Wert
    // beim Speichern still mitgeschickt. Bei HU/TÜV steht das feste Datum
    // per CSS-order VOR dem Intervall (sonst identische Feldreihenfolge wie
    // bei Inspektion/"eigene" -- siehe .hu-mode .wt-fld-fest).
    const applyFieldVisibility = (presetKey) => {
      const schema = this._wartungFeldSchema(presetKey);
      const sichtbar = new Set(schema.sichtbar);
      for (const [key, el] of Object.entries(fieldWraps)) {
        if (!el) continue;
        const zeigen = sichtbar.has(key);
        el.classList.toggle("hidden", !zeigen);
        if (!zeigen) el.querySelectorAll("input").forEach((inp) => { inp.value = ""; });
      }
      form.querySelector(".wt-group-faelligkeit").classList.toggle("hu-mode", presetKey === "tuev");
      if (faelligkeitHint) faelligkeitHint.textContent = presetKey === "tuev" ? HU_HINT : STANDARD_HINT;
    };

    // Vorlage befuellt nur LEERE Felder -- bleibt danach frei ueberschreibbar
    // (siehe const.py::WARTUNG_PRESETS-Docstring, "Presets sind nur Startwerte").
    presetSelect.addEventListener("change", () => {
      applyFieldVisibility(presetSelect.value);
      const preset = this._wartungPresets().find((p) => p.key === presetSelect.value);
      if (preset) {
        if (!nameInput.value.trim()) nameInput.value = preset.name || "";
        if (!kmInput.value.trim() && preset.km_intervall != null) kmInput.value = preset.km_intervall;
        if (!zeitInput.value.trim() && preset.zeit_intervall_monate != null) zeitInput.value = preset.zeit_intervall_monate;
      }
      updateValidity();
    });

    toggle.addEventListener("click", () => {
      const opening = form.classList.contains("hidden");
      form.classList.toggle("hidden");
      if (opening) {
        presetSelect.value = "";
        nameInput.value = "";
        kmInput.value = "";
        zeitInput.value = "";
        festInput.value = "";
        kostenInput.value = "";
        lastKmInput.value = "";
        lastDatumInput.value = "";
        reminderMonateInput.value = "";
        reminderKmInput.value = "";
        applyFieldVisibility("");
        updateValidity();
      }
    });
    cancelBtn.addEventListener("click", () => form.classList.add("hidden"));
    saveBtn.addEventListener("click", () => {
      const name = nameInput.value.trim();
      const km = parseFloat(kmInput.value.replace(",", "."));
      const zeit = parseInt(zeitInput.value, 10);
      if (!name || (isNaN(km) && isNaN(zeit) && !festInput.value)) return;
      const payload = { name };
      // Muss mitgeschickt werden, damit der Backend-Punkt den "typ"-Marker
      // bekommt (siehe coordinator.py::async_add_maintenance()) -- ohne
      // diese Zeile wuerde die Vorlagenwahl nur lokal die Felder vorbefuellen,
      // aber nie am gespeicherten Punkt ankommen (typ waere immer null).
      if (presetSelect.value) payload.preset = presetSelect.value;
      if (!isNaN(km)) payload.km_intervall = km;
      if (!isNaN(zeit)) payload.zeit_intervall_monate = zeit;
      if (festInput.value) payload.festes_datum = this._wartungMonthToDate(festInput.value);
      const kosten = parseFloat(kostenInput.value.replace(",", "."));
      if (!isNaN(kosten)) payload.kosten = kosten;
      const lastKm = parseFloat(lastKmInput.value.replace(",", "."));
      if (!isNaN(lastKm)) payload.last_done_km = lastKm;
      if (lastDatumInput.value) payload.last_done_datum = lastDatumInput.value;
      const reminderMonate = parseFloat(reminderMonateInput.value.replace(",", "."));
      if (!isNaN(reminderMonate)) payload.reminder_monate = reminderMonate;
      const reminderKm = parseFloat(reminderKmInput.value.replace(",", "."));
      if (!isNaN(reminderKm)) payload.reminder_km = reminderKm;
      this._call("add_maintenance", payload);
      form.classList.add("hidden");
    });
  }

  _renderWartungPresetOptions() {
    const select = this._r.wtPresetSelect;
    if (!select) return;
    const presets = this._wartungPresets();
    const sig = presets.map((p) => p.key).join(",");
    if (sig === this._wtPresetSig) return;
    this._wtPresetSig = sig;
    select.innerHTML = `<option value="">— eigene —</option>`
      + presets.map((p) => `<option value="${p.key}">${p.name}</option>`).join("");
  }

  _updateWartung() {
    const r = this._r;
    if (!r.wtContent) return;
    this._renderWartungPresetOptions();
    const eid = this._eid("wartung_faellig");
    const state = eid ? this._hass.states[eid] : null;
    const punkte = (state && Array.isArray((state.attributes || {}).punkte)) ? state.attributes.punkte : [];
    const hasPunkte = punkte.length > 0;
    r.wtEmpty.classList.toggle("hidden", hasPunkte);
    r.wtContent.classList.toggle("hidden", !hasPunkte);
    if (!hasPunkte) return;
    this._renderWartungList(punkte);
  }

  _renderWartungList(punkte) {
    const list = this._r.wtList;
    if (!list) return;
    const sig = punkte.map((p) =>
      `${p.id}:${p.name}:${p.km_intervall}:${p.zeit_intervall_monate}:${p.festes_datum}:`
      + `${JSON.stringify(p.last_done)}:${p.kosten}:${p.aktiv}:${p.reminder_tage}:${p.reminder_km}`
    ).join("|");
    if (sig === this._wtSig && list.dataset.built === "1") return;
    this._wtSig = sig;
    list.dataset.built = "1";
    list.innerHTML = "";
    const STATUS_LABELS = { ok: "OK", bald_faellig: "Bald fällig", ueberfaellig: "Überfällig", unbekannt: "Unbekannt" };
    const STATUS_COLORS = { ok: "#4ade80", bald_faellig: "#f97316", ueberfaellig: "#ef4444", unbekannt: "var(--ink-dim)" };
    const fmtDate = (iso) => {
      if (!iso) return "—";
      const d = new Date(iso);
      return isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-DE");
    };
    // Festes Fälligkeitsdatum wird nur noch monatsgenau erfasst (siehe
    // _wartungMonthToDate()) -- der exakte Tag (immer Monatsletzter bei
    // neu gespeicherten Werten) ist fuer die Anzeige nicht aussagekraeftig.
    const fmtMonthYear = (iso) => {
      if (!iso) return "—";
      const d = new Date(iso);
      return isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-DE", { month: "2-digit", year: "numeric" });
    };
    punkte.forEach((p) => {
      const row = document.createElement("div");
      row.className = "hist-card";
      const color = STATUS_COLORS[p.status] || STATUS_COLORS.unbekannt;
      const label = STATUS_LABELS[p.status] || p.status;
      // Das FRUEHERE (bereits von engine.wartung_status() ermittelte) Kriterium
      // fuehrt die Anzeige an. rest_km bleibt laut engine.wartung_status() auch
      // erhalten, wenn ein ANDERES Kriterium gewinnt -- dann als eigene
      // "noch X km bis Y km"-Zusatzzeile mit Zielwert (last_done.km +
      // km_intervall). Nur wenn rest_km die EINZIGE bekannte Groesse ist
      // (kein rest_tage, z.B. km_pro_tag unbekannt), wird es stattdessen zur
      // Primaerzeile -- sonst waere die Zusatzzeile ein reines Duplikat.
      let primaryText = null;
      if (p.rest_tage != null) {
        primaryText = `zuerst fällig: ${p.rest_tage >= 0 ? "in" : "vor"} ${Math.abs(p.rest_tage)} Tag(en)`;
        if (p.faellig_datum) {
          primaryText += ` (${p.naechste_quelle === "fest" ? fmtMonthYear(p.faellig_datum) : fmtDate(p.faellig_datum)})`;
        }
      } else if (p.rest_km != null) {
        primaryText = `zuerst fällig: ${p.rest_km >= 0 ? "in" : "vor"} ${this._fmtNum(Math.abs(p.rest_km), 0)} km`;
      }
      let secondaryKmText = null;
      if (p.rest_tage != null && p.rest_km != null) {
        const zielKm = (p.last_done && p.last_done.km != null && p.km_intervall)
          ? p.last_done.km + p.km_intervall : null;
        const abs = this._fmtNum(Math.abs(p.rest_km), 0);
        secondaryKmText = p.rest_km >= 0
          ? `noch ${abs} km` + (zielKm != null ? ` bis ${this._fmtNum(zielKm, 0)} km` : "")
          : `${abs} km über` + (zielKm != null ? ` ${this._fmtNum(zielKm, 0)} km` : " Fälligkeit");
      }
      const statusLine = [label];
      if (p.status !== "unbekannt") {
        if (primaryText) statusLine.push(primaryText);
        if (secondaryKmText) statusLine.push(secondaryKmText);
      }
      const kriterien = [];
      if (p.km_intervall) kriterien.push(`alle ${this._fmtNum(p.km_intervall, 0)} km`);
      if (p.zeit_intervall_monate) kriterien.push(`alle ${p.zeit_intervall_monate} Monate`);
      if (p.festes_datum) kriterien.push(`fest: ${fmtMonthYear(p.festes_datum)}`);
      const lastDoneParts = [];
      if (p.last_done && p.last_done.km != null) lastDoneParts.push(`${this._fmtNum(p.last_done.km, 0)} km`);
      if (p.last_done && p.last_done.datum) lastDoneParts.push(fmtDate(p.last_done.datum));
      row.innerHTML = `
        <div class="hist-top">
          <span class="hist-date">
            <span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${color};margin-right:6px"></span>
            ${p.name}${p.aktiv === false ? ` <span class="hist-meta">· pausiert</span>` : ""}
          </span>
          <div class="hist-actions">
            <button class="btn-icon sm wt-done" title="Als erledigt markieren"><ha-icon icon="mdi:check"></ha-icon></button>
            <button class="btn-icon sm wt-edit" title="Bearbeiten"><ha-icon icon="mdi:pencil"></ha-icon></button>
            <button class="btn-icon sm wt-delete" title="Löschen"><ha-icon icon="mdi:delete"></ha-icon></button>
          </div>
        </div>
        <div class="hist-figures">
          <div class="hist-figures-left">
            <span class="hist-price" style="color:${color}">${statusLine.join(" · ")}</span>
            <span class="hist-fee">${kriterien.join(" · ") || "kein Kriterium"}</span>
            <span class="hist-fee">Letzter Service: ${lastDoneParts.join(" · ") || "—"}</span>
          </div>
          ${p.kosten != null ? `<span class="hist-cost">${this._fmtNum(p.kosten, 2)} €</span>` : ""}
        </div>
        <div class="hist-edit-form grouped hidden">
          <div class="wt-group">
            <label>Name<input type="text" class="wte-name" value="${p.name}"></label>
            <label><input type="checkbox" class="wte-aktiv" ${p.aktiv !== false ? "checked" : ""}> Aktiv</label>
          </div>
          <div class="wt-group">
            <div class="sub-head wt-group-title">Fälligkeit</div>
            <div class="dim wt-group-hint">Mindestens ein Kriterium angeben. Bei mehreren gilt, was zuerst eintritt.</div>
            ${p.typ !== "tuev" ? `<label>Kilometer-Intervall (leer = kein Kriterium)<input type="text" inputmode="decimal" class="wte-km" value="${p.km_intervall ?? ""}"></label>` : ""}
            <label>Intervall in Monaten (leer = kein Kriterium)<input type="text" inputmode="decimal" class="wte-zeit" value="${p.zeit_intervall_monate ?? ""}"></label>
            <label>Festes Fälligkeitsdatum (leer = kein Kriterium)<input type="month" class="wte-fest" value="${this._wartungDateToMonth(p.festes_datum)}"></label>
          </div>
          <div class="wt-group">
            <div class="sub-head wt-group-title">Letzter Service</div>
            <label>Kilometerstand<input type="text" inputmode="decimal" class="wte-last-km" value="${(p.last_done && p.last_done.km != null) ? p.last_done.km : ""}"></label>
            <label>Datum<input type="date" class="wte-last-datum" value="${(p.last_done && p.last_done.datum) ? p.last_done.datum : ""}"></label>
          </div>
          <div class="wt-group">
            <div class="sub-head wt-group-title">Erinnerung (leer = globaler Standard)</div>
            <label>Vorwarnzeit (Monate)<input type="text" inputmode="decimal" class="wte-reminder-monate" value="${p.reminder_tage != null ? Math.round((p.reminder_tage / 30.44) * 10) / 10 : ""}"></label>
            <label>Vorwarnzeit (km)<input type="text" inputmode="decimal" class="wte-reminder-km" value="${p.reminder_km ?? ""}"></label>
          </div>
          <div class="wt-group">
            <label>Kosten €<input type="text" inputmode="decimal" class="wte-kosten" value="${p.kosten ?? ""}"></label>
          </div>
          <div class="wt-group wt-group-actions">
            <button class="btn btn-primary wte-save">Speichern</button>
            <button class="btn btn-ghost wte-cancel">Abbrechen</button>
          </div>
        </div>
        <div class="hist-delete-confirm hidden">
          <span class="hist-delete-text">Diesen Wartungspunkt dauerhaft löschen?</span>
          <button class="btn btn-danger wtd-confirm">Löschen</button>
          <button class="btn btn-ghost wtd-cancel">Abbrechen</button>
        </div>`;
      const form = row.querySelector(".hist-edit-form");
      const delConfirm = row.querySelector(".hist-delete-confirm");
      const wteKm = row.querySelector(".wte-km");
      const wteZeit = row.querySelector(".wte-zeit");
      const wteFest = row.querySelector(".wte-fest");
      const wteSave = row.querySelector(".wte-save");
      // Server lehnt das Entfernen des letzten Kriteriums ohnehin ab
      // (async_edit_maintenance()), aber ohne clientseitige Sperre wuerde
      // ein Klick auf Speichern dabei stillschweigend nichts tun.
      const updateEditValidity = () => {
        wteSave.disabled = !(wteKm?.value.trim()) && !wteZeit.value.trim() && !wteFest.value;
      };
      [wteKm, wteZeit].forEach((el) => el?.addEventListener("input", updateEditValidity));
      wteFest.addEventListener("change", updateEditValidity);
      updateEditValidity();
      row.querySelector(".wt-done").addEventListener("click", () => {
        this._call("mark_maintenance_done", { wartung_id: p.id });
      });
      row.querySelector(".wt-edit").addEventListener("click", () => {
        delConfirm.classList.add("hidden");
        form.classList.toggle("hidden");
      });
      row.querySelector(".wte-cancel").addEventListener("click", () => form.classList.add("hidden"));
      row.querySelector(".wte-save").addEventListener("click", () => {
        const payload = { wartung_id: p.id };
        const name = row.querySelector(".wte-name").value.trim();
        if (name) payload.name = name;
        // Kein wte-km bei HU-Punkten (siehe Template oben) -- Feld dann
        // komplett aus dem Payload weglassen statt "" zu senden: ""
        // loescht das Kriterium serverseitig explizit (async_edit_maintenance()),
        // ein fehlender Key laesst den gespeicherten Wert dagegen unangetastet.
        if (wteKm) {
          const kmVal = wteKm.value.trim();
          if (kmVal === "") {
            payload.km_intervall = "";
          } else {
            const v = parseFloat(kmVal.replace(",", "."));
            if (!isNaN(v)) payload.km_intervall = v;
          }
        }
        const zeitVal = row.querySelector(".wte-zeit").value.trim();
        if (zeitVal === "") {
          payload.zeit_intervall_monate = "";
        } else {
          const v = parseInt(zeitVal, 10);
          if (!isNaN(v)) payload.zeit_intervall_monate = v;
        }
        const wteFestVal = row.querySelector(".wte-fest").value;
        payload.festes_datum = wteFestVal ? this._wartungMonthToDate(wteFestVal) : "";
        const kostenVal = row.querySelector(".wte-kosten").value.trim();
        if (kostenVal === "") {
          payload.kosten = "";
        } else {
          const v = parseFloat(kostenVal.replace(",", "."));
          if (!isNaN(v)) payload.kosten = v;
        }
        const lastKmVal = row.querySelector(".wte-last-km").value.trim();
        if (lastKmVal !== "") {
          const v = parseFloat(lastKmVal.replace(",", "."));
          if (!isNaN(v)) payload.last_done_km = v;
        }
        const lastDatumVal = row.querySelector(".wte-last-datum").value;
        if (lastDatumVal) payload.last_done_datum = lastDatumVal;
        const reminderMonateVal = row.querySelector(".wte-reminder-monate").value.trim();
        if (reminderMonateVal === "") {
          payload.reminder_monate = "";
        } else {
          const v = parseFloat(reminderMonateVal.replace(",", "."));
          if (!isNaN(v)) payload.reminder_monate = v;
        }
        const reminderKmVal = row.querySelector(".wte-reminder-km").value.trim();
        if (reminderKmVal === "") {
          payload.reminder_km = "";
        } else {
          const v = parseFloat(reminderKmVal.replace(",", "."));
          if (!isNaN(v)) payload.reminder_km = v;
        }
        payload.aktiv = row.querySelector(".wte-aktiv").checked;
        this._call("edit_maintenance", payload);
        form.classList.add("hidden");
      });
      row.querySelector(".wt-delete").addEventListener("click", () => {
        form.classList.add("hidden");
        delConfirm.classList.toggle("hidden");
      });
      row.querySelector(".wtd-cancel").addEventListener("click", () => delConfirm.classList.add("hidden"));
      row.querySelector(".wtd-confirm").addEventListener("click", () => {
        this._call("delete_maintenance", { wartung_id: p.id });
        delConfirm.classList.add("hidden");
      });
      list.appendChild(row);
    });
  }

  // --- Update loop ------------------------------------------------------------

  _update() {
    if (!this._built || !this._hass) return;
    if (this._view === "uebersicht_beta") this._updateUebersichtBeta();
    else if (this._view === "fahrzeuge") this._updateVehicle();
    else if (this._view === "profil") this._updateProfil();
    else if (this._view === "analyse") this._updateAnalyse();
    else if (this._view === "leasing") this._updateLeasing();
    else if (this._view === "ladekarten") this._updateLadekarten();
    else if (this._view === "wartung") this._updateWartung();
  }

  // --- Update: Fahrzeuge (unchanged) ------------------------------------------

  _updateVehicle() {
    const r = this._r;
    // Modus-neutraler Guard (statt vhExtKwhTotal, siehe _fillVehicleContent()):
    // die Heim- bzw. Fremdladung-Karte kann je Lade-Modus fehlen, die
    // Haupt-Fahrzeugkarte (u.a. vh-odo) dagegen immer.
    if (!r.vhOdo) return;

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
    // auftauchen, ohne bei jedem hass-Update (praktisch dauernd) nachzufragen. Ohne
    // Heimladen-Karte (siehe _fillVehicleContent()) gibt es nichts zu befuellen.
    if (r.histHomeList) {
      if (this._homeSessions === null || Date.now() - this._homeSessionsFetchedAt > 300000) {
        this._fetchHomeSessions();
      } else {
        this._renderHomeHistory();
      }
    }

    if (r.vhExtKwhTotal) {
      r.vhExtKwhTotal.textContent  = this._num("total_kwh", 1);
      r.vhExtCostTotal.textContent = this._num("total_cost", 2);
      r.vhExtCount.textContent     = this._num("count", 0);
      r.vhExtKwhLast.textContent   = this._num("last_kwh", 2);
      r.vhExtCostLast.textContent  = this._num("last_cost", 2);
      r.vhExtPriceLast.textContent = this._num("last_price", 4);
      r.vhExtDurLast.textContent   = this._duration("last_duration");
    }
    if (r.vhHomeKwh) {
      r.vhHomeKwh.textContent      = this._num("home_kwh", 1);
      r.vhHomeCost.textContent     = this._num("home_cost", 2);
    }
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
    r.vhKwhDay.textContent       = this._num("kwh_day", 1);
    r.vhKwhWeek.textContent      = this._num("kwh_week", 1);
    r.vhKwhMonth.textContent     = this._num("kwh_month", 1);
    r.vhKwhYear.textContent      = this._num("kwh_year", 1);
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

  // --- Ladekarten-Helfer (siehe coordinator.py::ladekarten_stats()) ------------
  // Genutzt vom neuen "Ladekarten"-Tab UND von den Erfassen-/Bearbeiten-
  // Formularen der Fremdladung-Historie (Karte optional zuordnen).

  _ladekartenList() {
    const eid = this._eid("ladekarten_kosten");
    const s = eid && this._hass ? this._hass.states[eid] : null;
    return (s && Array.isArray((s.attributes || {}).karten)) ? s.attributes.karten : [];
  }

  _karteName(karteId) {
    if (karteId == null) return null;
    const karte = this._ladekartenList().find((k) => k.id === karteId);
    return karte ? karte.name : null;
  }

  // "— keine —" plus eine Option je Karte, die uebergebene selectedId
  // vorausgewaehlt -- fuer die karte-<select> in beiden Fremdladung-
  // Formularen (manuell erfassen / bearbeiten).
  _karteOptionsHtml(selectedId) {
    const opts = [`<option value="">— keine —</option>`];
    this._ladekartenList().forEach((k) => {
      const sel = k.id === selectedId ? " selected" : "";
      opts.push(`<option value="${k.id}"${sel}>${k.name}</option>`);
    });
    return opts.join("");
  }

  // --- Anbieter-Helfer (siehe coordinator.py::charging_location_stats()) -
  // WO geladen wurde (Ladenetz-/Betreibername) -- NICHT zu verwechseln
  // mit den Ladekarten-Helfern oben (WOMIT bezahlt wurde). Freitext ohne
  // festen Katalog, daher nur eine Vorschlagsliste (<datalist>) statt
  // eines <select>, siehe _anbieterDatalistHtml().

  _bekannteAnbieter() {
    const eid = this._eid("charging_location_breakdown");
    const s = eid && this._hass ? this._hass.states[eid] : null;
    const list = s && Array.isArray((s.attributes || {}).bekannte_anbieter) ? s.attributes.bekannte_anbieter : [];
    return list;
  }

  // <option>-Liste der bereits verwendeten Anbieter, fuer die kombinierten
  // Freitext-Inputs (list="...") in Erfassen-/Bearbeiten-/Bestaetigen-
  // Formularen -- Auswahl fuellt das Feld, freie Eingabe bleibt moeglich.
  _anbieterOptionsHtml() {
    return this._bekannteAnbieter().map((name) => `<option value="${name}"></option>`).join("");
  }

  // Fertiges <datalist>-Element fuer einmalig aus Template-Strings
  // gebaute Bereiche (Historie-Zeilen, offene Fremdladungen) -- dort wird
  // ohnehin bei jedem Rebuild neu gerendert, ein statisches <datalist> mit
  // spaeter befuellten Optionen (wie im Manuell-Formular) waere unnoetig.
  _anbieterDatalistHtml(id) {
    return `<datalist id="${id}">${this._anbieterOptionsHtml()}</datalist>`;
  }

  _renderPendingCharges(items, el = this._r.estExtItem) {
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
        kwh: p.energy_kwh != null ? Number(p.energy_kwh).toFixed(2) : "", price: "", fee: "", blockFee: "", timeFee: "", anbieter: "",
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
          <label>Anbieter (optional)<input type="text" class="pf-anbieter" list="pf-anbieter-list-${key}" value="${st.anbieter}" placeholder="z.B. EnBW"></label>
          ${this._anbieterDatalistHtml(`pf-anbieter-list-${key}`)}
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
      const anbieterInput = row.querySelector(".pf-anbieter");
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
      anbieterInput.addEventListener("input", (e) => { st.anbieter = e.target.value; });
      confirmBtn.addEventListener("click", () => {
        const kwh = parseFloat(st.kwh), price = parseFloat(st.price);
        if (isNaN(kwh) || isNaN(price)) return;
        const fee = parseFloat(st.fee);
        const blockFee = parseFloat(st.blockFee);
        const timeFee = parseFloat(st.timeFee);
        const payload = {
          kwh, price_kwh: price, start_ts: key,
          start_fee: isNaN(fee) ? 0 : fee, block_fee: isNaN(blockFee) ? 0 : blockFee,
          time_fee: isNaN(timeFee) ? 0 : timeFee,
        };
        if (st.anbieter && st.anbieter.trim()) payload.anbieter = st.anbieter.trim();
        this._call("log_charge", payload);
        delete fs[key];
      });
      row.querySelector(".pf-discard").addEventListener("click", () => {
        this._call("discard_pending", { start_ts: key });
        delete fs[key];
      });
      el.appendChild(row);
    });
  }

  _renderPendingTrips(items, el = this._r.estTripItem) {
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
    const karten = this._ladekartenList();
    const hasKarten = karten.length > 0;
    const bekannteAnbieter = this._bekannteAnbieter();
    // Ladekarten-/Anbieter-Liste im Signatur-String, damit eine neu
    // angelegte/gelöschte Karte bzw. ein neuer Anbieter die (sonst nur an
    // erfasst_ts geknüpfte) Render-Sperre durchbricht -- sonst würde ein
    // bereits offenes Bearbeiten-Formular nicht die aktuelle Karten-/
    // Anbieter-Vorschlagsliste zeigen.
    const sig = expanded + "|" + full.map((h) => h.erfasst_ts).join(",") + "|" + karten.map((k) => k.id).join(",")
      + "|" + bekannteAnbieter.join(",");
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
            ${this._karteName(h.karte_id) ? `<span class="hist-fee">🎫 ${this._karteName(h.karte_id)}</span>` : ""}
            ${h.anbieter ? `<span class="hist-fee">🏢 ${h.anbieter}</span>` : ""}
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
          <label>Ladeende (nicht Abstecken)<input type="datetime-local" class="hf-end-ts" value="${this._toDatetimeLocal(endTs)}"></label>
          <label>SoC Start (%)<input type="text" inputmode="decimal" class="hf-soc-start" value="${h.soc_start ?? ""}"></label>
          <label>SoC Ende (%)<input type="text" inputmode="decimal" class="hf-soc-end" value="${h.soc_end ?? ""}"></label>
          ${hasKarten ? `<label>Ladekarte<select class="hf-karte">${this._karteOptionsHtml(h.karte_id)}</select></label>` : ""}
          <label>Anbieter (optional)<input type="text" class="hf-anbieter" list="hf-anbieter-list-${ts}" value="${h.anbieter || ""}"></label>
          ${this._anbieterDatalistHtml(`hf-anbieter-list-${ts}`)}
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
        const karteSelect = row.querySelector(".hf-karte");
        if (karteSelect) {
          payload.karte_id = karteSelect.value === "" ? 0 : parseInt(karteSelect.value, 10);
        }
        payload.anbieter = row.querySelector(".hf-anbieter").value.trim();
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
    const entryId = this._configEntryId();
    if (!entryId || !this._hass || !this._hass.callWS) {
      // _homeSessions bleibt null (nicht []), damit ohne Dauerschleife erneut
      // versucht wird, sobald z. B. die Entity-Registry nachträglich verfügbar ist.
      this._homeSessionsFetching = false;
      this._renderHomeHistory();
      this._refreshBetaWallboxIfActive();
      return;
    }
    try {
      const res = await this._hass.callWS({ type: "ev_assistant/evcc_sessions", config_entry_id: entryId });
      this._homeSessions = Array.isArray(res && res.sessions) ? res.sessions : [];
    } catch (err) {
      this._homeSessions = [];
    } finally {
      this._homeSessionsFetching = false;
      this._renderHomeHistory();
      this._refreshBetaWallboxIfActive();
    }
  }

  // _fetchHomeSessions() ist ein WS-Abruf (keine reaktive hass.states-
  // Aktualisierung), der Vehicle-Tab-eigene Aufrufer oben stoesst dort nur
  // _renderHomeHistory() an -- die Wallbox-Karte im Uebersicht-Beta-Tab
  // (siehe _updateBetaWallbox()) braucht denselben "Fetch fertig"-Trigger,
  // unabhaengig davon, welcher Tab den Abruf ausgeloest hat.
  _refreshBetaWallboxIfActive() {
    if (this._view === "uebersicht_beta" && this._r.betaWallboxCard) this._updateBetaWallbox();
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

  // Reihen fuer "Ladeuebersicht"/"Kostenuebersicht" je Lade-Modus (siehe
  // _fillVehicleContent()/chargeLegend fuer die dazugehoerige Legende) --
  // die Bucket-Summenbildung selbst bleibt fuer beide Reihen unveraendert,
  // nur die tatsaechlich gezeichnete/gestapelte Reihe wird gefiltert.
  _chargeSeries() {
    const modus = this._ladeModus();
    if (modus === "nur_zuhause") return [{key: "home", color: "var(--c-home)"}];
    if (modus === "nur_auswaerts") return [{key: "ext", color: "var(--c-ext)"}];
    return [{key: "home", color: "var(--c-home)"}, {key: "ext", color: "var(--c-ext)"}];
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
    this._svgBarChart(this._r && this._r.overviewChart, buckets, this._chargeSeries());
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
    this._svgBarChart(this._r && this._r.kostenChart, buckets, this._chargeSeries(), {});
  }

  _renderChartSolar() {
    // Rein heim-basiert -- ohne Heimladen-Karte (siehe _fillVehicleContent(),
    // "nur_auswaerts") existiert #solar-chart gar nicht mehr; _svgBarChart()
    // wuerde das zwar ohnehin selbst abfangen (wrap === null), aber so bleibt
    // die Absicht hier explizit statt implizit ueber einen fremden Guard.
    if (this._ladeModus() === "nur_auswaerts") return;
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

  // --- Tab: Übersicht (Beta) ---------------------------------------------------
  //
  // Urspruenglich als paralleles Layout-Experiment ("Konzept A") neben dem
  // klassischen Übersicht-Tab eingefuehrt, zum Vergleich, bevor die alte
  // Seite abgeloest wird -- der klassische Tab wurde 2026-09-24 entfernt
  // (Code archiviert in dev/archive/legacy-overview-panel.js), dies ist
  // seitdem der einzige Übersicht-Tab. Verwendet ausschliesslich bereits
  // vorhandene Sensoren/Attribute, keine neue Rechenlogik. Status-/Ladeort-
  // Karten sind eigene, bewusst duplizierte Implementierungen statt aus
  // dem (inzwischen archivierten) klassischen Tab wiederverwendet, um
  // diesen bei seiner damaligen Entwicklung nicht anfassen zu muessen.

  // Baufunktion je EINZELKARTE, passend zum aktuellen Lademodus (siehe
  // const.py::PANEL_LAYOUT_KEYS fuer die gueltigen Schluessel). null fuer
  // eine Karte, die im aktuellen Modus gar nicht existiert (z.B. Wallbox
  // bei "nur_auswaerts") -- die wird in _buildUebersichtBeta()/
  // _openPanelLayoutModal() dann auch nicht als waehlbar angeboten.
  // Vormals feste 2-Spalten-Paare ("hero"/"bottom") sind hier bewusst in
  // ihre Einzelkarten aufgetrennt (Nutzerwunsch 2026-09-23: "ich wuerde das
  // panel gerne in grids aufteilen, so das der nutzer auch karten
  // nebeneinander anordnen kann"), damit jede Karte frei mit jeder anderen
  // kombinierbar ist -- auf Kosten des vorher ungleichen Spaltenverhaeltnisses
  // der Hero-Zeile (jetzt zwei gleichwertige Karten statt gross+klein).
  _panelSectionBuilders(modus) {
    return {
      hero_cost: () => this._buildBetaHeroCard(),
      // "nur_auswaerts" behaelt bewusst den bisherigen zweiten Hero-Slot
      // (letzte Fremdladung statt Fahrzeug-SoC, das dort strukturell nicht
      // zutrifft).
      hero_secondary: modus === "nur_auswaerts"
        ? () => this._buildBetaLastChargeCard()
        : () => this._buildBetaSocCard(),
      // Nur wo ueberhaupt eine eigene Wallbox relevant ist -- in
      // "nur_auswaerts" komplett weggelassen statt leer/mit Nur-Nullen
      // gerendert (siehe Kartenkopf-Kommentar dort).
      wallbox: modus !== "nur_auswaerts" ? () => this._buildBetaWallboxCard() : null,
      kpi: () => this._buildBetaKpiCard(),
      comparison: () => this._buildBetaComparisonBarsCard(),
      location: modus === "nur_auswaerts"
        ? () => this._buildBetaAcDcCard()
        : () => this._buildBetaLadeortBarsCard(),
      evcc_mode: () => this._buildBetaEvccModeCard(),
      evcc_plan: modus !== "nur_auswaerts" ? () => this._buildBetaEvccPlanCard() : null,
    };
  }

  // Default-Groesse je Karte, wenn der Nutzer noch keine eigene gewaehlt
  // hat (siehe _panelLayoutSize()) -- ergibt in etwa das bisherige, vor der
  // freien Anordenbarkeit gewohnte Bild (Karten paarweise nebeneinander),
  // ohne dass es eine harte Vorgabe waere.
  _panelLayoutDefaultSize(key) {
    return (key === "evcc_mode" || key === "evcc_plan") ? "full" : "half";
  }

  // Kombiniert die im aktuellen Modus verfuegbaren Sektions-Schluessel mit
  // der vom Nutzer gespeicherten Sichtbarkeit/Reihenfolge: gespeicherte, im
  // aktuellen Modus noch verfuegbare Schluessel zuerst (in ihrer
  // gespeicherten Reihenfolge, nur sichtbare), danach alle DEM NUTZER NOCH
  // UNBEKANNTEN Schluessel (z.B. neu in einer spaeteren Version) als
  // sichtbar angehaengt -- so verschwindet eine neue Karte nie einfach
  // kommentarlos, nur weil eine alte gespeicherte Einstellung sie noch
  // nicht kennt. `layout` wird als Parameter uebergeben statt hier selbst
  // per _panelLayout() geholt, da dessen einmalig konsumiertes
  // this._panelLayoutOverride (siehe dort) sonst bei einem zweiten Aufruf
  // im selben Ablauf (siehe _openPanelLayoutModal()) bereits verbraucht
  // waere.
  _panelLayoutOrder(available, layout) {
    const saved = layout.filter((e) => available.includes(e.key));
    const savedKeys = saved.map((e) => e.key);
    return [
      ...saved.filter((e) => e.visible).map((e) => e.key),
      ...available.filter((k) => !savedKeys.includes(k)),
    ];
  }

  // Wie _panelLayoutOrder(), aber fuer das "Panel anpassen"-Popup: dort
  // muessen auch AUSGEBLENDETE Karten in der Liste erscheinen (nur mit
  // leerem Haekchen), sonst kann man eine einmal ausgeblendete Karte nie
  // wieder einblenden (Nutzerfehler 2026-09-23: "sobald ich was abhake,
  // verschwindet es aus der liste. ich kann es auch nicht erneut...
  // auswaehlen"). _panelLayoutOrder() liess unsichtbare Karten absichtlich
  // weg (fuers eigentliche Panel-Grid korrekt), war hier aber die falsche
  // Wahl.
  _panelLayoutFullOrder(available, layout) {
    const saved = layout.filter((e) => available.includes(e.key));
    const savedKeys = saved.map((e) => e.key);
    return [...savedKeys, ...available.filter((k) => !savedKeys.includes(k))];
  }

  // Gespeicherte Groessenstufe fuer eine Karte (third/half/twothirds/full,
  // siehe const.py::PANEL_LAYOUT_SIZES), sonst _panelLayoutDefaultSize().
  _panelLayoutSize(key, layout) {
    const entry = layout.find((e) => e.key === key);
    return (entry && entry.size) || this._panelLayoutDefaultSize(key);
  }

  _buildUebersichtBeta() {
    const div = (cls) => { const d = document.createElement("div"); d.className = cls; return d; };
    const modus = this._ladeModus();
    const wrap = document.createElement("div");
    wrap.className = "tab-wrap";

    const pillRow = div("beta-pending-row");
    const chargePill = document.createElement("button");
    chargePill.type = "button";
    chargePill.className = "beta-pending-pill beta-pending-pill-charge hidden";
    chargePill.innerHTML = `<ha-icon icon="mdi:ev-station"></ha-icon><span class="beta-pending-pill-text">—</span>`;
    chargePill.addEventListener("click", () => this._openPendingModal("charges"));
    const tripPill = document.createElement("button");
    tripPill.type = "button";
    tripPill.className = "beta-pending-pill beta-pending-pill-trip hidden";
    tripPill.innerHTML = `<ha-icon icon="mdi:road-variant"></ha-icon><span class="beta-pending-pill-text">—</span>`;
    tripPill.addEventListener("click", () => this._openPendingModal("trips"));
    const layoutBtn = document.createElement("button");
    layoutBtn.type = "button";
    layoutBtn.className = "beta-layout-btn";
    layoutBtn.title = "Panel anpassen";
    layoutBtn.innerHTML = `<ha-icon icon="mdi:view-dashboard-edit-outline"></ha-icon>`;
    layoutBtn.addEventListener("click", () => this._openPanelLayoutModal(modus));
    pillRow.append(chargePill, tripPill, layoutBtn);
    wrap.appendChild(pillRow);
    this._r.betaPendingChargePill = chargePill;
    this._r.betaPendingChargePillText = chargePill.querySelector(".beta-pending-pill-text");
    this._r.betaPendingTripPill = tripPill;
    this._r.betaPendingTripPillText = tripPill.querySelector(".beta-pending-pill-text");

    const grid = div("beta-grid");

    // "Ausgaben ueber die letzten Monate" (echte Monatshistorie) bewusst
    // NICHT gebaut -- cost_periods traegt nur die aktuelle Periode plus
    // GENAU einen Vormonatswert (siehe _buildBetaHeroCard()), keine
    // Mehrmonats-Reihe. Ohne neue Aggregation aus den Rohdaten (history/
    // evcc-Sessions) waere das nur erfunden -- offener Punkt fuer einen
    // Folge-Prompt, siehe CHANGELOG.
    const builders = this._panelSectionBuilders(modus);
    const available = Object.keys(builders).filter((k) => builders[k]);
    const layout = this._panelLayout();
    for (const key of this._panelLayoutOrder(available, layout)) {
      const card = builders[key]();
      card.classList.add(`panel-card-size-${this._panelLayoutSize(key, layout)}`);
      grid.appendChild(card);
    }

    wrap.appendChild(grid);
    return wrap;
  }

  _buildBetaHeroCard() {
    const { card } = this._card("Diesen Monat, bisher", "mdi:cash-multiple");
    card.classList.add("hero-card");
    const val = document.createElement("div");
    val.className = "hero-value";
    val.innerHTML = `<span id="beta-hero-cost" class="mono">—</span><span class="hero-unit">EUR</span>`;
    card.appendChild(val);
    const sub = document.createElement("div");
    sub.className = "hero-sub hidden";
    card.appendChild(sub);
    this._r.betaHeroCost = val.querySelector("#beta-hero-cost");
    this._r.betaHeroSub = sub;
    return card;
  }

  _buildBetaKpiCard() {
    const { card } = this._card("Kennzahlen", "mdi:chart-box-outline");
    const kpis = document.createElement("div");
    kpis.className = "kpi-row";
    kpis.innerHTML = `
      <div class="kpi"><div class="kv mono" id="beta-kpi-eur100">—</div><div class="kl">EUR/100km</div></div>
      <div class="kpi"><div class="kv mono beta-accent" id="beta-kpi-savings">—</div><div class="kl">EUR Ersparnis ggü. Verbrenner</div></div>
      <div class="kpi"><div class="kv mono beta-accent" id="beta-kpi-co2">—</div><div class="kl">kg CO2 gespart</div></div>
    `;
    card.appendChild(kpis);
    this._r.betaKpiEur100  = kpis.querySelector("#beta-kpi-eur100");
    this._r.betaKpiSavings = kpis.querySelector("#beta-kpi-savings");
    this._r.betaKpiCo2     = kpis.querySelector("#beta-kpi-co2");
    return card;
  }

  // Fahrzeug-SoC als eigene, kompakte Karte neben dem Hero -- bewusst ohne
  // eigenen Karten-Header/Icon (siehe _card()), da nur eine einzelne
  // Kennzahl-Zeile gezeigt wird. Quelle: dieselbe SoC-Entitaet wie
  // Fahrzeug-Tab (_eid("soc_entity"), Schritt 1) -- NICHT
  // evcc_live_attrs().vehicle_soc (evccs eigene, ggf. abweichende Sicht).
  _buildBetaSocCard() {
    const card = document.createElement("div");
    card.className = "card beta-soc-card";
    card.innerHTML = `
      <div class="beta-soc-row">
        <span class="bl">Fahrzeug-SoC</span>
        <span class="bv mono" id="beta-soc-val">—</span>
      </div>
      <div class="veh-soc-bar-wrap beta-soc-bar-wrap"><div class="veh-soc-bar-fill" id="beta-soc-fill" style="background:var(--accent-2)"></div></div>
    `;
    this._r.betaSocVal = card.querySelector("#beta-soc-val");
    this._r.betaSocFill = card.querySelector("#beta-soc-fill");
    return card;
  }

  // Wallbox-Karte -- nur gemischt/nur_zuhause (siehe _buildUebersichtBeta()).
  // HARTES Kriterium: identische Struktur/Hoehe in allen 3 Zustaenden
  // (laedt/verbunden/nicht verbunden), siehe _updateBetaWallbox() -- kein
  // Zustand darf Zeilen ein-/ausblenden, nur deren INHALT wechselt.
  // Ring wiederverwendet das SVG-Zeichenmuster des (inzwischen archivierten)
  // klassischen Übersicht-Tabs (dort Live-kW-Solar/Netz-Split, hier
  // Solar-%/Netz-%-Split einer Ladesession) -- eigene, kleinere Instanz.
  _buildBetaWallboxCard() {
    const card = document.createElement("div");
    card.className = "card beta-wallbox-card";

    const size = 88, stroke = 10, pad = 6;
    const rv = (size - stroke) / 2 - pad;
    const circ = +(2 * Math.PI * rv).toFixed(2);
    const cx = size / 2, cy = size / 2;

    card.innerHTML = `
      <div class="beta-wallbox-head">
        <div class="beta-wallbox-status">
          <span class="beta-wb-icon" id="beta-wb-icon"><ha-icon icon="mdi:ev-station"></ha-icon></span>
          <span id="beta-wb-status-text">—</span>
        </div>
        <span class="beta-mode-pill" id="beta-wb-mode-pill">—</span>
      </div>
      <div class="beta-wallbox-limits" id="beta-wb-limits">Min-Limit —% · Ladelimit —%</div>
      <div class="beta-wallbox-caption" id="beta-wb-caption">—</div>
      <div class="beta-wallbox-body">
        <div class="beta-wallbox-ring-wrap" id="beta-wb-ring-wrap">
          <div class="ring" style="width:${size}px;height:${size}px">
            <svg width="${size}" height="${size}" overflow="visible" style="transform:rotate(-90deg)">
              <circle cx="${cx}" cy="${cy}" r="${rv}" fill="none" stroke="var(--bg-0)" stroke-width="${stroke}"/>
              <circle class="beta-wb-ring-solar" cx="${cx}" cy="${cy}" r="${rv}" fill="none" stroke="var(--accent)"
                stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="0 ${circ}"/>
              <circle class="beta-wb-ring-grid" cx="${cx}" cy="${cy}" r="${rv}" fill="none" stroke="var(--ink-dim)"
                stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="0 ${circ}"/>
            </svg>
          </div>
          <div class="beta-wallbox-legend">
            <span class="cleg"><span class="cleg-dot" style="background:var(--accent)"></span>Solar</span>
            <span class="cleg"><span class="cleg-dot" style="background:var(--ink-dim)"></span>Netz</span>
          </div>
        </div>
        <div class="beta-wallbox-stats">
          <div class="statblock"><div class="statval mono" id="beta-wb-stat1-val">—</div><div class="dim" id="beta-wb-stat1-label">—</div></div>
          <div class="statblock"><div class="statval mono" id="beta-wb-stat2-val">—</div><div class="dim" id="beta-wb-stat2-label">—</div></div>
          <div class="statblock"><div class="statval mono" id="beta-wb-stat3-val">—</div><div class="dim" id="beta-wb-stat3-label">—</div></div>
        </div>
      </div>
      <div class="beta-wallbox-buffer">
        <div class="beta-wb-buffer-row">
          <span class="beta-wb-buffer-label">Puffer (Min-/Ziel-SoC)</span>
          <span class="beta-wb-buffer-val" id="beta-wb-buffer-val">—%</span>
          <button type="button" class="beta-wb-buffer-reset" id="beta-wb-buffer-reset" title="Auf Konfigurationswert zurücksetzen">
            <ha-icon icon="mdi:restore"></ha-icon>
          </button>
        </div>
        <input type="range" class="beta-wb-buffer-slider" id="beta-wb-buffer-slider" min="0" max="100" step="1" value="20">
      </div>
      <div class="beta-wallbox-balancing">
        <label class="beta-wb-balancing-row">
          <input type="checkbox" class="beta-wb-balancing-toggle" id="beta-wb-balancing-toggle">
          <span class="beta-wb-balancing-label">Wöchentliche Vollladung (Balancing)</span>
        </label>
        <div class="dim beta-wb-balancing-status" id="beta-wb-balancing-status"></div>
      </div>
    `;
    const q = (s) => card.querySelector(s);
    this._r.betaWallboxCard   = card;
    this._r.betaWbIcon        = q("#beta-wb-icon");
    this._r.betaWbStatusText  = q("#beta-wb-status-text");
    this._r.betaWbModePill    = q("#beta-wb-mode-pill");
    this._r.betaWbLimits      = q("#beta-wb-limits");
    this._r.betaWbCaption     = q("#beta-wb-caption");
    this._r.betaWbRingWrap    = q("#beta-wb-ring-wrap");
    this._r.betaWbRingSolar   = q(".beta-wb-ring-solar");
    this._r.betaWbRingGrid    = q(".beta-wb-ring-grid");
    this._r.betaWbRingCirc    = circ;
    this._r.betaWbStat1Val    = q("#beta-wb-stat1-val");
    this._r.betaWbStat1Label  = q("#beta-wb-stat1-label");
    this._r.betaWbStat2Val    = q("#beta-wb-stat2-val");
    this._r.betaWbStat2Label  = q("#beta-wb-stat2-label");
    this._r.betaWbStat3Val    = q("#beta-wb-stat3-val");
    this._r.betaWbStat3Label  = q("#beta-wb-stat3-label");
    this._r.betaWbBufferVal    = q("#beta-wb-buffer-val");
    this._r.betaWbBufferSlider = q("#beta-wb-buffer-slider");
    this._r.betaWbBufferReset  = q("#beta-wb-buffer-reset");
    this._r.betaWbBalancingToggle = q("#beta-wb-balancing-toggle");
    this._r.betaWbBalancingStatus = q("#beta-wb-balancing-status");

    // set_weekly_full_charge_enabled (siehe coordinator.py::async_set_
    // weekly_full_charge_enabled()) -- ANDERS als der Puffer-Regler oben
    // (reiner Laufzeit-Override) schreibt das direkt in die Konfiguration
    // und loest einen kurzen Neuladen der Integration aus, damit der
    // Options-Flow nie einen anderen Wert zeigt als hier gesetzt.
    this._r.betaWbBalancingToggle.addEventListener("change", (e) => {
      this._call("set_weekly_full_charge_enabled", { enabled: e.target.checked });
    });

    // Live-Vorschau beim Ziehen (input), Service-Aufruf erst beim
    // Loslassen (change) -- verhindert eine Flut von Service-Calls
    // waehrend des Ziehens, siehe _call()/coordinator.py::async_set_
    // usage_profile_buffer_pct() (loest je Aufruf eine evcc-Neube-
    // wertung aus, das soll nicht bei jedem Zwischenwert passieren).
    this._r.betaWbBufferSlider.addEventListener("input", (e) => {
      this._r.betaWbBufferVal.textContent = `${e.target.value}%`;
    });
    this._r.betaWbBufferSlider.addEventListener("change", (e) => {
      this._call("set_usage_profile_buffer_pct", { buffer_pct: parseFloat(e.target.value) });
    });
    this._r.betaWbBufferReset.addEventListener("click", () => {
      this._call("set_usage_profile_buffer_pct", {});
    });
    return card;
  }

  // "nur_auswaerts": keine Live-Wallbox vorhanden -- letzte bestaetigte
  // Fremdladung aus last_cost-Attributen (= dict(history[0]), siehe
  // sensor.py::LastCostSensor.extra_state_attributes) statt Live-Status.
  _buildBetaLastChargeCard() {
    const { card } = this._card("Letzte Ladung", "mdi:ev-station");
    card.classList.add("beta-status-card");
    const list = document.createElement("div");
    list.className = "beta-status-list";
    list.innerHTML = `
      <div class="beta-status-row" id="beta-last-date-row"><span class="bl">Datum</span><span class="bv" id="beta-last-date">—</span></div>
      <div class="beta-status-row" id="beta-last-kwh-row"><span class="bl">kWh</span><span class="bv" id="beta-last-kwh">—</span></div>
      <div class="beta-status-row" id="beta-last-cost-row"><span class="bl">Kosten</span><span class="bv" id="beta-last-cost">—</span></div>
      <div class="beta-status-row" id="beta-last-price-row"><span class="bl">Preis</span><span class="bv" id="beta-last-price">—</span></div>
      <div class="beta-status-row" id="beta-last-duration-row"><span class="bl">Dauer</span><span class="bv" id="beta-last-duration">—</span></div>
    `;
    card.appendChild(list);
    const q = (s) => list.querySelector(s);
    this._r.betaLastChargeCard  = card;
    this._r.betaLastDateRow     = q("#beta-last-date-row");
    this._r.betaLastDate        = q("#beta-last-date");
    this._r.betaLastKwhRow      = q("#beta-last-kwh-row");
    this._r.betaLastKwh         = q("#beta-last-kwh");
    this._r.betaLastCostRow     = q("#beta-last-cost-row");
    this._r.betaLastCost        = q("#beta-last-cost");
    this._r.betaLastPriceRow    = q("#beta-last-price-row");
    this._r.betaLastPrice       = q("#beta-last-price");
    this._r.betaLastDurationRow = q("#beta-last-duration-row");
    this._r.betaLastDuration    = q("#beta-last-duration");
    return card;
  }

  // Vergleich zum Verbrenner als zwei horizontale Proportionsbalken statt
  // der Zahlen-Tabelle des (inzwischen archivierten) klassischen
  // Übersicht-Tabs -- gleiche Datenquelle (savings()-Sensor), nur neu
  // visualisiert.
  _buildBetaComparisonBarsCard() {
    const { card } = this._card("Vergleich zum Verbrenner", "mdi:gas-station-off");
    const body = document.createElement("div");
    body.innerHTML = `
      <div class="beta-bar-row">
        <div class="beta-bar-label"><span>EV</span><span class="mono" id="beta-cmp-ev-val">—</span></div>
        <div class="beta-bar-track"><div class="beta-bar-fill" id="beta-cmp-ev-fill" style="background:var(--accent-2)"></div></div>
      </div>
      <div class="beta-bar-row">
        <div class="beta-bar-label"><span>Verbrenner</span><span class="mono" id="beta-cmp-verb-val">—</span></div>
        <div class="beta-bar-track"><div class="beta-bar-fill" id="beta-cmp-verb-fill" style="background:var(--ink-dim)"></div></div>
      </div>
    `;
    card.appendChild(body);
    const q = (s) => body.querySelector(s);
    this._r.betaCmpEvVal    = q("#beta-cmp-ev-val");
    this._r.betaCmpEvFill   = q("#beta-cmp-ev-fill");
    this._r.betaCmpVerbVal  = q("#beta-cmp-verb-val");
    this._r.betaCmpVerbFill = q("#beta-cmp-verb-fill");
    return card;
  }

  // "gemischt"/"nur_zuhause": Ladeort-Aufschluesselung (Heim/Fremd) als
  // segmentierter Proportionsbalken statt Zahlen-Tabelle -- dieselben
  // charging_location_breakdown-Attribute wie die alte Karte/der
  // Analyse-Tab (siehe dort), nur neu visualisiert.
  _buildBetaLadeortBarsCard() {
    const { card } = this._card("Ladeort-Aufschlüsselung", "mdi:chart-donut");
    const body = document.createElement("div");
    body.innerHTML = `
      <div class="beta-bar-track beta-bar-track-split" id="beta-loc-track">
        <div class="beta-bar-fill" id="beta-loc-home-fill" style="background:var(--accent)"></div>
        <div class="beta-bar-fill" id="beta-loc-ext-fill" style="background:var(--accent-2)"></div>
      </div>
      <div class="beta-wallbox-legend beta-loc-legend">
        <span class="cleg"><span class="cleg-dot" style="background:var(--accent)"></span>Heim <span class="mono" id="beta-loc-home-val">—</span></span>
        <span class="cleg"><span class="cleg-dot" style="background:var(--accent-2)"></span>Fremd <span class="mono" id="beta-loc-ext-val">—</span></span>
      </div>
    `;
    card.appendChild(body);
    const q = (s) => body.querySelector(s);
    this._r.betaLocCard     = card;
    this._r.betaLocHomeFill = q("#beta-loc-home-fill");
    this._r.betaLocExtFill  = q("#beta-loc-ext-fill");
    this._r.betaLocHomeVal  = q("#beta-loc-home-val");
    this._r.betaLocExtVal   = q("#beta-loc-ext-val");
    return card;
  }

  // "nur_auswaerts": Heimladen ist strukturell praktisch immer leer, daher
  // hier statt der Heim/Fremd-Aufschlüsselung nur die AC/DC-Einordnung der
  // Fremdladung (siehe engine.ac_dc_breakdown()) -- als Schätzung markiert,
  // analog zum Hinweis im Analyse-Tab.
  _buildBetaAcDcCard() {
    const { card, head } = this._card("Fremdladung nach AC/DC", "mdi:chart-donut");
    head.querySelector("h2").title = "Geschätzt aus Ø-Ladeleistung (kWh/Ladedauer), keine direkte AC/DC-Messung.";
    const grid = document.createElement("div");
    grid.className = "km-grid";
    grid.innerHTML = `
      <div class="km-col hidden" id="beta-acdc-ac-col">
        <div class="sub-head">AC</div>
        <div class="km-item"><span class="km-label">kWh</span><span class="km-val" id="beta-acdc-ac-kwh">—</span><span class="km-unit">kWh</span></div>
        <div class="km-item"><span class="km-label">Anteil</span><span class="km-val" id="beta-acdc-ac-pct">—</span><span class="km-unit">%</span></div>
      </div>
      <div class="km-col hidden" id="beta-acdc-dc-col">
        <div class="sub-head">DC</div>
        <div class="km-item"><span class="km-label">kWh</span><span class="km-val" id="beta-acdc-dc-kwh">—</span><span class="km-unit">kWh</span></div>
        <div class="km-item"><span class="km-label">Anteil</span><span class="km-val" id="beta-acdc-dc-pct">—</span><span class="km-unit">%</span></div>
      </div>
    `;
    card.appendChild(grid);
    const note = document.createElement("div");
    note.className = "profil-empty";
    note.style.cssText = "padding:4px 0 0;font-size:0.72rem";
    note.textContent = "Geschätzt aus der Durchschnittsleistung je Ladung, keine direkte AC/DC-Messung.";
    card.appendChild(note);
    const q = (s) => grid.querySelector(s);
    this._r.betaAcdcCard  = card;
    this._r.betaAcdcAcCol = q("#beta-acdc-ac-col");
    this._r.betaAcdcAcKwh = q("#beta-acdc-ac-kwh");
    this._r.betaAcdcAcPct = q("#beta-acdc-ac-pct");
    this._r.betaAcdcDcCol = q("#beta-acdc-dc-col");
    this._r.betaAcdcDcKwh = q("#beta-acdc-dc-kwh");
    this._r.betaAcdcDcPct = q("#beta-acdc-dc-pct");
    return card;
  }

  // Sichtbarmachung der automatischen evcc-Modus-/SoC-Steuerung (separat
  // entwickeltes Feature, siehe coordinator.py::EvccModeControlSensor) --
  // eigene volle-Breite Karte statt in heroRow/bottomRow, da relativ
  // zeilenreich. Standardmaessig per "hidden" versteckt (siehe
  // _updateBetaEvccMode()), da die Steuerung selbst standardmaessig aus ist.
  _buildBetaEvccModeCard() {
    const { card, head } = this._card("Automatische Ladesteuerung", "mdi:tune-variant");
    head.querySelector("h2").title =
      "Setzt evccs Lademodus sowie Min-/Ziel-SoC automatisch anhand des Nutzungsprofils " +
      "(Fahrzeug + optional Haus/Speicher) und gleicht dabei laufend evccs Live-Zustand ab " +
      "-- ein manueller evcc-Eingriff hält daher nur bis zum nächsten Zyklus (~1 Min.), " +
      "außer der Schalter unten ist aktiv.";
    card.classList.add("beta-status-card", "beta-evcc-card", "hidden");

    const badge = document.createElement("div");
    badge.className = "beta-evcc-badge";
    badge.innerHTML = `<span class="beta-evcc-dot"></span><span id="beta-evcc-mode-label">—</span>`;
    card.appendChild(badge);

    const list = document.createElement("div");
    list.className = "beta-status-list";
    list.innerHTML = `
      <div class="beta-status-row"><span class="bl">Min-SoC</span><span class="bv" id="beta-evcc-min-soc">—</span></div>
      <div class="beta-status-row"><span class="bl">Ziel-SoC</span><span class="bv" id="beta-evcc-target-soc">—</span></div>
      <div class="beta-status-row"><span class="bl">Rest-Bedarf heute</span><span class="bv" id="beta-evcc-rest-heute">—</span></div>
      <div class="beta-status-row"><span class="bl">PV fürs Auto</span><span class="bv" id="beta-evcc-pv-fuer-auto">—</span></div>
      <div class="beta-status-row"><span class="bl">Zuletzt geschrieben</span><span class="bv" id="beta-evcc-last-written">—</span></div>
      <div class="beta-status-row hidden" id="beta-evcc-scope-warn-row">
        <span class="bl">SoC-Steuerung</span><span class="bv beta-evcc-warn">nicht verfügbar — siehe Repariere</span>
      </div>
    `;
    card.appendChild(list);

    // Manuelle Pause (siehe coordinator.py::async_set_evcc_mode_control_
    // pause()/services.yaml::set_evcc_mode_control_pause) -- seit dem
    // evcc-Live-Zustand-Abgleich in _async_apply_evcc_mode_control() haelt
    // ein manueller evcc-Eingriff sonst nur noch bis zum naechsten Zyklus
    // (~1 Min.), nicht mehr bis zur naechsten echten Empfehlungsaenderung.
    // Einfacher Dauer-Schalter statt Zeitfenster (Nutzerentscheidung,
    // Produktionsfeedback 2026-09-18) -- analog dem Balancing-Schalter in
    // _buildBetaWallboxCard(), nur hier als reiner Laufzeit-Override (kein
    // Integrations-Reload).
    const pause = document.createElement("div");
    pause.className = "beta-evcc-pause";
    pause.innerHTML = `
      <label class="beta-evcc-pause-row">
        <input type="checkbox" class="beta-evcc-pause-toggle" id="beta-evcc-pause-toggle">
        <span class="bl">Automatik pausiert</span>
      </label>
    `;
    card.appendChild(pause);
    const qp = (s) => pause.querySelector(s);
    this._r.betaEvccPauseToggle = qp("#beta-evcc-pause-toggle");
    this._r.betaEvccPauseToggle.addEventListener("change", (e) => {
      this._call("set_evcc_mode_control_pause", { paused: e.target.checked });
    });

    // Manueller Modus (siehe coordinator.py::async_set_evcc_manual_mode()) --
    // im Gegensatz zur Pause oben session-scoped (endet automatisch beim
    // Trennen des Fahrzeugs, siehe _check_evcc_manual_mode_session_end()),
    // daher eigener Bereich statt Wiederverwendung des Pause-Schalters
    // (Nutzerentscheidung 2026-09-22).
    const manual = document.createElement("div");
    manual.className = "beta-evcc-manual";
    manual.innerHTML = `
      <div class="beta-evcc-manual-row">
        <select id="beta-evcc-manual-select">
          <option value="pv">Smart</option>
          <option value="minpv">Smart + Immer laden</option>
          <option value="now">Schnell</option>
        </select>
        <button type="button" id="beta-evcc-manual-set-btn">Manuell setzen</button>
      </div>
      <div class="beta-evcc-manual-status hidden" id="beta-evcc-manual-status">
        <span class="bl">Manuell aktiv</span>
        <span class="bv" id="beta-evcc-manual-status-text">—</span>
        <button type="button" id="beta-evcc-manual-clear-btn">Beenden</button>
      </div>
    `;
    card.appendChild(manual);
    const qm = (s) => manual.querySelector(s);
    this._r.betaEvccManualSelect  = qm("#beta-evcc-manual-select");
    this._r.betaEvccManualSetBtn  = qm("#beta-evcc-manual-set-btn");
    this._r.betaEvccManualStatus  = qm("#beta-evcc-manual-status");
    this._r.betaEvccManualStatusText = qm("#beta-evcc-manual-status-text");
    this._r.betaEvccManualClearBtn = qm("#beta-evcc-manual-clear-btn");
    this._r.betaEvccManualSetBtn.addEventListener("click", () => {
      this._call("set_evcc_manual_mode", { mode: this._r.betaEvccManualSelect.value });
    });
    this._r.betaEvccManualClearBtn.addEventListener("click", () => {
      this._call("clear_evcc_manual_mode", {});
    });

    const q = (s) => list.querySelector(s);
    this._r.betaEvccCard        = card;
    this._r.betaEvccModeLabel   = badge.querySelector("#beta-evcc-mode-label");
    this._r.betaEvccDot         = badge.querySelector(".beta-evcc-dot");
    this._r.betaEvccMinSoc      = q("#beta-evcc-min-soc");
    this._r.betaEvccTargetSoc   = q("#beta-evcc-target-soc");
    this._r.betaEvccRestHeute   = q("#beta-evcc-rest-heute");
    this._r.betaEvccPvFuerAuto  = q("#beta-evcc-pv-fuer-auto");
    this._r.betaEvccLastWritten = q("#beta-evcc-last-written");
    this._r.betaEvccScopeWarnRow = q("#beta-evcc-scope-warn-row");
    return card;
  }

  // evccs eigener Ladeplan (Zielzeit-Laden, siehe coordinator.py::
  // async_set_evcc_charge_plan()/EvccChargePlanSensor) -- absichtlich eine
  // EIGENE Karte statt Teil von _buildBetaEvccModeCard(): funktioniert
  // unabhaengig von CONF_EVCC_MODE_CONTROL_ENABLED (siehe dortige
  // "hidden"-Vorbelegung, die nur fuer den Modus-Karte gilt), pausiert bei
  // aktivem Plan aber die dortige profilbasierte Steuerung (siehe
  // _async_apply_evcc_mode_control()). Formular bleibt immer sichtbar
  // (auch bei bereits aktivem Plan) -- erneutes Absenden aendert den Plan
  // einfach, statt zwischen zwei Ansichten hin- und herzuschalten.
  _buildBetaEvccPlanCard() {
    const { card } = this._card("Ladeplan", "mdi:calendar-clock");
    card.classList.add("beta-status-card", "hidden");

    // Aktueller Stand (SoC + Restreichweite) -- immer sichtbar, unabhaengig
    // von einem aktiven Plan, damit man beim Ausfuellen des Formulars weiss,
    // wo man gerade steht (Nutzerwunsch 2026-09-22).
    const current = document.createElement("div");
    current.className = "beta-status-row beta-plan-current-row";
    current.innerHTML = `<span class="bl">Aktuell</span><span class="bv" id="beta-plan-current">—</span>`;
    card.appendChild(current);

    const status = document.createElement("div");
    status.className = "beta-plan-status hidden";
    status.innerHTML = `
      <div class="beta-status-row"><span class="bl">Ziel</span><span class="bv" id="beta-plan-target">—</span></div>
      <div class="beta-status-row" id="beta-plan-start-row"><span class="bl">Geplanter Start</span><span class="bv" id="beta-plan-start">—</span></div>
      <div class="beta-status-row"><span class="bl">Status</span><span class="bv" id="beta-plan-active">—</span></div>
      <div class="beta-status-row beta-plan-erwartung-row hidden" id="beta-plan-erwartung-row"><span class="bl">Erwartung</span><span class="bv" id="beta-plan-erwartung">—</span></div>
    `;
    card.appendChild(status);

    // Formular selbst NICHT mehr fest auf der Karte (Nutzerwunsch
    // 2026-09-22: "auf der karte einen button hinzufuegen mit ladeplan
    // anlegen. dieser button oeffnet ein popup") -- stattdessen ein
    // Button, der das Modal aus _buildLadeplanModal() oeffnet.
    const actions = document.createElement("div");
    actions.className = "beta-plan-actions";
    actions.innerHTML = `
      <button type="button" class="beta-plan-open-btn" id="beta-plan-open-btn">Ladeplan anlegen</button>
      <button type="button" class="beta-plan-clear-btn hidden" id="beta-plan-clear-btn">Plan löschen</button>
    `;
    card.appendChild(actions);

    const q = (s) => card.querySelector(s);
    this._r.betaPlanCard       = card;
    this._r.betaPlanCurrent    = q("#beta-plan-current");
    this._r.betaPlanStatus     = status;
    this._r.betaPlanTarget     = q("#beta-plan-target");
    this._r.betaPlanStartRow   = q("#beta-plan-start-row");
    this._r.betaPlanStart      = q("#beta-plan-start");
    this._r.betaPlanActive     = q("#beta-plan-active");
    this._r.betaPlanErwartungRow = q("#beta-plan-erwartung-row");
    this._r.betaPlanErwartung  = q("#beta-plan-erwartung");
    this._r.betaPlanOpenBtn    = q("#beta-plan-open-btn");
    this._r.betaPlanClearBtn   = q("#beta-plan-clear-btn");

    this._r.betaPlanOpenBtn.addEventListener("click", () => this._openLadeplanModal());
    this._r.betaPlanClearBtn.addEventListener("click", () => {
      this._call("clear_evcc_charge_plan", {});
    });
    return card;
  }

  // --- Popup: Ladeplan anlegen -------------------------------------------------
  //
  // Eigenes Overlay (analog _buildPendingModal()), ausserhalb von this._main
  // in _renderShell() angehaengt, damit der "Ladeplan anlegen"-Button auf der
  // Ladeplan-Karte (siehe _buildBetaEvccPlanCard()) es jederzeit oeffnen kann.
  // EIGENE ladeplan-modal-*-CSS-Klassen statt der pending-modal-*-Klassen
  // (Nutzerwunsch 2026-09-22: "popup mittig auf dem bildschirm oeffnen,
  // nicht am unteren rand") -- das Fahrten/Fremdladungen-Popup wird auf
  // schmalen Bildschirmen bewusst als Bottom-Sheet dargestellt, das soll
  // hier NICHT gelten, unabhaengig von der Fensterbreite.
  _buildLadeplanModal() {
    const overlay = document.createElement("div");
    overlay.className = "ladeplan-modal-overlay hidden";
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) this._closeLadeplanModal();
    });
    const modal = document.createElement("div");
    modal.className = "ladeplan-modal";
    modal.innerHTML = `
      <div class="ladeplan-modal-head">
        <span class="ic"><ha-icon icon="mdi:calendar-clock"></ha-icon></span>
        <h2>Ladeplan anlegen</h2>
        <button type="button" class="ladeplan-modal-close" aria-label="Schließen"><ha-icon icon="mdi:close"></ha-icon></button>
      </div>
      <div class="ladeplan-modal-body">
        <div class="beta-plan-live-feedback beta-plan-status-badge hidden" id="ladeplan-status-badge"></div>
        <div class="beta-status-row"><span class="bl">Aktuell</span><span class="bv" id="ladeplan-modal-current">—</span></div>
        <label class="beta-plan-field">Zielzeit<input type="datetime-local" id="ladeplan-time-input"></label>
        <div class="beta-plan-live-feedback hidden" id="ladeplan-live-feedback"></div>
        <label class="beta-plan-field beta-plan-slider-field" id="ladeplan-soc-field">
          <div class="beta-plan-slider-label"><span>Ziel</span><span class="beta-plan-slider-value" id="ladeplan-soc-value">80%</span></div>
          <div class="beta-plan-slider-wrap">
            <input type="range" id="ladeplan-soc-slider" min="0" max="100" step="1" value="80">
            <div class="beta-plan-slider-mark hidden" id="ladeplan-soc-mark"></div>
          </div>
        </label>
        <div class="beta-plan-buttons">
          <button type="button" class="beta-plan-set-btn" id="ladeplan-set-btn">Plan setzen</button>
        </div>
      </div>`;
    modal.querySelector(".ladeplan-modal-close").addEventListener("click", () => this._closeLadeplanModal());
    overlay.appendChild(modal);
    this._ladeplanModalEl = overlay;

    // WICHTIG: in this._lp ablegen, NICHT this._r -- this._r wird von
    // _switchView() bei jedem Tab-Wechsel (auch dem direkt auf das erste
    // Rendern folgenden) auf {} zurueckgesetzt, dieses Popup aber nur
    // EINMAL gebaut (siehe this._lp-Kommentar im Konstruktor). Genau das
    // war der Bug, der alle Slider-Faelle wirkungslos gemacht hat.
    const q = (s) => modal.querySelector(s);
    this._lp.statusBadge  = q("#ladeplan-status-badge");
    this._lp.modalCurrent = q("#ladeplan-modal-current");
    this._lp.liveFeedback = q("#ladeplan-live-feedback");
    this._lp.timeInput    = q("#ladeplan-time-input");
    this._lp.socSlider    = q("#ladeplan-soc-slider");
    this._lp.socMark      = q("#ladeplan-soc-mark");
    this._lp.socValue     = q("#ladeplan-soc-value");
    this._lp.setBtn       = q("#ladeplan-set-btn");

    // NUR EIN Slider (%, die von evcc tatsaechlich verwendete Einheit) --
    // km wird lediglich zur Anzeige mitgerechnet (Nutzerwunsch 2026-09-23:
    // "km und soc zusammen im slider anzeigen" / "radiobuttons entfernen").
    // Vorher gab es zwei separate Slider mit eigenem %/km-Umschalter, die
    // beim Wechsel nicht synchron blieben -- mit nur einer Quelle entfaellt
    // dieses Problem strukturell.
    this._lp.socSlider.addEventListener("input", () => {
      if (Number(this._lp.socSlider.value) < (this._lp.socMinVal ?? 0)) {
        this._lp.socSlider.value = String(this._lp.socMinVal ?? 0);
      }
      this._updateLadeplanSocValueLabel();
      this._updateLadeplanLiveFeedback();
    });
    // Nutzerwunsch 2026-09-23: "nachdem ich zeit und ziel soc eingestellt
    // habe sollte ueber dem slider direkt die auswertung erscheinen ob die
    // ladung so moeglich ist" -- Zielzeit-Aenderung loest dieselbe Live-
    // Neuberechnung aus wie ein Slider-Dreh.
    this._lp.timeInput.addEventListener("input", () => this._updateLadeplanLiveFeedback());

    this._lp.setBtn.addEventListener("click", () => {
      const targetTime = this._fromDatetimeLocal(this._lp.timeInput.value);
      if (targetTime === null) return;
      const targetSoc = parseFloat(this._lp.socSlider.value);
      if (isNaN(targetSoc)) return;
      this._call("set_evcc_charge_plan", { target_time: targetTime, target_soc: targetSoc });
      this._closeLadeplanModal();
    });
    return overlay;
  }

  // Kombinierte "64% · 175 km"-Anzeige fuer den Slider-Wert (Nutzerwunsch
  // 2026-09-23: "km und soc zusammen im slider anzeigen") -- km wird aus
  // _ladeplanConversionInputs() abgeleitet, "—" ohne bekannten Verbrauch/
  // verfuegbare kWh statt einer geratenen Zahl.
  _updateLadeplanSocValueLabel() {
    if (!this._lp.socValue) return;
    const socVal = parseFloat(this._lp.socSlider.value);
    let kmText = "—";
    const conv = this._ladeplanConversionInputs();
    if (conv && !isNaN(socVal)) {
      const km = ((socVal / 100) * conv.usableKwh) / conv.consumption * 100;
      kmText = `${Math.round(km)} km`;
    }
    this._lp.socValue.textContent = `${socVal}% · ${kmText}`;
  }

  // Ermittelt das MINIMUM (aktueller SoC, Nutzerwunsch 2026-09-22: "der
  // slider darf nicht negativ verschoben werden koennen. man will ja laden
  // und nicht entladen") und positioniert den senkrechten Strich auf dem
  // Track an dieser Stelle (Slider bleibt visuell 0-100 -- Nutzerwunsch:
  // "der slider startet bei 47 und nicht bei 0%"; KEINE Zahl/Zeile mehr
  // dazu, Nutzerwunsch 2026-09-23: "entferne die zeile komplett"). Das
  // Nicht-unter-den-Ist-Stand-Verschieben selbst wird ueber den 'input'-
  // Handler in _buildLadeplanModal() durchgesetzt (Wert zurueckschnappen
  // statt Track kappen).
  _updateLadeplanSliderBounds(soc, range) {
    const lp = this._lp;
    if (!lp.socSlider) return;
    const socMin = isNaN(soc) ? 0 : Math.round(Math.min(100, Math.max(0, soc)));
    lp.socMinVal = socMin;
    if (!isNaN(soc)) {
      lp.socMark.style.left = `${socMin}%`;
      lp.socMark.classList.remove("hidden");
    } else {
      lp.socMark.classList.add("hidden");
    }
    // Erstes Oeffnen (in dieser Seiten-Sitzung): Slider auf den aktuellen
    // SoC setzen statt auf den statischen HTML-Default "80" stehenzulassen
    // (Nutzerwunsch 2026-09-23: "der sliderbutton startet bzw steht nicht
    // bei dem aktuellen soc, sondern auf 80"). Danach nur noch nach oben
    // korrigieren, wenn ein bereits eingestellter Wert unter das (ggf.
    // gestiegene) neue Minimum faellt -- NICHT bei jedem erneuten Oeffnen
    // ueberschreiben, siehe Kommentar unten in _openLadeplanModal()/vorherige
    // Fassung (sprang sonst wieder auf einen festen Wert zurueck).
    if (!lp.initialized) {
      lp.socSlider.value = String(socMin);
      lp.initialized = true;
    } else if (Number(lp.socSlider.value) < socMin) {
      lp.socSlider.value = String(socMin);
    }
    this._updateLadeplanSocValueLabel();
  }

  _openLadeplanModal() {
    if (!this._ladeplanModalEl) return;
    this._updateLadeplanStatusBadge();
    // Aktuellen Stand (SoC/Reichweite) im Modal aus derselben, bereits von
    // _updateBetaEvccPlan() gepflegten Karten-Zeile uebernehmen, statt ihn
    // hier ein zweites Mal zu berechnen.
    if (this._r.betaPlanCurrent && this._lp.modalCurrent) {
      this._lp.modalCurrent.textContent = this._r.betaPlanCurrent.textContent;
    }
    const socEid = this._eid("soc_entity");
    const soc = socEid ? parseFloat(this._raw(socEid) ?? NaN) : NaN;
    const rangeEid = this._eid("range_estimate");
    const range = rangeEid ? parseFloat(this._raw(rangeEid) ?? NaN) : NaN;
    this._updateLadeplanSliderBounds(soc, range);
    this._updateLadeplanLiveFeedback();
    this._ladeplanModalEl.classList.remove("hidden");
  }

  // Status-Badge in der ersten Zeile des Popups (Nutzerwunsch 2026-09-23:
  // "in der ersten zeile eine statusanzeige einfuegen ob evcc bzw das auto
  // ladebereit ist. zentriert") -- dieselbe connected/charging-Grundlage
  // wie _updateBetaWallbox() (evcc_live_attrs().connected/charging), hier
  // aber auf die Frage "ladebereit?" zugeschnitten statt der dortigen
  // Lädt/Verbunden/Nicht-verbunden-Pille.
  _updateLadeplanStatusBadge() {
    if (!this._lp.statusBadge) return;
    const live = this._evccLive();
    const connected = live.connected;
    if (connected == null) {
      this._lp.statusBadge.classList.add("hidden");
      return;
    }
    const charging = live.charging;
    const power = parseFloat(live.charge_power ?? NaN);
    const isCharging = charging === true && !isNaN(power) && power > 0.05;
    this._lp.statusBadge.classList.remove("hidden", "lvl-ok", "lvl-warn", "lvl-bad");
    if (!connected) {
      this._lp.statusBadge.textContent = "Nicht angeschlossen";
      this._lp.statusBadge.classList.add("lvl-bad");
    } else if (isCharging) {
      this._lp.statusBadge.textContent = "Ladebereit – lädt bereits";
      this._lp.statusBadge.classList.add("lvl-ok");
    } else {
      this._lp.statusBadge.textContent = "Ladebereit";
      this._lp.statusBadge.classList.add("lvl-ok");
    }
  }

  // Gemeinsame Grundlage fuer die %<->km-Umrechnung: sowohl beim Umschalten
  // des Einheiten-Radios (Slider-Sync, siehe _buildLadeplanModal()) als auch
  // fuer _ladeplanFeedback() gebraucht. usable_kwh wird aus available_kwh/soc
  // zurueckgerechnet (available_kwh = soc/100*usable_kwh, siehe
  // coordinator.py::available_kwh()) statt separat exponiert. null, wenn
  // SoC/verfuegbare kWh/Verbrauchsschnitt (noch) nicht bekannt sind.
  _ladeplanConversionInputs() {
    const socEid = this._eid("soc_entity");
    const soc = socEid ? parseFloat(this._raw(socEid) ?? NaN) : NaN;
    const availEid = this._eid("available_kwh");
    const available = availEid ? parseFloat(this._raw(availEid) ?? NaN) : NaN;
    if (isNaN(soc) || soc <= 0 || isNaN(available)) return null;
    const usableKwh = available / (soc / 100);
    if (!(usableKwh > 0)) return null;
    const rangeEid = this._eid("range_estimate");
    const rs = rangeEid && this._hass ? this._hass.states[rangeEid] : null;
    const consumption = rs && rs.attributes ? parseFloat(rs.attributes.verbrauch_kwh_100km) : NaN;
    if (isNaN(consumption) || consumption <= 0) return null;
    return { usableKwh, consumption };
  }

  // Live-Erreichbarkeits-Einschaetzung im Popup, click-fuer-click
  // nachgerechnet (Nutzerwunsch 2026-09-23, siehe Aufrufstellen in
  // _buildLadeplanModal()/_openLadeplanModal()) -- gleiche Grundformel wie
  // coordinator.py::_evcc_charge_plan_feedback_text(), hier in JS
  // dupliziert, da das VOR dem Absenden greifen muss (mit Werten, die der
  // Server noch gar nicht kennt). max_charge_power_kw kommt ueber
  // evcc_live_attrs(). Kurzform statt Fliesstext (Nutzerwunsch: "text
  // vereinfachen zu viel text") plus Ampel-Farbe (ok/warn/bad) statt
  // reinem Text. Gibt {level, text} oder null (keine Aussage moeglich,
  // z.B. max. Ladeleistung noch unbekannt) zurueck.
  _ladeplanFeedback() {
    if (!this._ladeplanModalEl) return null;
    const targetTime = this._fromDatetimeLocal(this._lp.timeInput.value);
    if (targetTime === null) return null;
    const socEid = this._eid("soc_entity");
    const soc = socEid ? parseFloat(this._raw(socEid) ?? NaN) : NaN;
    const availEid = this._eid("available_kwh");
    const available = availEid ? parseFloat(this._raw(availEid) ?? NaN) : NaN;
    if (isNaN(soc) || soc <= 0 || isNaN(available)) return null;
    const usableKwh = available / (soc / 100);
    if (!(usableKwh > 0)) return null;

    const targetSoc = parseFloat(this._lp.socSlider.value);
    if (isNaN(targetSoc)) return null;

    const neededKwh = (targetSoc / 100) * usableKwh - available;
    if (neededKwh <= 0) return { level: "ok", text: "Ziel bereits erreicht" };
    const maxPowerKw = this._evccLive().max_charge_power_kw;
    if (!maxPowerKw || maxPowerKw <= 0) return null;

    const hoursNeeded = neededKwh / maxPowerKw;
    const nowTs = Date.now() / 1000;
    const hoursAvailable = (targetTime - nowTs) / 3600;
    const puffer = hoursAvailable - hoursNeeded;
    const finishText = this._fmtTime(nowTs + hoursNeeded * 3600);
    const kwhText = `${neededKwh.toFixed(1)} kWh nötig`;
    if (puffer < 0) {
      return { level: "bad", text: `Nicht rechtzeitig – ${kwhText}, fehlen ca. ${this._fmtDuration(Math.abs(puffer) * 60)}` };
    }
    // Schwelle wie bei coordinator.py::_evcc_charge_plan_feedback_text()
    // (0.25h) -- ein Slider-Fall mit z.B. 36 min Puffer (< 1h, aber deutlich
    // VOR der Zielzeit fertig) wirkte mit der vorherigen 1h-Schwelle
    // unangebracht alarmierend orange (Nutzerwunsch 2026-09-23: "warum ist
    // es orange wenn es vor der zielzeit ist?").
    if (puffer < 0.25) {
      return { level: "warn", text: `Knapp – ${kwhText}, fertig ca. ${finishText}` };
    }
    return { level: "ok", text: `Erreichbar – ${kwhText}, fertig ca. ${finishText}` };
  }

  _updateLadeplanLiveFeedback() {
    if (!this._lp.liveFeedback) return;
    const fb = this._ladeplanFeedback();
    this._lp.liveFeedback.classList.toggle("hidden", !fb);
    this._lp.liveFeedback.classList.remove("lvl-ok", "lvl-warn", "lvl-bad");
    if (!fb) return;
    this._lp.liveFeedback.textContent = fb.text;
    this._lp.liveFeedback.classList.add(`lvl-${fb.level}`);
  }

  _closeLadeplanModal() {
    if (this._ladeplanModalEl) this._ladeplanModalEl.classList.add("hidden");
  }

  // --- Popup: Panel anpassen (Beta-Karten Sichtbarkeit/Reihenfolge) -----------
  //
  // Nutzerwunsch 2026-09-23: "der nutzer bekommt eine auswahl von karten,
  // die er selber im panel anordnen oder auch auswaehlen kann, welche
  // karten er ueberhaupt angezeigt bekommen moechte" -- "serverseitig
  // speichern, mit drag & drop". Eigenes Overlay analog _buildLadeplanModal()
  // (zentriert, ausserhalb von this._main), Refs bewusst in this._pl statt
  // this._r (siehe Konstruktor-Kommentar).

  _panelLayoutLabel(key, modus) {
    const labels = {
      hero_cost: "Kosten (diesen Monat)",
      hero_secondary: modus === "nur_auswaerts" ? "Letzte Fremdladung" : "Fahrzeug-SoC",
      wallbox: "Wallbox",
      kpi: "Kennzahlen",
      comparison: "Vergleich ggü. Verbrenner",
      location: modus === "nur_auswaerts" ? "AC/DC-Aufschlüsselung" : "Ladeorte",
      evcc_mode: "Automatische Ladesteuerung",
      evcc_plan: "Ladeplan",
    };
    return labels[key] || key;
  }

  _buildPanelLayoutModal() {
    const overlay = document.createElement("div");
    overlay.className = "ladeplan-modal-overlay hidden";
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) this._closePanelLayoutModal();
    });
    const modal = document.createElement("div");
    modal.className = "ladeplan-modal";
    modal.innerHTML = `
      <div class="ladeplan-modal-head">
        <span class="ic"><ha-icon icon="mdi:view-dashboard-edit-outline"></ha-icon></span>
        <h2>Panel anpassen</h2>
        <button type="button" class="ladeplan-modal-close" aria-label="Schließen"><ha-icon icon="mdi:close"></ha-icon></button>
      </div>
      <div class="ladeplan-modal-body">
        <div class="panel-layout-hint">Häkchen = sichtbar. Zum Umsortieren am Griff ziehen.</div>
        <div class="panel-layout-list" id="panel-layout-list"></div>
        <div class="beta-plan-buttons">
          <button type="button" class="beta-plan-set-btn" id="panel-layout-save-btn">Speichern</button>
        </div>
      </div>`;
    modal.querySelector(".ladeplan-modal-close").addEventListener("click", () => this._closePanelLayoutModal());
    overlay.appendChild(modal);
    this._panelLayoutModalEl = overlay;

    this._pl.list = modal.querySelector("#panel-layout-list");
    this._pl.saveBtn = modal.querySelector("#panel-layout-save-btn");

    this._pl.saveBtn.addEventListener("click", () => {
      const rows = Array.from(this._pl.list.querySelectorAll(".panel-layout-row"));
      const layout = rows.map((row) => ({
        key: row.dataset.key,
        visible: row.querySelector("input[type=checkbox]").checked,
        size: row.dataset.size,
      }));
      this._call("set_panel_layout", { layout });
      // Optimistisches lokales Update (siehe _panelLayout()) statt auf den
      // Server-Roundtrip zu warten -- _switchView() baut den aktuellen Tab
      // (hier immer "uebersicht_beta", da nur von dort oeffenbar) komplett
      // neu auf.
      this._panelLayoutOverride = layout;
      this._closePanelLayoutModal();
      this._switchView(this._view);
    });
    return overlay;
  }

  // Reine Zeigergesten-basierte Umsortierung (Pointer Events statt
  // HTML5-Drag&Drop, das auf Touch-Geraeten nicht funktioniert -- das Panel
  // muss geraeteadaptiv/responsiv sein, siehe Projektziel) -- beim Ziehen
  // wird die gezogene Zeile einfach mit der Nachbarzeile vertauscht, sobald
  // der Zeiger deren Mittelpunkt ueberquert, kein schwebendes Duplikat/keine
  // absolute Positionierung noetig.
  // Nutzerfeedback 2026-09-23: "waehrend des ziehens sehr ungenau und die
  // liste flackert. man sieht nicht richtig wohin man was zieht" -- die
  // erste Fassung hat die gezogene Zeile bei jedem Pointer-Move direkt in
  // den echten Listenfluss einsortiert; da sich dadurch bei jedem Tick die
  // Nachbar-Positionen selbst mitverschoben haben, konnte derselbe
  // Pointer-Y-Wert abwechselnd beide Richtungen der Swap-Bedingung
  // erfuellen (Oszillation/Flackern). Jetzt der uebliche Ghost+Platzhalter-
  // Ansatz: die gezogene Zeile wird waehrend des Ziehens `position: fixed`
  // (folgt dem Zeiger 1:1, komplett aus dem Layoutfluss der Liste heraus,
  // dadurch keine Rueckkopplung mehr moeglich), ein leerer Platzhalter
  // gleicher Hoehe zeigt an, wo sie beim Loslassen landen wuerde und wird
  // nur anhand der Positionen der UEBRIGEN (nicht der gezogenen) Zeilen
  // verschoben.
  _makeReorderable(listEl) {
    let dragRow = null;
    let placeholder = null;
    let offsetY = 0;

    const onPointerMove = (e) => {
      if (!dragRow) return;
      dragRow.style.top = `${e.clientY - offsetY}px`;
      const rows = Array.from(listEl.children).filter((r) => r !== dragRow && r !== placeholder);
      let target = null;
      for (const r of rows) {
        const rect = r.getBoundingClientRect();
        if (e.clientY < rect.top + rect.height / 2) { target = r; break; }
      }
      if (target) {
        if (placeholder.nextElementSibling !== target) listEl.insertBefore(placeholder, target);
      } else if (placeholder !== listEl.lastElementChild) {
        listEl.appendChild(placeholder);
      }
    };
    const onPointerUp = () => {
      if (!dragRow) return;
      listEl.insertBefore(dragRow, placeholder);
      placeholder.remove();
      dragRow.classList.remove("dragging");
      dragRow.style.position = "";
      dragRow.style.top = "";
      dragRow.style.left = "";
      dragRow.style.width = "";
      dragRow = null;
      placeholder = null;
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
    listEl.querySelectorAll(".panel-layout-handle").forEach((handle) => {
      handle.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        const row = handle.closest(".panel-layout-row");
        const rect = row.getBoundingClientRect();
        offsetY = e.clientY - rect.top;

        placeholder = document.createElement("div");
        placeholder.className = "panel-layout-placeholder";
        placeholder.style.height = `${rect.height}px`;
        row.after(placeholder);

        dragRow = row;
        dragRow.classList.add("dragging");
        dragRow.style.width = `${rect.width}px`;
        dragRow.style.left = `${rect.left}px`;
        dragRow.style.top = `${rect.top}px`;

        window.addEventListener("pointermove", onPointerMove);
        window.addEventListener("pointerup", onPointerUp);
      });
    });
  }

  _openPanelLayoutModal(modus) {
    if (!this._panelLayoutModalEl) return;
    const builders = this._panelSectionBuilders(modus);
    const available = Object.keys(builders).filter((k) => builders[k]);
    const layout = this._panelLayout();
    const saved = layout.filter((e) => available.includes(e.key));
    const visibleMap = new Map(saved.map((e) => [e.key, e.visible]));
    const order = this._panelLayoutFullOrder(available, layout);

    const SIZE_LABELS = { third: "⅓", half: "½", twothirds: "⅔", full: "▭" };
    this._pl.list.innerHTML = "";
    for (const key of order) {
      const visible = visibleMap.has(key) ? visibleMap.get(key) : true;
      const size = this._panelLayoutSize(key, layout);
      const row = document.createElement("div");
      row.className = "panel-layout-row";
      row.dataset.key = key;
      row.dataset.size = size;
      row.innerHTML = `
        <span class="panel-layout-handle"><ha-icon icon="mdi:drag"></ha-icon></span>
        <label class="panel-layout-label">
          <input type="checkbox" ${visible ? "checked" : ""}>
          <span>${this._panelLayoutLabel(key, modus)}</span>
        </label>
        <div class="panel-layout-sizes">
          ${Object.entries(SIZE_LABELS).map(([s, label]) => `
            <button type="button" class="panel-layout-size-btn${s === size ? " active" : ""}" data-size="${s}" title="${s}">${label}</button>
          `).join("")}
        </div>
      `;
      row.querySelectorAll(".panel-layout-size-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          row.dataset.size = btn.dataset.size;
          row.querySelectorAll(".panel-layout-size-btn").forEach((b) => b.classList.toggle("active", b === btn));
        });
      });
      this._pl.list.appendChild(row);
    }
    this._makeReorderable(this._pl.list);
    this._panelLayoutModalEl.classList.remove("hidden");
  }

  _closePanelLayoutModal() {
    if (this._panelLayoutModalEl) this._panelLayoutModalEl.classList.add("hidden");
  }

  _updateBetaEvccPlan() {
    const r = this._r;
    if (!r.betaPlanCard) return;
    const eid = this._eid("evcc_charge_plan");
    const s = eid ? this._hass.states[eid] : null;
    // Karte selbst nur ausblenden, wenn ueberhaupt kein evcc-State vorliegt
    // (kein evcc_host konfiguriert/erreichbar) -- analog _updateBetaWallbox().
    const available = !!s && s.state !== "unavailable";
    r.betaPlanCard.classList.toggle("hidden", !available);
    if (!available) return;

    // Aktueller Stand -- immer sichtbar, unabhaengig vom Plan-Status,
    // dieselben Quellen wie _updateBetaSoc()/RangeEstimateSensor.
    const socEid = this._eid("soc_entity");
    const soc = socEid ? parseFloat(this._raw(socEid) ?? NaN) : NaN;
    const rangeEid = this._eid("range_estimate");
    const range = rangeEid ? parseFloat(this._raw(rangeEid) ?? NaN) : NaN;
    const socText = isNaN(soc) ? "—" : `${Math.round(soc)}%`;
    const rangeText = isNaN(range) ? "—" : `${this._fmtNum(range, 0)} km`;
    r.betaPlanCurrent.textContent = `${socText} · ${rangeText}`;

    const hasPlan = s.state && s.state !== "unknown";
    r.betaPlanStatus.classList.toggle("hidden", !hasPlan);
    r.betaPlanClearBtn.classList.toggle("hidden", !hasPlan);
    if (hasPlan) {
      const attrs = s.attributes || {};
      const targetSoc = typeof attrs.target_soc === "number" ? `${Math.round(attrs.target_soc)}%` : "—";
      r.betaPlanTarget.textContent = `${targetSoc} bis ${this._fmtDate(new Date(s.state).getTime() / 1000)}`;
      const projStart = attrs.projected_start ? new Date(attrs.projected_start).getTime() / 1000 : null;
      r.betaPlanStartRow.classList.toggle("hidden", !projStart);
      if (projStart) r.betaPlanStart.textContent = this._fmtDate(projStart);
      r.betaPlanActive.textContent = attrs.aktiv ? "Lädt gerade nach Plan" : "Geplant";
      const erwartung = typeof attrs.erwartung === "string" ? attrs.erwartung : null;
      r.betaPlanErwartungRow.classList.toggle("hidden", !erwartung);
      if (erwartung) r.betaPlanErwartung.textContent = erwartung;
    }
  }

  _updateUebersichtBeta() {
    const r = this._r;
    // Nutzerfehler 2026-09-23: "ladeplan wird allerdings wenn man die karte
    // einzeln auswaehlt nicht angezeigt" -- Ursache war zweigeteilt: (1)
    // dieser Guard hing an r.betaHeroCost, das es nur noch gibt, wenn die
    // Nutzer:in "hero" ueberhaupt eingeblendet hat -- war sie ausgeblendet,
    // brach die GESAMTE Funktion hier sofort ab, noch bevor irgendeine
    // andere (sichtbare!) Karte aktualisiert wurde. r.betaPendingChargePill
    // wird dagegen IMMER gebaut (Pending-Pill-Zeile ist nie Teil des
    // anpassbaren Layouts), also ein verlaesslicher Indikator "wurde
    // _buildUebersichtBeta() ueberhaupt schon aufgerufen". (2) siehe die
    // beiden neuen if(r.betaHeroCost)/if(r.betaKpiEur100)-Bloecke weiter
    // unten -- die griffen vorher ungeschuetzt auf ggf. gar nicht gebaute
    // Karten zu, was mit einer TypeError die Funktion an genau dieser
    // Stelle abbrach (u.a. VOR dem _updateBetaEvccPlan()-Aufruf ganz unten).
    if (!r.betaPendingChargePill) return;
    const modus = this._ladeModus();

    // Getrennte blinkende Pills fuer offene Fremdladungen/Fahrten -- oeffnen
    // dieselben Bestaetigen/Verwerfen-Karten wie #est-card (Fahrzeuge-Tab),
    // siehe _buildPendingModal()/_renderPendingCharges()/_renderPendingTrips().
    const pendingCharges = this._pendingList("pending", "offene_ladungen");
    const pendingTrips = this._pendingList("trip_pending", "offene_fahrten");
    r.betaPendingChargePill.classList.toggle("hidden", pendingCharges.length === 0);
    if (pendingCharges.length > 0) {
      r.betaPendingChargePillText.textContent = pendingCharges.length === 1
        ? "1 offene Fremdladung"
        : `${pendingCharges.length} offene Fremdladungen`;
    }
    r.betaPendingTripPill.classList.toggle("hidden", pendingTrips.length === 0);
    if (pendingTrips.length > 0) {
      r.betaPendingTripPillText.textContent = pendingTrips.length === 1
        ? "1 offene Fahrt"
        : `${pendingTrips.length} offene Fahrten`;
    }
    // Wenn die aktuell fokussierte Art (siehe _openPendingModal()) waehrend
    // das Popup offen ist leer laeuft (z.B. letzte Fremdladung bestaetigt),
    // schliessen -- auch wenn die JEWEILS ANDERE Art noch offene Eintraege
    // hat, denn die wird ja gerade ausgeblendet gezeigt.
    const focus = this._pendingModalFocus;
    const focusedEmpty = focus === "charges" ? pendingCharges.length === 0
      : focus === "trips" ? pendingTrips.length === 0
      : pendingCharges.length === 0 && pendingTrips.length === 0;
    if (focusedEmpty) this._closePendingModal();
    this._applyPendingModalFilter(pendingCharges, pendingTrips);
    this._renderPendingCharges(pendingCharges, this._pendingModalCharges);
    this._renderPendingTrips(pendingTrips, this._pendingModalTrips);

    // "hero"-Sektion kann jetzt ausgeblendet sein (siehe Panel-Layout) --
    // eigener Guard statt Annahme, dass r.betaHeroCost immer existiert.
    if (r.betaHeroCost) {
      r.betaHeroCost.textContent = this._num("cost_month", 2);

      // Hero-Untertitel: NUR "Vormonat X EUR". "differenz_vorperiode" ist,
      // trotz des Namens, KEINE Differenz zwischen den Monaten, sondern
      // bereits der komplette Vormonats-Betrag selbst -- siehe sensor.py::
      // _CostPeriodSensor.native_value() (cost - baseline = Verbrauch seit
      // Periodenbeginn) vs. engine.update_period_baseline()'s "prev"
      // (= Baseline-Differenz zum ROLLOVER-Zeitpunkt = exakt der Verbrauch
      // der GESAMTEN abgeschlossenen Vorperiode, dieselbe Formel nur fuer
      // die alte statt die laufende Periode ausgewertet). KEIN "Ø"-Wert:
      // dafuer braeuchte es eine echte Mehrmonats-Reihe, die es (noch) nicht
      // gibt -- siehe Kommentar in _buildUebersichtBeta() zur
      // zurueckgestellten Monatshistorie. Fehlt der Vormonats-Datenpunkt
      // (allererster Monat seit Einrichtung), entfaellt die Zeile komplett
      // statt einen Fantasiewert zu zeigen.
      const costEid = this._eid("cost_month");
      const costState = costEid ? this._hass.states[costEid] : null;
      const vormonat = costState && costState.attributes ? costState.attributes.differenz_vorperiode : null;
      const hasVormonat = typeof vormonat === "number";
      r.betaHeroSub.classList.toggle("hidden", !hasVormonat);
      if (hasVormonat) {
        r.betaHeroSub.innerHTML = `Vormonat <span class="mono">${this._fmtNum(vormonat, 2)}</span> €`;
      }
    }

    const locEid = this._eid("charging_location_breakdown");
    const locState = locEid ? this._hass.states[locEid] : null;
    const locAttrs = (locState && locState.attributes) || {};
    const fmt = (v, decimals = 1) => (typeof v === "number" ? this._fmtNum(v, decimals) : "—");

    // "kpi"-Sektion kann jetzt ausgeblendet sein (siehe Panel-Layout) --
    // locEid/locState/locAttrs/fmt bleiben trotzdem oben unbedingt berechnet,
    // die braucht _updateBetaLadeortBars()/_updateBetaAcDc() weiter unten
    // unabhaengig von der KPI-Sichtbarkeit.
    if (r.betaKpiEur100) {
      r.betaKpiEur100.textContent  = fmt(locAttrs.eur_je_100km, 2);
      r.betaKpiSavings.textContent = this._num("savings", 2);
      r.betaKpiCo2.textContent     = this._num("co2_savings", 1);
    }

    this._updateBetaComparisonBars();

    if (modus === "nur_auswaerts") {
      this._updateBetaLastCharge();
      this._updateBetaAcDc(locAttrs);
    } else {
      this._updateBetaSoc();
      this._updateBetaWallbox();
      this._updateBetaLadeortBars(locAttrs);
    }

    this._updateBetaEvccMode();
    if (modus !== "nur_auswaerts") this._updateBetaEvccPlan();
  }

  // Fahrzeug-SoC-Zeile (Aufgabe 3.2) -- Quelle wie Fahrzeug-Tab
  // (_eid("soc_entity")), NICHT evcc_live_attrs().vehicle_soc.
  _updateBetaSoc() {
    const r = this._r;
    if (!r.betaSocVal) return;
    const socEid = this._eid("soc_entity");
    const soc = socEid ? parseFloat(this._raw(socEid) ?? NaN) : NaN;
    r.betaSocVal.innerHTML = isNaN(soc) ? "—" : `${Math.round(soc)}<small>%</small>`;
    if (!isNaN(soc)) r.betaSocFill.style.width = `${Math.max(0, Math.min(100, soc))}%`;
  }

  // Vergleich zum Verbrenner (Proportionsbalken) -- dieselben Werte/Formeln
  // wie im (inzwischen archivierten) klassischen Übersicht-Tab, hier
  // bewusst dupliziert statt eine gemeinsame Methode aufzurufen, da jene
  // zusaetzlich auf eine dort gebaute, hier nicht vorhandene Ausgaben-
  // Karte angewiesen war.
  _updateBetaComparisonBars() {
    const r = this._r;
    if (!r.betaCmpEvVal) return;
    const savEid = this._eid("savings");
    const savState = savEid ? this._hass.states[savEid] : null;
    const savAttr = savState ? (savState.attributes || {}) : {};
    const evCost   = parseFloat(savAttr.kosten_ev_gesamt);
    const verbCost = parseFloat(savAttr.kosten_verbrenner_geschaetzt);
    const fmt2 = (v) => (isNaN(v) ? "—" : this._fmtNum(v, 2));
    r.betaCmpEvVal.textContent   = fmt2(evCost) + (isNaN(evCost) ? "" : " €");
    r.betaCmpVerbVal.textContent = fmt2(verbCost) + (isNaN(verbCost) ? "" : " €");
    const maxCost = Math.max(isNaN(evCost) ? 0 : evCost, isNaN(verbCost) ? 0 : verbCost, 0.01);
    r.betaCmpEvFill.style.width   = isNaN(evCost) ? "0%" : `${Math.max(2, Math.round(evCost / maxCost * 100))}%`;
    r.betaCmpVerbFill.style.width = isNaN(verbCost) ? "0%" : `${Math.max(2, Math.round(verbCost / maxCost * 100))}%`;
  }

  // Ladeort-Aufschluesselung (Proportionsbalken) -- ersetzt
  // _updateBetaLadeort() (alte Zahlen-Tabelle) fuer gemischt/nur_zuhause.
  _updateBetaLadeortBars(locAttrs) {
    const r = this._r;
    if (!r.betaLocCard) return;
    const fmt = (v, decimals = 1) => (typeof v === "number" ? this._fmtNum(v, decimals) : "—");
    const heim = locAttrs.heim;
    const fremd = locAttrs.fremd;
    r.betaLocCard.classList.toggle("hidden", !heim && !fremd);
    const homePct = heim && typeof heim.kwh_anteil_pct === "number" ? heim.kwh_anteil_pct : 0;
    const extPct  = fremd && typeof fremd.kwh_anteil_pct === "number" ? fremd.kwh_anteil_pct : 0;
    r.betaLocHomeFill.style.width = `${homePct}%`;
    r.betaLocExtFill.style.width  = `${extPct}%`;
    r.betaLocHomeVal.textContent = heim ? `${fmt(heim.kwh, 1)} kWh` : "—";
    r.betaLocExtVal.textContent  = fremd ? `${fmt(fremd.kwh, 1)} kWh` : "—";
  }

  // Orthogonal zum Heim-/Fremdlade-Modus (evcc-Steuerung betrifft nur
  // Heimladen, laeuft aber unabhaengig vom obigen if/else), daher ausserhalb
  // davon und immer aufgerufen.
  _updateBetaEvccMode() {
    const r = this._r;
    if (!r.betaEvccCard) return;
    const eid = this._eid("evcc_mode_control");
    const s = eid ? this._hass.states[eid] : null;
    const attrs = (s && s.attributes) || {};
    const active = !!attrs.aktiv && s.state && s.state !== "unknown" && s.state !== "unavailable";
    r.betaEvccCard.classList.toggle("hidden", !active);
    if (!active) return;

    r.betaEvccModeLabel.textContent = this._evccModeLabel(s.state);
    r.betaEvccDot.style.background = this._evccModeColor(s.state);

    const pct = (v) => (typeof v === "number" ? `${Math.round(v)} %` : "—");
    const kwh = (v) => (typeof v === "number" ? `${this._fmtNum(v, 1)} kWh` : "—");
    r.betaEvccMinSoc.textContent      = pct(attrs.min_soc);
    r.betaEvccTargetSoc.textContent   = pct(attrs.target_soc);
    r.betaEvccPvFuerAuto.textContent  = kwh(attrs.pv_fuer_auto_kwh);
    r.betaEvccLastWritten.textContent = this._fmtDate(attrs.zuletzt_geschrieben);

    // Rest-Bedarf heute: Endwert direkt sichtbar, komplette Rechenkette als
    // Tooltip -- analog dem Erklaerungs-Muster am Kartentitel in
    // _buildBetaAcDcCard(), hier aber pro Zeile, da die Kette sich auf
    // GENAU diesen Wert bezieht.
    r.betaEvccRestHeute.textContent = kwh(attrs.rest_heute_kwh);
    const chainParts = [];
    if (typeof attrs.rest_heute_roh_kwh === "number") chainParts.push(`Fahrzeug-Bedarf ${this._fmtNum(attrs.rest_heute_roh_kwh, 1)} kWh`);
    if (typeof attrs.pv_rest_heute_roh_kwh === "number") chainParts.push(`PV-Prognose ${this._fmtNum(attrs.pv_rest_heute_roh_kwh, 1)} kWh`);
    if (typeof attrs.haus_rest_heute_kwh === "number" && attrs.haus_rest_heute_kwh > 0) chainParts.push(`abzüglich Haus/Speicher ${this._fmtNum(attrs.haus_rest_heute_kwh, 1)} kWh`);
    r.betaEvccRestHeute.title = chainParts.length ? chainParts.join(" · ") : "";

    // Fehlende SoC-Steuerung (siehe Repair-Issue evcc_soc_scope_failed)
    // sichtbar machen statt nur im Log/unter Einstellungen -> System ->
    // Repariere zu verstecken -- Modus wird trotzdem gesetzt (siehe
    // coordinator.py::_async_apply_evcc_mode_control()), daher kein
    // Blockieren der ganzen Karte, nur ein Hinweis. Min- und Ziel-SoC haben
    // eigene, unabhaengig geprobte Scopes (min_soc_scope/limit_soc_scope,
    // siehe dort) statt eines gemeinsamen "soc_scope" -- der Hinweis feuert,
    // sobald mindestens einer davon fehlt.
    const scopeOk = attrs.min_soc_scope != null && attrs.limit_soc_scope != null;
    r.betaEvccScopeWarnRow.classList.toggle("hidden", scopeOk);

    // Pause-Status (siehe coordinator.py::async_set_evcc_mode_control_
    // pause()) -- reiner Anzeige-Sync wie r.betaWbBalancingToggle oben,
    // kein Sonderfall fuer "gerade angeklickt" noetig (einfacher Ein/Aus-
    // Schalter, kein Schieberegler mit Zwischenzustaenden).
    r.betaEvccPauseToggle.checked = !!attrs.pausiert;

    // Manueller Modus (siehe coordinator.py::async_set_evcc_manual_mode()) --
    // waehrend aktiv Auswahl/Setzen-Button ausblenden (nichts zum Setzen,
    // solange schon einer laeuft), stattdessen Status + Beenden-Button.
    const manualActive = !!attrs.manueller_modus_aktiv;
    r.betaEvccManualSelect.closest(".beta-evcc-manual-row").classList.toggle("hidden", manualActive);
    r.betaEvccManualStatus.classList.toggle("hidden", !manualActive);
    if (manualActive) {
      r.betaEvccManualStatusText.textContent = this._evccModeLabel(attrs.manueller_modus);
    }
  }

  // Wallbox-Karte (Aufgabe 3.3) -- IMMER dieselbe Struktur, nur der
  // INHALT wechselt je Zustand (laedt/verbunden/nicht verbunden). Die
  // Karte selbst wird nur ausgeblendet, wenn ueberhaupt kein evcc-State
  // vorliegt (kein evcc_host konfiguriert/erreichbar) -- "nicht verbunden"
  // ist dagegen ein regulaerer, sichtbarer Zustand (Fahrzeug einfach nicht
  // angesteckt).
  _updateBetaWallbox() {
    const r = this._r;
    if (!r.betaWbStatusText) return;
    const live = this._evccLive();
    const ev = (key) => (live[key] === undefined || live[key] === null) ? null : live[key];
    const connected = ev("connected");
    r.betaWallboxCard.classList.toggle("hidden", connected == null);
    if (connected == null) return;

    const charging = ev("charging");
    const power = parseFloat(ev("charge_power") ?? NaN);
    const isCharging = charging === true && !isNaN(power) && power > 0.05;
    const state = !connected ? "disconnected" : (isCharging ? "charging" : "connected");

    const STATUS_TEXT = { charging: "Lädt", connected: "Verbunden", disconnected: "Nicht verbunden" };
    r.betaWbStatusText.textContent = STATUS_TEXT[state];
    r.betaWbIcon.classList.toggle("beta-wb-icon-active", state !== "disconnected");

    // Modus-Pill: LIVE-Modus von evcc (kann "off" sein, wenn nichts
    // angesteckt ist) -- NICHT der von ev_assistant empfohlene Modus
    // (siehe _updateBetaEvccMode() fuer Letzteren, eigene Karte).
    const liveMode = ev("mode");
    r.betaWbModePill.textContent = this._evccModeLabel(liveMode);
    r.betaWbModePill.style.setProperty("--pill-color", this._evccModeColor(liveMode));
    r.betaWbModePill.classList.toggle("beta-mode-pill-pulse", state === "charging");

    // Min-Limit/Ladelimit -- IMMER sichtbar (auch nicht verbunden), aus
    // den live "effective*"-evcc-Feldern (siehe coordinator.py::
    // evcc_live_attrs(), korrigiert fuer Fahrzeug-Scope).
    const fmtPct = (v) => (typeof v === "number" ? `${Math.round(v)}%` : "—");
    r.betaWbLimits.textContent = `Min-Limit ${fmtPct(ev("min_soc"))} · Ladelimit ${fmtPct(ev("limit_soc"))}`;

    // Letzte Heimladung -- dieselbe Quelle wie Fahrzeug-Tab (_homeSessions/
    // _homeSessionsFiltered(), siehe _fetchHomeSessions()). 5-Minuten-
    // Cache gemeinsam mit dem Fahrzeug-Tab genutzt/aufgefrischt.
    if (this._homeSessions === null || Date.now() - this._homeSessionsFetchedAt > 300000) {
      this._fetchHomeSessions();
    }
    const lastHome = this._homeSessionsFiltered()[0] || null;

    r.betaWbCaption.textContent = state === "charging"
      ? "Aktuelle Ladung"
      : `Letzte Ladung${lastHome && lastHome.startTs != null ? " · " + this._fmtDate(lastHome.startTs) : ""}`;

    // Ring (Solar/Netz): live waehrend des Ladens, sonst Solaranteil der
    // letzten Session -- bei verbunden/nicht-verbunden gedimmt (~55%).
    const solarPct = state === "charging"
      ? parseFloat(ev("session_solar_pct") ?? NaN)
      : (lastHome && lastHome.solarPct != null ? lastHome.solarPct : NaN);
    const frac = isNaN(solarPct) ? 0 : Math.max(0, Math.min(100, solarPct)) / 100;
    const circ = r.betaWbRingCirc;
    const solarLen = +(circ * frac).toFixed(2);
    r.betaWbRingSolar.setAttribute("stroke-dasharray", `${solarLen} ${circ}`);
    r.betaWbRingGrid.setAttribute("stroke-dasharray", `${+(circ - solarLen).toFixed(2)} ${circ}`);
    r.betaWbRingGrid.setAttribute("stroke-dashoffset", `${-solarLen}`);
    r.betaWbRingWrap.style.opacity = state === "charging" ? "1" : "0.55";

    // Drei Statfelder -- je Zustand unterschiedlicher Inhalt, aber IMMER
    // drei Felder befuellt (siehe Kartenkopf-Kommentar: feste Struktur).
    if (state === "charging") {
      const phases = parseInt(ev("phases_active") ?? "3", 10) || 3;
      const durSec = parseFloat(ev("charge_duration") ?? NaN);
      r.betaWbStat1Val.textContent   = !isNaN(power) ? this._fmtNum(power, 1) : "—";
      r.betaWbStat1Label.textContent = "kW";
      r.betaWbStat2Val.textContent   = String(phases);
      r.betaWbStat2Label.textContent = "Phasen";
      r.betaWbStat3Val.textContent   = (!isNaN(durSec) && durSec > 0) ? this._fmtDuration(Math.round(durSec / 60)) : "—";
      r.betaWbStat3Label.textContent = "Dauer";
    } else {
      r.betaWbStat1Val.textContent   = lastHome && lastHome.kwh != null ? this._fmtNum(lastHome.kwh, 2) : "—";
      r.betaWbStat1Label.textContent = "kWh";
      r.betaWbStat2Val.textContent   = lastHome && lastHome.durMin != null ? this._fmtDuration(lastHome.durMin) : "—";
      r.betaWbStat2Label.textContent = "Dauer";
      r.betaWbStat3Val.textContent   = lastHome && lastHome.pricePerKwh != null ? this._fmtNum(lastHome.pricePerKwh, 3) + " €/kWh" : "—";
      r.betaWbStat3Label.textContent = "Preis";
    }

    // Puffer-Schieberegler: aktuellen Wert (Override oder Konfigurations-
    // Default, siehe coordinator.py::_usage_profile_buffer_pct()) aus dem
    // "puffer_prozent"-Attribut von usage_profile_tomorrow uebernehmen --
    // aber NICHT, waehrend der Nutzer den Regler gerade selbst zieht,
    // sonst reisst ein zwischenzeitliches Update den Wert unter der Maus
    // weg (analog dem Scroll-Erhalt an anderer Stelle im Panel).
    if (this.shadowRoot.activeElement !== r.betaWbBufferSlider) {
      const needEid = this._eid("usage_profile_tomorrow");
      const needState = needEid ? this._hass.states[needEid] : null;
      const bufferPct = needState && needState.attributes ? parseFloat(needState.attributes.puffer_prozent) : NaN;
      if (!isNaN(bufferPct)) {
        r.betaWbBufferSlider.value = bufferPct;
        r.betaWbBufferVal.textContent = `${this._fmtNum(bufferPct, 0)}%`;
      }
    }

    // Balancing-Schalter: aktuellen Wert (Override oder Konfigurations-
    // Default, siehe coordinator.py::_weekly_full_charge_enabled()) sowie
    // Status/naechste Faelligkeit aus den evcc_mode_control-Attributen
    // (siehe sensor.py::EvccModeControlSensor) uebernehmen -- nicht
    // waehrend der Nutzer den Schalter gerade selbst antippt, analog dem
    // Puffer-Regler oben.
    if (this.shadowRoot.activeElement !== r.betaWbBalancingToggle) {
      const evccEid = this._eid("evcc_mode_control");
      const evccState = evccEid ? this._hass.states[evccEid] : null;
      const evccAttrs = (evccState && evccState.attributes) || {};
      r.betaWbBalancingToggle.checked = !!evccAttrs.balancing_enabled;
      if (evccAttrs.balancing_aktiv) {
        r.betaWbBalancingStatus.textContent = "Aktiv — lädt gerade auf 100% (Zellbalancing)";
      } else if (evccAttrs.balancing_enabled && evccAttrs.naechste_vollladung_faellig_ts != null) {
        r.betaWbBalancingStatus.textContent = `Nächste fällig: ${this._fmtDate(evccAttrs.naechste_vollladung_faellig_ts)}`;
      } else {
        r.betaWbBalancingStatus.textContent = "";
      }
    }
  }

  _updateBetaLastCharge() {
    const r = this._r;
    if (!r.betaLastDate) return;
    const eid = this._eid("last_cost");
    const s = eid ? this._hass.states[eid] : null;
    const attrs = (s && s.attributes) || {};
    const hasAny = !!s && s.state !== "unavailable" && s.state !== "unknown";

    const startTs = attrs.start_ts;
    r.betaLastDateRow.classList.toggle("hidden", startTs == null);
    if (startTs != null) r.betaLastDate.textContent = this._fmtDate(startTs);

    r.betaLastKwhRow.classList.toggle("hidden", !hasAny);
    if (hasAny) r.betaLastKwh.textContent = this._fmtNum(attrs.kwh, 2) + " kWh";

    r.betaLastCostRow.classList.toggle("hidden", !hasAny);
    if (hasAny) r.betaLastCost.textContent = this._fmtNum(parseFloat(s.state), 2) + " EUR";

    const price = attrs.preis_kwh;
    r.betaLastPriceRow.classList.toggle("hidden", price == null);
    if (price != null) r.betaLastPrice.textContent = this._fmtNum(price, 3) + " EUR/kWh";

    const durStr = this._fmtDuration(attrs.dauer_min);
    r.betaLastDurationRow.classList.toggle("hidden", durStr == null);
    if (durStr != null) r.betaLastDuration.textContent = durStr;

    r.betaLastChargeCard.classList.toggle("hidden", !hasAny);
  }

  _updateBetaAcDc(locAttrs) {
    const r = this._r;
    if (!r.betaAcdcAcCol) return;
    const fmt = (v, decimals = 1) => (typeof v === "number" ? this._fmtNum(v, decimals) : "—");
    const acDc = locAttrs.ac_dc || {};
    r.betaAcdcAcCol.classList.toggle("hidden", !acDc.ac);
    if (acDc.ac) {
      r.betaAcdcAcKwh.textContent = fmt(acDc.ac.kwh, 1);
      r.betaAcdcAcPct.textContent = fmt(acDc.ac.kwh_anteil_pct, 1);
    }
    r.betaAcdcDcCol.classList.toggle("hidden", !acDc.dc);
    if (acDc.dc) {
      r.betaAcdcDcKwh.textContent = fmt(acDc.dc.kwh, 1);
      r.betaAcdcDcPct.textContent = fmt(acDc.dc.kwh_anteil_pct, 1);
    }
    r.betaAcdcCard.classList.toggle("hidden", !acDc.ac && !acDc.dc);
  }

  // --- Styles -----------------------------------------------------------------

  _buildStyles() {
    const el = document.createElement("style");
    el.textContent = `
      :host {
        display: block; height: 100%;
        --accent: #8fbd39;
        /* Zweiter Akzent (Petrol/Cyan) fuer Fahrzeug-/Ladezustand (SoC,
           Wallbox-Status, siehe Uebersicht-Beta) -- bewusst blauer als das
           bestehende --c-trip (Teal #14b8a6, an "Fahrt" gebunden, siehe
           weiter unten), damit --accent (Lime) fuer Ersparnis/CO2/Solar
           reserviert bleibt statt dekorativ auf jede positive Zahl
           gestreut zu werden. */
        --accent-2: #0891b2;
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
        /* Lokaler Mono-Stack fuer Zahlen-Readouts -- bewusst kein
           Web-Font-Import (siehe font-family oben), nur System-Monospace. */
        --font-mono: ui-monospace, SFMono-Regular, Consolas, monospace;
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
      /* Scrollbare Leiste mit Pfeil-Buttons (Tab-Leiste, Fahrzeug-Umschalter) --
         siehe _buildScrollWrap(). */
      .scroll-wrap { display: flex; align-items: center; gap: 4px; min-width: 0; flex: 1; }
      .tabs-wrap { align-items: stretch; height: 100%; }
      .scroll-arrow {
        flex-shrink: 0; align-self: center; display: flex; align-items: center; justify-content: center;
        width: 30px; height: 30px; border-radius: 8px; border: 1px solid var(--line-s);
        background: none; cursor: pointer; color: var(--ink-mid); --mdc-icon-size: 16px;
        transition: color 0.15s, border-color 0.15s;
      }
      .scroll-arrow:hover { color: var(--ink); border-color: var(--ink-mid); }
      .tabs { display: flex; align-items: stretch; gap: 2px; height: 100%; min-width: 0; flex: 1; overflow-x: auto; scrollbar-width: none; }
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
        display: flex; align-items: center; padding: 10px 30px; gap: 4px;
        border-bottom: 1px solid var(--line); flex-shrink: 0;
      }
      .vt-bar-scroll { display: flex; align-items: center; min-width: 0; flex: 1; overflow-x: auto; scrollbar-width: none; }
      .vt-bar-scroll::-webkit-scrollbar { display: none; }

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
      .charts-grid { display: grid; grid-template-columns: repeat(var(--charts-cols, 3), 1fr); gap: 0; margin-top: 10px; }
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
      .vh-3col { display: grid; grid-template-columns: repeat(var(--vh3-cols, 3), 1fr); gap: var(--gap); align-items: start; }
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
      .badge-urlaub { margin-left: auto; background: var(--bg-0); color: var(--ink-dim); border: 1px solid var(--line); }
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
      .wd-bar.no-data  { background: transparent; border: 1px dashed var(--line-s); }
      .wd-label { font-size: 0.7rem; color: var(--ink-dim); margin-top: 6px; font-weight: 600; }

      /* Mischpreis-Skala (Analyse-Tab: Wirtschaftlichkeit Netz-Zuschuss) --
         horizontaler Farbverlauf guenstig (Einspeisung) -> teuer (Netz),
         mit Markern fuer die konfigurierte Schwelle und den aktuellen
         Mischpreis, siehe _updateAnalyseMischpreis(). */
      .mischpreis-scale-wrap { margin: 10px 0 4px; }
      .mischpreis-scale {
        position: relative; height: 10px; border-radius: 5px; margin-bottom: 6px;
        background: linear-gradient(to right, #4ade80, #f97316, #ef4444);
      }
      .mischpreis-marker {
        position: absolute; top: -4px; width: 2px; height: 18px;
        background: var(--ink); transform: translateX(-1px); transition: left 0.4s ease;
      }
      .mischpreis-marker-schwelle { background: var(--ink-mid); opacity: 0.85; }
      .mischpreis-marker-aktuell { width: 3px; background: var(--ink); box-shadow: 0 0 0 1px var(--bg-1); }
      .mischpreis-scale-labels { display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--ink-dim); }

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

      /* Anbieter-Verteilung (Analyse-Tab) -- nutzt dieselbe Balken-Optik
         wie veh-soc-bar-wrap/-fill, nur horizontal ueber die volle Breite
         statt der festen 120px, siehe _updateAnalyse(). */
      .anbieter-bar-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
      .anbieter-bar-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
      .anbieter-bar-row .veh-soc-bar-wrap { width: 100%; }
      .anbieter-bar-label { flex-shrink: 1; min-width: 0; font-size: 0.82rem; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .anbieter-bar-val { flex-shrink: 0; text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 1px; }
      .anbieter-bar-val-main { font-size: 0.82rem; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
      .anbieter-bar-val-sub { font-size: 0.68rem; color: var(--ink-dim); font-variant-numeric: tabular-nums; }

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
      /* Gruppierte Variante (siehe _buildWartung()/_renderWartungList()) --
         Gruppen stehen untereinander, jede Gruppe ist innen wieder eine
         umbrechende Reihe wie das normale .hist-edit-form. */
      .hist-edit-form.grouped { flex-direction: column; align-items: stretch; gap: 14px; }
      .wt-group { display: flex; align-items: flex-end; gap: 10px; flex-wrap: wrap; }
      .wt-group-title { width: 100%; }
      .wt-group-hint { width: 100%; margin-bottom: 2px; }
      .wt-group-actions { justify-content: flex-end; }
      /* HU/TÜV: festes Datum vor dem Intervall, ohne die DOM-Reihenfolge
         (und damit die Feldreihenfolge bei Inspektion/"eigene") anzufassen. */
      .wt-group-faelligkeit.hu-mode .wt-fld-fest { order: -1; }
      .hist-delete-confirm {
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 10px;
      }
      .hist-delete-text { font-size: 12px; color: var(--ink-mid); }

      /* Uebersicht (Beta) -- Konzept A */
      .beta-pending-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0 0 12px; }
      .beta-layout-btn {
        margin-left: auto; border: 1px solid var(--line); background: var(--bg-0); color: var(--ink-mid);
        border-radius: 8px; padding: 6px 8px; cursor: pointer; display: flex; align-items: center;
        --mdc-icon-size: 18px;
      }
      .beta-layout-btn:hover { color: var(--ink); }
      .panel-layout-hint { font-size: 0.78rem; color: var(--ink-mid); margin-bottom: 4px; }
      .panel-layout-list { display: flex; flex-direction: column; gap: 6px; position: relative; }
      .panel-layout-row {
        display: flex; align-items: center; flex-wrap: wrap; gap: 8px 10px; border: 1px solid var(--line);
        border-radius: 8px; padding: 8px 10px; background: var(--bg-0);
      }
      /* Ghost+Platzhalter-Drag (siehe _makeReorderable()): die gezogene
         Zeile wird komplett aus dem Listenfluss herausgeloest und folgt dem
         Zeiger 1:1, statt bei jedem Tick im echten Listenfluss verschoben
         zu werden (das flackerte vorher). */
      .panel-layout-row.dragging {
        position: fixed; z-index: 1000; box-shadow: 0 4px 16px rgba(0,0,0,0.35);
        opacity: 0.97; pointer-events: none;
      }
      .panel-layout-placeholder {
        border: 2px dashed var(--line); border-radius: 8px; background: transparent;
      }
      .panel-layout-handle {
        display: flex; align-items: center; color: var(--ink-dim); cursor: grab;
        touch-action: none; --mdc-icon-size: 20px;
      }
      .panel-layout-label { display: flex; align-items: center; gap: 8px; font-size: 0.88rem; color: var(--ink); cursor: pointer; flex: 1 1 140px; }
      .panel-layout-label input { accent-color: var(--accent-2); cursor: pointer; }
      .panel-layout-sizes { display: flex; gap: 4px; margin-left: auto; }
      .panel-layout-size-btn {
        border: 1px solid var(--line); background: var(--bg-1); color: var(--ink-mid);
        border-radius: 6px; width: 28px; height: 28px; font-size: 0.85rem; cursor: pointer;
      }
      .panel-layout-size-btn.active { border-color: var(--accent-2); color: var(--accent-2); }
      .beta-pending-pill {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 6px 14px; border-radius: 9999px;
        font-size: 0.78rem; font-weight: 700; cursor: pointer; --mdc-icon-size: 15px;
        animation: pending-pill-blink 1.6s ease-in-out infinite;
      }
      .beta-pending-pill:hover { filter: brightness(1.12); }
      /* Farben = dieselben --c-ext/--c-trip-Variablen wie ueberall sonst
         fuer "Fremdladung"/"Fahrt" (card-ext/card-trip, cleg-dot, siehe
         :host-Definition weiter unten) -- statt eigener Ad-hoc-Farben. */
      .beta-pending-pill-charge {
        --pending-color: var(--c-ext);
        border: 1px solid color-mix(in oklab, var(--c-ext) 55%, transparent);
        background: color-mix(in oklab, var(--c-ext) 18%, var(--bg-1));
        color: var(--c-ext);
      }
      .beta-pending-pill-trip {
        --pending-color: var(--c-trip);
        border: 1px solid color-mix(in oklab, var(--c-trip) 55%, transparent);
        background: color-mix(in oklab, var(--c-trip) 18%, var(--bg-1));
        color: var(--c-trip);
      }
      @keyframes pending-pill-blink {
        0%, 100% { box-shadow: 0 0 0 0 color-mix(in oklab, var(--pending-color) 55%, transparent); }
        50% { box-shadow: 0 0 0 6px color-mix(in oklab, var(--pending-color) 0%, transparent); }
      }
      @media (prefers-reduced-motion: reduce) { .beta-pending-pill { animation: none; } }
      .pending-modal-overlay {
        position: fixed; inset: 0; z-index: 50; background: rgba(0,0,0,0.55);
        display: flex; align-items: center; justify-content: center; padding: 16px;
      }
      .pending-modal-overlay.hidden { display: none; }
      .pending-modal {
        background: var(--bg-1); border: 1px solid var(--line); border-radius: var(--radius);
        max-width: 520px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 0 0 16px;
      }
      .pending-modal-head {
        display: flex; align-items: center; gap: 9px; padding: 14px var(--pad);
        position: sticky; top: 0; background: var(--bg-1); border-bottom: 1px solid var(--line);
        --mdc-icon-size: 17px;
      }
      .pending-modal-head .ic { color: var(--ink-dim); display: grid; place-items: center; }
      .pending-modal-head h2 { flex: 1; margin: 0; font-size: 0.95rem; color: var(--ink); }
      .pending-modal-close {
        border: none; background: none; color: var(--ink-mid); cursor: pointer;
        display: flex; align-items: center; padding: 4px; --mdc-icon-size: 18px;
      }
      .pending-modal-close:hover { color: var(--ink); }
      .pending-modal-body { padding: 14px var(--pad) 0; display: flex; flex-direction: column; gap: 14px; }
      @media (max-width: 500px) {
        .pending-modal-overlay { padding: 0; align-items: flex-end; }
        .pending-modal { max-width: none; max-height: 88vh; border-radius: var(--radius) var(--radius) 0 0; }
      }
      /* Eigene Klassen statt pending-modal-* (Nutzerwunsch 2026-09-22:
         immer mittig, auch auf schmalen Bildschirmen -- KEIN Bottom-Sheet
         wie beim Fahrten/Fremdladungen-Popup). */
      .ladeplan-modal-overlay {
        position: fixed; inset: 0; z-index: 50; background: rgba(0,0,0,0.55);
        display: flex; align-items: center; justify-content: center; padding: 16px;
      }
      .ladeplan-modal-overlay.hidden { display: none; }
      .ladeplan-modal {
        background: var(--bg-1); border: 1px solid var(--line); border-radius: var(--radius);
        max-width: 420px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 0 0 16px;
      }
      .ladeplan-modal-head {
        display: flex; align-items: center; gap: 9px; padding: 14px var(--pad);
        position: sticky; top: 0; background: var(--bg-1); border-bottom: 1px solid var(--line);
        --mdc-icon-size: 17px;
      }
      .ladeplan-modal-head .ic { color: var(--ink-dim); display: grid; place-items: center; }
      .ladeplan-modal-head h2 { flex: 1; margin: 0; font-size: 0.95rem; color: var(--ink); }
      .ladeplan-modal-close {
        border: none; background: none; color: var(--ink-mid); cursor: pointer;
        display: flex; align-items: center; padding: 4px; --mdc-icon-size: 18px;
      }
      .ladeplan-modal-close:hover { color: var(--ink); }
      .ladeplan-modal-body { padding: 14px var(--pad) 0; display: flex; flex-direction: column; gap: 14px; }
      .beta-plan-slider-field { gap: 6px; }
      .beta-plan-slider-label { display: flex; justify-content: space-between; align-items: baseline; font-size: 0.78rem; color: var(--ink-mid); }
      .beta-plan-slider-value { font-family: var(--font-mono); font-size: 0.9rem; color: var(--ink); }
      .beta-plan-slider-wrap { position: relative; padding: 8px 0; }
      .beta-plan-slider-wrap input[type="range"] {
        width: 100%; margin: 0; accent-color: var(--accent-2); cursor: pointer;
      }
      /* Reiner senkrechter Strich, KEIN Label mehr (Nutzerwunsch 2026-09-23:
         "entferne die zeile komplett") -- left wird per JS als Prozent-
         position auf dem vollen 0-100-Track gesetzt (aktueller SoC). */
      .beta-plan-slider-mark {
        position: absolute; left: 0; top: 0; bottom: 0; width: 2px;
        background: var(--ink-dim); pointer-events: none;
      }
      .beta-plan-slider-mark.hidden { display: none; }
      .beta-plan-live-feedback {
        font-size: 0.85rem; font-weight: 600; line-height: 1.4; text-align: center;
        border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px;
      }
      .beta-plan-live-feedback.hidden { display: none; }
      .beta-plan-live-feedback.lvl-ok {
        color: #2e7d32; border-color: color-mix(in oklab, #2e7d32 55%, transparent);
        background: color-mix(in oklab, #2e7d32 15%, var(--bg-0));
      }
      .beta-plan-live-feedback.lvl-warn {
        color: #ef6c00; border-color: color-mix(in oklab, #ef6c00 55%, transparent);
        background: color-mix(in oklab, #ef6c00 15%, var(--bg-0));
      }
      .beta-plan-live-feedback.lvl-bad {
        color: #c62828; border-color: color-mix(in oklab, #c62828 55%, transparent);
        background: color-mix(in oklab, #c62828 15%, var(--bg-0));
      }
      /* Frei kombinierbares Karten-Grid (Nutzerwunsch 2026-09-23: "ich
         wuerde das panel gerne in grids aufteilen, so das der nutzer auch
         karten nebeneinander anordnen kann" / "vlt auch die groesse
         aendern kann") -- flex-wrap statt der vorherigen festen 2-Spalten-
         Grids, jede Karte traegt ihre eigene panel-card-size-*-Klasse
         (siehe _buildUebersichtBeta()/_panelLayoutSize()). Feste
         Groessenstufen statt freiem Ziehen/Resize (aufwaendiger,
         fehleranfaelliger). */
      .beta-grid { display: flex; flex-wrap: wrap; gap: var(--gap); align-items: stretch; }
      .beta-grid > * { min-width: 0; }
      .panel-card-size-third     { flex: 0 0 auto; width: calc(33.333% - var(--gap) * 2 / 3); }
      .panel-card-size-half      { flex: 0 0 auto; width: calc(50% - var(--gap) / 2); }
      .panel-card-size-twothirds { flex: 0 0 auto; width: calc(66.666% - var(--gap) / 3); }
      .panel-card-size-full      { flex: 0 0 auto; width: 100%; }
      .hero-card { display: flex; flex-direction: column; justify-content: center; }
      .hero-value { font-size: 2.6rem; font-weight: 800; line-height: 1.1; margin-top: 6px; color: var(--ink); }
      .hero-value .hero-unit { font-size: 1.1rem; font-weight: 600; margin-left: 6px; color: var(--ink-mid); }
      .hero-sub { font-size: 0.85rem; color: var(--ink-mid); margin-top: 6px; }

      /* Zahlen-Readout-Utility (Aufgabe 2: --font-mono) -- ueberall im
         redesignten Uebersicht-Beta-Tab fuer Kennzahlen verwendet. */
      .mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
      .beta-accent { color: var(--accent); }

      /* Redesignte Uebersicht-Beta-Karten-Header: normale Gross-/Klein-
         schreibung statt der sonst ueberall im Panel genutzten
         Grossbuchstaben-Eyebrow-Optik (.card-head h2, siehe dort) --
         bewusst nur fuer diesen Tab gescoped, alle anderen Tabs
         unveraendert. */
      .beta-grid .card-head h2 { text-transform: none; letter-spacing: normal; }

      /* Fahrzeug-SoC-Karte (Aufgabe 3.2) -- kompakte Einzeiler-Karte neben
         dem Hero, kein eigener Kartenkopf/Icon. */
      .beta-soc-card { display: flex; flex-direction: column; justify-content: center; gap: 10px; }
      .beta-soc-row { display: flex; align-items: baseline; justify-content: space-between; }
      .beta-soc-row .bl { color: var(--ink-mid); font-size: 0.85rem; }
      .beta-soc-row .bv { font-size: 1.6rem; font-weight: 800; }
      .beta-soc-bar-wrap { width: 100%; }

      /* Wallbox-Karte (Aufgabe 3.3) -- feste Struktur/Hoehe in allen drei
         Zustaenden (laedt/verbunden/nicht verbunden), siehe
         _updateBetaWallbox(): kein Zustand darf Zeilen ein-/ausblenden. */
      .beta-wallbox-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
      .beta-wallbox-status { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 0.95rem; --mdc-icon-size: 20px; }
      .beta-wb-icon { display: flex; color: var(--ink-dim); transition: color 0.2s ease; }
      .beta-wb-icon.beta-wb-icon-active { color: var(--accent-2); }
      .beta-mode-pill {
        --pill-color: var(--ink-dim);
        display: inline-flex; align-items: center; padding: 4px 12px; border-radius: 9999px;
        font-size: 0.72rem; font-weight: 700; color: var(--pill-color);
        border: 1px solid color-mix(in oklab, var(--pill-color) 45%, transparent);
        background: color-mix(in oklab, var(--pill-color) 12%, transparent);
      }
      .beta-mode-pill.beta-mode-pill-pulse { animation: beta-pill-pulse 1.8s ease-in-out infinite; }
      @keyframes beta-pill-pulse {
        0%, 100% { border-color: color-mix(in oklab, var(--pill-color) 45%, transparent); }
        50% { border-color: color-mix(in oklab, var(--pill-color) 90%, transparent); }
      }
      @media (prefers-reduced-motion: reduce) { .beta-mode-pill.beta-mode-pill-pulse { animation: none; } }
      .beta-wallbox-limits { font-size: 0.78rem; color: var(--ink-mid); margin-top: 10px; }
      .beta-wallbox-caption { font-size: 0.78rem; color: var(--ink-dim); margin-top: 2px; }
      .beta-wallbox-body { display: flex; align-items: center; gap: 20px; margin-top: 14px; }
      .beta-wallbox-ring-wrap { display: flex; flex-direction: column; align-items: center; gap: 8px; flex-shrink: 0; transition: opacity 0.3s ease; }
      .beta-wb-ring-solar, .beta-wb-ring-grid { transition: stroke-dasharray 0.5s ease, stroke-dashoffset 0.5s ease; }
      .beta-wallbox-legend { display: flex; gap: 12px; flex-wrap: wrap; }
      .beta-wallbox-stats { flex: 1; display: flex; justify-content: space-around; gap: 10px; min-width: 0; }
      .statval { font-size: 1.15rem; font-weight: 700; line-height: 1.1; }
      .statlabel { font-size: 0.7rem; color: var(--ink-mid); margin-top: 3px; }
      .beta-wallbox-buffer { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--line); }
      .beta-wb-buffer-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
      .beta-wb-buffer-label { font-size: 0.78rem; color: var(--ink-mid); flex: 1; }
      .beta-wb-buffer-val { font-size: 0.85rem; font-weight: 700; font-family: var(--font-mono); }
      .beta-wb-buffer-reset {
        display: grid; place-items: center; border: none; background: none; color: var(--ink-dim);
        cursor: pointer; padding: 2px; border-radius: 6px; --mdc-icon-size: 16px;
      }
      .beta-wb-buffer-reset:hover { color: var(--ink); background: var(--bg-0); }
      .beta-wb-buffer-slider {
        width: 100%; margin: 0; accent-color: var(--accent-2); cursor: pointer;
      }
      .beta-wallbox-balancing { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); }
      .beta-wb-balancing-row { display: flex; align-items: center; gap: 8px; cursor: pointer; }
      .beta-wb-balancing-toggle { accent-color: var(--accent-2); cursor: pointer; }
      .beta-wb-balancing-label { font-size: 0.78rem; color: var(--ink-mid); }
      .beta-wb-balancing-status { font-size: 0.72rem; margin-top: 4px; min-height: 1em; }

      /* Proportionsbalken (Aufgabe 3.6: Vergleich zum Verbrenner,
         Ladeort-Aufschluesselung) -- ersetzen die frueheren Zahlen-Tabellen. */
      .beta-bar-row + .beta-bar-row { margin-top: 14px; }
      .beta-bar-label { display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 5px; }
      .beta-bar-track { height: 10px; border-radius: 9999px; background: var(--bg-0); overflow: hidden; }
      .beta-bar-fill { height: 100%; border-radius: 9999px; transition: width 0.5s ease; }
      .beta-bar-track-split { display: flex; }
      .beta-bar-track-split .beta-bar-fill { border-radius: 0; transition: width 0.5s ease; }
      .beta-bar-track-split .beta-bar-fill:first-child { border-radius: 9999px 0 0 9999px; }
      .beta-bar-track-split .beta-bar-fill:last-child { border-radius: 0 9999px 9999px 0; }
      .beta-loc-legend { margin-top: 10px; }
      .beta-status-list { display: flex; flex-direction: column; gap: 10px; margin-top: 4px; }
      .beta-status-row { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; font-size: 0.85rem; }
      .beta-status-row .bl { color: var(--ink-mid); }
      .beta-status-row .bv { font-weight: 600; }
      .beta-evcc-badge {
        display: flex; align-items: center; gap: 8px; margin: 2px 0 12px; font-weight: 700; font-size: 0.95rem;
      }
      .beta-evcc-dot {
        width: 10px; height: 10px; border-radius: 50%; background: var(--ink-dim); flex-shrink: 0;
      }
      .beta-evcc-warn { color: #f97316; font-weight: 600; }
      .beta-evcc-pause { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); }
      .beta-evcc-pause-row { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; cursor: pointer; }
      .beta-evcc-pause-row .bl { color: var(--ink-mid); }
      .beta-evcc-pause-toggle { accent-color: var(--accent-2); cursor: pointer; }
      .beta-evcc-manual { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); }
      .beta-evcc-manual-row { display: flex; align-items: center; gap: 8px; }
      .beta-evcc-manual-row select {
        flex: 1; border: 1px solid var(--line); background: var(--bg-0); color: var(--ink);
        border-radius: 8px; padding: 5px 8px; font-size: 0.82rem;
      }
      .beta-evcc-manual-row button, .beta-evcc-manual-status button {
        border: 1px solid var(--accent-2); background: var(--bg-0); color: var(--accent-2);
        font-size: 0.78rem; padding: 6px 12px; border-radius: 8px; cursor: pointer; white-space: nowrap;
      }
      .beta-evcc-manual-row button:hover, .beta-evcc-manual-status button:hover { opacity: 0.8; }
      .beta-evcc-manual-status {
        display: flex; align-items: center; gap: 8px; font-size: 0.82rem;
      }
      .beta-evcc-manual-status .bl { color: var(--ink-mid); }
      .beta-evcc-manual-status .bv { flex: 1; }
      .beta-evcc-manual-status button { border-color: var(--line); color: var(--ink); }
      .beta-plan-status { display: flex; flex-direction: column; gap: 10px; margin-bottom: 12px; }
      .beta-plan-actions { display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid var(--line); }
      .beta-plan-field { display: flex; flex-direction: column; gap: 4px; font-size: 0.78rem; color: var(--ink-mid); }
      .beta-plan-field input {
        border: 1px solid var(--line); background: var(--bg-0); color: var(--ink);
        border-radius: 8px; padding: 5px 8px; font-size: 0.85rem; font-family: var(--font-mono);
      }
      .beta-plan-field input[type="number"] { width: 70px; }
      .beta-plan-buttons { display: flex; gap: 8px; margin-left: auto; justify-content: flex-end; }
      .beta-plan-open-btn, .beta-plan-set-btn, .beta-plan-clear-btn {
        border: 1px solid var(--line); background: var(--bg-0); color: var(--ink);
        font-size: 0.78rem; padding: 6px 12px; border-radius: 8px; cursor: pointer;
      }
      .beta-plan-open-btn, .beta-plan-set-btn { color: var(--accent-2); border-color: var(--accent-2); }
      .beta-plan-open-btn:hover, .beta-plan-set-btn:hover, .beta-plan-clear-btn:hover { opacity: 0.8; }
      @media (max-width: 900px) {
        .panel-card-size-third, .panel-card-size-half, .panel-card-size-twothirds { width: 100%; }
      }
      @container panel (max-width: 900px) {
        .panel-card-size-third, .panel-card-size-half, .panel-card-size-twothirds { width: 100%; }
      }

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
        .wt-group label { flex: 1 1 100%; }
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
        .wt-group label { flex: 1 1 100%; }
      }
    `;
    return el;
  }
}

customElements.define("ev-assistant-panel", EVAssistantPanel);
