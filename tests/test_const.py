"""Tests fuer const.py -- reine Funktionen ohne HA-Import (anders als
coordinator.py/config_flow.py, die sich deshalb nicht per pytest testen
lassen, siehe conftest.py)."""
from const import (
    DEFAULT_LADE_MODUS,
    LADE_MODUS_GEMISCHT,
    LADE_MODUS_NUR_AUSWAERTS,
    LADE_MODUS_NUR_ZUHAUSE,
    resolve_lade_modus,
)


def test_resolve_lade_modus_fehlender_wert_liefert_gemischt():
    assert resolve_lade_modus(None) == LADE_MODUS_GEMISCHT
    assert resolve_lade_modus(None) == DEFAULT_LADE_MODUS


def test_resolve_lade_modus_unbekannter_wert_liefert_gemischt():
    # z.B. ein Tippfehler oder ein Wert aus einer zukuenftigen Version, den
    # diese Version noch nicht kennt -- defensiv wie ein fehlender Wert.
    assert resolve_lade_modus("unbekannt") == LADE_MODUS_GEMISCHT


def test_resolve_lade_modus_gueltige_werte_bleiben_erhalten():
    assert resolve_lade_modus(LADE_MODUS_NUR_ZUHAUSE) == LADE_MODUS_NUR_ZUHAUSE
    assert resolve_lade_modus(LADE_MODUS_GEMISCHT) == LADE_MODUS_GEMISCHT
    assert resolve_lade_modus(LADE_MODUS_NUR_AUSWAERTS) == LADE_MODUS_NUR_AUSWAERTS
