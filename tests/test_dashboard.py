"""Tests de dashboard.py — sin red, con una base SQLite local real."""

from __future__ import annotations

from dashboard import _comparacion_por_puesto, _filas_para_revisar
from e14.almacen import Almacen
from e14.modelo import ActaE14, FUENTE_TESTIGO


def test_filas_para_revisar_solo_lista_necesita_revision_y_sin_verificar(tmp_path):
    alm = Almacen(str(tmp_path / "t.db"))
    alm.guardar(ActaE14(codigo_mesa="1_1_1_1", fuente=FUENTE_TESTIGO, c1=1, c2=2,
                        necesita_revision=True, notas="REVISAR: c1=1 (conf baja 50%)"))
    alm.guardar(ActaE14(codigo_mesa="1_1_1_2", fuente=FUENTE_TESTIGO, c1=3, c2=4,
                        necesita_revision=False))
    pendientes = _filas_para_revisar(alm)
    assert [f["codigo_mesa"] for f in pendientes] == ["1_1_1_1"]
    alm.cerrar()


def test_filas_para_revisar_desaparece_tras_marcar_verificado(tmp_path):
    alm = Almacen(str(tmp_path / "t.db"))
    alm.guardar(ActaE14(codigo_mesa="1_1_1_1", fuente=FUENTE_TESTIGO, c1=1, c2=2,
                        necesita_revision=True))
    assert len(_filas_para_revisar(alm)) == 1
    alm.marcar_verificado("1_1_1_1", FUENTE_TESTIGO, verificado=True, nota="ok")
    assert _filas_para_revisar(alm) == []
    alm.cerrar()


def test_comparacion_por_puesto_agrupa_y_cuenta_por_zona_puesto():
    testigo = {
        "1_1_3_2": {"c1": 10, "c2": 5, "confianza": 0.95},
        "1_1_3_3": {"c1": 8, "c2": 5, "confianza": 0.5},
        "1_2_1_1": {"c1": 1, "c2": 1, "confianza": 0.9},
    }
    registraduria = {
        "1_1_3_2": {"c1": 10, "c2": 5, "confianza": 0.9},
        "1_1_3_3": {"c1": 9, "c2": 5, "confianza": 0.9},
        "1_2_1_1": {"c1": 1, "c2": 1, "confianza": 0.9},
    }
    grupos = _comparacion_por_puesto(testigo, registraduria)
    g1 = next(g for g in grupos if g["zona"] == "1" and g["puesto"] == "3")
    assert g1["total"] == 2 and g1["coincide"] == 1 and g1["discrepancia"] == 1
    assert g1["confianza_baja"] == 1
    g2 = next(g for g in grupos if g["zona"] == "2" and g["puesto"] == "1")
    assert g2["total"] == 1 and g2["coincide"] == 1
