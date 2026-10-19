/*
 * ev-assistant-glow-panel.js -- Wrapper, der die Glow-Karte (mg-car-dashboard.js,
 * Kopie aus deepblue120/glow-dashboard, Stand siehe GLOW_VERSION) als zweites
 * Sidebar-Panel einbettet. Das klassische Panel bleibt unveraendert.
 *
 * Die Karte (ab glow-dashboard v3.2) bringt keine fahrzeugspezifischen Defaults
 * mehr mit: Der Wrapper reicht die komplette Panel-Konfiguration als
 * `ev_assistant_panel` durch (Fahrzeugauswahl, api_version-Pruefung) und setzt
 * zusaetzlich die car-Optionen des ersten Fahrzeugs, die die Karte bei
 * mehreren Fahrzeugen selbst wieder verwirft. Siehe weskona/ev_assistant#12.
 */
class EvAssistantGlowPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._panel = null;
    this._card = null;
    this._loading = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._card) this._card.hass = hass;
  }

  set panel(panel) {
    this._panel = panel;
    if (this._card) this._card.setConfig(this._cardConfig());
  }

  set narrow(_narrow) {}

  connectedCallback() {
    if (this._card || this._loading) return;
    this.style.display = "block";
    this.style.height = "100%";
    this.style.overflow = "auto";
    // Die Karte liegt neben diesem Modul; die Cache-Busting-Query wird uebernommen.
    const url = new URL("mg-car-dashboard.js", import.meta.url);
    url.search = new URL(import.meta.url).search;
    this._loading = import(url.href)
      .then(() => this._mount())
      .catch((err) => {
        this.textContent = "Glow-Karte konnte nicht geladen werden: " + err;
      });
  }

  _mount() {
    this._card = document.createElement("mg-car-dashboard");
    this._card.setConfig(this._cardConfig());
    if (this._hass) this._card.hass = this._hass;
    this.replaceChildren(this._card);
  }

  // Panel-Konfiguration (siehe __init__.py::_async_register_panel) -> Kartenkonfiguration.
  // Nur gesetzte Felder uebernehmen, der Rest bleibt bei den Defaults der Karte.
  _cardConfig() {
    const cfg = (this._panel && this._panel.config) || {};
    const ent = cfg.entities || {};
    const car = {};
    const energy = {};
    if (cfg.name) car.name = cfg.name;
    if (cfg.config_entry_id) car.ev_assistant_entry = cfg.config_entry_id;
    if (cfg.evcc_vehicle_name) car.evcc_vehicle = cfg.evcc_vehicle_name;
    if (ent.soc_entity) car.soc = ent.soc_entity;
    if (ent.motor_entity) car.status = ent.motor_entity;
    if (ent.plug_entity) car.cable = ent.plug_entity;
    const power = ent.power_entity || ent.home_entity;
    if (power) energy.car_power = power;
    return { ev_assistant_panel: cfg, car, energy };
  }
}

if (!customElements.get("ev-assistant-glow-panel")) {
  customElements.define("ev-assistant-glow-panel", EvAssistantGlowPanel);
}
