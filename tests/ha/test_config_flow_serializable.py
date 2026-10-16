"""Regressionsnetz: jedes Config-/Options-Flow-Formular muss sich mit HAs
eigener Formular-Serialisierung in JSON fuers Frontend wandeln lassen.

Hintergrund: 0.99.53 fuehrte fuer die Rueckfall-Abfahrtszeit vol.Match(...)
ein. HA (Core 2026.9, Serialisierung ueber "probatio") kann das nicht
serialisieren -> HTTP 500 beim Anzeigen des evcc-Schritts, im Frontend nur
als verwirrendes "not a valid option" sichtbar. Die uebrigen Flow-Tests rufen
die async_step_*-Methoden direkt auf und gehen nie durch diese Serialisierung."""
import pytest
from homeassistant.helpers import config_validation as cv

# Imports aus custom_components.* wie in den uebrigen tests/ha/-Tests erst
# INNERHALB der Tests (siehe conftest.py): auf Modulebene scheitert schon das
# Einsammeln der Tests mit "No module named 'custom_components'".
_BUILDER_NAMES = [
    "build_comparison_schema", "build_detection_schema", "build_evcc_loadpoint_schema",
    "build_evcc_schema", "build_heimladen_schema", "build_leasing_schema",
    "build_modus_schema", "build_output_schema", "build_power_schema",
    "build_trip_schema", "build_vehicle_schema",
]


def _to_field_list(schema):
    try:
        from probatio.codecs.fields import to_field_list  # HA >= 2026.9
    except ImportError:
        import voluptuous_serialize

        return voluptuous_serialize.convert(schema, custom_serializer=cv.custom_serializer)
    return to_field_list(schema, custom_serializer=cv.custom_serializer)


def test_builderliste_vollstaendig():
    """Faengt ein neu hinzugekommenes build_*_schema() ab, das hier noch
    nicht mitgeprueft wuerde."""
    from custom_components.ev_assistant import config_flow

    found = sorted(n for n in dir(config_flow) if n.startswith("build_") and n.endswith("_schema"))
    assert found == sorted(_BUILDER_NAMES)


@pytest.mark.parametrize("name", _BUILDER_NAMES)
def test_formular_serialisierbar(name):
    from custom_components.ev_assistant import config_flow

    builder = getattr(config_flow, name)
    schema = builder({}, ["Loadpoint 1", "Loadpoint 2"]) if name == "build_evcc_loadpoint_schema" else builder({})
    assert _to_field_list(schema)


@pytest.mark.parametrize("value, ok", [
    ("06:00", True), ("6:30", True), ("23:59", True),
    ("24:00", False), ("06:60", False), ("abc", False), ("0600", False),
])
def test_rueckfall_abfahrtszeit_pruefung(value, ok):
    from custom_components.ev_assistant import config_flow
    from custom_components.ev_assistant.const import CONF_EVCC_DEPARTURE_FALLBACK_TIME

    errors: dict = {}
    config_flow._validate_departure_time({CONF_EVCC_DEPARTURE_FALLBACK_TIME: value}, errors)
    assert (errors == {}) is ok
    if not ok:
        assert errors == {CONF_EVCC_DEPARTURE_FALLBACK_TIME: "invalid_time"}


def test_rueckfall_abfahrtszeit_leer_ist_erlaubt():
    from custom_components.ev_assistant import config_flow

    errors: dict = {}
    config_flow._validate_departure_time({}, errors)
    assert errors == {}
