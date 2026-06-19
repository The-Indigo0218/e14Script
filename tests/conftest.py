"""Fixtures compartidos para los tests."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

# Encabezado idéntico al del Excel real "Mesa a Mesa" de la Registraduría.
ENCABEZADO = [
    "DEP", "DEPNOMBRE", "MUN", "MUNNOMBRE", "ZONA", "PUESTO", "PUESNOMBRE",
    "MESA", "COMUCODIGO", "COMUNOMBRE", "CORCODIGO", "CORNOMBRE", "CIR",
    "PAR", "PARNOMBRE", "CAN", "CANCEDULA", "CANNOMBRE", "VOTOS",
]


def _fila(mun, munnombre, zona, puesto, mesa, can, votos):
    """Una fila del Excel para un candidato/mesa (solo importan las columnas del catálogo)."""
    return [
        5, "BOLIVAR", mun, munnombre, zona, puesto, "PUESTO X",
        mesa, 0, "NACIONAL", 1, "PRESIDENTE", 0, 26, "AGRUP",
        can, 79262397, "CANDIDATO X", votos,
    ]


@pytest.fixture
def excel_catalogo(tmp_path: Path) -> Path:
    """
    Genera un Excel mínimo con la estructura del oficial:
      - Cartagena (MUN 1): 2 mesas, cada una repetida por 2 candidatos.
      - El Peñón (MUN 27) con mojibake en el nombre: 1 mesa.
    Sirve para probar dedup, universo por municipio y reparación de nombres.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(ENCABEZADO)
    # Cartagena, zona 21 puesto 1 mesa 13 -> 2 candidatos (debe deduplicar a 1 mesa)
    ws.append(_fila(1, "CARTAGENA", 21, 1, 13, 1, 130))
    ws.append(_fila(1, "CARTAGENA", 21, 1, 13, 2, 3))
    # Cartagena, otra mesa
    ws.append(_fila(1, "CARTAGENA", 1, 1, 1, 1, 40))
    ws.append(_fila(1, "CARTAGENA", 1, 1, 1, 2, 18))
    # El Peñón con nombre mal codificado (UTF-8 leído como Latin-1)
    ws.append(_fila(27, "EL PEÃ‘ON", 5, 2, 7, 1, 9))
    ruta = tmp_path / "catalogo_test.xlsx"
    wb.save(ruta)
    return ruta
