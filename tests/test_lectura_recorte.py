"""Tests del recorte de la región de votación cableado en lectura.leer_acta_pdf."""

from __future__ import annotations

import cv2
import numpy as np

from e14 import lectura
from e14.alineacion import LAYOUT_ACTA_COMPLETA, ResultadoAlineacion, columnas_de_layout
from e14.modelo import FUENTE_TESTIGO
from e14.ocr import LecturaOCR


def test_recortar_votos_activo_param_manda_sobre_entorno(monkeypatch):
    monkeypatch.setenv("OCR_RECORTAR_VOTOS", "1")
    assert lectura._recortar_votos_activo(False) is False   # el param gana
    assert lectura._recortar_votos_activo(True) is True
    assert lectura._recortar_votos_activo(None) is True     # cae al entorno


def test_recortar_votos_activo_entorno_apagado_por_defecto(monkeypatch):
    monkeypatch.delenv("OCR_RECORTAR_VOTOS", raising=False)
    assert lectura._recortar_votos_activo(None) is False


class _AlineadorFalso:
    """Devuelve una imagen alineada fija (sin tocar disco ni SIFT)."""
    dpi = 150

    def __init__(self, alineada):
        self._alineada = alineada

    def alinear_paginas(self, paginas, solo_layouts=None):
        return [ResultadoAlineacion(
            indice_pagina=1, layout_id=LAYOUT_ACTA_COMPLETA,
            inliers=200, confiable=True, imagen_alineada=self._alineada,
        )]


class _OCRFalso:
    """Registra la altura de la imagen que recibió reconocer_votos."""
    def __init__(self):
        self.altura_recibida = None

    def reconocer_votos(self, imagen_alineada, layout_id) -> LecturaOCR:
        self.altura_recibida = imagen_alineada.shape[0]
        cols = columnas_de_layout(layout_id)
        return LecturaOCR(
            valores={c: 1 for c in cols},
            confianzas={c: 0.99 for c in cols},
            confianza_global=0.99,
            necesita_revision=False,
        )


def _png_brillante(tmp_path):
    """Imagen alineada uniforme y clara (así mejorar_para_ocr no recorta negros)."""
    img = np.full((1363, 469), 200, dtype=np.uint8)
    ruta = tmp_path / "1_1_3_2_testigo.png"
    cv2.imwrite(str(ruta), img)
    return ruta, img


def _altura_ocr(tmp_path, monkeypatch, recortar):
    monkeypatch.setattr(lectura, "detectar_copias_en_evidencia", lambda *a, **k: ([], None))
    ruta, img = _png_brillante(tmp_path)
    ocr = _OCRFalso()
    lectura.leer_acta_pdf(str(ruta), _AlineadorFalso(img), ocr, FUENTE_TESTIGO,
                          codigo_mesa="1_1_3_2", recortar_votos=recortar)
    return ocr.altura_recibida


def test_recorte_reduce_la_imagen_que_llega_al_ocr(tmp_path, monkeypatch):
    alto_full = _altura_ocr(tmp_path, monkeypatch, recortar=False)
    alto_recorte = _altura_ocr(tmp_path, monkeypatch, recortar=True)
    assert alto_recorte < alto_full
    # ROI acta_completa = (0,0.36,1,0.885) -> ~52% del alto antes de escalar.
    assert alto_recorte / alto_full < 0.6
