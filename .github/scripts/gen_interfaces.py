#!/usr/bin/env python3
"""Erzeugt docs/stable-interfaces.md (en) und docs/stable-interfaces.de.md aus dem Code.

Die Seiten sind die Liste der Schnittstellen, die ab 1.0 stabil bleiben (siehe
README, Abschnitt "Status & Known Limitations"): Dienste, Entitaeten, Config-/
Optionsschluessel, WebSocket-Befehle und die Panel-Konfiguration mit ihrer
`api_version`. Alles wird per `ast`/Textauswertung direkt aus dem Quellcode
gelesen (kein Home Assistant noetig), damit die Liste nicht von Hand
auseinanderlaufen kann:

    gen_interfaces.py            schreibt beide Dateien neu
    gen_interfaces.py --check    Exit 1, wenn die Dateien nicht zum Code passen

tests/test_stable_interfaces.py ruft den Check auf: Wer einen Dienst, eine
Entitaet, einen Schluessel oder einen WebSocket-Befehl hinzufuegt, aendert oder
entfernt, muss die Seiten neu erzeugen -- und sieht dabei im Diff, ob er gerade
eine zugesagte Schnittstelle bricht.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMP = ROOT / "custom_components" / "ev_assistant"
OUT_EN = ROOT / "docs" / "stable-interfaces.md"
OUT_DE = ROOT / "docs" / "stable-interfaces.de.md"

# Dienste, die ausdruecklich NICHT zur Stabilitaetszusage gehoeren (Testwerkzeuge).
NOT_STABLE_SERVICES = {
    "simulate_event": "test helper",
    "simulate_trip": "test helper",
}


# --------------------------------------------------------------------------- Quellen lesen

def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _const_strings(tree: ast.Module) -> dict[str, str]:
    """Modulweite NAME = "string"-Zuweisungen."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def registered_services() -> list[str]:
    """Namen der in __init__.py per hass.services.async_register registrierten Dienste."""
    consts = _const_strings(_parse(COMP / "const.py"))
    names: set[str] = set()
    for node in ast.walk(_parse(COMP / "__init__.py")):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_register"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Name)
            and node.args[1].id.startswith("SERVICE_")
        ):
            names.add(consts[node.args[1].id])
    return sorted(names)


def service_fields() -> dict[str, list[tuple[str, bool]]]:
    """services.yaml: Dienst -> [(Feld, Pflichtfeld)] (einfacher Zeilenparser, kein PyYAML)."""
    result: dict[str, list[tuple[str, bool]]] = {}
    service = None
    in_fields = False
    field = None
    for line in (COMP / "services.yaml").read_text(encoding="utf-8").splitlines():
        if re.match(r"^[a-z_0-9]+:\s*$", line):
            service = line.rstrip(":").strip()
            result[service] = []
            in_fields = False
            field = None
        elif service and re.match(r"^  fields:\s*$", line):
            in_fields = True
        elif service and re.match(r"^  [a-z_]+:", line):
            in_fields = False
        elif in_fields and (m := re.match(r"^    ([a-z_0-9]+):\s*$", line)):
            field = m.group(1)
            result[service].append((field, False))
        elif in_fields and field and re.match(r"^      required:\s*true\s*$", line):
            result[service][-1] = (field, True)
    return result


def _entity_classes(path: Path) -> list[dict]:
    """Klassen mit Entity-Schluessel (3. Argument von super().__init__) bzw. unique_id."""
    out = []
    for node in _parse(path).body:
        if not isinstance(node, ast.ClassDef):
            continue
        info = {"class": node.name, "key": None, "translation_key": None, "unit": None}
        for item in node.body:
            if isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "_attr_translation_key":
                        info["translation_key"] = item.value.value
                    if isinstance(target, ast.Name) and target.id == "_attr_native_unit_of_measurement":
                        info["unit"] = item.value.value
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "__init__"
                and len(sub.args) >= 3
                and isinstance(sub.args[2], ast.Constant)
                and isinstance(sub.args[2].value, str)
            ):
                info["key"] = sub.args[2].value
        if info["key"] is None and info["translation_key"] == "vehicle_image":
            info["key"] = "vehicle_image"
        if info["key"]:
            out.append(info)
    return out


