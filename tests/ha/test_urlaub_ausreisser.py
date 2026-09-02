"""Tests fuer den optionalen Urlaubsmodus (CONF_URLAUB_ENTITY, siehe
coordinator.py::_urlaub_aktiv()) und die automatische, nutzerunsichtbare
Ausreisser-Daempfung (OUTLIER_DAMPING_FACTOR, siehe engine.py::
clamp_weekday_contribution()) an allen drei Wochentags-Profil-
Buchungsstellen (_apply_trip_baselines()/_update_house_usage_profile()/
_update_vehicle_discharge_profile()) sowie der evcc-Steuerungs-Pause
(_async_apply_evcc_mode_control()). Reine Daempfungslogik selbst ist
bereits in tests/test_engine.py abgedeckt (clamp_weekday_contribution()) --
hier nur die HA-Verdrahtung: Entity-Lesen, das Einfrieren von
"weekday_applied"/"urlaub" auf dem Trip-Record fuer exakte
sign=-1-Reversibilitaet bei Loeschen/Editieren, sowie die Rollover-Stellen
Haus/Fahrzeug (analog zueinander, kein Reversibilitaets-Thema dort -- siehe
jeweiliger Docstring in coordinator.py)."""
from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="ua1", options=None):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


def _trip_rec(kwh=None, km=None, ts=None):
    rec = {"start_ts": ts if ts is not None else dt_util.now().timestamp()}
    if kwh is not None:
        rec["verbrauch_kwh"] = kwh
    if km is not None:
        rec["km"] = km
    return rec


def _seed_7_tage_schnitt(coordinator, weekday_kwh=10.0, avg_consumption=20.0):
    """7-Kalendertage-Spanne, jeder Wochentag kommt genau einmal vor --
    weekday_kwh_exact_totals[key] entspricht dann direkt dem Schnitt fuer
    diesen Wochentag, analog test_evcc_mode_control.py::_seed_usage_profile()."""
    coordinator.data["fahrtenbuch_first_ts"] = (dt_util.now() - timedelta(days=6)).timestamp()
    coordinator.data["weekday_kwh_exact_totals"] = {str(wd): weekday_kwh for wd in range(7)}
    coordinator.data["weekday_km_est_totals"] = {}
    coordinator._usage_profile_cache = None
    coordinator._vehicle_avg_consumption_kwh_per_100km = lambda: avg_consumption


# ----- _urlaub_aktiv ---------------------------------------------------------

async def test_urlaub_aktiv_ohne_konfigurierte_entitaet_gibt_false(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "ua1")
    assert coordinator._urlaub_aktiv() is False


