"""Tests del catálogo leído del Excel de la Registraduría."""

from __future__ import annotations

import pytest

from e14.catalogo import (
    cargar_catalogo,
    crear_estructura_lote,
    nombre_carpeta_lote,
    slug_municipio,
)


def test_departamento_es_registraduria_no_dane(excel_catalogo):
    cat = cargar_catalogo(excel_catalogo)
    # En la codificación de la Registraduría, Bolívar = 5 (NO 13 como en DANE).
    assert cat.departamento == "5"
    assert cat.departamento_nombre == "BOLIVAR"


def test_deduplica_mesas_repetidas_por_candidato(excel_catalogo):
    cat = cargar_catalogo(excel_catalogo)
    # 5 filas en el Excel (4 de Cartagena + 1 de El Peñón) -> 3 mesas únicas.
    assert cat.total_mesas() == 3
    assert len(cat.mesas_de(1)) == 2


def test_universo_de_municipio_son_codigos_canonicos(excel_catalogo):
    cat = cargar_catalogo(excel_catalogo)
    assert cat.codigos_de(1) == {"1_21_1_13", "1_1_1_1"}


def test_nombres_municipio_y_orden(excel_catalogo):
    cat = cargar_catalogo(excel_catalogo)
    assert cat.municipios() == ["1", "27"]
    assert cat.nombre_municipio(1) == "CARTAGENA"


def test_repara_mojibake_en_nombre(excel_catalogo):
    cat = cargar_catalogo(excel_catalogo)
    # 'EL PEÃ‘ON' (UTF-8 leído como Latin-1) -> 'EL PEÑON'
    assert cat.nombre_municipio(27) == "EL PEÑON"


def test_slug_municipio_sin_acentos_ni_espacios():
    assert slug_municipio("EL CARMEN DE BOLIVAR") == "el_carmen_de_bolivar"
    assert slug_municipio("EL PEÑON") == "el_penon"


def test_crear_estructura_lote(excel_catalogo, tmp_path):
    cat = cargar_catalogo(excel_catalogo)
    assert nombre_carpeta_lote(cat, 1) == "01_cartagena"
    lote = crear_estructura_lote(tmp_path / "datos", cat, 1)
    assert (lote / "testigos").is_dir()
    assert (lote / "registraduria").is_dir()
    # Idempotente: correr de nuevo no falla.
    crear_estructura_lote(tmp_path / "datos", cat, 1)


def test_excel_inexistente_da_error_claro(tmp_path):
    with pytest.raises(FileNotFoundError):
        cargar_catalogo(tmp_path / "no_existe.xlsx")
