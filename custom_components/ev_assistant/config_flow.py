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
    CONF_DROP_ENDS, CONF_EFFICIENCY, CONF_HOME_ENTITY, CONF_HOME_TEMPLATE,
    CONF_HOME_TOPIC, CONF_IDLE_TIMEOUT, CONF_NOISE, CONF_NOTIFY_SERVICE,
    CONF_POWER_ENTITY, CONF_POWER_IS_AC, CONF_POWER_TEMPLATE, CONF_POWER_TOPIC,
    CONF_PUBLISH_TOPIC, CONF_SOC_ENTITY, CONF_SOC_TEMPLATE, CONF_SOC_TOPIC,
    CONF_START_DELTA, CONF_USABLE_KWH, DEFAULT_DROP_ENDS, DEFAULT_EFFICIENCY,
    DEFAULT_IDLE_TIMEOUT, DEFAULT_NOISE, DEFAULT_POWER_IS_AC,
    DEFAULT_PUBLISH_TOPIC, DEFAULT_START_DELTA, DEFAULT_TEMPLATE,
    DEFAULT_USABLE_KWH, DOMAIN,
)

_ENTITY = selector.EntitySelector(selector.EntitySelectorConfig())


def _clean(user_input: dict) -> dict:
    """Leere Strings entfernen (nicht gesetzte Optionale)."""
    return {k: v for k, v in user_input.items() if v not in ("", None)}


def build_schema(cur: dict) -> vol.Schema:
    """Gemeinsames Schema fuer Config- und Options-Flow.

    Entitaeten via suggested_value vorbelegen (bleiben optional/leer moeglich),
    Zahlen/Templates via default.
    """
    def sv(key):
        return {"suggested_value": cur.get(key)}

    return vol.Schema({
        # --- SoC (Pflicht: Entity ODER Topic) ---
        vol.Optional(CONF_SOC_ENTITY, description=sv(CONF_SOC_ENTITY)): _ENTITY,
        vol.Optional(CONF_SOC_TOPIC, description=sv(CONF_SOC_TOPIC)): str,
        vol.Optional(CONF_SOC_TEMPLATE, default=cur.get(CONF_SOC_TEMPLATE, DEFAULT_TEMPLATE)): str,
        # --- Heim-Laden (evcc/Warp) ---
        vol.Optional(CONF_HOME_ENTITY, description=sv(CONF_HOME_ENTITY)): _ENTITY,
        vol.Optional(CONF_HOME_TOPIC, description=sv(CONF_HOME_TOPIC)): str,
        vol.Optional(CONF_HOME_TEMPLATE, default=cur.get(CONF_HOME_TEMPLATE, DEFAULT_TEMPLATE)): str,
        # --- Ladeleistung (optional) ---
        vol.Optional(CONF_POWER_ENTITY, description=sv(CONF_POWER_ENTITY)): _ENTITY,
        vol.Optional(CONF_POWER_TOPIC, description=sv(CONF_POWER_TOPIC)): str,
        vol.Optional(CONF_POWER_TEMPLATE, default=cur.get(CONF_POWER_TEMPLATE, DEFAULT_TEMPLATE)): str,
        # --- Ausgabe / Fahrzeug / Erkennung ---
        vol.Optional(CONF_PUBLISH_TOPIC, default=cur.get(CONF_PUBLISH_TOPIC, DEFAULT_PUBLISH_TOPIC)): str,
        vol.Optional(CONF_NOTIFY_SERVICE, default=cur.get(CONF_NOTIFY_SERVICE, "")): str,
        vol.Optional(CONF_USABLE_KWH, default=cur.get(CONF_USABLE_KWH, DEFAULT_USABLE_KWH)): vol.Coerce(float),
        vol.Optional(CONF_EFFICIENCY, default=cur.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)): vol.Coerce(float),
        vol.Optional(CONF_POWER_IS_AC, default=cur.get(CONF_POWER_IS_AC, DEFAULT_POWER_IS_AC)): bool,
        vol.Optional(CONF_START_DELTA, default=cur.get(CONF_START_DELTA, DEFAULT_START_DELTA)): vol.Coerce(float),
        vol.Optional(CONF_NOISE, default=cur.get(CONF_NOISE, DEFAULT_NOISE)): vol.Coerce(float),
        vol.Optional(CONF_IDLE_TIMEOUT, default=cur.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)): vol.Coerce(float),
        vol.Optional(CONF_DROP_ENDS, default=cur.get(CONF_DROP_ENDS, DEFAULT_DROP_ENDS)): vol.Coerce(float),
    })


def _has_soc(data: dict) -> bool:
    return bool(data.get(CONF_SOC_ENTITY) or data.get(CONF_SOC_TOPIC))


class EvAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not _has_soc(cleaned):
                errors["base"] = "no_soc_source"
            else:
                return self.async_create_entry(title="EV Assistant", data=cleaned)

        return self.async_show_form(
            step_id="user", data_schema=build_schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EvAssistantOptionsFlow(config_entry)


class EvAssistantOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not _has_soc(cleaned):
                errors["base"] = "no_soc_source"
            else:
                return self.async_create_entry(title="", data=cleaned)

        cur = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init", data_schema=build_schema(cur), errors=errors
        )
