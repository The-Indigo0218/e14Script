"""Tests de la nomenclatura canónica NuMunicipio-zona-puesto-mesa."""

from __future__ import annotations

from e14.mesa import (
    codigo_canonico,
    normalizar_codigo,
    codigo_mesa_desde_archivo,
    municipio_zona_puesto_mesa_desde_codigo,
)


def test_codigo_canonico_quita_ceros():
    assert codigo_canonico(1, 21, 1, 13) == "1_21_1_13"
    assert codigo_canonico("01", "21", "01", "13") == "1_21_1_13"


def test_normalizar_codigo_unifica_guiones_y_ceros():
    # La misma mesa escrita de formas distintas debe colapsar al mismo código.
    formas = ["1_21_01_13", "1-21-01-13", "1_21_1_13", "01_21_01_13"]
    assert {normalizar_codigo(f) for f in formas} == {"1_21_1_13"}


def test_normalizar_codigo_no_numerico_se_mantiene():
    # Código legado con municipio textual: no calza patrón numérico -> minúscula.
    assert normalizar_codigo("Cartagena_21_01_13") == "cartagena_21_1_13"


def test_codigo_desde_archivo_quita_sufijo_fuente():
    assert codigo_mesa_desde_archivo("1_21_01_13_testigo.pdf") == "1_21_01_13"
    assert codigo_mesa_desde_archivo("1_21_01_13_registraduria.pdf") == "1_21_01_13"


def test_archivo_y_catalogo_cruzan_tras_normalizar():
    # El nombre de archivo trae ceros; el catálogo no. Tras normalizar, coinciden.
    desde_archivo = normalizar_codigo(codigo_mesa_desde_archivo("1_21_01_13_testigo.pdf"))
    desde_catalogo = codigo_canonico(1, 21, 1, 13)
    assert desde_archivo == desde_catalogo


def test_meta_desde_codigo_numerico():
    meta = municipio_zona_puesto_mesa_desde_codigo("1_21_01_13")
    assert meta == {"municipio": "1", "zona": "21", "puesto": "01", "mesa": "13"}
