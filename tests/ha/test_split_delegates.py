"""Umbau von coordinator.py (Issue #12): Wartung, Ladekarten, Leasing und
Import/Export/Backup liegen in eigenen Klassen (maintenance.py, charge_cards.py,
leasing.py, notifications.py, data_transfer.py). Die Methoden des Coordinators bleiben mit
gleichem Namen und gleicher Signatur bestehen und rufen nur durch -- Dienste,
Sensoren, Panel und Tests sehen dieselbe Schnittstelle. Diese Tests pruefen
mechanisch fuer jede durchgereichte Methode, dass Signatur und Weiterleitung
stimmen; das Verhalten selbst sichern die Fachtests und test_data_contract.py."""
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# (Klasse, Attribut am Coordinator, [(Name am Coordinator, Name in der Klasse)])
_DELEGATES = [
    ("maintenance.Maintenance", "_maintenance", [
        ("_migrate_wartung_zeit_einheiten",) * 2, ("_migrate_wartung_erledigt_anzahl",) * 2,
        ("_migrate_wartung_hu_typ",) * 2, ("_migrate_wartung_hu_name",) * 2,
        ("async_add_maintenance",) * 2, ("async_edit_maintenance",) * 2,
        ("async_delete_maintenance",) * 2, ("async_mark_maintenance_done",) * 2,
        ("wartung_stats",) * 2, ("_check_wartung_thresholds",) * 2,
    ]),
    ("charge_cards.ChargeCards", "_charge_cards", [
        ("async_add_ladekarte",) * 2, ("async_edit_ladekarte",) * 2,
        ("async_add_ladekarte_preisstufe",) * 2, ("async_delete_ladekarte_preisstufe",) * 2,
        ("async_delete_ladekarte",) * 2, ("_ladekarten_cost_total",) * 2, ("ladekarten_stats",) * 2,
    ]),
    ("leasing.Leasing", "_leasing", [("leasing_stats",) * 2, ("_check_leasing_thresholds",) * 2]),
    ("notifications.Notifications", "_notifications", [
        ("_en",) * 2, ("_notify",) * 2, ("_push",) * 2, ("_notify_soc_threshold",) * 2,
        ("_notify_trip",) * 2, ("_dismiss_trip",) * 2, ("_notify_tankerkoenig_unavailable",) * 2,
        ("_dismiss_tankerkoenig_unavailable",) * 2, ("_persistent_notification",) * 2, ("_dismiss",) * 2,
    ]),
    ("data_transfer.DataTransfer", "_transfer", [
        ("async_import_fahrtenbuch", "import_fahrtenbuch"), ("async_export_fahrtenbuch", "export_fahrtenbuch"),
        ("async_export_event_log", "export_event_log"), ("async_export_backup", "export_backup"),
        ("async_restore_backup", "restore_backup"),
    ]),
]
_CASES = [(cls, attr, c_name, h_name) for cls, attr, pairs in _DELEGATES for c_name, h_name in pairs]


def _host_class(path):
    import importlib

    module, name = path.split(".")
    return getattr(importlib.import_module(f"custom_components.ev_assistant.{module}"), name)


def _args_for(signature):
    """Platzhalterwerte fuer alle Parameter (ohne self): positional, soweit moeglich."""
    args = []
    params = [p for name, p in signature.parameters.items() if name != "self"]
    for i, param in enumerate(params):
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        args.append(f"wert_{i}")
    return args


@pytest.mark.parametrize("cls_path, attr, coordinator_name, host_name", _CASES)
def test_signatur_ist_identisch(cls_path, attr, coordinator_name, host_name):
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    host_cls = _host_class(cls_path)
    coordinator_sig = inspect.signature(getattr(EvAssistantCoordinator, coordinator_name))
    host_sig = inspect.signature(getattr(host_cls, host_name))
    assert coordinator_sig == host_sig, f"{coordinator_name}: Signatur weicht von {cls_path}.{host_name} ab"
    assert inspect.iscoroutinefunction(getattr(EvAssistantCoordinator, coordinator_name)) == \
        inspect.iscoroutinefunction(getattr(host_cls, host_name))


@pytest.mark.parametrize("cls_path, attr, coordinator_name, host_name", _CASES)
async def test_aufruf_wird_unveraendert_durchgereicht(cls_path, attr, coordinator_name, host_name):
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    host_cls = _host_class(cls_path)
    is_async = inspect.iscoroutinefunction(getattr(host_cls, host_name))
    mock = AsyncMock(return_value="ergebnis") if is_async else MagicMock(return_value="ergebnis")
    coordinator = EvAssistantCoordinator.__new__(EvAssistantCoordinator)  # kein HA noetig: nur Weiterleitung
    setattr(coordinator, attr, host_cls.__new__(host_cls))
    args = _args_for(inspect.signature(getattr(host_cls, host_name)))
    with patch.object(host_cls, host_name, new=mock):
        result = getattr(coordinator, coordinator_name)(*args)
        if is_async:
            result = await result
    assert result == "ergebnis"
    mock.assert_called_once()
    assert list(mock.call_args.args) + list(mock.call_args.kwargs.values()) == args
