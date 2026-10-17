"""Puffer in km (0.99.52): fester Zuschlag nach PV-Abzug, %-Rueckfall."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_mc_helpers", Path(__file__).with_name("test_evcc_mode_control.py"))
_mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mc)
_make_coordinator = _mc._make_coordinator
_seed_usage_profile = _mc._seed_usage_profile


async def _coord(hass, coordinators, entry_id, options=None, consumption=20.0):
    from custom_components.ev_assistant.const import CONF_EVCC_MODE_CONTROL_ENABLED, CONF_USABLE_KWH

    opts = {CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0, **(options or {})}
    coordinator, entry = await _make_coordinator(hass, coordinators, entry_id, options=opts)
    _seed_usage_profile(coordinator, weekday_kwh=10.0, avg_consumption=consumption)
    coordinator._soc = 50.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    return coordinator, entry


async def test_aufloesung_override_vor_konfig_vor_default(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USAGE_PROFILE_BUFFER_KM

    c, _ = await _coord(hass, coordinators, "bk1")
    assert c._usage_profile_buffer_km() == 30.0
    c2, _ = await _coord(hass, coordinators, "bk2", options={CONF_USAGE_PROFILE_BUFFER_KM: 50.0})
    assert c2._usage_profile_buffer_km() == 50.0
    await c2.async_set_usage_profile_buffer_km(15.0)
    assert c2._usage_profile_buffer_km() == 15.0
    await c2.async_set_usage_profile_buffer_km(None)
    assert c2._usage_profile_buffer_km() == 50.0


async def test_klemmung_und_fehlender_schluessel(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "bk3")
    await c.async_set_usage_profile_buffer_km(999.0)
    assert c._usage_profile_buffer_km() == 300.0
    await c.async_set_usage_profile_buffer_km(-5.0)
    assert c._usage_profile_buffer_km() == 0.0
    c.data.pop("usage_profile_buffer_km_override", None)  # altes Backup ohne Schluessel
    assert c._usage_profile_buffer_km() == 30.0


def test_service_schema_null_ist_reset():
    from custom_components.ev_assistant import SET_USAGE_PROFILE_BUFFER_KM_SCHEMA as S

    assert S({"config_entry_id": "x", "buffer_km": None})["buffer_km"] is None
    assert S({"config_entry_id": "x", "buffer_km": "25"})["buffer_km"] == 25.0
    assert "buffer_km" not in S({"config_entry_id": "x"})


def test_optionsfeld_km_statt_prozent_und_prozent_bleibt_erhalten():
    from custom_components.ev_assistant.config_flow import _all_step_schema_keys, build_trip_schema

    keys = {str(k) for k in build_trip_schema({}).schema}
    assert "usage_profile_buffer_km" in keys and "usage_profile_buffer_pct" not in keys
    # %-Wert gehoert zu keinem Formular -> wird beim Speichern aus entry.data durchgereicht
    assert "usage_profile_buffer_pct" not in _all_step_schema_keys()
    defaults = {str(k): k.default() for k in build_trip_schema({}).schema if hasattr(k, "default") and callable(k.default)}
    assert defaults["usage_profile_buffer_km"] == 30.0


async def test_benoetigt_morgen_hat_festen_km_zuschlag(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "bk4")
    need = c.usage_profile_tomorrow()
    assert need["puffer_art"] == "km" and need["puffer_km"] == 30.0
    assert need["puffer_kwh"] == 6.0 and need["benoetigt_kwh"] == 16.0  # 10 + 30 km * 0.2
    assert need["puffer_prozent"] == 20.0  # Rueckfallwert, unveraendert
    await c.async_set_usage_profile_buffer_km(50.0)
    assert c.usage_profile_tomorrow()["benoetigt_kwh"] == 20.0


async def test_ohne_verbrauch_gilt_prozent_rueckfall(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "bk5")
    c.range_conversion = lambda: {}
    need = c.usage_profile_tomorrow()
    assert need["puffer_art"] == "prozent" and need["puffer_km"] is None
    assert need["benoetigt_kwh"] == 12.0 and need["puffer_kwh"] == 2.0


async def test_min_und_target_enthalten_puffer_nach_pv_abzug(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_PV_FORECAST_TODAY_REMAINING_ENTITY

    c, _ = await _coord(
        hass, coordinators, "bk6", options={CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest"},
    )
    # Riesige PV-Prognose deckt allen Rohbedarf -> nur der feste Puffer bleibt (Mindestreserve)
    hass.states.async_set("sensor.pv_rest", "500.0", {"unit_of_measurement": "kWh"})
    t = c._evcc_mode_targets()
    assert t["min_kwh"] == 6.0 and t["target_kwh"] == 6.0
    assert t["puffer_art"] == "km" and t["puffer_km"] == 30.0 and t["puffer_kwh"] == 6.0
    await c.async_set_usage_profile_buffer_km(0.0)
    assert c._evcc_mode_targets()["min_kwh"] == 0.0


async def test_attribute_am_sensor_und_vor_pv_laden_konsistent(hass, coordinators):
    from custom_components.ev_assistant.binary_sensor import ChargeBeforePvBinarySensor
    from custom_components.ev_assistant.sensor import EvccModeControlSensor, UsageProfileTomorrowSensor

    c, entry = await _coord(hass, coordinators, "bk7")
    a = EvccModeControlSensor(c, entry).extra_state_attributes
    assert (a["puffer_art"], a["puffer_km"], a["puffer_kwh"], a["puffer_prozent"]) == ("km", 30.0, 6.0, 20.0)
    u = UsageProfileTomorrowSensor(c, entry)
    assert u.native_value == 16.0
    assert u.extra_state_attributes["puffer_art"] == "km"
    assert u.extra_state_attributes["puffer_km_max"] == 300.0  # Panel setzt keine eigene Grenze
    b = ChargeBeforePvBinarySensor(c, entry).extra_state_attributes
    assert b["benoetigt_morgen_kwh"] == 16.0
    await c.async_set_usage_profile_buffer_km(60.0)
    assert ChargeBeforePvBinarySensor(c, entry).extra_state_attributes["benoetigt_morgen_kwh"] == 22.0
