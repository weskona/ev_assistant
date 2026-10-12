"""Fahrzeugbild je Config-Entry (images.py, image.py, Services
set_vehicle_image/clear_vehicle_image, async_remove_entry).

Hochgeladene Dateien kommen in Produktion aus home_assistant.components.
file_upload (process_uploaded_file); hier wird dieser Kontextmanager durch
eine Testversion ersetzt, die auf Dateien im tmp_path zeigt."""
import contextlib
import io
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _entry(hass, entry_id="img1", soc="sensor.img_soc"):
    from custom_components.ev_assistant.const import CONF_SOC_ENTITY, CONF_USABLE_KWH, DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_SOC_ENTITY: soc, CONF_USABLE_KWH: 50.0}, options={}, entry_id=entry_id
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _image_eid(hass, entry):
    return er.async_get(hass).async_get_entity_id("image", "ev_assistant", f"{entry.entry_id}_vehicle_image")


def _bild_bytes(size=(80, 40), fmt="JPEG", mode="RGB", color=(200, 30, 30), exif=None) -> bytes:
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


@pytest.fixture
def uploads(tmp_path):
    """Registriert Upload-Dateien (file_id -> Pfad) und patcht file_upload."""
    dateien: dict[str, Path] = {}

    @contextlib.contextmanager
    def fake_process_uploaded_file(hass, file_id):
        if file_id not in dateien:
            raise ValueError("File does not exist")
        yield dateien[file_id]

    def add(file_id: str, data: bytes) -> str:
        path = tmp_path / f"upload_{file_id}"
        path.write_bytes(data)
        dateien[file_id] = path
        return file_id

    with patch("homeassistant.components.file_upload.process_uploaded_file", fake_process_uploaded_file):
        yield add


async def _set(hass, entry, file_id):
    from custom_components.ev_assistant.const import DOMAIN

    await hass.services.async_call(
        DOMAIN, "set_vehicle_image", {"config_entry_id": entry.entry_id, "file_id": file_id}, blocking=True
    )


async def _clear(hass, entry):
    from custom_components.ev_assistant.const import DOMAIN

    await hass.services.async_call(DOMAIN, "clear_vehicle_image", {"config_entry_id": entry.entry_id}, blocking=True)


def _bild_dir(hass) -> Path:
    from custom_components.ev_assistant.images import image_dir

    return image_dir(hass.config.config_dir)


async def test_ohne_bild_ist_die_entitaet_unknown_versteckt_und_aktiviert(hass):
    entry = _entry(hass)
    await _setup(hass, entry)
    eid = _image_eid(hass, entry)
    assert eid is not None
    assert hass.states.get(eid).state == "unknown"
    reg = er.async_get(hass).async_get(eid)
    assert reg.hidden_by is not None  # versteckt ...
    assert reg.disabled_by is None  # ... aber aktiviert


async def test_gueltiges_bild_datei_entitaet_und_panel_config(hass, uploads):
    from custom_components.ev_assistant import _build_entity_map

    entry = _entry(hass)
    await _setup(hass, entry)
    await _set(hass, entry, uploads("f1", _bild_bytes()))
    eid = _image_eid(hass, entry)
    assert hass.states.get(eid).state != "unknown"
    assert (_bild_dir(hass) / f"{entry.entry_id}.jpg").is_file()
    assert _build_entity_map(er.async_get(hass), entry)["vehicle_image"] == eid
    # Das Bild liegt nur als Datei vor, nie in self.data/Store:
    coordinator = hass.data["ev_assistant"][entry.entry_id]
    assert "vehicle_image" not in coordinator.data
    assert ".jpg" not in str(coordinator.data)


async def test_bild_wird_ueber_image_entity_ausgeliefert(hass, uploads):
    from homeassistant.components.image import async_get_image

    entry = _entry(hass)
    await _setup(hass, entry)
    await _set(hass, entry, uploads("f1", _bild_bytes()))
    bild = await async_get_image(hass, _image_eid(hass, entry))
    assert bild.content_type == "image/jpeg"
    assert Image.open(io.BytesIO(bild.content)).format == "JPEG"


