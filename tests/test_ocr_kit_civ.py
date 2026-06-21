"""Tests de extracción de KIT/CIV (con confianza) en la respuesta OCR — sin red."""

from __future__ import annotations

import json

from e14.ocr import UMBRAL_REVISION, _parsear_respuesta

COLS = ["c1", "c2"]


def _respuesta(kit=None, civ=None) -> str:
    campos = {c: {"valor": 1, "confianza": 0.95} for c in COLS}
    return json.dumps({"campos": campos, "kit": kit, "civ": civ})


def test_parsear_respuesta_extrae_kit_y_civ_con_su_confianza():
    lectura = _parsear_respuesta(
        _respuesta(kit={"valor": "K-04521", "confianza": 0.9},
                  civ={"valor": "CIV-9981", "confianza": 0.4}),
        COLS,
    )
    assert lectura.numero_kit == "K-04521"
    assert lectura.confianza_kit == 0.9
    assert lectura.civ == "CIV-9981"
    assert lectura.confianza_civ == 0.4


def test_civ_confianza_baja_marca_necesita_revision():
    lectura = _parsear_respuesta(
        _respuesta(kit={"valor": "K-1", "confianza": 0.99},
                  civ={"valor": "4-64-07-14", "confianza": 0.4}),
        COLS,
    )
    assert lectura.necesita_revision is True
    assert "CIV=4-64-07-14" in lectura.detalle_api
    assert UMBRAL_REVISION > 0.4


def test_sin_kit_ni_civ_no_marca_revision_por_eso():
    lectura = _parsear_respuesta(_respuesta(), COLS)
    assert lectura.numero_kit is None
    assert lectura.civ is None
    assert lectura.confianza_kit == 0.0
    assert lectura.confianza_civ == 0.0
    assert lectura.necesita_revision is False  # nadie reportó baja confianza


def test_tolera_kit_civ_como_texto_suelto_sin_confianza():
    """Compatibilidad si la API devuelve un string en vez del objeto {valor, confianza}."""
    lectura = _parsear_respuesta(_respuesta(kit="K-04521", civ="CIV-9981"), COLS)
    assert lectura.numero_kit == "K-04521"
    assert lectura.confianza_kit == 0.0
