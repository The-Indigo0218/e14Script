"""Tests de cobertura de un lote (municipio)."""

from __future__ import annotations

import pytest

from e14.catalogo import cargar_catalogo, crear_estructura_lote
from e14.cobertura import cobertura_lote


@pytest.fixture
def lote_cartagena(excel_catalogo, tmp_path):
    """
    Catálogo + carpeta de lote de Cartagena con archivos de prueba.
    Universo Cartagena (del fixture): mesas 1_21_1_13 y 1_1_1_1.
    Se colocan:
      - 1_21_01_13 en AMBAS fuentes (con ceros, para probar el cruce) -> lista.
      - 1_1_1_1 solo testigo                                          -> solo_testigo.
      - 1_99_9_9 solo registraduría, NO está en el catálogo           -> fuera_de_catalogo.
    """
    cat = cargar_catalogo(excel_catalogo)
    datos = tmp_path / "datos"
    lote = crear_estructura_lote(datos, cat, 1)
    (lote / "testigos" / "1_21_01_13_testigo.pdf").write_bytes(b"x")
    (lote / "registraduria" / "1_21_01_13_registraduria.pdf").write_bytes(b"x")
    (lote / "testigos" / "1_1_1_1_testigo.pdf").write_bytes(b"x")
    (lote / "registraduria" / "1_99_9_9_registraduria.pdf").write_bytes(b"x")
    return cat, datos


def test_cobertura_clasifica_estados(lote_cartagena):
    cat, datos = lote_cartagena
    cob = cobertura_lote(cat, 1, datos)
    assert cob.listas == {"1_21_1_13"}            # ceros normalizados, cruza
    assert cob.solo_testigo == {"1_1_1_1"}
    assert cob.solo_registraduria == set()
    assert cob.faltan_ambas == set()
    assert cob.fuera_de_catalogo == {"1_99_9_9"}  # archivo no esperado -> alerta


def test_cobertura_conteos_y_porcentaje(lote_cartagena):
    cat, datos = lote_cartagena
    cob = cobertura_lote(cat, 1, datos)
    assert cob.resumen() == {
        "esperadas": 2, "listas": 1, "solo_testigo": 1,
        "solo_registraduria": 0, "faltan_ambas": 0, "fuera_de_catalogo": 1,
    }
    assert cob.pct_listas == 50.0


def test_cobertura_sin_carpeta_todo_falta(excel_catalogo, tmp_path):
    # No se crean carpetas: todo el universo cuenta como faltante.
    cat = cargar_catalogo(excel_catalogo)
    cob = cobertura_lote(cat, 1, tmp_path / "datos")
    assert cob.resumen()["esperadas"] == 2
    assert cob.faltan_ambas == cob.esperadas
    assert cob.listas == set()
    assert cob.pct_listas == 0.0


def test_municipio_acepta_codigo_con_cero(lote_cartagena):
    # '01' debe resolver al mismo lote que 1.
    cat, datos = lote_cartagena
    assert cobertura_lote(cat, "01", datos).resumen() == cobertura_lote(cat, 1, datos).resumen()


def test_texto_incluye_alerta_fuera_de_catalogo(lote_cartagena):
    cat, datos = lote_cartagena
    texto = cobertura_lote(cat, 1, datos).texto()
    assert "CARTAGENA" in texto
    assert "Fuera de catálogo" in texto
