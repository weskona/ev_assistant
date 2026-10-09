"""Tests fuer __init__.py::_build_entity_map() -- welche Entitaeten in die
Panel-Konfiguration gehen. Neben den eigenen Entitaeten (unique_id-Suffix)
und der SoC-Quelle stehen dort die konfigurierten Quell-Entitaeten aus
_PANEL_SOURCE_ENTITY_KEYS, damit Dashboard-Karten sie per `get_panels`
uebernehmen koennen statt sie ein zweites Mal von Hand einzutragen."""
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _entry(hass, data=None, options=None, entry_id="pm1"):
    from custom_components.ev_assistant.const import DOMAIN

    entry = MockConfigEntry(domain=DOMAIN, data=data or {}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    return entry


async def test_quell_entitaeten_aus_options_und_data(hass):
    from custom_components.ev_assistant import _build_entity_map

    entry = _entry(
        hass,
        data={"soc_entity": "sensor.auto_soc", "motor_entity": "binary_sensor.alt_motor"},
        options={
            "motor_entity": "binary_sensor.auto_motor",   # options schlagen data
            "plug_entity": "binary_sensor.auto_stecker",
            "home_entity": "sensor.wallbox_leistung",
        },
    )
    m = _build_entity_map(er.async_get(hass), entry)
    assert m["soc_entity"] == "sensor.auto_soc"
    assert m["motor_entity"] == "binary_sensor.auto_motor"
    assert m["plug_entity"] == "binary_sensor.auto_stecker"
    assert m["home_entity"] == "sensor.wallbox_leistung"


async def test_leere_und_nicht_konfigurierte_felder_fehlen(hass):
    from custom_components.ev_assistant import _build_entity_map

    entry = _entry(hass, options={"soc_entity": "sensor.auto_soc", "plug_entity": "", "power_entity": None})
    m = _build_entity_map(er.async_get(hass), entry)
    assert m == {"soc_entity": "sensor.auto_soc"}


async def test_keine_templates_oder_benachrichtigungen(hass):
    from custom_components.ev_assistant import _build_entity_map

    entry = _entry(hass, options={
        "soc_template": "{{ 50 }}",
        "notify_entities": ["notify.handy"],
        "evcc_host": "http://evcc.local:7070",
    })
    assert _build_entity_map(er.async_get(hass), entry) == {}


async def test_eigene_entitaeten_bleiben_erhalten(hass):
    from custom_components.ev_assistant import _build_entity_map
    from custom_components.ev_assistant.const import DOMAIN

    entry = _entry(hass, options={"plug_entity": "binary_sensor.auto_stecker"})
    reg = er.async_get(hass)
    reg.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_odo", config_entry=entry, suggested_object_id="ev_km_stand")
    m = _build_entity_map(reg, entry)
    assert m["odo"] == "sensor.ev_km_stand"
    assert m["plug_entity"] == "binary_sensor.auto_stecker"
