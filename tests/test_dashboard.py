"""Tests de dashboard.py — sin red, con una base SQLite local real."""

from __future__ import annotations

from dashboard import _filas_para_revisar
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