@pytest.mark.parametrize(
    ("daten", "key"),
    [
        (_bild_bytes(fmt="GIF", mode="P", color=1), "image_format"),
        (b"das ist kein bild" * 10, "image_unreadable"),
    ],
)
async def test_falsches_format_oder_kaputt_ergibt_validation_error_ohne_datei(hass, uploads, daten, key):
    entry = _entry(hass)
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError) as err:
        await _set(hass, entry, uploads("f1", daten))
    assert err.value.translation_key == key
    assert not list(_bild_dir(hass).glob("*")) if _bild_dir(hass).exists() else True
    assert hass.states.get(_image_eid(hass, entry)).state == "unknown"


async def test_zu_grosse_datei_ergibt_validation_error(hass, uploads, monkeypatch):
    from custom_components.ev_assistant import images

    monkeypatch.setattr(images, "MAX_RAW_BYTES", 100)
    entry = _entry(hass)
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError) as err:
        await _set(hass, entry, uploads("f1", _bild_bytes(size=(200, 200))))
    assert err.value.translation_key == "image_too_large"
    assert not (_bild_dir(hass) / f"{entry.entry_id}.jpg").exists()


async def test_dekompressionsbombe_wird_vor_dem_dekodieren_abgelehnt(hass, uploads, monkeypatch):
    from custom_components.ev_assistant import images

    monkeypatch.setattr(images, "MAX_PIXELS", 1000)
    entry = _entry(hass)
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError) as err:
        await _set(hass, entry, uploads("f1", _bild_bytes(size=(100, 100), fmt="PNG")))
    assert err.value.translation_key == "image_too_many_pixels"
    assert not list(_bild_dir(hass).glob("*")) if _bild_dir(hass).exists() else True


async def test_exif_gps_wird_verworfen(hass, uploads):
    exif = Image.Exif()
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (52.0, 31.0, 12.0)
    gps[3] = "E"
    gps[4] = (13.0, 24.0, 18.0)
    exif[0x010F] = "Handyhersteller"
    quelle = _bild_bytes(exif=exif)
    assert Image.open(io.BytesIO(quelle)).getexif().get_ifd(0x8825), "Testbild muss GPS enthalten"

    entry = _entry(hass)
    await _setup(hass, entry)
    await _set(hass, entry, uploads("f1", quelle))
    gespeichert = Image.open(_bild_dir(hass) / f"{entry.entry_id}.jpg")
    assert not gespeichert.getexif()
    assert not gespeichert.getexif().get_ifd(0x8825)
    assert "exif" not in gespeichert.info
    assert b"Handyhersteller" not in (_bild_dir(hass) / f"{entry.entry_id}.jpg").read_bytes()


async def test_exif_orientation_wird_angewendet(hass, uploads):
    exif = Image.Exif()
    exif[0x0112] = 6  # 90 Grad im Uhrzeigersinn drehen
    entry = _entry(hass)
    await _setup(hass, entry)
    await _set(hass, entry, uploads("f1", _bild_bytes(size=(80, 40), exif=exif)))
    assert Image.open(_bild_dir(hass) / f"{entry.entry_id}.jpg").size == (40, 80)


async def test_seitenverhaeltnis_bleibt_und_laengste_seite_hoechstens_1200(hass, uploads):
    entry = _entry(hass)
    await _setup(hass, entry)
    await _set(hass, entry, uploads("f1", _bild_bytes(size=(3000, 1500))))
    breite, hoehe = Image.open(_bild_dir(hass) / f"{entry.entry_id}.jpg").size
    assert max(breite, hoehe) <= 1200
    assert breite == 2 * hoehe


async def test_freigestelltes_bild_behaelt_transparenz_als_webp(hass, uploads):
    from homeassistant.components.image import async_get_image

    entry = _entry(hass)
    await _setup(hass, entry)
    quelle = Image.new("RGBA", (60, 30), (0, 0, 0, 0))
    quelle.putpixel((30, 15), (255, 0, 0, 255))
    buf = io.BytesIO()
    quelle.save(buf, format="PNG")
    await _set(hass, entry, uploads("f1", buf.getvalue()))
    pfad = _bild_dir(hass) / f"{entry.entry_id}.webp"
    assert pfad.is_file() and not (_bild_dir(hass) / f"{entry.entry_id}.jpg").exists()
    ergebnis = Image.open(pfad).convert("RGBA")
    assert ergebnis.getpixel((0, 0))[3] == 0  # Hintergrund bleibt durchsichtig
    assert (await async_get_image(hass, _image_eid(hass, entry))).content_type == "image/webp"


