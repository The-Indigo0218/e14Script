"""Tests de descargar_drive.py — sin red (ArchivoDrive de prueba, sin tocar Google)."""

from __future__ import annotations

from pathlib import Path

from e14.catalogo import cargar_catalogo
from e14.drive import ArchivoDrive
from e14.mesa import fuente_desde_archivo
from e14.modelo import FUENTE_REGISTRADURIA, FUENTE_TESTIGO
from descargar_drive import planear_destinos


def test_fuente_desde_archivo_clasifica_por_sufijo():
    assert fuente_desde_archivo("1_21_01_13_testigo.pdf") == FUENTE_TESTIGO
    assert fuente_desde_archivo("1_21_01_13_jurados.png") == FUENTE_TESTIGO
    assert fuente_desde_archivo("1_21_01_13_registraduria.pdf") == FUENTE_REGISTRADURIA
    assert fuente_desde_archivo("1_21_01_13_delegados.pdf") == FUENTE_REGISTRADURIA
    assert fuente_desde_archivo("acta_sin_convencion.pdf") is None


def test_planear_destinos_ubica_segun_catalogo(excel_catalogo, tmp_path):
    cat = cargar_catalogo(excel_catalogo)
    archivos = [
        ArchivoDrive(id="a1", nombre="1_21_01_13_testigo.pdf", tamano=100),
        ArchivoDrive(id="a2", nombre="1_21_01_13_registraduria.pdf", tamano=120),
    ]
    base = tmp_path / "datos"
    ubicados, sin_clasificar = planear_destinos(cat, archivos, base)

    assert sin_clasificar == []
    destinos = {a.nombre: d for a, d in ubicados}
    assert destinos["1_21_01_13_testigo.pdf"] == base / "01_cartagena" / "testigos" / "1_21_01_13_testigo.pdf"
    assert destinos["1_21_01_13_registraduria.pdf"] == (
        base / "01_cartagena" / "registraduria" / "1_21_01_13_registraduria.pdf"
    )


def test_planear_destinos_ignora_archivos_no_clasificables(excel_catalogo, tmp_path):
    cat = cargar_catalogo(excel_catalogo)
    archivos = [
        ArchivoDrive(id="b1", nombre="foto_random.jpg", tamano=10),          # sin sufijo de fuente
        ArchivoDrive(id="b2", nombre="9999_1_1_1_testigo.pdf", tamano=10),  # municipio fuera del catálogo
    ]
    ubicados, sin_clasificar = planear_destinos(cat, archivos, tmp_path / "datos")

    assert ubicados == []
    assert {a.nombre for a in sin_clasificar} == {"foto_random.jpg", "9999_1_1_1_testigo.pdf"}


def test_planear_destinos_no_le_importa_de_que_subcarpeta_de_drive_vino(excel_catalogo, tmp_path):
    """Drive no aporta jerarquía: la ubicación final depende solo del nombre del archivo."""
    cat = cargar_catalogo(excel_catalogo)
    archivos = [ArchivoDrive(id="c1", nombre="1_1_1_1_testigo.pdf", tamano=50)]
    base = tmp_path / "datos"
    ubicados, _ = planear_destinos(cat, archivos, base)
    assert ubicados[0][1] == base / "01_cartagena" / "testigos" / "1_1_1_1_testigo.pdf"
