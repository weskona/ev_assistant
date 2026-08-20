"""Fixtures fuer die HA-Verdrahtungsschicht (coordinator/config_flow/__init__),
siehe requirements_test.txt fuer die Abhaengigkeit (pytest-homeassistant-
custom-component) und tests/conftest.py fuer den unabhaengigen, reinen
engine.py-Teststil (der bewusst NICHT hierher verschoben wird).

Kein `pytest_plugins = "pytest_homeassistant_custom_component"` noetig: das
Paket registriert sich bereits ueber einen pytest11-Entry-Point und ist damit
fuer JEDEN pytest-Lauf in einer venv aktiv, in der es installiert ist --
unabhaengig von einer Deklaration hier (seit pytest 9 waere eine Deklaration
in einem nicht-Top-Level-conftest.py ohnehin ein Fehler)."""
import os
import pathlib

import pytest


@pytest.fixture
def hass_config_dir(tmp_path: pathlib.Path) -> str:
    """Ersetzt die Standard-hass_config_dir (das "testing_config"-Verzeichnis
    aus pytest-homeassistant-custom-component) durch ein frisches Verzeichnis,
    das per Symlink auf UNSERE echte custom_components/ev_assistant zeigt.

    Noetig, weil Home Assistant's eigener Custom-Integration-Loader
    (homeassistant.loader._async_mount_config_dir) beim hass-Fixture-Setup
    "hass.config.config_dir" einmalig vorne an sys.path haengt, `import
    custom_components` ausfuehrt und DIESES Ergebnis dauerhaft in
    sys.modules cached. Zeigt config_dir auf das Plugin-eigene
    "testing_config" (Standard), gewinnt dessen eigenes
    custom_components/__init__.py (ein regulaeres Package) das Rennen --
    unsere echte Integration waere fuer den Rest des Testlaufs unsichtbar,
    selbst mit korrektem sys.path/PYTHONPATH (regulaere Packages schlagen
    Namespace-Package-Merges, siehe custom_components/__init__.py im
    Repo-Root fuer die dazugehoerige Gegenmassnahme auf unserer Seite)."""
    cc = tmp_path / "custom_components"
    cc.mkdir()
    (cc / "__init__.py").touch()
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    os.symlink(repo_root / "custom_components" / "ev_assistant", cc / "ev_assistant")
    return str(tmp_path)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Aktiviert enable_custom_integrations automatisch fuer jeden Test in
    diesem Verzeichnis, statt es in jedem einzelnen Test explizit anzufordern."""
    yield


@pytest.fixture
def coordinators():
    """Sammelt in einem Test direkt (ohne den vollen Entry-Lifecycle, siehe
    test_entry_lifecycle.py) erzeugte EvAssistantCoordinator-Instanzen und
    hebt beim Test-Teardown deren async_track_time_interval()-Listener
    zuverlaessig auf -- auch wenn eine Assertion im Testkoerper fehlschlaegt.
    Ohne das faellt der eigentliche Fehlschlag hinter einem verwirrenden
    "Lingering timer"-Fehler von pytest-homeassistant-custom-component's
    eigener Aufraeum-Pruefung unter."""
    created: list = []
    yield created
    for coordinator in created:
        for unsub in coordinator._unsub:
            unsub()
