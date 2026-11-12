"""Die Lade-Empfehlung ("Laden kann warten" / "Laden empfehlenswert") rechnet mit
der PV, die DEM AUTO von morgen bleibt (Prognose minus Hausverbrauch laut
Hausprofil), nicht mit der rohen Prognose fuers ganze Haus -- sonst widerspricht
sie der Ladesteuerung ("PV fuers Auto: 0 km"). Beobachtung 2026-11-12: Prognose
19,4 kWh, Hausverbrauch 26,0 kWh, 13,0 von 20,1 kWh Bedarf im Akku -> die
Empfehlung sagte "kann warten", die Steuerung lud zu Recht."""
from datetime import timedelta
from unittest.mock import patch

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _coordinator(hass, coordinators, house_by_weekday, pv_forecast, available=13.0, need=20.1):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="cbp_net")
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    patches = [
        patch.object(coordinator, "available_kwh", return_value=available),
        patch.object(coordinator, "usage_profile_tomorrow", return_value={"benoetigt_kwh": need}),
        patch.object(coordinator, "_pv_forecast_tomorrow_kwh", return_value=pv_forecast),
        patch.object(coordinator, "house_usage_profile", return_value=house_by_weekday),
    ]
    for p in patches:
        p.start()
    return coordinator, patches


def _tomorrow_wd():
    return (dt_util.now().date() + timedelta(days=1)).weekday()


async def test_haus_frisst_die_prognose_dann_laden_empfehlenswert(hass, coordinators):
    c, patches = await _coordinator(hass, coordinators, {_tomorrow_wd(): 26.0}, pv_forecast=19.4)
    try:
        rec = c.charge_before_pv_recommended()
    finally:
        for p in patches:
            p.stop()
    assert rec["empfehlung"] is True                  # 13,0 + 0 < 20,1
    assert rec["pv_fuer_auto_morgen_kwh"] == 0.0
    assert rec["pv_prognose_morgen_kwh"] == 19.4      # rohe Prognose bleibt sichtbar


async def test_genug_pv_nach_haus_dann_laden_kann_warten(hass, coordinators):
    c, patches = await _coordinator(hass, coordinators, {_tomorrow_wd(): 5.0}, pv_forecast=19.4)
    try:
        rec = c.charge_before_pv_recommended()
    finally:
        for p in patches:
            p.stop()
    assert rec["empfehlung"] is False                 # 13,0 + 14,4 >= 20,1
    assert rec["pv_fuer_auto_morgen_kwh"] == 14.4


async def test_ohne_hausprofil_bleibt_es_bei_der_rohen_prognose(hass, coordinators):
    c, patches = await _coordinator(hass, coordinators, None, pv_forecast=19.4)
    try:
        rec = c.charge_before_pv_recommended()
    finally:
        for p in patches:
            p.stop()
    assert rec["empfehlung"] is False                 # wie bisher: 13,0 + 19,4 >= 20,1
    assert "pv_fuer_auto_morgen_kwh" not in rec


async def test_hausprofil_ohne_wert_fuer_morgen_bleibt_bei_der_rohen_prognose(hass, coordinators):
    other = (_tomorrow_wd() + 3) % 7
    c, patches = await _coordinator(hass, coordinators, {other: 26.0}, pv_forecast=19.4)
    try:
        rec = c.charge_before_pv_recommended()
    finally:
        for p in patches:
            p.stop()
    assert rec["empfehlung"] is False
    assert "pv_fuer_auto_morgen_kwh" not in rec


async def test_ohne_prognose_unveraendert(hass, coordinators):
    c, patches = await _coordinator(hass, coordinators, {_tomorrow_wd(): 26.0}, pv_forecast=None)
    try:
        rec = c.charge_before_pv_recommended()
    finally:
        for p in patches:
            p.stop()
    assert rec["empfehlung"] is True                  # 13,0 < 20,1, keine Prognose
    assert "pv_fuer_auto_morgen_kwh" not in rec
