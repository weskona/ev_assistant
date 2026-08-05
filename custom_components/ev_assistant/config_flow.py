"""Config- und Options-Flow fuer ev_assistant.

Pro Signal waehlbar: eine HA-Entitaet. Dadurch nutzbar mit Hersteller-
Integrationen (Stellantis, VW, ...) und mit jeder anderen Integration,
die ihre Werte als HA-Entitaet bereitstellt (z.B. WiCAN Pro).
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CO2_PER_KWH,
    CONF_DROP_ENDS, CONF_EFFICIENCY, CONF_ERSTZULASSUNG, CONF_GPS_ENTITY, CONF_HOME_ENTITY,
    CONF_HOME_PRICE_ENTITY, CONF_HOME_PRICE_KWH, CONF_IDLE_TIMEOUT,
    CONF_MOTOR_DEBOUNCE, CONF_MOTOR_ENTITY,
    CONF_NOISE, CONF_NOTIFY_SERVICE, CONF_ODO_ENTITY, CONF_PLUG_DEBOUNCE, CONF_PLUG_ENTITY,
    CONF_POWER_ENTITY, CONF_POWER_IS_AC,
    CONF_SOC_ENTITY, CONF_START_DELTA,
    CONF_TRIP_AUTO_CONFIRM, CONF_TRIP_IDLE_TIMEOUT, CONF_TRIP_MIN_KM, CONF_USAGE_PROFILE_BUFFER_PCT,
    CONF_USABLE_KWH, CONF_VEHICLE_HERSTELLER, CONF_VEHICLE_MODELL,
    CONF_VERBRENNER_L_100KM, CONF_VERBRENNER_PRICE_ENTITY, CONF_VERBRENNER_PRICE_PER_LITER,
    CONF_TANKERKOENIG_FUEL_TYPE,
    CONF_WALLBOX_ENERGY_ENTITY,
    CONF_EVCC_CHARGE_POWER, CONF_EVCC_CHARGE_STATUS, CONF_EVCC_MODE,
    CONF_EVCC_PHASES_ACTIVE, CONF_EVCC_VEHICLE_SOC, CONF_EVCC_LIMIT_SOC,
    CONF_EVCC_SESSION_ENERGY, CONF_EVCC_SESSION_SOLAR_PCT, CONF_EVCC_SESSION_PRICE,
    CONF_EVCC_CHARGE_DURATION, CONF_EVCC_TARIFF_GRID, CONF_EVCC_TARIFF_FEEDIN,
    CONF_EVCC_STAT_TOTAL_KWH, CONF_EVCC_STAT_SOLAR_PCT, CONF_EVCC_STAT_AVG_PRICE,
    CONF_EVCC_PV_POWER, CONF_EVCC_GRID_POWER, CONF_EVCC_BATTERY_POWER,
    CONF_EVCC_VEHICLE_NAME,
    DEFAULT_CO2_PER_KWH_G,
    DEFAULT_DROP_ENDS,
    DEFAULT_EFFICIENCY, DEFAULT_IDLE_TIMEOUT, DEFAULT_MOTOR_DEBOUNCE, DEFAULT_NOISE, DEFAULT_PLUG_DEBOUNCE,
    DEFAULT_POWER_IS_AC, DEFAULT_START_DELTA,
    DEFAULT_TRIP_AUTO_CONFIRM, DEFAULT_TRIP_IDLE_TIMEOUT, DEFAULT_TRIP_MIN_KM, DEFAULT_USAGE_PROFILE_BUFFER_PCT,
    DEFAULT_USABLE_KWH, DOMAIN,
)

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
_VERBRENNER_PRICE_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)
_HOME_PRICE_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)
_GPS_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["person", "device_tracker", "sensor"])
)
_PLUG_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="binary_sensor")
)
_MOTOR_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="binary_sensor")
)
_TANKERKOENIG_FUEL_TYPE = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"value": "super", "label": "Super (E5)"},
            {"value": "super_e10", "label": "Super E10"},
            {"value": "diesel", "label": "Diesel"},
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

_EVCC_VEHICLE_NAME = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
)


async def _discover_evcc_entities(hass) -> dict:
    """Evcc-Entities aus evcc_intg automatisch ermitteln und auf CONF_EVCC_*-Keys mappen."""
    from homeassistant.helpers import entity_registry as er

    ent_reg = er.async_get(hass)
    evcc_ids: set[str] = set()
    for entry in hass.config_entries.async_entries("evcc_intg"):
        for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            if not e.disabled_by:
                evcc_ids.add(e.entity_id)
    if not evcc_ids:
        return {}

    def pick(*candidates: str) -> str | None:
        for c in candidates:
            if c in evcc_ids:
                return c
        return None

    lp = next(
        (eid[len("sensor."):-len("_charge_power")]
         for eid in sorted(evcc_ids)
         if eid.startswith("sensor.evcc_") and eid.endswith("_charge_power")),
        None,
    )
    # Manche evcc_intg-Versionen/Konfigurationen exponieren Fahrzeugdaten nicht
    # ueber den Ladepunkt-Praefix (sensor.{lp}_vehicle_soc), sondern ueber einen
    # eigenen "configvehicle"-Namensraum (sensor.evcc_{vehicle}_configvehicle_soc,
    # z.B. wenn evcc_intg das Fahrzeug getrennt vom Ladepunkt fuehrt).
    vk = next(
        (eid[len("sensor.evcc_"):-len("_configvehicle_soc")]
         for eid in sorted(evcc_ids)
         if eid.startswith("sensor.evcc_") and eid.endswith("_configvehicle_soc")),
        None,
    )

    discovered: dict = {
        CONF_EVCC_PV_POWER:       pick("sensor.evcc_pv_power"),
        CONF_EVCC_GRID_POWER:     pick("sensor.evcc_grid_power"),
        CONF_EVCC_BATTERY_POWER:  pick("sensor.evcc_battery_power"),
        CONF_EVCC_TARIFF_GRID:    pick("sensor.evcc_tariff_grid"),
        CONF_EVCC_TARIFF_FEEDIN:  pick("sensor.evcc_tariff_feed_in"),
        CONF_EVCC_STAT_TOTAL_KWH: pick("sensor.evcc_stat_total_charged_kwh"),
        CONF_EVCC_STAT_SOLAR_PCT: pick("sensor.evcc_stat_total_solar_percentage"),
        CONF_EVCC_STAT_AVG_PRICE: pick("sensor.evcc_stat_total_avg_price"),
    }
    if lp:
        discovered.update({
            CONF_EVCC_CHARGE_POWER:      pick(f"sensor.{lp}_charge_power"),
            CONF_EVCC_CHARGE_STATUS:     pick(f"binary_sensor.{lp}_charging"),
            CONF_EVCC_MODE:              pick(f"select.{lp}_mode"),
            CONF_EVCC_PHASES_ACTIVE:     pick(f"sensor.{lp}_phases_active"),
            CONF_EVCC_VEHICLE_SOC:       pick(f"sensor.{lp}_vehicle_soc"),
            CONF_EVCC_LIMIT_SOC:         pick(f"select.{lp}_limit_soc", f"number.{lp}_limit_soc"),
            CONF_EVCC_SESSION_ENERGY:    pick(f"sensor.{lp}_session_energy"),
            CONF_EVCC_SESSION_SOLAR_PCT: pick(f"sensor.{lp}_session_solar_percentage"),
            CONF_EVCC_SESSION_PRICE:     pick(f"sensor.{lp}_session_price"),
            CONF_EVCC_CHARGE_DURATION:   pick(f"sensor.{lp}_charge_duration"),
        })
    if vk:
        # setdefault greift nicht, wenn lp bereits einen (fehlgeschlagenen)
        # Versuch mit Wert None eingetragen hat -- daher explizit pruefen.
        if not discovered.get(CONF_EVCC_VEHICLE_SOC):
            discovered[CONF_EVCC_VEHICLE_SOC] = pick(f"sensor.evcc_{vk}_configvehicle_soc")
        if not discovered.get(CONF_EVCC_LIMIT_SOC):
            discovered[CONF_EVCC_LIMIT_SOC] = pick(f"sensor.evcc_{vk}_configvehicle_limitsoc")
    return {k: v for k, v in discovered.items() if v is not None}


def _clean(user_input: dict) -> dict:
    """Leere Strings entfernen (nicht gesetzte Optionale)."""
    return {k: v for k, v in user_input.items() if v not in ("", None)}


def build_vehicle_schema(cur: dict) -> vol.Schema:
    """Schritt 1: Fahrzeugdaten + SoC-Entität."""
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        vol.Required(CONF_VEHICLE_HERSTELLER, default=cur.get(CONF_VEHICLE_HERSTELLER, "")): str,
        vol.Required(CONF_VEHICLE_MODELL, default=cur.get(CONF_VEHICLE_MODELL, "")): str,
        vol.Optional(CONF_ERSTZULASSUNG, description=sv(CONF_ERSTZULASSUNG)): selector.DateSelector(),
        vol.Optional(CONF_ODO_ENTITY, description=sv(CONF_ODO_ENTITY)): _ODO_ENTITY,
        vol.Required(CONF_SOC_ENTITY, description=sv(CONF_SOC_ENTITY)): _SOC_ENTITY,
        vol.Required(CONF_USABLE_KWH, default=cur.get(CONF_USABLE_KWH, DEFAULT_USABLE_KWH)): vol.Coerce(float),
        vol.Optional(CONF_EFFICIENCY, default=cur.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)): vol.Coerce(float),
    })


def build_evcc_schema(cur: dict) -> vol.Schema:
    """Schritt 2: evcc-Fahrzeugname + Wallbox-Leistungsentität."""
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        vol.Optional(
            CONF_EVCC_VEHICLE_NAME,
            description={"suggested_value": cur.get(CONF_EVCC_VEHICLE_NAME)},
        ): _EVCC_VEHICLE_NAME,
        vol.Optional(CONF_HOME_ENTITY, description=sv(CONF_HOME_ENTITY)): _HOME_ENTITY,
    })


def build_power_schema(cur: dict) -> vol.Schema:
    """Schritt 3: Fahrzeug-Ladeleistung + Wallbox-Energiezähler."""
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        vol.Optional(CONF_POWER_ENTITY, description=sv(CONF_POWER_ENTITY)): _POWER_ENTITY,
        vol.Optional(CONF_POWER_IS_AC, default=cur.get(CONF_POWER_IS_AC, DEFAULT_POWER_IS_AC)): bool,
        vol.Optional(CONF_WALLBOX_ENERGY_ENTITY, description=sv(CONF_WALLBOX_ENERGY_ENTITY)): _WALLBOX_ENERGY_ENTITY,
    })


def build_output_schema(cur: dict) -> vol.Schema:
    """Schritt 4: Push-Benachrichtigung."""
    return vol.Schema({
        vol.Optional(CONF_NOTIFY_SERVICE, default=cur.get(CONF_NOTIFY_SERVICE, "")): str,
    })


def build_detection_schema(cur: dict) -> vol.Schema:
    """Schritt 5: ChargeDetector-Schwellwerte."""
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        vol.Optional(CONF_START_DELTA, default=cur.get(CONF_START_DELTA, DEFAULT_START_DELTA)): vol.Coerce(float),
        vol.Optional(CONF_NOISE, default=cur.get(CONF_NOISE, DEFAULT_NOISE)): vol.Coerce(float),
        vol.Optional(CONF_IDLE_TIMEOUT, default=cur.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)): vol.Coerce(float),
        vol.Optional(CONF_DROP_ENDS, default=cur.get(CONF_DROP_ENDS, DEFAULT_DROP_ENDS)): vol.Coerce(float),
        vol.Optional(CONF_PLUG_ENTITY, description=sv(CONF_PLUG_ENTITY)): _PLUG_ENTITY,
        vol.Optional(
            CONF_PLUG_DEBOUNCE, default=cur.get(CONF_PLUG_DEBOUNCE, DEFAULT_PLUG_DEBOUNCE)
        ): vol.Coerce(float),
    })


def build_trip_schema(cur: dict) -> vol.Schema:
    """Schritt 6: TripDetector-Schwellwerte + GPS."""
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        vol.Optional(CONF_TRIP_MIN_KM, default=cur.get(CONF_TRIP_MIN_KM, DEFAULT_TRIP_MIN_KM)): vol.Coerce(float),
        vol.Optional(
            CONF_TRIP_IDLE_TIMEOUT, default=cur.get(CONF_TRIP_IDLE_TIMEOUT, DEFAULT_TRIP_IDLE_TIMEOUT)
        ): vol.Coerce(float),
        vol.Optional(CONF_GPS_ENTITY, description=sv(CONF_GPS_ENTITY)): _GPS_ENTITY,
        vol.Optional(CONF_MOTOR_ENTITY, description=sv(CONF_MOTOR_ENTITY)): _MOTOR_ENTITY,
        vol.Optional(
            CONF_MOTOR_DEBOUNCE, default=cur.get(CONF_MOTOR_DEBOUNCE, DEFAULT_MOTOR_DEBOUNCE)
        ): vol.Coerce(float),
        vol.Optional(
            CONF_TRIP_AUTO_CONFIRM, default=cur.get(CONF_TRIP_AUTO_CONFIRM, DEFAULT_TRIP_AUTO_CONFIRM)
        ): bool,
        vol.Optional(
            CONF_USAGE_PROFILE_BUFFER_PCT,
            default=cur.get(CONF_USAGE_PROFILE_BUFFER_PCT, DEFAULT_USAGE_PROFILE_BUFFER_PCT),
        ): vol.Coerce(float),
    })


def build_comparison_schema(cur: dict) -> vol.Schema:
    """Schritt 7: Kostenvergleich Verbrenner.

    Kraftstoffpreis-Prioritaet: tankerkoenig_fuel_type (guenstigste offene
    Tankerkoenig-Station, automatisch ermittelt) > verbrenner_price_entity
    (eigene Entitaet) > verbrenner_price_per_liter (fester Wert). Nur eines
    davon konfigurieren, je nachdem, welche Quelle genutzt werden soll.
    """
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        vol.Optional(CONF_HOME_PRICE_KWH, description=sv(CONF_HOME_PRICE_KWH)): vol.Coerce(float),
        vol.Optional(CONF_HOME_PRICE_ENTITY, description=sv(CONF_HOME_PRICE_ENTITY)): _HOME_PRICE_ENTITY,
        vol.Optional(CONF_VERBRENNER_L_100KM, description=sv(CONF_VERBRENNER_L_100KM)): vol.Coerce(float),
        vol.Optional(CONF_VERBRENNER_PRICE_PER_LITER, description=sv(CONF_VERBRENNER_PRICE_PER_LITER)): vol.Coerce(float),
        vol.Optional(CONF_VERBRENNER_PRICE_ENTITY, description=sv(CONF_VERBRENNER_PRICE_ENTITY)): _VERBRENNER_PRICE_ENTITY,
        vol.Optional(CONF_TANKERKOENIG_FUEL_TYPE, description=sv(CONF_TANKERKOENIG_FUEL_TYPE)): _TANKERKOENIG_FUEL_TYPE,
        vol.Optional(
            CONF_CO2_PER_KWH, default=cur.get(CONF_CO2_PER_KWH, DEFAULT_CO2_PER_KWH_G)
        ): vol.Coerce(float),
    })


def _has_vehicle_name(data: dict) -> bool:
    return bool(data.get(CONF_VEHICLE_HERSTELLER)) and bool(data.get(CONF_VEHICLE_MODELL))


class EvAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Mehrschrittige Ersteinrichtung (7 Schritte).

    1 fahrzeug:    Eckdaten, ODO, SoC-Entitaet, Akkugroesse.
    2 evcc:        Fahrzeugname in evcc + Wallbox-Leistungsentitaet.
    3 ladeleistung: Fahrzeug-Ladeleistung + Wallbox-Energiezaehler.
    4 ausgabe:     Push-Benachrichtigung.
    5 erkennung:   ChargeDetector-Schwellwerte.
    6 fahrtenbuch: TripDetector + GPS.
    7 vergleich:   Kostenvergleich; legt Eintrag an (inkl. evcc-Discovery).
    """

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        return await self.async_step_fahrzeug(user_input)

    async def async_step_fahrzeug(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not _has_vehicle_name(cleaned):
                errors["base"] = "vehicle_name_required"
            else:
                self._data = {**self._data, **cleaned}
                return await self.async_step_evcc()

        cur = user_input if user_input is not None else self._data
        return self.async_show_form(
            step_id="fahrzeug", data_schema=build_vehicle_schema(cur), errors=errors
        )

    async def async_step_evcc(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_ladeleistung()

        cur = user_input if user_input is not None else self._data
        return self.async_show_form(
            step_id="evcc", data_schema=build_evcc_schema(cur)
        )

    async def async_step_ladeleistung(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_ausgabe()

        cur = user_input if user_input is not None else self._data
        return self.async_show_form(
            step_id="ladeleistung", data_schema=build_power_schema(cur)
        )

    async def async_step_ausgabe(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_erkennung()

        cur = user_input if user_input is not None else self._data
        return self.async_show_form(
            step_id="ausgabe", data_schema=build_output_schema(cur)
        )

    async def async_step_erkennung(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_fahrtenbuch()

        cur = user_input if user_input is not None else self._data
        return self.async_show_form(
            step_id="erkennung", data_schema=build_detection_schema(cur)
        )

    async def async_step_fahrtenbuch(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_vergleich()

        cur = user_input if user_input is not None else self._data
        return self.async_show_form(
            step_id="fahrtenbuch", data_schema=build_trip_schema(cur)
        )

    async def async_step_vergleich(self, user_input=None) -> FlowResult:
        if user_input is not None:
            cleaned = _clean(user_input)
            self._data = {**self._data, **cleaned}
            self._data = {**self._data, **await _discover_evcc_entities(self.hass)}
            hersteller = self._data.get(CONF_VEHICLE_HERSTELLER)
            modell = self._data.get(CONF_VEHICLE_MODELL)
            fahrzeug = f"{hersteller} {modell}".strip() if (hersteller or modell) else None
            title = f"EV Assistant ({fahrzeug})" if fahrzeug else "EV Assistant"
            return self.async_create_entry(title=title, data=self._data)

        cur = self._data
        return self.async_show_form(
            step_id="vergleich", data_schema=build_comparison_schema(cur)
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EvAssistantOptionsFlow(config_entry)


class EvAssistantOptionsFlow(OptionsFlow):
    """Spiegelt dieselbe 7-Schritt-Kette wie die Ersteinrichtung."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._data: dict = {}

    def _current(self) -> dict:
        return {**self._entry.data, **self._entry.options, **self._data}

    async def async_step_init(self, user_input=None) -> FlowResult:
        return await self.async_step_fahrzeug(user_input)

    async def async_step_fahrzeug(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not _has_vehicle_name(cleaned):
                errors["base"] = "vehicle_name_required"
            else:
                self._data = {**self._data, **cleaned}
                return await self.async_step_evcc()

        return self.async_show_form(
            step_id="fahrzeug", data_schema=build_vehicle_schema(self._current()), errors=errors
        )

    async def async_step_evcc(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_ladeleistung()

        return self.async_show_form(
            step_id="evcc", data_schema=build_evcc_schema(self._current())
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
            return await self.async_step_fahrtenbuch()

        return self.async_show_form(
            step_id="erkennung", data_schema=build_detection_schema(self._current())
        )

    async def async_step_fahrtenbuch(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {**self._data, **_clean(user_input)}
            return await self.async_step_vergleich()

        return self.async_show_form(
            step_id="fahrtenbuch", data_schema=build_trip_schema(self._current())
        )

    async def async_step_vergleich(self, user_input=None) -> FlowResult:
        if user_input is not None:
            cleaned = _clean(user_input)
            self._data = {**self._data, **cleaned}
            self._data = {**self._data, **await _discover_evcc_entities(self.hass)}
            return self.async_create_entry(title="", data=self._data)

        return self.async_show_form(
            step_id="vergleich", data_schema=build_comparison_schema(self._current())
        )
