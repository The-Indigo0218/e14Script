"""Tests del orquestador de lote (auditar.py) — sin OCR, con lector falso."""

from __future__ import annotations

import pytest

from auditar import seleccionar_mesas, procesar_lote
from e14.almacen import Almacen
from e14.cobertura import cobertura_lote
from e14.modelo import ActaE14, FUENTE_TESTIGO, FUENTE_REGISTRADURIA


def _lector_falso(registro):
    """Lector inyectable que no hace OCR: solo registra la llamada y devuelve un acta."""
    def lector(ruta, fuente, codigo):
        registro.append((fuente, codigo, ruta.name))
        return ActaE14(codigo_mesa=codigo, fuente=fuente, archivo_origen=str(ruta), c1=10, c2=5)
    return lector


def test_seleccionar_solo_listas_por_defecto(lote_cartagena):
    cat, datos = lote_cartagena
    cob = cobertura_lote(cat, 1, datos)
    assert seleccionar_mesas(cob) == ["1_21_1_13"]
    assert set(seleccionar_mesas(cob, incluir_parciales=True)) == {"1_21_1_13", "1_1_1_1"}


def test_procesa_par_listo_con_codigo_canonico(lote_cartagena, tmp_path):
    cat, datos = lote_cartagena
    registro = []
    alm = Almacen(tmp_path / "t.db")
    res = procesar_lote(cat, 1, datos, alm, _lector_falso(registro))
    # La mesa lista tiene 2 fuentes -> 2 lecturas, con el código canónico (sin ceros).
    assert res["leidas"] == 2 and res["seleccionadas"] == 1
    assert {(f, c) for f, c, _ in registro} == {
        (FUENTE_TESTIGO, "1_21_1_13"), (FUENTE_REGISTRADURIA, "1_21_1_13")
    }
    # Y se guardó en DB con ese mismo código (cruza con el catálogo).
    assert set(alm.leer_por_fuente(FUENTE_TESTIGO)) == {"1_21_1_13"}
    alm.cerrar()


def test_idempotente_no_reprocesa(lote_cartagena, tmp_path):
    cat, datos = lote_cartagena
    alm = Almacen(tmp_path / "t.db")
    procesar_lote(cat, 1, datos, alm, _lector_falso([]))
    registro2 = []
    res2 = procesar_lote(cat, 1, datos, alm, _lector_falso(registro2))
    assert res2["leidas"] == 0 and res2["saltadas"] == 1
    assert registro2 == []
    alm.cerrar()


def test_reauditar_fuerza_relectura(lote_cartagena, tmp_path):
    cat, datos = lote_cartagena
    alm = Almacen(tmp_path / "t.db")
    procesar_lote(cat, 1, datos, alm, _lector_falso([]))
    registro2 = []
    res2 = procesar_lote(cat, 1, datos, alm, _lector_falso(registro2), reauditar=True)
    assert res2["leidas"] == 2 and res2["saltadas"] == 0
    alm.cerrar()


def test_incluir_parciales_procesa_solo_testigo(lote_cartagena, tmp_path):
    cat, datos = lote_cartagena
    registro = []
    alm = Almacen(tmp_path / "t.db")
    res = procesar_lote(cat, 1, datos, alm, _lector_falso(registro), incluir_parciales=True)
    # 1_21_1_13 (2 fuentes) + 1_1_1_1 (solo testigo) = 3 lecturas.
    assert res["leidas"] == 3
    assert (FUENTE_TESTIGO, "1_1_1_1") in {(f, c) for f, c, _ in registro}
    alm.cerrar()


def test_paralelo_da_el_mismo_resultado_que_secuencial(lote_cartagena, tmp_path):
    cat, datos = lote_cartagena
    registro = []
    alm = Almacen(tmp_path / "t.db")
    res = procesar_lote(cat, 1, datos, alm, _lector_falso(registro),
                        incluir_parciales=True, paralelo=4)
    # Mismo resultado que sin --paralelo: 1_21_1_13 (2 fuentes) + 1_1_1_1 (testigo) = 3.
    assert res["leidas"] == 3 and res["errores"] == 0
    assert {(f, c) for f, c, _ in registro} == {
        (FUENTE_TESTIGO, "1_21_1_13"), (FUENTE_REGISTRADURIA, "1_21_1_13"),
        (FUENTE_TESTIGO, "1_1_1_1"),
    }
    assert set(alm.leer_por_fuente(FUENTE_TESTIGO)) == {"1_21_1_13", "1_1_1_1"}
    alm.cerrar()


def test_limite_recorta_mesas(lote_cartagena, tmp_path):
    cat, datos = lote_cartagena
    alm = Almacen(tmp_path / "t.db")
    res = procesar_lote(cat, 1, datos, alm, _lector_falso([]),
                        incluir_parciales=True, limite=1)
    # Orden: 1_1_1_1 (solo testigo) va primera -> con límite 1 se procesa solo esa.
    assert res["leidas"] == 1
    alm.cerrar()
