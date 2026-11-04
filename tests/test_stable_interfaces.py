"""Die Liste der stabilen Schnittstellen (docs/stable-interfaces*.md) wird aus dem
Code erzeugt (.github/scripts/gen_interfaces.py). Diese Tests brauchen kein Home
Assistant (reine Quelltext-Auswertung, laufen auch im Job "Engine-Tests") und
zwingen dazu, die Seiten bei jeder Aenderung an einer zugesagten Schnittstelle
neu zu erzeugen -- der Diff zeigt dann, ob gerade etwas bricht."""
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "gen_interfaces.py"
_spec = importlib.util.spec_from_file_location("gen_interfaces", _SCRIPT)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_seiten_entsprechen_dem_code():
    assert gen.main(["--check"]) == 0, "python3 .github/scripts/gen_interfaces.py ausfuehren und den Diff pruefen"


def test_registrierte_dienste_haben_einen_services_yaml_eintrag_und_umgekehrt():
    registered = set(gen.registered_services())
    documented = set(gen.service_fields())
    assert registered == documented, (registered ^ documented)


def test_jeder_dienst_nimmt_config_entry_id():
    for name, fields in gen.service_fields().items():
        assert ("config_entry_id", True) in fields, name


def test_testwerkzeuge_sind_registrierte_dienste():
    assert set(gen.NOT_STABLE_SERVICES) <= set(gen.registered_services())


def test_entitaeten_schluessel_sind_eindeutig_je_plattform():
    ents = gen.entities()
    assert len(ents) >= 60
    pairs = [(e["platform"], e["key"]) for e in ents]
    assert len(pairs) == len(set(pairs))


def test_websocket_befehle_und_panel_konfiguration():
    assert set(gen.websocket_commands()) == {
        "ev_assistant/charges", "ev_assistant/evcc_sessions", "ev_assistant/event_log", "ev_assistant/trips",
    }
    api, keys, sources = gen.panel_config()
    assert api >= 1
    assert {"api_version", "config_entry_id", "entities", "vehicles"} <= set(keys)
    assert "soc_entity" in sources


def test_config_schluessel_gefunden():
    keys = {k for _, k, _ in gen.config_keys()}
    assert {"soc_entity", "usable_kwh", "lade_modus", "home_charging_method", "evcc_host"} <= keys
