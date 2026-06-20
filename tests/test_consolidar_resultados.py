"""Tests de consolidar_resultados.py — sin red, con bases SQLite locales reales."""

from __future__ import annotations

from e14.almacen import Almacen
from e14.modelo import ActaE14, FUENTE_REGISTRADURIA, FUENTE_TESTIGO
from consolidar_resultados import _es_aprobado, fila_a_acta, mergear_db_descargada


def test_es_aprobado_acepta_variantes_comunes():
    for valor in ("si", "Sí", "SI", "x", "X", "true", "1", " aprobado "):
        assert _es_aprobado(valor) is True
    for valor in ("", "no", "pendiente", "rechazado"):
        assert _es_aprobado(valor) is False


def test_fila_a_acta_reconstruye_booleanos_desde_enteros_de_sqlite():
    fila = {
        "codigo_mesa": "1_1_1_1", "fuente": FUENTE_TESTIGO, "c1": 10, "c2": 5,
        "blanco": 1, "nulos": 0, "no_marcados": 0, "necesita_revision": 1,
        "verificado_manualmente": 0, "confianza": 0.9,
    }
    acta = fila_a_acta(fila)
    assert acta.codigo_mesa == "1_1_1_1"
    assert acta.c1 == 10 and acta.c2 == 5
    assert acta.necesita_revision is True
    assert acta.verificado_manualmente is False


def test_mergear_db_descargada_integra_filas_en_la_maestra(tmp_path):
    # Base "descargada" (simula la de una persona del equipo).
    origen = Almacen(tmp_path / "persona.db")
    origen.guardar(ActaE14(codigo_mesa="1_1_1_1", fuente=FUENTE_TESTIGO, c1=10, c2=5))
    origen.guardar(ActaE14(codigo_mesa="1_1_1_1", fuente=FUENTE_REGISTRADURIA, c1=10, c2=5))
    origen.cerrar()

    maestra = Almacen(tmp_path / "maestra.db")
    n = mergear_db_descargada(maestra, tmp_path / "persona.db")
    assert n == 2
    assert set(maestra.leer_por_fuente(FUENTE_TESTIGO)) == {"1_1_1_1"}
    assert maestra.leer_por_fuente(FUENTE_TESTIGO)["1_1_1_1"]["c1"] == 10
    maestra.cerrar()


def test_mergear_db_descargada_archiva_version_anterior_si_la_mesa_ya_existia(tmp_path):
    maestra = Almacen(tmp_path / "maestra.db")
    maestra.guardar(ActaE14(codigo_mesa="1_1_1_1", fuente=FUENTE_TESTIGO, c1=999, c2=999))

    origen = Almacen(tmp_path / "persona.db")
    origen.guardar(ActaE14(codigo_mesa="1_1_1_1", fuente=FUENTE_TESTIGO, c1=10, c2=5))
    origen.cerrar()

    mergear_db_descargada(maestra, tmp_path / "persona.db")
    # La maestra queda con el valor nuevo, pero la versión vieja no se perdió.
    assert maestra.leer_por_fuente(FUENTE_TESTIGO)["1_1_1_1"]["c1"] == 10
    assert maestra.num_versiones("1_1_1_1", FUENTE_TESTIGO) == 1
    historial = maestra.historial("1_1_1_1", FUENTE_TESTIGO)
    assert historial[0]["c1"] == "999" or historial[0]["c1"] == 999
    maestra.cerrar()