async def test_ersetzen_raeumt_andere_endung_auf(hass, uploads):
    entry = _entry(hass)
    await _setup(hass, entry)
    await _set(hass, entry, uploads("f1", _bild_bytes()))
    quelle = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    buf = io.BytesIO()
    quelle.save(buf, format="PNG")
    await _set(hass, entry, uploads("f2", buf.getvalue()))
    assert sorted(p.name for p in _bild_dir(hass).iterdir()) == [f"{entry.entry_id}.webp"]


async def test_clear_loescht_datei_und_setzt_entitaet_auf_unknown(hass, uploads):
    entry = _entry(hass)
    await _setup(hass, entry)
    await _set(hass, entry, uploads("f1", _bild_bytes()))
    await _clear(hass, entry)
    assert not (_bild_dir(hass) / f"{entry.entry_id}.jpg").exists()
    assert hass.states.get(_image_eid(hass, entry)).state == "unknown"


async def test_unbekannte_config_entry_id_ergibt_validation_error(hass, uploads):
    from custom_components.ev_assistant.const import DOMAIN

    entry = _entry(hass)
    await _setup(hass, entry)
    for dienst, daten in (
        ("set_vehicle_image", {"config_entry_id": "gibt_es_nicht", "file_id": uploads("f1", _bild_bytes())}),
        ("clear_vehicle_image", {"config_entry_id": "gibt_es_nicht"}),
    ):
        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(DOMAIN, dienst, daten, blocking=True)
        assert err.value.translation_key == "unknown_config_entry"


async def test_unbekannte_file_id_ergibt_validation_error(hass, uploads):
    entry = _entry(hass)
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError) as err:
        await _set(hass, entry, "abgelaufen")
    assert err.value.translation_key == "unknown_file_id"


async def test_unload_loescht_die_datei_nicht_remove_entry_schon(hass, uploads):
    entry = _entry(hass)
    await _setup(hass, entry)
    await _set(hass, entry, uploads("f1", _bild_bytes()))
    datei = _bild_dir(hass) / f"{entry.entry_id}.jpg"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert datei.is_file()
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not datei.exists()


async def test_neustart_mit_vorhandener_datei_ist_state_nicht_unknown(hass, uploads):
    entry = _entry(hass)
    await _setup(hass, entry)
    await _set(hass, entry, uploads("f1", _bild_bytes()))
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(_image_eid(hass, entry)).state not in ("unknown", "unavailable")


async def test_verwaiste_dateien_werden_beim_setup_aufgeraeumt(hass):
    verzeichnis = _bild_dir(hass)
    verzeichnis.mkdir(parents=True)
    (verzeichnis / "geloeschter_entry.jpg").write_bytes(b"x")
    (verzeichnis / "img1.jpg.tmp").write_bytes(b"x")
    entry = _entry(hass, "img1")
    (verzeichnis / "img1.jpg").write_bytes(_bild_bytes())
    await _setup(hass, entry)
    assert sorted(p.name for p in verzeichnis.iterdir()) == ["img1.jpg"]


async def test_zwei_fahrzeuge_sind_unabhaengig(hass, uploads):
    from custom_components.ev_assistant import _build_entity_map

    a = _entry(hass, "veh_a", "sensor.a_soc")
    b = _entry(hass, "veh_b", "sensor.b_soc")
    await _setup(hass, a)  # laedt die Integration und damit auch den zweiten Entry
    assert b.state.value == "loaded"
    eid_a, eid_b = _image_eid(hass, a), _image_eid(hass, b)
    assert eid_a and eid_b and eid_a != eid_b
    reg = er.async_get(hass)
    assert _build_entity_map(reg, a)["vehicle_image"] == eid_a
    assert _build_entity_map(reg, b)["vehicle_image"] == eid_b

    await _set(hass, a, uploads("fa", _bild_bytes(color=(255, 0, 0))))
    assert (_bild_dir(hass) / "veh_a.jpg").is_file()
    assert not (_bild_dir(hass) / "veh_b.jpg").exists()
    assert hass.states.get(eid_b).state == "unknown"

    await _set(hass, b, uploads("fb", _bild_bytes(color=(0, 0, 255))))
    await _clear(hass, a)
    assert not (_bild_dir(hass) / "veh_a.jpg").exists()
    assert (_bild_dir(hass) / "veh_b.jpg").is_file()
    assert hass.states.get(eid_a).state == "unknown"
    assert hass.states.get(eid_b).state != "unknown"
