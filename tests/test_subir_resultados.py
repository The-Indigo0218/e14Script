"""Tests de subir_resultados.py — sin red, con una base SQLite local real."""

from __future__ import annotations

from e14.almacen import Almacen
from e14.modelo import ActaE14, FUENTE_REGISTRADURIA, FUENTE_TESTIGO
from subir_resultados import _slug, resumen_local


def test_slug_normaliza_nombre_de_persona():
    assert _slug("Juan Pérez") == "juan_pérez"
    assert _slug("  María-José  ") == "maría_josé"


def test_resumen_local_cuenta_coincidencias_discrepancias_y_confianza_baja(tmp_path):
    alm = Almacen(tmp_path / "t.db")
    # Mesa que coincide, ambas con confianza alta.
    alm.guardar(ActaE14(codigo_mesa="1_1_1_1", fuente=FUENTE_TESTIGO, c1=10, c2=5, confianza=0.95))
    alm.guardar(ActaE14(codigo_mesa="1_1_1_1", fuente=FUENTE_REGISTRADURIA, c1=10, c2=5, confianza=0.95))
    # Mesa con discrepancia, testigo con confianza baja.
    alm.guardar(ActaE14(codigo_mesa="1_1_1_2", fuente=FUENTE_TESTIGO, c1=8, c2=5, confianza=0.5))
    alm.guardar(ActaE14(codigo_mesa="1_1_1_2", fuente=FUENTE_REGISTRADURIA, c1=9, c2=5, confianza=0.9))
    alm.cerrar()

    r = resumen_local(str(tmp_path / "t.db"))
    assert r["total"] == 2
    assert r["COINCIDE"] == 1
    assert r["DISCREPANCIA"] == 1
    assert r["confianza_baja"] == 1
