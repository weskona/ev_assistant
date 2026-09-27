"""Tests fuer const.py -- reine Funktionen ohne HA-Import (anders als
coordinator.py/config_flow.py, die sich deshalb nicht per pytest testen
lassen, siehe conftest.py)."""
from const import (
    DEFAULT_LADE_MODUS,
    HOME_CHARGING_METHOD_EVCC,
    HOME_CHARGING_METHOD_GENERISCH,
    LADE_MODUS_GEMISCHT,
    LADE_MODUS_NUR_AUSWAERTS,
    LADE_MODUS_NUR_ZUHAUSE,
    resolve_home_charging_method,
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


def test_resolve_home_charging_method_fehlender_wert_mit_evcc_host_liefert_evcc():
    # Bestandsinstallation mit bereits konfiguriertem evcc_host -- Default
    # darf sich fuer sie nicht aendern (Nutzerwunsch "WICHTIG").
    assert resolve_home_charging_method(None, "http://evcc.local:7070") == HOME_CHARGING_METHOD_EVCC


def test_resolve_home_charging_method_fehlender_wert_ohne_evcc_host_liefert_generisch():
    # Bestandsinstallation OHNE evcc (z.B. fugazzy) -- Default deckt das ab,
    # ohne dass aktiv etwas umgestellt werden muss.
    assert resolve_home_charging_method(None, None) == HOME_CHARGING_METHOD_GENERISCH
    assert resolve_home_charging_method(None, "") == HOME_CHARGING_METHOD_GENERISCH


def test_resolve_home_charging_method_unbekannter_wert_faellt_auf_evcc_host_zurueck():
    assert resolve_home_charging_method("unbekannt", "http://evcc.local:7070") == HOME_CHARGING_METHOD_EVCC
    assert resolve_home_charging_method("unbekannt", None) == HOME_CHARGING_METHOD_GENERISCH


def test_resolve_home_charging_method_gueltiger_wert_hat_vorrang_vor_evcc_host():
    # Explizit gespeicherter Wert gewinnt immer, unabhaengig von evcc_host --
    # sonst koennte der Nutzer nie zu "generisch" wechseln, waehrend evcc_host
    # noch (ungenutzt) gespeichert ist.
    assert resolve_home_charging_method(HOME_CHARGING_METHOD_GENERISCH, "http://evcc.local:7070") == (
        HOME_CHARGING_METHOD_GENERISCH
    )
    assert resolve_home_charging_method(HOME_CHARGING_METHOD_EVCC, None) == HOME_CHARGING_METHOD_EVCC
