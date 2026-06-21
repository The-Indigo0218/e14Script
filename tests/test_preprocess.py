"""Tests del recorte de región de interés (preprocess.recortar_region)."""

import numpy as np

from e14.preprocess import recortar_region


def _lienzo(h=100, w=200):
    return np.arange(h * w, dtype=np.uint8).reshape(h, w)


def test_recorta_fracciones_a_pixeles():
    img = _lienzo(100, 200)
    # mitad inferior derecha
    out = recortar_region(img, (0.5, 0.5, 1.0, 1.0))
    assert out.shape == (50, 100)
    # esquina superior izquierda del recorte == pixel (50, 100) del original
    assert out[0, 0] == img[50, 100]


def test_roi_franja_vertical_full_width():
    img = _lienzo(1000, 469)
    out = recortar_region(img, (0.0, 0.27, 1.0, 0.665))
    assert out.shape[1] == 469               # ancho completo
    assert out.shape[0] == int(round(0.665 * 1000)) - int(round(0.27 * 1000))


def test_roi_degenerado_devuelve_original():
    img = _lienzo()
    # x1 <= x0 → no recorta, devuelve la imagen tal cual
    assert recortar_region(img, (0.8, 0.0, 0.2, 1.0)) is img


def test_imagen_vacia_no_explota():
    vacia = np.zeros((0, 0), dtype=np.uint8)
    assert recortar_region(vacia, (0.1, 0.1, 0.9, 0.9)) is vacia


def test_recorte_reduce_pixeles():
    img = _lienzo(1363, 469)
    out = recortar_region(img, (0.0, 0.27, 1.0, 0.665))
    assert out.size < img.size
    assert out.size / img.size < 0.45        # ~39% del folio
