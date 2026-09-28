"""Regressionsnetz fuer die Anzeigereihenfolge des Fahrtenbuchs (WS-Kommando
ev_assistant/trips) und der Ladehistorie (ev_assistant/charges), siehe
websocket_api.py::_handle_trips()/_handle_charges(): beide muessen nach dem
tatsaechlichen Zeitpunkt (start_ts) absteigend sortiert sein, unabhaengig
von der Bestaetigungs-/Speicherreihenfolge in self.data["history"]/
["fahrten"] -- sonst landet eine nachtraeglich manuell erfasste oder
spaeter bestaetigte/bearbeitete Ladung bzw. Fahrt an der falschen
chronologischen Position im Panel.

Die Sortierung lag frueher in sensor.py::LastCostSensor.historie/
LastTripSensor.fahrtenbuch (Entity-Attribut) -- seit dem 16KB-Attribut-Fix
(2026-09-28, siehe CHANGELOG) liefern die Sensoren nur noch die Felder des
letzten Eintrags selbst, die volle sortierte Liste kommt ausschliesslich
per WS-Kommando (siehe test_home_generic_live_attrs.py-analoge
Sensor-Tests fuer den unsortierten "letzter Eintrag"-Teil)."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


class _FakeConnection:
    def __init__(self):
        self.result = None
        self.error = None

    def send_result(self, msg_id, result):
        self.result = result

    def send_error(self, msg_id, code, message):
        self.error = (code, message)


def _make_coordinator(hass, coordinators, entry_id):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    hass.data.setdefault(DOMAIN, {})[entry_id] = coordinator
    return coordinator, entry


def _unwrap(handler):
    """Die websocket_command-Handler sind mit @async_response dekoriert,
    das die eigentliche Coroutine in einen synchronen Callback verpackt, der
    sie nur als Background-Task einplant (kein direkt awaitbares Ergebnis
    mehr) -- @wraps(func) legt die urspruengliche Coroutine-Funktion aber
    unter __wrapped__ ab, die hier fuer direkte Tests genutzt wird."""
    return handler.__wrapped__


async def test_charges_ws_sortiert_nach_start_ts(hass, coordinators):
    from custom_components.ev_assistant.websocket_api import _handle_charges
    _handle_charges = _unwrap(_handle_charges)

    coordinator, entry = _make_coordinator(hass, coordinators, "sort1")
    await coordinator.async_setup()

    # Speicherreihenfolge (Bestaetigung) != chronologische Reihenfolge:
    # der ZULETZT bestaetigte Eintrag (erfasst_ts=300, Index 0) liegt
    # chronologisch in der MITTE (start_ts=500) -- eine nachtraeglich
    # manuell erfasste aeltere Ladung (start_ts=100) wurde erst DANACH
    # eingetragen (erfasst_ts=200) und landet dadurch an Index 1.
    coordinator.data["history"] = [
        {"erfasst_ts": 300, "start_ts": 500, "kwh": 20.0, "kosten": 10.0},  # zuletzt bestaetigt, mittlere Zeit
        {"erfasst_ts": 200, "start_ts": 100, "kwh": 5.0, "kosten": 2.5},    # nachtraeglich erfasst, aelteste Zeit
        {"erfasst_ts": 100, "start_ts": 900, "kwh": 30.0, "kosten": 15.0},  # zuerst bestaetigt, juengste Zeit
    ]

    conn = _FakeConnection()
    await _handle_charges(hass, conn, {"id": 1, "config_entry_id": entry.entry_id})

    assert [c["start_ts"] for c in conn.result["charges"]] == [900, 500, 100]


async def test_charges_ws_ohne_start_ts_faellt_auf_erfasst_ts_zurueck(hass, coordinators):
    from custom_components.ev_assistant.websocket_api import _handle_charges
    _handle_charges = _unwrap(_handle_charges)

    coordinator, entry = _make_coordinator(hass, coordinators, "sort2")
    await coordinator.async_setup()

    # Ein Eintrag ganz ohne start_ts (z.B. ein rein manueller Alt-Eintrag)
    # darf nicht verschwinden, sondern degradiert auf erfasst_ts.
    coordinator.data["history"] = [
        {"erfasst_ts": 50, "kwh": 1.0, "kosten": 0.5},
        {"erfasst_ts": 200, "start_ts": 100, "kwh": 2.0, "kosten": 1.0},
    ]

    conn = _FakeConnection()
    await _handle_charges(hass, conn, {"id": 1, "config_entry_id": entry.entry_id})

    charges = conn.result["charges"]
    assert len(charges) == 2
    assert charges[0]["start_ts"] == 100
    assert charges[1]["erfasst_ts"] == 50


async def test_trips_ws_sortiert_nach_start_ts(hass, coordinators):
    from custom_components.ev_assistant.websocket_api import _handle_trips
    _handle_trips = _unwrap(_handle_trips)

    coordinator, entry = _make_coordinator(hass, coordinators, "sort3")
    await coordinator.async_setup()

    # Analog: async_edit_trip(start_ts=...) kann start_ts nachtraeglich
    # aendern, ohne die Liste neu zu sortieren.
    coordinator.data["fahrten"] = [
        {"erfasst_ts": 300, "start_ts": 500, "km": 10.0},
        {"erfasst_ts": 200, "start_ts": 100, "km": 5.0},
        {"erfasst_ts": 100, "start_ts": 900, "km": 20.0},
    ]

    conn = _FakeConnection()
    await _handle_trips(hass, conn, {"id": 1, "config_entry_id": entry.entry_id})

    assert [f["start_ts"] for f in conn.result["trips"]] == [900, 500, 100]


async def test_charges_ws_unbekannte_config_entry_id_liefert_fehler(hass, coordinators):
    from custom_components.ev_assistant.websocket_api import _handle_charges
    _handle_charges = _unwrap(_handle_charges)

    conn = _FakeConnection()
    await _handle_charges(hass, conn, {"id": 1, "config_entry_id": "does-not-exist"})

    assert conn.result is None
    assert conn.error is not None


async def test_last_cost_sensor_attribute_ist_nur_noch_letzter_eintrag(hass, coordinators):
    """Regression: das 16KB-Ueberlauf-Fix darf "historie" NICHT mehr als
    Attribut anhaengen -- nur noch die Felder von hist[0] selbst."""
    from custom_components.ev_assistant.sensor import LastCostSensor

    coordinator, entry = _make_coordinator(hass, coordinators, "attrs1")
    await coordinator.async_setup()
    coordinator.data["history"] = [
        {"erfasst_ts": 100, "start_ts": 100, "kwh": 5.0, "kosten": 2.5},
    ]

    sensor = LastCostSensor(coordinator, entry)
    attrs = sensor.extra_state_attributes

    assert "historie" not in attrs
    assert attrs["kosten"] == 2.5


async def test_last_trip_sensor_attribute_ist_nur_noch_letzter_eintrag(hass, coordinators):
    """Regression: das 16KB-Ueberlauf-Fix darf "fahrtenbuch" NICHT mehr als
    Attribut anhaengen -- nur noch die Felder von fahrten[0] selbst."""
    from custom_components.ev_assistant.sensor import LastTripSensor

    coordinator, entry = _make_coordinator(hass, coordinators, "attrs2")
    await coordinator.async_setup()
    coordinator.data["fahrten"] = [
        {"erfasst_ts": 100, "start_ts": 100, "km": 12.5, "start_ort": "A", "end_ort": "B"},
    ]

    sensor = LastTripSensor(coordinator, entry)
    attrs = sensor.extra_state_attributes

    assert "fahrtenbuch" not in attrs
    assert attrs["km"] == 12.5