async def test_urlaub_aktiv_an_gibt_true(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ua2", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    assert coordinator._urlaub_aktiv() is True


async def test_urlaub_aktiv_aus_gibt_false(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ua3", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "off")
    assert coordinator._urlaub_aktiv() is False


async def test_urlaub_aktiv_unknown_gibt_false_failsafe(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ua4", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "unknown")
    assert coordinator._urlaub_aktiv() is False


async def test_urlaub_aktiv_fehlende_entitaet_gibt_false(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ua5", options={CONF_URLAUB_ENTITY: "input_boolean.existiert_nicht"},
    )
    assert coordinator._urlaub_aktiv() is False


# ----- _apply_trip_baselines: Urlaubsausschluss + Reversibilitaet ----------

async def test_apply_trip_baselines_urlaub_aktiv_schliesst_fahrt_aus(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "atb1", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    rec = _trip_rec(kwh=10.0)
    coordinator._apply_trip_baselines(rec, 1)
    assert coordinator.data.get("weekday_kwh_exact_totals", {}) == {}
    assert rec["urlaub"] is True
    assert rec["weekday_applied"] is None


async def test_apply_trip_baselines_urlaub_inaktiv_bucht_normal(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb2")
    rec = _trip_rec(kwh=10.0)
    weekday = dt_util.now().date().weekday()
    coordinator._apply_trip_baselines(rec, 1)
    assert coordinator.data["weekday_kwh_exact_totals"] == {str(weekday): 10.0}
    assert rec["urlaub"] is False
    assert rec["weekday_applied"] == ["exact", 10.0]


async def test_apply_trip_baselines_loeschen_nimmt_eingefrorenen_urlaubsstand_zurueck(hass, coordinators):
    """sign=-1 (Loeschen) MUSS den bei sign=+1 eingefrorenen Stand
    zuruecknehmen, NICHT den aktuellen (ggf. veraenderten) Urlaubsschalter
    neu abfragen -- siehe Kommentar in _apply_trip_baselines()."""
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "atb3", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    rec = _trip_rec(kwh=10.0)
    coordinator._apply_trip_baselines(rec, 1)  # ausgeschlossen (Urlaub aktiv)
    assert coordinator.data.get("weekday_kwh_exact_totals", {}) == {}
    hass.states.async_set("input_boolean.urlaub", "off")  # Urlaub inzwischen beendet
    coordinator._apply_trip_baselines(rec, -1)  # Loeschen -- darf NICHTS abziehen
    assert coordinator.data.get("weekday_kwh_exact_totals", {}) == {}


async def test_apply_trip_baselines_bestaetigen_dann_loeschen_ist_exakt_reversibel(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb4")
    rec = _trip_rec(kwh=10.0)
    weekday = dt_util.now().date().weekday()
    coordinator._apply_trip_baselines(rec, 1)
    coordinator._apply_trip_baselines(rec, -1)
    assert coordinator.data["weekday_kwh_exact_totals"][str(weekday)] == 0.0


async def test_apply_trip_baselines_altbestand_ohne_weekday_applied_faellt_auf_rohwert_zurueck(hass, coordinators):
    """Records von VOR Einfuehrung dieses Felds (kein "weekday_applied"-Key)
    duerfen beim Loeschen nicht stillschweigend nichts abziehen -- Fallback
    auf den rohen weekday_parts-Wert, exakt das, was sie urspruenglich ohne
    dieses Feature gebucht hatten."""
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb5")
    weekday = dt_util.now().date().weekday()
    coordinator.data["weekday_kwh_exact_totals"] = {str(weekday): 10.0}
    rec = _trip_rec(kwh=10.0)  # kein "weekday_applied"-Feld (Altbestand)
    coordinator._apply_trip_baselines(rec, -1)
    assert coordinator.data["weekday_kwh_exact_totals"][str(weekday)] == 0.0


async def test_apply_trip_baselines_ausreisser_wird_gedaempft(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb6")
    _seed_7_tage_schnitt(coordinator, weekday_kwh=10.0, avg_consumption=20.0)
    weekday = dt_util.now().date().weekday()
    rec = _trip_rec(kwh=100.0)  # 10x Schnitt
    coordinator._apply_trip_baselines(rec, 1)
    # Schwelle = 3 * 10 kWh Schnitt = 30 kWh statt der rohen 100 kWh
    assert coordinator.data["weekday_kwh_exact_totals"][str(weekday)] == 40.0  # 10 (Alt) + 30 (gekappt)
    assert rec["weekday_applied"] == ["exact", 30.0]


async def test_apply_trip_baselines_unauffaellige_fahrt_wird_nicht_gedaempft(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb7")
    _seed_7_tage_schnitt(coordinator, weekday_kwh=10.0, avg_consumption=20.0)
    weekday = dt_util.now().date().weekday()
    rec = _trip_rec(kwh=12.0)  # deutlich unter der 30-kWh-Schwelle
    coordinator._apply_trip_baselines(rec, 1)
    assert coordinator.data["weekday_kwh_exact_totals"][str(weekday)] == 22.0  # 10 + 12
    assert rec["weekday_applied"] == ["exact", 12.0]


# ----- _update_house_usage_profile: Urlaubsausschluss + Daempfung ----------

async def test_update_house_usage_profile_urlaub_aktiv_schliesst_tag_aus(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY, CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "huup_u1",
        options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus", CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "off")
    hass.states.async_set("sensor.haus", "1000.0")
    coordinator._update_house_usage_profile()
    coordinator.data["house_periods"]["day"]["key"] = "ein-anderer-tag"
    hass.states.async_set("input_boolean.urlaub", "on")
    hass.states.async_set("sensor.haus", "1015.0")
    coordinator._update_house_usage_profile()
    assert coordinator.data.get("house_weekday_kwh_totals", {}) == {}
    assert coordinator.data.get("house_weekday_day_counts", {}) == {}


async def test_update_house_usage_profile_ausreisser_wird_gedaempft(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "huup_u2", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    yesterday_wd = (dt_util.now().date() - timedelta(days=1)).weekday()
    coordinator.data["house_weekday_kwh_totals"] = {str(yesterday_wd): 20.0}
    coordinator.data["house_weekday_day_counts"] = {str(yesterday_wd): 2}
    hass.states.async_set("sensor.haus", "1000.0")
    coordinator._update_house_usage_profile()
    coordinator.data["house_periods"]["day"]["key"] = "ein-anderer-tag"
    hass.states.async_set("sensor.haus", "1100.0")  # 100 kWh -- 10x Schnitt (10 kWh)
    coordinator._update_house_usage_profile()
    assert coordinator.data["house_weekday_kwh_totals"][str(yesterday_wd)] == 50.0  # 20 + 30 (gekappt)
    assert coordinator.data["house_weekday_day_counts"][str(yesterday_wd)] == 3


# ----- _update_vehicle_discharge_profile: analog, Urlaubsausschluss -------

async def test_update_vehicle_discharge_profile_urlaub_aktiv_schliesst_tag_aus(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "uvdp1", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "off")
    coordinator.data["vehicle_discharge_kwh_total"] = 100.0
    coordinator._update_vehicle_discharge_profile()
    coordinator.data["vehicle_discharge_periods"]["day"]["key"] = "ein-anderer-tag"
    hass.states.async_set("input_boolean.urlaub", "on")
    coordinator.data["vehicle_discharge_kwh_total"] = 115.0
    coordinator._update_vehicle_discharge_profile()
    assert coordinator.data.get("vehicle_discharge_weekday_kwh_totals", {}) == {}
    assert coordinator.data.get("vehicle_discharge_weekday_day_counts", {}) == {}


# ----- _async_apply_evcc_mode_control: Urlaubs-Pause ------------------------

async def test_apply_evcc_mode_control_urlaub_aktiv_ist_no_op(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_URLAUB_ENTITY,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc_u1",
        options={
            CONF_EVCC_MODE_CONTROL_ENABLED: True,
            CONF_USABLE_KWH: 50.0,
            CONF_URLAUB_ENTITY: "input_boolean.urlaub",
        },
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    _seed_7_tage_schnitt(coordinator)
    coordinator._soc = 50.0
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_state = {"loadpoints": [{}]}
    await coordinator._async_apply_evcc_mode_control()
    coordinator._evcc_client.async_set_mode.assert_not_called()
    coordinator._evcc_client.async_probe_scope.assert_not_called()
    assert coordinator.data.get("evcc_mode_control") is None
