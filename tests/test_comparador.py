"""Tests de e14/comparador.py — KIT/CIV (identificadores, no votos)."""

from __future__ import annotations

from e14.comparador import comparar_mesa


def test_comparar_mesa_propaga_kit_y_civ_de_cada_fuente():
    fila_t = {"numero_kit": "K-100", "civ": "CIV-1"}
    fila_r = {"numero_kit": "K-100", "civ": "CIV-2"}
    comp = comparar_mesa("1_1_1_1", fila_t, fila_r)
    assert comp.kit_testigo == "K-100"
    assert comp.kit_registraduria == "K-100"
    assert comp.civ_testigo == "CIV-1"
    assert comp.civ_registraduria == "CIV-2"


def test_kit_coincide_none_si_falta_alguna_fuente():
    comp = comparar_mesa("1_1_1_1", {"numero_kit": "K-100"}, None)
    assert comp.kit_coincide is None


def test_kit_coincide_true_ignorando_mayusculas_y_espacios():
    comp = comparar_mesa("1_1_1_1", {"numero_kit": " k-100 "}, {"numero_kit": "K-100"})
    assert comp.kit_coincide is True


def test_civ_coincide_false_si_difieren():
    comp = comparar_mesa("1_1_1_1", {"civ": "CIV-1"}, {"civ": "CIV-2"})
    assert comp.civ_coincide is False


def test_comparar_mesa_propaga_confianza_de_kit_y_civ():
    fila_t = {"numero_kit": "K-100", "confianza_kit": 0.9, "civ": "CIV-1", "confianza_civ": 0.4}
    comp = comparar_mesa("1_1_1_1", fila_t, None)
    assert comp.confianza_kit_testigo == 0.9
    assert comp.confianza_civ_testigo == 0.4
    assert comp.confianza_kit_registraduria is None
