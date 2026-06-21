"""Tests de leer_identificadores.py — sin red, sin re-alinear imágenes reales."""

from __future__ import annotations

from e14.almacen import Almacen
from e14.modelo import ActaE14, FUENTE_REGISTRADURIA, FUENTE_TESTIGO
from e14.ocr import LecturaOCR
from leer_identificadores import _filas_del_puesto, _leer_una


def _alm_con_mesas(tmp_path) -> Almacen:
    alm = Almacen(tmp_path / "t.db")
    alm.guardar(ActaE14(codigo_mesa="1_1_3_2", fuente=FUENTE_TESTIGO, c1=1, c2=1,
                        archivo_origen="a.pdf"))
    alm.guardar(ActaE14(codigo_mesa="1_1_3_3", fuente=FUENTE_TESTIGO, c1=1, c2=1,
                        archivo_origen="b.pdf"))
    alm.guardar(ActaE14(codigo_mesa="1_2_1_1", fuente=FUENTE_TESTIGO, c1=1, c2=1,
                        archivo_origen="c.pdf"))
    alm.guardar(ActaE14(codigo_mesa="2_1_3_2", fuente=FUENTE_TESTIGO, c1=1, c2=1,
                        archivo_origen="d.pdf"))
    return alm


def test_filas_del_puesto_filtra_por_municipio_zona_puesto(tmp_path):
    alm = _alm_con_mesas(tmp_path)
    # Mismo puesto (1-1-3), dos mesas distintas (2 y 3): ambas deben quedar.
    filas = _filas_del_puesto(alm, "1", "1", "3", None)
    assert {f["codigo_mesa"] for f in filas} == {"1_1_3_2", "1_1_3_3"}
    alm.cerrar()


def test_filas_del_puesto_solo_municipio_trae_todas_sus_zonas(tmp_path):
    alm = _alm_con_mesas(tmp_path)
    filas = _filas_del_puesto(alm, "1", None, None, None)
    assert {f["codigo_mesa"] for f in filas} == {"1_1_3_2", "1_1_3_3", "1_2_1_1"}
    alm.cerrar()


def test_filas_del_puesto_filtra_por_fuente(tmp_path):
    alm = Almacen(tmp_path / "t.db")
    alm.guardar(ActaE14(codigo_mesa="1_1_3_2", fuente=FUENTE_TESTIGO, c1=1, c2=1, archivo_origen="a.pdf"))
    alm.guardar(ActaE14(codigo_mesa="1_1_3_2", fuente=FUENTE_REGISTRADURIA, c1=1, c2=1, archivo_origen="a2.pdf"))
    filas = _filas_del_puesto(alm, "1", "1", "3", FUENTE_REGISTRADURIA)
    assert len(filas) == 1 and filas[0]["fuente"] == FUENTE_REGISTRADURIA
    alm.cerrar()


class _OCRFalso:
    def leer_identificadores(self, imagen_alineada) -> LecturaOCR:
        return LecturaOCR({}, {}, 0.9, False, numero_kit="K-1", civ="C-1",
                          confianza_kit=0.9, confianza_civ=0.9)


def test_leer_una_reporta_error_si_falta_archivo_origen():
    fila = {"codigo_mesa": "1_1_3_2", "fuente": FUENTE_TESTIGO, "archivo_origen": None}
    r = _leer_una(fila, alineador=None, ocr=_OCRFalso())
    assert r["ok"] is False
    assert "sin archivo_origen" in r["mensaje"]
