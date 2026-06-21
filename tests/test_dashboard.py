"""Tests de dashboard.py — sin red, con una base SQLite local real."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

import dashboard
from dashboard import _comparacion_por_puesto, _filas_para_revisar
from e14.almacen import Almacen
from e14.modelo import ActaE14, FUENTE_TESTIGO


@pytest.fixture
def cliente():
    dashboard._CFG.update({
        "db": "actas.db", "catalogo": None, "hoja": None,
        "credenciales": "drive_credentials.json", "token": ".drive_token.json",
    })
    return dashboard.app.test_client()


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


def test_imagen_404_si_el_archivo_no_existe(cliente):
    resp = cliente.get("/imagen?archivo=no_existe_este_archivo_inventado.png")
    assert resp.status_code == 404


def test_imagen_404_si_el_archivo_no_es_una_imagen_valida(cliente, tmp_path):
    basura = tmp_path / "basura.png"
    basura.write_bytes(b"esto no es una imagen real, contenido inventado")
    resp = cliente.get(f"/imagen?archivo={basura}")
    assert resp.status_code == 404


def test_imagen_devuelve_png_con_una_imagen_sintetica(cliente, tmp_path):
    """Sin un E-14 real a mano: una imagen inventada alcanza para probar que la
    re-alineación a pedido (Capa 1, sin costo de API) no rompe el endpoint."""
    ruta = tmp_path / "inventada.png"
    cv2.imwrite(str(ruta), np.random.randint(0, 255, (1000, 800), dtype=np.uint8))
    resp = cliente.get(f"/imagen?archivo={ruta}")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert len(resp.data) > 0
