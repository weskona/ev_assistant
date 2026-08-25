"""Tests fuer die km-gewichtete Kraftstoffpreis-Durchschnittsbildung
(siehe coordinator.py::_verbrenner_price_average()/_migrate_verbrenner_
price_weighting()) -- ersetzt die fruehere zeitgewichtete Variante, die
die Ersparnis-Schaetzung auch bei stehendem Fahrzeug wandern liess."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="vpw1"):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    coordinator.data["odo"] = 10000.0
    coordinator.data["odo_start"] = 10000.0
    coordinator.data["odo_unit"] = "km"
    return coordinator


async def test_verbrenner_price_average_ohne_intervall_liefert_live_wert(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "vpw1")
    assert coordinator._verbrenner_price_average(1.899) == 1.899


async def test_verbrenner_price_average_bleibt_eingefroren_ohne_fahrt(hass, coordinators):
    """Kernszenario aus dem Nutzer-Report: sobald einmal ein echtes
    km-Gewicht existiert (hier: 500 km bei 1.80 EUR/L gefahren), darf sich
    der Durchschnitt bei stehendem Fahrzeug (km_driven unveraendert) NICHT
    mehr bewegen, auch wenn sich der Kraftstoffpreis mehrfach aendert."""
    coordinator = await _make_coordinator(hass, coordinators, "vpw2")

    coordinator._set_verbrenner_price("1.800")
    coordinator.data["odo"] = 10500.0  # 500 km gefahren, waehrend 1.80 galt
    coordinator._set_verbrenner_price("2.000")
    avg_1 = coordinator._verbrenner_price_average(coordinator._verbrenner_price_live)
    # 500 km bei 1.80 gewichtet, das offene 2.00-Intervall hat noch 0 km.
    assert avg_1 == 1.80

    # Fahrzeug steht: kein Kilometerstand-Update, aber der Preis aendert sich mehrfach.
    coordinator._set_verbrenner_price("2.500")
    avg_2 = coordinator._verbrenner_price_average(coordinator._verbrenner_price_live)
    assert avg_2 == avg_1

    coordinator._set_verbrenner_price("1.200")
    avg_3 = coordinator._verbrenner_price_average(coordinator._verbrenner_price_live)
    assert avg_3 == avg_1


async def test_verbrenner_price_average_bewegt_sich_nur_bei_tatsaechlicher_fahrt(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "vpw3")

    coordinator._set_verbrenner_price("1.800")
    # 100 km bei 1.80 EUR/L gefahren, dann Preiswechsel.
    coordinator.data["odo"] = 10100.0
    coordinator._set_verbrenner_price("2.000")
    # Weitere 100 km bei 2.00 EUR/L, dann Live-Wert nochmal 2.00 abfragen.
    coordinator.data["odo"] = 10200.0

    avg = coordinator._verbrenner_price_average(coordinator._verbrenner_price_live)
    # (1.80*100 + 2.00*100) / 200 = 1.90
    assert avg == 1.90


async def test_migration_verbrenner_price_weighting(hass, coordinators):
    coordinator = await _make_coordinator(hass, coordinators, "vpw4")
    # Alt-Zustand aus einer Installation von vor der Umstellung auf
    # km-Gewichtung direkt injiziert.
    coordinator.data["verbrenner_price_weighted_sum"] = 123.45
    coordinator.data["verbrenner_price_weighted_seconds"] = 987654.0
    coordinator.data["verbrenner_price_interval_start_ts"] = 1700000000.0

    geaendert = coordinator._migrate_verbrenner_price_weighting()
    assert geaendert is True
    assert "verbrenner_price_weighted_seconds" not in coordinator.data
    assert "verbrenner_price_interval_start_ts" not in coordinator.data
    assert coordinator.data["verbrenner_price_weighted_sum"] == 0.0
    assert coordinator.data["verbrenner_price_weighted_km"] == 0.0
    assert coordinator.data["verbrenner_price_interval_start_km"] == 0.0  # odo == odo_start hier

    # Idempotent: ein zweiter Lauf findet nichts mehr zu tun.
    assert coordinator._migrate_verbrenner_price_weighting() is False
