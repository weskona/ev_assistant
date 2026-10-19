"""Tests fuer .github/scripts/check_release.py (Release-Guard, siehe 0.99.39:
Release mit leerer manifest.json)."""
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "check_release.py"
_spec = importlib.util.spec_from_file_location("check_release", _SCRIPT)
check_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_release)

GOOD = {"domain": "ev_assistant", "name": "EV Assistant", "version": "0.99.42"}


def _repo(tmp_path, manifest_text=None, hacs_text='{"name": "EV Assistant"}', changelog="## [0.99.42]\n- x\n"):
    comp = tmp_path / "custom_components" / "ev_assistant"
    comp.mkdir(parents=True)
    if manifest_text is not None:
        (comp / "manifest.json").write_text(manifest_text, encoding="utf-8")
    if hacs_text is not None:
        (tmp_path / "hacs.json").write_text(hacs_text, encoding="utf-8")
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def _run(tmp_path, tag, *extra):
    return check_release.main([tag, "--root", str(tmp_path), *extra])


def test_valider_fall_besteht(tmp_path, capsys):
    root = _repo(tmp_path, json.dumps(GOOD))
    assert _run(root, "v0.99.42") == 0


def test_leere_manifest_faellt_durch(tmp_path, capsys):
    root = _repo(tmp_path, "")
    assert _run(root, "v0.99.42") == 1
    assert "ist leer" in capsys.readouterr().out


def test_manifest_nur_whitespace_faellt_durch(tmp_path):
    assert _run(_repo(tmp_path, "  \n"), "v0.99.42") == 1


def test_fehlende_manifest_faellt_durch(tmp_path, capsys):
    assert _run(_repo(tmp_path, None), "v0.99.42") == 1
    assert "existiert nicht" in capsys.readouterr().out


def test_kaputtes_json_faellt_durch(tmp_path, capsys):
    assert _run(_repo(tmp_path, '{"domain": "ev_assistant", '), "v0.99.42") == 1
    assert "kein valides JSON" in capsys.readouterr().out


def test_fehlendes_pflichtfeld_faellt_durch(tmp_path, capsys):
    manifest = {k: v for k, v in GOOD.items() if k != "name"}
    assert _run(_repo(tmp_path, json.dumps(manifest)), "v0.99.42") == 1
    assert "'name'" in capsys.readouterr().out


def test_falsche_domain_faellt_durch(tmp_path):
    assert _run(_repo(tmp_path, json.dumps({**GOOD, "domain": "andere"})), "v0.99.42") == 1


def test_versions_mismatch_faellt_durch(tmp_path, capsys):
    assert _run(_repo(tmp_path, json.dumps({**GOOD, "version": "0.99.41"})), "v0.99.42") == 1
    assert "passt nicht zum Tag" in capsys.readouterr().out


def test_suffix_tag_wird_komplett_verglichen(tmp_path):
    glow = {**GOOD, "version": "0.99.42-glow.2"}
    root = _repo(tmp_path, json.dumps(glow), changelog="")
    assert _run(root, "v0.99.42-glow.2") == 0
    # Nur der Teil vor dem "-" reicht NICHT:
    assert _run(_repo(tmp_path / "b", json.dumps(GOOD), changelog=""), "v0.99.42-glow.2") == 1


def test_kaputte_hacs_json_faellt_durch(tmp_path, capsys):
    root = _repo(tmp_path, json.dumps(GOOD), hacs_text="{kaputt")
    assert _run(root, "v0.99.42") == 1
    assert "hacs.json" in capsys.readouterr().out


def test_stabiler_tag_ohne_changelog_abschnitt_faellt_durch(tmp_path, capsys):
    root = _repo(tmp_path, json.dumps(GOOD), changelog="## [0.99.41]\n")
    assert _run(root, "v0.99.42") == 1
    assert "kein Abschnitt" in capsys.readouterr().out


def test_prerelease_ohne_changelog_abschnitt_warnt_nur(tmp_path, capsys):
    root = _repo(tmp_path, json.dumps({**GOOD, "version": "0.99.43-glow.1"}), changelog="## [0.99.42]\n")
    assert _run(root, "v0.99.43-glow.1") == 0
    assert "::warning::" in capsys.readouterr().out


