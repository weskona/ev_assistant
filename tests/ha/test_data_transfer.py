"""data_transfer.py::DataTransfer (Import/Export/Backup, aus coordinator.py
ausgelagert): Die oeffentlichen Methoden des Coordinators bleiben bestehen und
rufen nur noch durch. Das Verhalten selbst sichern test_data_contract.py,
test_archive.py, test_event_log.py und test_evcc_mode_control.py ab."""
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _coordinator(hass, coordinators, entry_id):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator


def test_modul_importiert_ohne_zyklus_zum_coordinator():
    """data_transfer.py darf den Coordinator nur fuer Typpruefung importieren."""
    import ast
    from pathlib import Path

    import custom_components.ev_assistant.data_transfer as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    runtime_imports = [
        n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    assert not [n for n in runtime_imports if isinstance(n, ast.ImportFrom) and n.module == "coordinator"]


@pytest.mark.parametrize("coordinator_name, transfer_name, args", [
    ("async_import_fahrtenbuch", "import_fahrtenbuch", ([],)),
    ("async_export_fahrtenbuch", "export_fahrtenbuch", ()),
    ("async_export_event_log", "export_event_log", ()),
    ("async_export_backup", "export_backup", ()),
    ("async_restore_backup", "restore_backup", ("{}",)),
])
async def test_coordinator_methoden_rufen_datatransfer_durch(
    hass, coordinators, coordinator_name, transfer_name, args,
):
    from custom_components.ev_assistant.data_transfer import DataTransfer

    coordinator = await _coordinator(hass, coordinators, f"dt_{transfer_name}")
    assert isinstance(coordinator._transfer, DataTransfer) and coordinator._transfer._host is coordinator
    with patch.object(DataTransfer, transfer_name, new=AsyncMock(return_value="ergebnis")) as mocked:
        result = await getattr(coordinator, coordinator_name)(*args)
    assert result == "ergebnis"
    mocked.assert_awaited_once_with(*args)
