"""Ein "except Exception: pass" im Integrationscode verschluckt Fehler spurlos.
Die Konvention des Projekts ("externe Abhaengigkeiten degradieren sauber", siehe
CONTRIBUTING.md) verlangt, dass ein Fehler zwar nicht die Integration umwirft,
aber im Log auftaucht. Der Test findet breite Handler (Exception/BaseException/
nackt), deren Rumpf nur aus `pass` besteht -- reine Quelltext-Auswertung, kein
Home Assistant noetig."""
import ast
from pathlib import Path

COMP = Path(__file__).resolve().parents[1] / "custom_components" / "ev_assistant"


def _silent_broad_handlers(path: Path) -> list[int]:
    hits = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.ExceptHandler):
            continue
        broad = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"))
        if broad and all(isinstance(stmt, ast.Pass) for stmt in node.body):
            hits.append(node.lineno)
    return hits


def test_keine_stillen_breiten_except_handler():
    found = {p.name: _silent_broad_handlers(p) for p in sorted(COMP.glob("*.py"))}
    found = {name: lines for name, lines in found.items() if lines}
    assert not found, f"'except Exception: pass' loggt nichts -- wenigstens _LOGGER.debug(...) ergaenzen: {found}"