def _zip(tmp_path, manifest_text, omit=None):
    path = tmp_path / "ev_assistant.zip"
    with zipfile.ZipFile(path, "w") as zf:
        if manifest_text is not None:
            zf.writestr("manifest.json", manifest_text)
        zf.writestr("__init__.py", "")
        for name in check_release.REQUIRED_ZIP_FILES:
            if name not in (omit or ()):
                zf.writestr(name, "x")
    return path


def test_zip_valide(tmp_path):
    root = _repo(tmp_path, "")  # Checkout-Manifest ist egal, geprueft wird die Zip
    assert _run(root, "v0.99.42", "--zip", str(_zip(tmp_path, json.dumps(GOOD)))) == 0


def test_zip_mit_leerer_manifest_faellt_durch(tmp_path, capsys):
    root = _repo(tmp_path, json.dumps(GOOD))
    assert _run(root, "v0.99.42", "--zip", str(_zip(tmp_path, ""))) == 1
    assert "ist leer" in capsys.readouterr().out


def test_zip_ohne_manifest_faellt_durch(tmp_path):
    root = _repo(tmp_path, json.dumps(GOOD))
    assert _run(root, "v0.99.42", "--zip", str(_zip(tmp_path, None))) == 1


def test_zip_nicht_lesbar_faellt_durch(tmp_path):
    root = _repo(tmp_path, json.dumps(GOOD))
    bad = tmp_path / "kaputt.zip"
    bad.write_bytes(b"kein zip")
    assert _run(root, "v0.99.42", "--zip", str(bad)) == 1


def test_alle_verstoesse_werden_gemeldet(tmp_path, capsys):
    root = _repo(tmp_path, json.dumps({**GOOD, "version": "0.0.1"}), hacs_text="{", changelog="")
    assert _run(root, "v0.99.42") == 1
    out = capsys.readouterr().out
    assert out.count("::error::") == 3


@pytest.mark.parametrize("tag", ["v0.99.42", "0.99.42"])
def test_tag_mit_und_ohne_v(tmp_path, tag):
    assert _run(_repo(tmp_path, json.dumps(GOOD)), tag) == 0


def _write_copy(root, text):
    path = root / "custom_components" / "ev_assistant" / "CHANGELOG.md"
    path.write_text(text, encoding="utf-8")


def test_changelog_kopie_identisch_besteht(tmp_path):
    root = _repo(tmp_path, json.dumps(GOOD))
    _write_copy(root, "## [0.99.42]\n- x\n")
    assert _run(root, "v0.99.42") == 0


def test_changelog_kopie_abweichend_faellt_durch(tmp_path, capsys):
    root = _repo(tmp_path, json.dumps(GOOD))
    _write_copy(root, "## [0.99.42]\n- y\n")
    assert _run(root, "v0.99.42") == 1
    assert "weicht von" in capsys.readouterr().out


def test_changelog_kopie_abweichend_bei_prerelease_nur_warnung(tmp_path, capsys):
    root = _repo(tmp_path, json.dumps({**GOOD, "version": "0.99.42-glow.1"}), changelog="## [0.99.42-glow.1]\n- x\n")
    _write_copy(root, "## [0.99.42-glow.1]\n- y\n")
    assert _run(root, "v0.99.42-glow.1") == 0
    assert "::warning::" in capsys.readouterr().out


def test_changelog_kopie_fehlt_ist_kein_fehler(tmp_path):
    # Kopie fehlt: nichts zu vergleichen (die Root-Datei prueft check_changelog()).
    assert _run(_repo(tmp_path, json.dumps(GOOD)), "v0.99.42") == 0


def test_zip_ohne_glow_karte_faellt_durch(tmp_path, capsys):
    root = _repo(tmp_path, json.dumps(GOOD))
    zip_path = _zip(tmp_path, json.dumps(GOOD), omit=["frontend/mg-car-dashboard.js"])
    assert _run(root, "v0.99.42", "--zip", str(zip_path)) == 1
    assert "frontend/mg-car-dashboard.js fehlt in der Zip" in capsys.readouterr().out


def test_zip_ohne_klassisches_panel_faellt_durch(tmp_path):
    root = _repo(tmp_path, json.dumps(GOOD))
    zip_path = _zip(tmp_path, json.dumps(GOOD), omit=["frontend/ev-assistant-panel.js"])
    assert _run(root, "v0.99.42", "--zip", str(zip_path)) == 1
