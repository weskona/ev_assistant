"""evccs Ladeplan liegt je FAHRZEUG (`vehicles{<key>}.plan`), der Loadpoint zeigt
ihn nur, solange das Auto angesteckt ist. Der Plan-Sensor (und damit die
Plan-Anzeige der Karten) faellt deshalb auf den Fahrzeugplan zurueck --
Vorfall 2026-10-10: Plan war in evcc gesetzt, das Auto abgesteckt, der Sensor
zeigte "kein Plan", die Karte meldete nach ihrem Timeout faelschlich eine
fehlgeschlagene Fahrzeug-Zuordnung. Die Steuerungslogik (Pause der
profilbasierten Modus-Steuerung) darf von dem Rueckfall NICHT beeinflusst werden."""
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make(hass, coordinators, entry_id, options=None):
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME, DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    opts = {CONF_EVCC_VEHICLE_NAME: "eRifter"}
    opts.update(options or {})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=opts, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator


def _zukunft(tage=1):
    return (dt_util.utcnow() + timedelta(days=tage)).strftime("%Y-%m-%dT%H:%M:%SZ")


async def test_fahrzeugplan_bei_abgestecktem_auto_wird_gezeigt(hass, coordinators):
    coordinator = await _make(hass, coordinators, "fp1")
    ziel = _zukunft()
    coordinator._evcc_state = {
        "vehicles": {"db:8": {"title": "eRifter", "plan": {"soc": 80, "time": ziel}}},
        "loadpoints": [{"connected": False, "effectivePlanTime": None, "planTime": None}],
    }
    assert coordinator._evcc_charge_plan_status() == {
        "target_time": ziel, "target_soc": 80, "projected_start": None, "projected_end": None, "aktiv": False,
    }


async def test_loadpoint_plan_hat_vorrang_vor_dem_fahrzeugplan(hass, coordinators):
    coordinator = await _make(hass, coordinators, "fp2")
    coordinator._evcc_state = {
        "vehicles": {"db:8": {"title": "eRifter", "plan": {"soc": 70, "time": _zukunft(2)}}},
        "loadpoints": [{
            "effectivePlanTime": "2099-01-01T06:00:00Z", "effectivePlanSoc": 80,
            "planProjectedStart": "x", "planProjectedEnd": "y", "planActive": True,
        }],
    }
    status = coordinator._evcc_charge_plan_status()
    assert status["target_soc"] == 80 and status["aktiv"] is True and status["projected_start"] == "x"


async def test_steuerungslogik_ignoriert_den_fahrzeugplan(hass, coordinators):
    """Ein am Fahrzeug gesetzter Plan bei abgestecktem Auto darf die
    profilbasierte Modus-Steuerung NICHT pausieren (wie vorher)."""
    coordinator = await _make(hass, coordinators, "fp3")
    coordinator._evcc_state = {
        "vehicles": {"db:8": {"title": "eRifter", "plan": {"soc": 80, "time": _zukunft()}}},
        "loadpoints": [{"connected": False, "effectivePlanTime": None, "planTime": None}],
    }
    assert coordinator._evcc_charge_plan_status() is not None   # Anzeige
    assert coordinator._evcc_charge_plan_active() is False       # Steuerung


async def test_abgelaufener_fahrzeugplan_zaehlt_nicht(hass, coordinators):
    coordinator = await _make(hass, coordinators, "fp4")
    coordinator._evcc_state = {
        "vehicles": {"db:8": {"title": "eRifter", "plan": {"soc": 80, "time": _zukunft(-1)}}},
        "loadpoints": [{"connected": False}],
    }
    assert coordinator._evcc_charge_plan_status() is None


async def test_ohne_plan_und_ohne_fahrzeugzuordnung_none(hass, coordinators):
    coordinator = await _make(hass, coordinators, "fp5")
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}, "loadpoints": [{"connected": False}]}
    assert coordinator._evcc_charge_plan_status() is None
    # Plan eines ANDEREN Fahrzeugs wird nicht angezeigt.
    coordinator._evcc_state = {
        "vehicles": {"db:9": {"title": "Zoe", "plan": {"soc": 80, "time": _zukunft()}}},
        "loadpoints": [{"connected": False}],
    }
    assert coordinator._evcc_charge_plan_status() is None
    coordinator._evcc_state = None
    assert coordinator._evcc_charge_plan_status() is None


async def test_sensor_wert_ist_zeitstempel_des_fahrzeugplans(hass, coordinators):
    from custom_components.ev_assistant.sensor import EvccChargePlanSensor

    coordinator = await _make(hass, coordinators, "fp6")
    ziel = _zukunft()
    coordinator._evcc_state = {
        "vehicles": {"db:8": {"title": "eRifter", "plan": {"soc": 80, "time": ziel}}},
        "loadpoints": [{"connected": False}],
    }
    entry = coordinator.entry
    sensor = EvccChargePlanSensor(coordinator, entry)
    assert sensor.native_value == dt_util.parse_datetime(ziel)
    attrs = sensor.extra_state_attributes
    assert attrs["target_soc"] == 80 and attrs["projected_start"] is None
