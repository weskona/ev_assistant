"""Config- und Options-Flow fuer ev_assistant.

Pro Signal waehlbar: HA-Entitaet (Vorrang) ODER MQTT-Topic. Dadurch nutzbar
mit Hersteller-Integrationen (Stellantis, VW, ...) und mit WiCAN-MQTT.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DROP_ENDS, CONF_EFFICIENCY, CONF_ERSTZULASSUNG, CONF_HOME_ENTITY,
    CONF_HOME_PRICE_ENTITY, CONF_HOME_PRICE_KWH, CONF_HOME_TEMPLATE, CONF_HOME_TOPIC, CONF_IDLE_TIMEOUT,
    CONF_NOISE, CONF_NOTIFY_SERVICE, CONF_ODO_ENTITY, CONF_POWER_ENTITY, CONF_POWER_IS_AC,
    CONF_POWER_TEMPLATE, CONF_POWER_TOPIC, CONF_PUBLISH_TOPIC,
    CONF_SOC_ENTITY, CONF_SOC_TEMPLATE, CONF_SOC_TOPIC, CONF_START_DELTA,
    CONF_USABLE_KWH, CONF_VEHICLE_HERSTELLER, CONF_VEHICLE_MODELL,
    CONF_VERBRENNER_L_100KM, CONF_VERBRENNER_PRICE_ENTITY, CONF_VERBRENNER_PRICE_PER_LITER,
    CONF_WALLBOX_ENERGY_ENTITY,
    CONF_WALLBOX_ENERGY_TEMPLATE, CONF_WALLBOX_ENERGY_TOPIC,
    DEFAULT_DROP_ENDS,
    DEFAULT_EFFICIENCY, DEFAULT_IDLE_TIMEOUT, DEFAULT_NOISE,
    DEFAULT_POWER_IS_AC, DEFAULT_PUBLISH_TOPIC, DEFAULT_START_DELTA,
    DEFAULT_TEMPLATE, DEFAULT_USABLE_KWH, DOMAIN,
)

# Entity-Picker je Signal auf den passenden device_class gefiltert, damit
# beim Anlegen/Bearbeiten nicht durch alle Entitaeten der Instanz gescrollt
# werden muss. Wer sein Signal ueber einen anderen device_class-losen
# Sensor oder binary_sensor abbildet, nutzt stattdessen die MQTT-Topic-
# Variante oder das Template-Feld zur Umrechnung.
_SOC_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="battery")
)
_HOME_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
_POWER_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
_WALLBOX_ENERGY_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
)
_ODO_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="distance")
)
# Kraftstoffpreis- und Heimstrompreis-Sensoren haben keinen einheitlichen
# device_class in HA (anders als die anderen Signale oben) -- daher
# ungefiltert auf sensor.
_VERBRENNER_PRICE_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)
_HOME_PRICE_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)


def _clean(user_input: dict) -> dict:
    """Leere Strings entfernen (nicht gesetzte Optionale)."""
    return {k: v for k, v in user_input.items() if v not in ("", None)}


def build_required_schema(cur: dict) -> vol.Schema:
    """Schritt 1 der Ersteinrichtung: nur die zwingend notwendigen Signale.

    SoC ist technisch Pflicht (Config-Flow bricht sonst ab), Heim-Laden ist
    es praktisch genauso — ohne dieses Signal wird jeder SoC-Anstieg als
    Fremdladen erkannt, auch normales Laden an der eigenen Wallbox.
    """
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        # --- SoC (Pflicht: Entity ODER Topic) ---
        vol.Optional(CONF_SOC_ENTITY, description=sv(CONF_SOC_ENTITY)): _SOC_ENTITY,
        vol.Optional(CONF_SOC_TOPIC, description=sv(CONF_SOC_TOPIC)): str,
        vol.Optional(CONF_SOC_TEMPLATE, default=cur.get(CONF_SOC_TEMPLATE, DEFAULT_TEMPLATE)): str,
        # --- Heim-Laden (Pflicht: Entity ODER Topic) ---
        vol.Optional(CONF_HOME_ENTITY, description=sv(CONF_HOME_ENTITY)): _HOME_ENTITY,
        vol.Optional(CONF_HOME_TOPIC, description=sv(CONF_HOME_TOPIC)): str,
        vol.Optional(CONF_HOME_TEMPLATE, default=cur.get(CONF_HOME_TEMPLATE, DEFAULT_TEMPLATE)): str,
    })


def build_vehicle_schema(cur: dict) -> vol.Schema:
    """Schritt 2: Fahrzeug-Eckdaten + Batterie-Kennwerte.

    Freitext statt HSN/TSN-Nachschlagen: die oeffentliche KBA-Liste
    identifiziert ueber die HSN nur den Hersteller (Tippfehler-Erkennung),
    nicht das Modell/die Variante — dafuer bringt sie nichts. Hersteller,
    Modell und nutzbare Akku-Kapazitaet sind Pflicht (Hersteller+Modell
    ergeben den Geraetenamen in der HA-Geraeteliste; ohne Kapazitaet lassen
    sich weder Fremdladungen noch der Ladewirkungsgrad sinnvoll schaetzen).
    Ladewirkungsgrad bleibt optional, da er automatisch aus echten
    Heim-Ladesessions kalibriert werden kann (siehe EfficiencyCalibrator).
    Kilometerstand ist eine reine Anzeige-Entitaet (kein Erkennungssignal),
    daher nur als HA-Entitaet waehlbar, ohne MQTT-Topic-Alternative.
    """
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        vol.Required(CONF_VEHICLE_HERSTELLER, default=cur.get(CONF_VEHICLE_HERSTELLER, "")): str,
        vol.Required(CONF_VEHICLE_MODELL, default=cur.get(CONF_VEHICLE_MODELL, "")): str,
        vol.Optional(CONF_ERSTZULASSUNG, description=sv(CONF_ERSTZULASSUNG)): selector.DateSelector(),
        vol.Optional(CONF_ODO_ENTITY, description=sv(CONF_ODO_ENTITY)): _ODO_ENTITY,
        vol.Required(CONF_USABLE_KWH, default=cur.get(CONF_USABLE_KWH, DEFAULT_USABLE_KWH)): vol.Coerce(float),
        vol.Optional(CONF_EFFICIENCY, default=cur.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)): vol.Coerce(float),
    })


def build_power_schema(cur: dict) -> vol.Schema:
    """Schritt 3: Ladeleistung + Wallbox-Energiemessung (beides optional).

    Ladeleistung verbessert die Energie-Schaetzung einer Fremdladung
    gegenueber der reinen SoC-Delta-Schaetzung. Die Wallbox-Energiemessung
    (kumulativer Zaehler, kWh) ermoeglicht die automatische Kalibrierung
    des Ladewirkungsgrads aus echten Heim-Ladesessions.
    """
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        vol.Optional(CONF_POWER_ENTITY, description=sv(CONF_POWER_ENTITY)): _POWER_ENTITY,
        vol.Optional(CONF_POWER_TOPIC, description=sv(CONF_POWER_TOPIC)): str,
        vol.Optional(CONF_POWER_TEMPLATE, default=cur.get(CONF_POWER_TEMPLATE, DEFAULT_TEMPLATE)): str,
        vol.Optional(CONF_POWER_IS_AC, default=cur.get(CONF_POWER_IS_AC, DEFAULT_POWER_IS_AC)): bool,
        vol.Optional(CONF_WALLBOX_ENERGY_ENTITY, description=sv(CONF_WALLBOX_ENERGY_ENTITY)): _WALLBOX_ENERGY_ENTITY,
        vol.Optional(CONF_WALLBOX_ENERGY_TOPIC, description=sv(CONF_WALLBOX_ENERGY_TOPIC)): str,
        vol.Optional(CONF_WALLBOX_ENERGY_TEMPLATE, default=cur.get(CONF_WALLBOX_ENERGY_TEMPLATE, DEFAULT_TEMPLATE)): str,
    })


def build_output_schema(cur: dict) -> vol.Schema:
    """Schritt 4: wohin erkannte Fremdladungen gemeldet werden."""
    return vol.Schema({
        vol.Optional(CONF_PUBLISH_TOPIC, default=cur.get(CONF_PUBLISH_TOPIC, DEFAULT_PUBLISH_TOPIC)): str,
        vol.Optional(CONF_NOTIFY_SERVICE, default=cur.get(CONF_NOTIFY_SERVICE, "")): str,
    })


def build_detection_schema(cur: dict) -> vol.Schema:
    """Schritt 5: Feinjustierung der Fremdlade-Erkennung (ChargeDetector)."""
    return vol.Schema({
        vol.Optional(CONF_START_DELTA, default=cur.get(CONF_START_DELTA, DEFAULT_START_DELTA)): vol.Coerce(float),
        vol.Optional(CONF_NOISE, default=cur.get(CONF_NOISE, DEFAULT_NOISE)): vol.Coerce(float),
        vol.Optional(CONF_IDLE_TIMEOUT, default=cur.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)): vol.Coerce(float),
        vol.Optional(CONF_DROP_ENDS, default=cur.get(CONF_DROP_ENDS, DEFAULT_DROP_ENDS)): vol.Coerce(float),
    })


def build_comparison_schema(cur: dict) -> vol.Schema:
    """Schritt 6: optionaler Kostenvergleich gegenueber einem Verbrenner.

    Alle Felder optional -- ohne sie bleiben die Ersparnis-Sensoren
    unbekannt statt einen Fehler zu werfen. Heimladen-Kosten setzen
    zusaetzlich eine konfigurierte Wallbox-Energiemessung (Schritt 3)
    voraus, da sonst keine Heimladen-kWh vorliegen. Heimstrompreis und
    Kraftstoffpreis: jeweils fester Wert ODER Live-Entitaet (z.B. ein
    dynamischer Tarif- bzw. Tankstellenpreis-Sensor) -- die Entitaet hat
    Vorrang, wenn beides gesetzt ist."""
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        vol.Optional(CONF_HOME_PRICE_KWH, description=sv(CONF_HOME_PRICE_KWH)): vol.Coerce(float),
        vol.Optional(CONF_HOME_PRICE_ENTITY, description=sv(CONF_HOME_PRICE_ENTITY)): _HOME_PRICE_ENTITY,
        vol.Optional(CONF_VERBRENNER_L_100KM, description=sv(CONF_VERBRENNER_L_100KM)): vol.Coerce(float),
        vol.Optional(CONF_VERBRENNER_PRICE_PER_LITER, description=sv(CONF_VERBRENNER_PRICE_PER_LITER)): vol.Coerce(float),
        vol.Optional(CONF_VERBRENNER_PRICE_ENTITY, description=sv(CONF_VERBRENNER_PRICE_ENTITY)): _VERBRENNER_PRICE_ENTITY,
    })


def _has_soc(data: dict) -> bool:
    return bool(data.get(CONF_SOC_ENTITY) or data.get(CONF_SOC_TOPIC))


def _has_home(data: dict) -> bool:
    return bool(data.get(CONF_HOME_ENTITY) or data.get(CONF_HOME_TOPIC))


def _has_vehicle_name(data: dict) -> bool:
    return bool(data.get(CONF_VEHICLE_HERSTELLER)) and bool(data.get(CONF_VEHICLE_MODELL))


class EvAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Mehrschrittige Ersteinrichtung.

    Schritt 1 (fahrzeug, Python-Methode async_step_user — von HA als
    Einstiegspunkt vorgegeben): Fahrzeug-Eckdaten (Marke & Modell) +
    Batterie-Kennwerte (Kapazitaet, Ladewirkungsgrad).
    Schritt 2 (grundsignale): zwingend notwendige Signale (SoC + Heim-Laden).
    Schritt 3 (ladeleistung): optionale Ladeleistungs-Quelle fuer eine
    genauere Energie-Schaetzung statt reiner SoC-Delta-Schaetzung.
    Schritt 4 (ausgabe): wohin erkannte Fremdladungen gemeldet werden
    (MQTT-Topic, notify-Service).
    Schritt 5 (erkennung): Feinjustierung der Fremdlade-Erkennung
    (ChargeDetector-Schwellwerte).
    Schritt 6 (vergleich): optionaler Kostenvergleich gegenueber einem
    Verbrenner. Der Eintrag wird erst am Ende dieser Kette angelegt.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Von HA vorgegebener Einstiegspunkt-Name — reicht direkt an
        async_step_fahrzeug weiter, damit Formular-Submits (die HA anhand
        des zuletzt gezeigten step_id routet, nicht anhand des aufrufenden
        Methodennamens) korrekt bei async_step_fahrzeug ankommen."""
        return await self.async_step_fahrzeug(user_input)

    async def async_step_fahrzeug(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not _has_vehicle_name(cleaned):
                errors["base"] = "vehicle_name_required"
            else:
                self._data = {**self._data, **cleaned}
                return await self.async_step_grundsignale()

        return self.async_show_form(
            step_id="fahrzeug", data_schema=build_vehicle_schema(user_input or {}), errors=errors
        )

    async def async_step_grundsignale(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not _has_soc(cleaned):
                errors["base"] = "no_soc_source"
            elif not _has_home(cleaned):
                errors["base"] = "no_home_source"
            else:
                self._data = {**self._data, **cleaned}
                return await self.async_step_ladeleistung()

        return self.async_show_form(
            step_id="grundsignale", data_schema=build_required_schema(user_input or {}), errors=errors
        )

    async def async_step_ladeleistung(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_ausgabe()

        return self.async_show_form(
            step_id="ladeleistung", data_schema=build_power_schema(user_input or {})
        )

    async def async_step_ausgabe(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_erkennung()

        return self.async_show_form(
            step_id="ausgabe", data_schema=build_output_schema(user_input or {})
        )

    async def async_step_erkennung(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_vergleich()

        return self.async_show_form(
            step_id="erkennung", data_schema=build_detection_schema(user_input or {})
        )

    async def async_step_vergleich(self, user_input=None) -> FlowResult:
        if user_input is not None:
            data = {**self._data, **_clean(user_input)}
            hersteller = data.get(CONF_VEHICLE_HERSTELLER)
            modell = data.get(CONF_VEHICLE_MODELL)
            fahrzeug = f"{hersteller} {modell}".strip() if (hersteller or modell) else None
            title = f"EV Assistant ({fahrzeug})" if fahrzeug else "EV Assistant"
            return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="vergleich", data_schema=build_comparison_schema(user_input or {})
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EvAssistantOptionsFlow(config_entry)


class EvAssistantOptionsFlow(OptionsFlow):
    """Spiegelt dieselbe Schrittkette wie die Ersteinrichtung (siehe
    EvAssistantConfigFlow: Fahrzeug -> Grundsignale -> Ladeleistung ->
    Ausgabe -> Erkennung -> Vergleich), damit man gezielt nur den
    betroffenen Bereich durchklicken kann statt eine Mammutseite mit allen
    Feldern auszufuellen.

    Wichtig: die Optionen werden erst am Ende der Kette (async_step_vergleich)
    EINMALIG geschrieben — mit dem ueber alle Schritte akkumulierten
    self._data. Wuerde man stattdessen bei jedem Zwischenschritt einzeln
    async_create_entry() aufrufen, wuerden die Felder der vorherigen Schritte
    verloren gehen (async_create_entry ERSETZT entry.options vollstaendig).
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._data: dict = {}

    def _current(self) -> dict:
        cur = {**self._entry.data, **self._entry.options, **self._data}
        cur.setdefault(CONF_PUBLISH_TOPIC, f"{DEFAULT_PUBLISH_TOPIC}/{self._entry.entry_id}")
        return cur

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Von HA vorgegebener Einstiegspunkt-Name — reicht direkt an
        async_step_fahrzeug weiter (siehe Kommentar in
        EvAssistantConfigFlow.async_step_user)."""
        return await self.async_step_fahrzeug(user_input)

    async def async_step_fahrzeug(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not _has_vehicle_name(cleaned):
                errors["base"] = "vehicle_name_required"
            else:
                self._data = {**self._data, **cleaned}
                return await self.async_step_grundsignale()

        return self.async_show_form(
            step_id="fahrzeug", data_schema=build_vehicle_schema(self._current()), errors=errors
        )

    async def async_step_grundsignale(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not _has_soc(cleaned):
                errors["base"] = "no_soc_source"
            elif not _has_home(cleaned):
                errors["base"] = "no_home_source"
            else:
                self._data = {**self._data, **cleaned}
                return await self.async_step_ladeleistung()

        return self.async_show_form(
            step_id="grundsignale", data_schema=build_required_schema(self._current()), errors=errors
        )

    async def async_step_ladeleistung(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_ausgabe()

        return self.async_show_form(
            step_id="ladeleistung", data_schema=build_power_schema(self._current())
        )

    async def async_step_ausgabe(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_erkennung()

        return self.async_show_form(
            step_id="ausgabe", data_schema=build_output_schema(self._current())
        )

    async def async_step_erkennung(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_vergleich()

        return self.async_show_form(
            step_id="erkennung", data_schema=build_detection_schema(self._current())
        )

    async def async_step_vergleich(self, user_input=None) -> FlowResult:
        if user_input is not None:
            data = {**self._data, **_clean(user_input)}
            return self.async_create_entry(title="", data=data)

        return self.async_show_form(
            step_id="vergleich", data_schema=build_comparison_schema(self._current())
        )
