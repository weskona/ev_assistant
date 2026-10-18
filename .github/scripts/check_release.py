#!/usr/bin/env python3
"""Prueft vor einem Release, ob manifest.json (und hacs.json) in Ordnung sind.

Hintergrund: Release 0.99.39 ging mit leerer manifest.json raus, weil
release.yml blind zippt. Aufruf:

    check_release.py <tag> [--zip ev_assistant.zip] [--root .]

Ohne --zip wird custom_components/ev_assistant/manifest.json aus dem
Checkout gelesen, mit --zip die manifest.json im Wurzelverzeichnis der Zip
(so, wie HACS sie installiert). Geprueft wird:
  - manifest.json existiert, ist nicht leer, ist valides JSON und enthaelt
    domain/name/version (domain == ev_assistant)
  - version == Tag ohne fuehrendes "v" -- auch bei Suffix-Tags komplett
    (v0.99.42-glow.2 <-> 0.99.42-glow.2)
  - hacs.json ist valides JSON
  - CHANGELOG.md hat einen Abschnitt "## [<version>]": bei stabilen Tags ein
    Fehler, bei Pre-Releases (Tag mit "-") nur eine Warnung
  - custom_components/ev_assistant/CHANGELOG.md (liegt in der Zip und wird
    im README verlinkt) ist identisch zum CHANGELOG.md im Root (das die
    Workflows fuer die Release-Notes lesen): bei stabilen Tags ein Fehler,
    bei Pre-Releases nur eine Warnung (auf glow-panel koennen beide per
    merge=union auseinanderlaufen). Fehlt die Kopie, wird nichts geprueft.

Exit-Code 0 = alles in Ordnung, 1 = mindestens ein Verstoss (alle werden
gemeldet), 2 = falscher Aufruf.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

DOMAIN = "ev_assistant"
REQUIRED_KEYS = ("domain", "name", "version")
MANIFEST_IN_REPO = Path("custom_components") / DOMAIN / "manifest.json"


def _load_manifest_text(root: Path, zip_path: Path | None) -> tuple[str | None, str, str]:
    """Liefert (Text oder None, Quellbeschreibung, Fehlermeldung oder '')."""
    if zip_path is not None:
        source = f"{zip_path}:manifest.json"
        try:
            with zipfile.ZipFile(zip_path) as zf:
                try:
                    return zf.read("manifest.json").decode("utf-8"), source, ""
                except KeyError:
                    return None, source, f"{source} fehlt in der Zip (manifest.json muss im Wurzelverzeichnis liegen)"
        except (OSError, zipfile.BadZipFile) as err:
            return None, source, f"{zip_path} ist keine lesbare Zip-Datei: {err}"
    path = root / MANIFEST_IN_REPO
    if not path.is_file():
        return None, str(path), f"{path} existiert nicht"
    try:
        return path.read_text(encoding="utf-8"), str(path), ""
    except (OSError, UnicodeDecodeError) as err:
        return None, str(path), f"{path} ist nicht lesbar: {err}"


def check_manifest(text: str, source: str, tag: str) -> list[str]:
    """Prueft den Manifest-Inhalt; liefert eine Liste von Fehlermeldungen."""
    if not text.strip():
        return [f"{source} ist leer"]
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as err:
        return [f"{source} ist kein valides JSON: {err}"]
    if not isinstance(manifest, dict):
        return [f"{source} enthaelt kein JSON-Objekt"]
    errors = [f"{source}: Pflichtfeld '{key}' fehlt oder ist leer" for key in REQUIRED_KEYS if not manifest.get(key)]
    if manifest.get("domain") and manifest["domain"] != DOMAIN:
        errors.append(f"{source}: domain ist '{manifest['domain']}', erwartet '{DOMAIN}'")
    expected = tag[1:] if tag.startswith("v") else tag
    version = manifest.get("version")
    if version and version != expected:
        errors.append(f"{source}: version '{version}' passt nicht zum Tag '{tag}' (erwartet '{expected}')")
    return errors


def check_hacs(root: Path) -> list[str]:
    path = root / "hacs.json"
    if not path.is_file():
        return [f"{path} existiert nicht"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        return [f"{path} ist kein valides JSON: {err}"]
    if not isinstance(data, dict) or not data.get("name"):
        return [f"{path}: Pflichtfeld 'name' fehlt"]
    return []


def check_changelog(root: Path, tag: str) -> tuple[list[str], list[str]]:
    """Liefert (Fehler, Warnungen) fuer den CHANGELOG-Abschnitt."""
    version = tag[1:] if tag.startswith("v") else tag
    path = root / "CHANGELOG.md"
    heading = f"## [{version}]"
    try:
        found = any(line.startswith(heading) for line in path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        found = False
    if found:
        return [], []
    message = f"{path}: kein Abschnitt '{heading}'"
    return ([], [message]) if "-" in version else ([message], [])


def check_changelog_copies(root: Path, tag: str) -> tuple[list[str], list[str]]:
    """Liefert (Fehler, Warnungen): CHANGELOG.md im Root und die Kopie unter
    custom_components/ev_assistant/ muessen identisch sein. Beide werden von
    Hand synchron gehalten (siehe merge-main-into-glow.yml, das beide per
    merge=union vereinigt) -- ohne Pruefung faellt eine vergessene Kopie erst
    auf, wenn jemand die Zip-Version liest."""
    version = tag[1:] if tag.startswith("v") else tag
    root_path = root / "CHANGELOG.md"
    copy_path = root / "custom_components" / DOMAIN / "CHANGELOG.md"
    try:
        root_text = root_path.read_bytes()
        copy_text = copy_path.read_bytes()
    except OSError:
        return [], []  # eine der beiden fehlt -- check_changelog() meldet das ggf. selbst
    if root_text == copy_text:
        return [], []
    message = f"{copy_path} weicht von {root_path} ab (beide muessen identisch sein)"
    return ([], [message]) if "-" in version else ([message], [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tag", help="Release-Tag, z. B. v0.99.42 oder v0.99.42-glow.2")
    parser.add_argument("--zip", dest="zip_path", type=Path, help="fertige ev_assistant.zip statt des Checkouts pruefen")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository-Wurzel (Standard: .)")
    args = parser.parse_args(argv)

    errors: list[str] = []
    text, source, load_error = _load_manifest_text(args.root, args.zip_path)
    if text is None:
        errors.append(load_error)
    else:
        errors += check_manifest(text, source, args.tag)
    errors += check_hacs(args.root)
    changelog_errors, warnings = check_changelog(args.root, args.tag)
    errors += changelog_errors
    copy_errors, copy_warnings = check_changelog_copies(args.root, args.tag)
    errors += copy_errors
    warnings += copy_warnings

    for warning in warnings:
        print(f"::warning::{warning}")
    for error in errors:
        print(f"::error::{error}")
    if errors:
        print(f"Release-Pruefung fuer {args.tag} FEHLGESCHLAGEN ({len(errors)} Verstoss/Verstoesse).", file=sys.stderr)
        return 1
    print(f"Release-Pruefung fuer {args.tag} bestanden ({source}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
