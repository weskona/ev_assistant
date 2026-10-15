"""km-zuerst (0.99.50): Umrechnungs-Attribute am evcc_mode_control-Sensor,
eine Quelle mit range_estimate, km-Text der Ladeplan-Rueckmeldung."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location("_mc_helpers", Path(__file__).with_name("test_evcc_mode_control.py"))
_mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mc)
_make_coordinator = _mc._make_coordinator
_seed_usage_profile = _mc._seed_usage_profile

KM_KEYS = {
    "usable_kwh", "verbrauch_kwh_100km", "km_pro_prozent", "reichweite_km", "min_km", "target_km",
    "target_soc_max_km", "rest_heute_km", "pv_fuer_auto_km",
}


def _sensor(coordinator, entry):
    from custom_components.ev_assistant.sensor import EvccModeControlSensor

    return EvccModeControlSensor(coordinator, entry)


async def _enabled(hass, coordinators, entry_id, consumption=20.0):
    from custom_components.ev_assistant.const import CONF_EVCC_MODE_CONTROL_ENABLED, CONF_USABLE_KWH

    coordinator, entry = await _make_coordinator(
        hass, coordinators, entry_id, options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0, avg_consumption=consumption)
    coordinator._soc = 50.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    return coordinator, entry


async def test_attribute_mit_bekanntem_verbrauch(hass, coordinators):
    coordinator, entry = await _enabled(hass, coordinators, "rk1")
    attrs = _sensor(coordinator, entry).extra_state_attributes
    assert KM_KEYS <= set(attrs)
    assert attrs["usable_kwh"] == 50.0
    assert attrs["verbrauch_kwh_100km"] == 20.0
    assert attrs["km_pro_prozent"] == 2.5
    # 50 % von 50 kWh bei 20 kWh/100 km
    assert attrs["reichweite_km"] == 125.0
    assert attrs["min_km"] == round(attrs["min_kwh"] / 20.0 * 100.0, 1)
    assert attrs["target_soc_max_km"] == round(attrs["target_soc_max"] * 2.5, 1)


async def test_reichweite_km_ist_der_state_von_range_estimate(hass, coordinators):
    from custom_components.ev_assistant.sensor import RangeEstimateSensor

    coordinator, entry = await _enabled(hass, coordinators, "rk2")
    attrs = _sensor(coordinator, entry).extra_state_attributes
    range_sensor = RangeEstimateSensor(coordinator, entry)
    assert attrs["reichweite_km"] == range_sensor.native_value
    assert range_sensor.extra_state_attributes["verbrauch_kwh_100km"] == attrs["verbrauch_kwh_100km"]


async def test_eine_verbrauchsquelle_auch_mit_temperaturband(hass, coordinators):
    from custom_components.ev_assistant.sensor import RangeEstimateSensor

    coordinator, entry = await _enabled(hass, coordinators, "rk3")
    coordinator._outside_temp = 2.0
    from custom_components.ev_assistant.const import TEMP_BUCKET_BOUNDARIES
    from custom_components.ev_assistant.engine import temperature_bucket

    bucket = temperature_bucket(2.0, TEMP_BUCKET_BOUNDARIES)
    with patch.object(coordinator, "_consumption_by_temp_bucket", return_value={bucket: 25.0}):
        attrs = _sensor(coordinator, entry).extra_state_attributes
        range_sensor = RangeEstimateSensor(coordinator, entry)
        assert attrs["verbrauch_kwh_100km"] == 25.0
        assert range_sensor.extra_state_attributes["verbrauch_kwh_100km"] == 25.0
        assert range_sensor.native_value == attrs["reichweite_km"] == 100.0


async def test_ohne_verbrauch_fehlen_alle_km_schluessel(hass, coordinators):
    coordinator, entry = await _enabled(hass, coordinators, "rk4")
    coordinator._vehicle_avg_consumption_kwh_per_100km = lambda: None
    coordinator._rolling_consumption_cache = None
    attrs = _sensor(coordinator, entry).extra_state_attributes
    assert not KM_KEYS & set(attrs)
    assert "min_kwh" in attrs  # kWh-Attribute bleiben


async def test_ohne_steuerung_nur_umrechnung_und_reichweite(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, entry = await _make_coordinator(hass, coordinators, "rk5", options={CONF_USABLE_KWH: 50.0})
    _seed_usage_profile(coordinator, avg_consumption=20.0)
    coordinator._soc = 80.0
    attrs = _sensor(coordinator, entry).extra_state_attributes
    assert attrs["km_pro_prozent"] == 2.5
    assert attrs["reichweite_km"] == 200.0
    assert not {"min_km", "target_km", "rest_heute_km", "pv_fuer_auto_km", "target_soc_max_km"} & set(attrs)


async def test_unbekannter_soc_laesst_reichweite_weg(hass, coordinators):
    coordinator, entry = await _enabled(hass, coordinators, "rk6")
    coordinator._soc = None
    attrs = _sensor(coordinator, entry).extra_state_attributes
    assert "reichweite_km" not in attrs
    assert attrs.get("km_pro_prozent") == 2.5


async def test_usable_kwh_null_gibt_keine_km(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, entry = await _make_coordinator(hass, coordinators, "rk7", options={CONF_USABLE_KWH: 0})
    _seed_usage_profile(coordinator, avg_consumption=20.0)
    assert coordinator.range_conversion() == {}


async def test_feedback_text_km_zuerst(hass, coordinators):
    coordinator, _ = await _enabled(hass, coordinators, "rk8")
    coordinator._evcc_max_charge_power_kw = lambda: 11.0
    import time

    text = coordinator._evcc_charge_plan_feedback_text(75, time.time() + 12 * 3600)
    # 25 % von 50 kWh = 12,5 kWh = 62,5 km -> 65 km
    assert text.startswith("Erreichbar: +65 km (12,5 kWh)")
    assert "fertig ca." in text
    knapp = coordinator._evcc_charge_plan_feedback_text(75, time.time() + 600)
    assert knapp.startswith("Knapp: +65 km")


async def test_feedback_text_ohne_verbrauch_bleibt_kwh(hass, coordinators):
    import time

    coordinator, _ = await _enabled(hass, coordinators, "rk9")
    coordinator._vehicle_avg_consumption_kwh_per_100km = lambda: None
    coordinator._rolling_consumption_cache = None
    coordinator._evcc_max_charge_power_kw = lambda: 11.0
    text = coordinator._evcc_charge_plan_feedback_text(75, time.time() + 12 * 3600)
    assert text.startswith("Benoetigt ca. 12.5 kWh")
    assert "km" not in text


async def test_nutzungsprofil_km_attribute(hass, coordinators):
    from custom_components.ev_assistant.sensor import UsageProfileSensor, UsageProfileTomorrowSensor

    coordinator, entry = await _enabled(hass, coordinators, "rk10")
    profil = UsageProfileSensor(coordinator, entry).extra_state_attributes
    # 10 kWh je Wochentag bei 20 kWh/100 km = 50 km; kWh-Attribute bleiben
    assert profil["montag"] == 10.0
    assert set(profil["km_je_wochentag"].values()) == {50.0}
    assert len(profil["km_je_wochentag"]) == 7
    morgen = UsageProfileTomorrowSensor(coordinator, entry).extra_state_attributes
    assert morgen["benoetigt_km"] == round(morgen["benoetigt_kwh"] / 20.0 * 100.0, 1)
    assert morgen["roh_km"] == round(morgen["roh_kwh"] / 20.0 * 100.0, 1)


async def test_nutzungsprofil_ohne_verbrauch_keine_km(hass, coordinators):
    from custom_components.ev_assistant.sensor import UsageProfileSensor, UsageProfileTomorrowSensor

    coordinator, entry = await _enabled(hass, coordinators, "rk11")
    coordinator._vehicle_avg_consumption_kwh_per_100km = lambda: None
    coordinator._rolling_consumption_cache = None
    assert "km_je_wochentag" not in UsageProfileSensor(coordinator, entry).extra_state_attributes
    morgen = UsageProfileTomorrowSensor(coordinator, entry).extra_state_attributes
    assert "benoetigt_km" not in morgen and "benoetigt_kwh" in morgen


async def test_empfehlung_km_attribute(hass, coordinators):
    from custom_components.ev_assistant.binary_sensor import ChargeBeforePvBinarySensor

    coordinator, entry = await _enabled(hass, coordinators, "rk12")
    attrs = ChargeBeforePvBinarySensor(coordinator, entry).extra_state_attributes
    assert attrs["verfuegbare_km"] == round(attrs["verfuegbare_kwh"] / 20.0 * 100.0, 1)
    assert attrs["benoetigt_morgen_km"] == round(attrs["benoetigt_morgen_kwh"] / 20.0 * 100.0, 1)