def entities() -> list[dict]:
    names = json.loads((COMP / "translations" / "en.json").read_text(encoding="utf-8")).get("entity", {})
    rows = []
    for platform, fname in (("sensor", "sensor.py"), ("binary_sensor", "binary_sensor.py"), ("image", "image.py")):
        for info in _entity_classes(COMP / fname):
            tk = info["translation_key"]
            info["platform"] = platform
            info["name"] = names.get(platform, {}).get(tk, {}).get("name", "") if tk else ""
            rows.append(info)
    return sorted(rows, key=lambda r: (r["platform"], r["key"]))


def config_keys() -> list[tuple[str, str, str]]:
    """(Schritt, Schluessel, Pflicht/Optional) aus den build_*_schema()-Funktionen der config_flow.py."""
    consts = _const_strings(_parse(COMP / "const.py"))
    rows: list[tuple[str, str, str]] = []
    for node in _parse(COMP / "config_flow.py").body:
        if not (isinstance(node, ast.FunctionDef) and re.fullmatch(r"build_\w+_schema", node.name)):
            continue
        step = node.name[len("build_"):-len("_schema")]
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr in ("Required", "Optional")
                and sub.args
                and isinstance(sub.args[0], ast.Name)
                and sub.args[0].id in consts
            ):
                rows.append((step, consts[sub.args[0].id], sub.func.attr.lower()))
    return sorted(set(rows))


def websocket_commands() -> list[str]:
    cmds = []
    for node in _parse(COMP / "websocket_api.py").body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and node.value.value.startswith("ev_assistant/")
        ):
            cmds.append(node.value.value)
    return sorted(cmds)


def panel_config() -> tuple[int, list[str], list[str]]:
    """(api_version, Schluessel der Panel-Konfiguration, Schluessel der Quell-Entitaeten)."""
    init = _parse(COMP / "__init__.py")
    consts = _const_strings(_parse(COMP / "const.py"))
    api = 0
    keys: list[str] = []
    sources: list[str] = []
    for node in ast.walk(init):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_PANEL_API_VERSION" for t in node.targets):
            api = node.value.value
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_PANEL_SOURCE_ENTITY_KEYS" for t in node.targets
        ):
            sources = [consts[e.id] for e in node.value.elts if isinstance(e, ast.Name) and e.id in consts]
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "panel_config":
            keys += [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Subscript)
            and isinstance(node.targets[0].value, ast.Name)
            and node.targets[0].value.id == "panel_config"
            and isinstance(node.targets[0].slice, ast.Constant)
        ):
            keys.append(node.targets[0].slice.value)
    return api, sorted(set(keys)), sorted(set(sources) | {"soc_entity"})


# --------------------------------------------------------------------------- Ausgabe

