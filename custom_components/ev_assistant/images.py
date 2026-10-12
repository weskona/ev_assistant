"""Fahrzeugbild je Config-Entry: Verarbeitung und Ablage (rein dateibasiert).

Alles hier ist SYNCHRON und gehoert in den Executor (Pillow dekodiert,
kodiert und schreibt Dateien) -- die Services in __init__.py und die
Image-Entitaet (image.py) rufen es ueber hass.async_add_executor_job() auf.

Ablauf einer hochgeladenen Datei (process_image()):
  1. Rohgroesse und Format pruefen (JPEG/PNG/WebP), die Pixelzahl aus dem
     Header VOR dem Dekodieren (Dekompressionsbomben), dann verify().
  2. EXIF-Orientierung anwenden, danach ALLE Metadaten verwerfen (Handyfotos
     enthalten GPS) -- das Ergebnis wird aus den reinen Pixeln neu kodiert.
  3. Seitenverhaeltnis erhalten, laengste Seite hoechstens MAX_SIDE_PX.
  4. Neu kodieren: JPEG, bei Transparenz (freigestellte Fahrzeuge) WebP mit
     Alpha-Kanal; die Qualitaet sinkt schrittweise, bis das Ergebnis grob
     TARGET_BYTES erreicht.

Gespeichert wird unter <config>/ev_assistant_images/<entry_id>.<ext>
(jpg oder webp, atomar per tmp + os.replace). Die Datei gehoert dem Entry:
async_remove_entry() loescht sie, ein Unload nicht.

Pillow ist seit Home Assistant 2024.4 Core-Abhaengigkeit und wird deshalb
erst hier importiert (kein Eintrag in manifest.requirements)."""
from __future__ import annotations

import contextlib
import io
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

IMAGE_DIR_NAME = "ev_assistant_images"
# Hardlimits gegen Missbrauch/Speicherdruck (die file_upload-Grenze von Home
# Assistant liegt bei 100 MB und ist fuer uns zu hoch).
MAX_RAW_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 50_000_000
MAX_SIDE_PX = 1200
TARGET_BYTES = 300 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
QUALITY_STEPS = (88, 82, 76, 70, 62, 54, 46)
MAX_DOWNSCALE_ROUNDS = 4
# Erweiterung je Ausgabeformat und passender content_type
EXT_JPEG = "jpg"
EXT_WEBP = "webp"
CONTENT_TYPES = {EXT_JPEG: "image/jpeg", EXT_WEBP: "image/webp"}


class ImageProcessingError(Exception):
    """Nutzerbehebbarer Fehler bei der Bildverarbeitung. `key` ist der
    translation_key unter "exceptions" in strings.json, `placeholders` die
    zugehoerigen Platzhalter."""

    def __init__(self, key: str, placeholders: dict[str, str] | None = None) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = placeholders or {}


def image_dir(config_dir: str) -> Path:
    return Path(config_dir) / IMAGE_DIR_NAME


def find_image(directory: Path, entry_id: str) -> Path | None:
    """Vorhandene Bilddatei des Entries (jpg oder webp), sonst None."""
    for ext in (EXT_JPEG, EXT_WEBP):
        path = directory / f"{entry_id}.{ext}"
        if path.is_file():
            return path
    return None


def image_info(directory: Path, entry_id: str) -> tuple[datetime, str] | None:
    """(Zeitpunkt der letzten Aenderung UTC, content_type) oder None."""
    path = find_image(directory, entry_id)
    if path is None:
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, tz=timezone.utc), CONTENT_TYPES[path.suffix.lstrip(".")]


def read_image(directory: Path, entry_id: str) -> bytes | None:
    path = find_image(directory, entry_id)
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError:
        _LOGGER.warning("ev_assistant: Fahrzeugbild %s nicht lesbar", path)
        return None


def _encode(img, ext: str, quality: int) -> bytes:
    buf = io.BytesIO()
    if ext == EXT_WEBP:
        img.save(buf, format="WEBP", quality=quality, method=4)
    else:
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def process_image(source: Path) -> tuple[bytes, str]:
    """Prueft, normalisiert und kodiert das hochgeladene Bild neu.
    Rueckgabe (Bytes, Erweiterung). Wirft ImageProcessingError."""
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as err:  # pragma: no cover - Core hat Pillow seit 2024.4
        raise ImageProcessingError("pillow_missing") from err

    try:
        size = source.stat().st_size
    except OSError as err:
        raise ImageProcessingError("image_unreadable") from err
    if size > MAX_RAW_BYTES:
        raise ImageProcessingError("image_too_large", {"max_mb": str(MAX_RAW_BYTES // (1024 * 1024))})

    try:
        with Image.open(source) as probe:
            fmt = probe.format
            width, height = probe.size  # nur Header, noch nichts dekodiert
        if fmt not in ALLOWED_FORMATS:
            raise ImageProcessingError("image_format", {"formats": "JPEG, PNG, WebP"})
        if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
            raise ImageProcessingError("image_too_many_pixels", {"max_mp": str(MAX_PIXELS // 1_000_000)})
        with Image.open(source) as checked:
            checked.verify()
        with Image.open(source) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            has_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
            img = img.convert("RGBA" if has_alpha else "RGB")
    except ImageProcessingError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning,
            OSError, SyntaxError, ValueError, MemoryError, EOFError) as err:
        raise ImageProcessingError("image_unreadable") from err

    ext = EXT_WEBP if has_alpha else EXT_JPEG
    # Neu aus reinen Pixeln aufbauen: so bleiben garantiert keine Metadaten
    # (EXIF/GPS/ICC/Kommentare) uebrig.
    clean = Image.new(img.mode, img.size)
    clean.paste(img)
    clean.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX), Image.Resampling.LANCZOS)

    data = b""
    for _ in range(MAX_DOWNSCALE_ROUNDS):
        for quality in QUALITY_STEPS:
            data = _encode(clean, ext, quality)
            if len(data) <= TARGET_BYTES:
                return data, ext
        w, h = clean.size
        clean = clean.resize((max(1, int(w * 0.85)), max(1, int(h * 0.85))), Image.Resampling.LANCZOS)
    return data, ext


def store_image(directory: Path, entry_id: str, data: bytes, ext: str) -> Path:
    """Schreibt das Bild atomar und entfernt eine Datei mit anderer Endung."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{entry_id}.{ext}"
    tmp = directory / f"{entry_id}.{ext}.tmp"
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()
    for other in (EXT_JPEG, EXT_WEBP):
        if other != ext:
            with contextlib.suppress(OSError):
                (directory / f"{entry_id}.{other}").unlink()
    return target


def remove_images(directory: Path, entry_id: str) -> bool:
    """Loescht die Bilddatei(en) des Entries. True, wenn etwas geloescht wurde."""
    removed = False
    for ext in (EXT_JPEG, EXT_WEBP):
        path = directory / f"{entry_id}.{ext}"
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


def cleanup_orphans(directory: Path, valid_entry_ids: set[str]) -> list[str]:
    """Loescht Dateien (und liegengebliebene .tmp), die zu keinem Entry mehr
    gehoeren. Rueckgabe: Namen der geloeschten Dateien."""
    removed: list[str] = []
    if not directory.is_dir():
        return removed
    for path in directory.iterdir():
        if not path.is_file():
            continue
        name = path.name
        stem = name.split(".", 1)[0]
        if stem in valid_entry_ids and not name.endswith(".tmp"):
            continue
        with contextlib.suppress(OSError):
            path.unlink()
            removed.append(name)
    return removed