TEXT = {
    "en": {
        "title": "Stable interfaces",
        "intro": (
            "This page lists the interfaces that stay stable within 1.x (see *Status & Known Limitations* in the "
            "[README](../README.md)). **It is generated from the code** by `.github/scripts/gen_interfaces.py`; "
            "a test fails when the code and this page differ. If you add, rename or remove something here, "
            "run `python3 .github/scripts/gen_interfaces.py` and look at the diff of this page: a removed or renamed "
            "entry is a **breaking change** and needs a major version and a CHANGELOG entry."
        ),
        "rules": "What \"stable\" means",
        "rules_list": [
            "**Additive changes are allowed** in 1.x: new services, new optional service fields, new entities, new "
            "attributes, new config keys with a default.",
            "**Not allowed** in 1.x: removing or renaming an entry below, changing the meaning of a field, making an "
            "optional field required, changing an entity's `unique_id` key.",
            "**Attributes** of the entities: the promise covers the attributes documented on the wiki page "
            "[Sensors & Entities](https://github.com/weskona/ev_assistant/wiki/Sensors-and-Entities); "
            "undocumented attributes may change.",
            "**Not part of the promise:** the test helpers `simulate_event` and `simulate_trip`, the numbers behind the "
            "automatic control (thresholds, estimates, recommendations) and the Glow card itself.",
        ],
        "services": "Services",
        "services_note": (
            "Domain `ev_assistant`. A trailing `?` marks an optional field, all others are required; "
            "every service additionally takes `config_entry_id` (the vehicle)."
        ),
        "col_service": "Service",
        "col_fields": "Fields",
        "col_status": "Status",
        "stable": "stable",
        "test_helper": "not part of the promise (test helper)",
        "entities": "Entities",
        "entities_note": (
            "The `unique_id` of every entity is `<config_entry_id>_<key>`. The key is stable; the entity ID "
            "(`sensor.<name>`) follows the translated name and the user's own renames."
        ),
        "col_platform": "Platform",
        "col_key": "Key (unique_id suffix)",
        "col_name": "Name (en)",
        "col_cfgkey": "Key",
        "config": "Config-flow and options keys",
        "config_note": (
            "Stored in the config entry (`data`/`options`). Existing installations keep working without "
            "reconfiguration: keys are not renamed without a migration."
        ),
        "col_step": "Step",
        "col_kind": "Required",
        "ws": "WebSocket commands",
        "ws_note": "Every command takes `config_entry_id`. They are the interface of the panel and the Glow card.",
        "panel": "Panel configuration",
        "panel_note": (
            "The panel hands this configuration to the Glow card. `api_version` is raised on every incompatible "
            "change to the fields below, the WebSocket commands or `evcc_live`; the card compares it with the "
            "version it expects and warns on a mismatch."
        ),
        "panel_api": "Current `api_version`",
        "panel_keys": "Top-level keys",
        "panel_sources": "Keys of `entities` (besides the `unique_id` keys above, which are present when the entity exists)",
        "yes": "yes",
    },
    "de": {
        "title": "Stabile Schnittstellen",
        "intro": (
            "Diese Seite listet die Schnittstellen, die innerhalb von 1.x stabil bleiben (siehe *Status & bekannte "
            "Grenzen* in der [README](../README.de.md)). **Sie wird aus dem Code erzeugt** "
            "(`.github/scripts/gen_interfaces.py`); ein Test schlägt fehl, wenn Code und Seite auseinanderlaufen. "
            "Wer hier etwas hinzufügt, umbenennt oder entfernt, führt `python3 .github/scripts/gen_interfaces.py` aus "
            "und prüft den Diff dieser Seite: ein entfernter oder umbenannter Eintrag ist ein **inkompatibler "
            "Bruch** und braucht eine neue Hauptversion und einen CHANGELOG-Eintrag."
        ),
        "rules": "Was „stabil“ heißt",
        "rules_list": [
            "**Additive Änderungen sind erlaubt** in 1.x: neue Dienste, neue optionale Dienstfelder, neue Entitäten, "
            "neue Attribute, neue Config-Schlüssel mit Standardwert.",
            "**Nicht erlaubt** in 1.x: einen Eintrag unten entfernen oder umbenennen, die Bedeutung eines Feldes "
            "ändern, ein optionales Feld zum Pflichtfeld machen, den `unique_id`-Schlüssel einer Entität ändern.",
            "**Attribute** der Entitäten: die Zusage gilt für die auf der Wiki-Seite "
            "[Sensoren & Entitäten](https://github.com/weskona/ev_assistant/wiki/Sensors-and-Entities-DE) "
            "dokumentierten Attribute; nicht dokumentierte können sich ändern.",
            "**Nicht Teil der Zusage:** die Testwerkzeuge `simulate_event` und `simulate_trip`, die Zahlen hinter der "
            "automatischen Steuerung (Schwellen, Schätzungen, Empfehlungen) und die Glow-Karte selbst.",
        ],
        "services": "Dienste",
        "services_note": (
            "Domain `ev_assistant`. Ein angehängtes `?` kennzeichnet ein optionales Feld, alle anderen sind Pflicht; "
            "jeder Dienst nimmt zusätzlich `config_entry_id` (das Fahrzeug)."
        ),
        "col_service": "Dienst",
        "col_fields": "Felder",
        "col_status": "Status",
        "stable": "stabil",
        "test_helper": "nicht Teil der Zusage (Testwerkzeug)",
        "entities": "Entitäten",
        "entities_note": (
            "Die `unique_id` jeder Entität ist `<config_entry_id>_<Schlüssel>`. Der Schlüssel ist stabil; die "
            "Entity-ID (`sensor.<name>`) folgt dem übersetzten Namen und den eigenen Umbenennungen des Nutzers."
        ),
        "col_platform": "Plattform",
        "col_key": "Schlüssel (unique_id-Suffix)",
        "col_name": "Name (en)",
        "col_cfgkey": "Schlüssel",
        "config": "Config-Flow- und Optionsschlüssel",
        "config_note": (
            "Gespeichert im Config-Entry (`data`/`options`). Bestehende Installationen laufen ohne Neukonfiguration "
            "weiter: Schlüssel werden nicht ohne Migration umbenannt."
        ),
        "col_step": "Schritt",
        "col_kind": "Pflicht",
        "ws": "WebSocket-Befehle",
        "ws_note": "Jeder Befehl nimmt `config_entry_id`. Sie sind die Schnittstelle von Panel und Glow-Karte.",
        "panel": "Panel-Konfiguration",
        "panel_note": (
            "Das Panel reicht diese Konfiguration an die Glow-Karte weiter. `api_version` wird bei jeder "
            "inkompatiblen Änderung der Felder unten, der WebSocket-Befehle oder von `evcc_live` erhöht; die Karte "
            "vergleicht sie mit der erwarteten Version und warnt bei Abweichung."
        ),
        "panel_api": "Aktuelle `api_version`",
        "panel_keys": "Schlüssel der obersten Ebene",
        "panel_sources": (
            "Schlüssel von `entities` (neben den `unique_id`-Schlüsseln oben, "
            "die vorhanden sind, wenn die Entität existiert)"
        ),
        "yes": "ja",
    },
}


def render(lang: str) -> str:
    t = TEXT[lang]
    services = registered_services()
    fields = service_fields()
    ents = entities()
    cfg = config_keys()
    ws = websocket_commands()
    api, pkeys, psources = panel_config()

    out = [f"# {t['title']}", "", t["intro"], "", f"## {t['rules']}", ""]
    out += [f"- {line}" for line in t["rules_list"]]

    out += ["", f"## {t['services']}", "", t["services_note"], ""]
    out += [f"| {t['col_service']} | {t['col_fields']} | {t['col_status']} |", "|---|---|---|"]
    for name in services:
        fs = [f + ("" if req else "?") for f, req in fields.get(name, []) if f != "config_entry_id"]
        status = t["test_helper"] if name in NOT_STABLE_SERVICES else t["stable"]
        out.append(f"| `{name}` | {', '.join(f'`{f}`' for f in fs) or '–'} | {status} |")

    out += ["", f"## {t['entities']}", "", t["entities_note"], ""]
    out += [f"| {t['col_platform']} | {t['col_key']} | {t['col_name']} |", "|---|---|---|"]
    for e in ents:
        out.append(f"| {e['platform']} | `{e['key']}` | {e['name'] or '–'} |")

    out += ["", f"## {t['config']}", "", t["config_note"], ""]
    out += [f"| {t['col_step']} | {t['col_cfgkey']} | {t['col_kind']} |", "|---|---|---|"]
    for step, key, kind in cfg:
        out.append(f"| {step} | `{key}` | {t['yes'] if kind == 'required' else '–'} |")

    out += ["", f"## {t['ws']}", "", t["ws_note"], ""]
    out += [f"- `{c}`" for c in ws]

    out += ["", f"## {t['panel']}", "", t["panel_note"], "", f"- {t['panel_api']}: **{api}**"]
    out += [f"- {t['panel_keys']}: " + ", ".join(f"`{k}`" for k in pkeys)]
    out += [f"- {t['panel_sources']}: " + ", ".join(f"`{k}`" for k in psources), ""]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    targets = ((OUT_EN, "en"), (OUT_DE, "de"))
    if "--check" in argv:
        stale = [p.name for p, lang in targets if not p.exists() or p.read_text(encoding="utf-8") != render(lang)]
        if stale:
            hint = "`python3 .github/scripts/gen_interfaces.py` ausfuehren und den Diff pruefen"
            print(f"::error::{', '.join(stale)} passt nicht zum Code -- {hint}", file=sys.stderr)
            return 1
        print("docs/stable-interfaces*.md entsprechen dem Code.")
        return 0
    OUT_EN.parent.mkdir(exist_ok=True)
    for path, lang in targets:
        path.write_text(render(lang), encoding="utf-8")
        print(f"geschrieben: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
