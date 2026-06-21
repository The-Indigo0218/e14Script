"""Tests de la segmentación de imágenes con varias copias del E-14."""

from __future__ import annotations

import numpy as np

from e14.alineacion import ResultadoAlineacion, LAYOUT_ACTA_COMPLETA
from e14.segmentacion import (
    _cortes, subregiones, _esquemas_por_forma,
    alinear_actas_en_pagina, alinear_actas_en_paginas,
)


def test_cortes_reparte_y_absorbe_resto():
    assert _cortes(100, 2) == [(0, 50), (50, 100)]
    assert _cortes(100, 3) == [(0, 33), (33, 66), (66, 100)]   # último absorbe el resto


def test_subregiones_grilla():
    img = np.zeros((600, 600), dtype=np.uint8)
    cols = subregiones(img, 1, 3)
    assert len(cols) == 3
    assert all(c.shape[0] == 600 for c in cols)        # alto completo
    assert [c.shape[1] for c in cols] == [200, 200, 200]
    filas = subregiones(img, 2, 1)
    assert len(filas) == 2 and all(f.shape[1] == 600 for f in filas)


def test_esquemas_cuadrada_prueba_3col_primero():
    # 3 actas lado a lado → imagen ~cuadrada → debe intentar 3 columnas primero.
    img = np.zeros((600, 600), dtype=np.uint8)
    assert _esquemas_por_forma(img)[0] == (1, 3)


def test_esquemas_muy_alta_prueba_3fila_primero():
    img = np.zeros((1800, 200), dtype=np.uint8)   # ratio ~0.11 → 3 apiladas
    assert _esquemas_por_forma(img)[0] == (3, 1)


class _AlineadorPorAncho:
    """
    Fake: una región es 'acta' (confiable) si su ratio ancho/alto está cerca de
    la forma de un acta sola (~0.33). Simula que SIFT solo casa una copia entera.
    """
    def alinear_pagina(self, pagina, indice=1, solo_layouts=None):
        h, w = pagina.shape[:2]
        ratio = w / h if h else 99
        es_acta = 0.25 <= ratio <= 0.45
        return ResultadoAlineacion(
            indice_pagina=indice,
            layout_id=LAYOUT_ACTA_COMPLETA if es_acta else None,
            inliers=120 if es_acta else 5,
            confiable=es_acta,
            imagen_alineada=pagina if es_acta else None,
        )


def test_una_sola_acta_devuelve_el_folio_completo():
    # Folio único alto y angosto (ratio 0.33) → casa entero, sin cortar.
    acta = np.zeros((600, 200), dtype=np.uint8)
    res = alinear_actas_en_pagina(_AlineadorPorAncho(), acta)
    assert len(res) == 1 and res[0].confiable


def test_tres_copias_lado_a_lado_se_segmentan():
    # 3 actas (200x600 c/u) lado a lado → 600x600 → debe hallar 3 actas.
    img = np.zeros((600, 600), dtype=np.uint8)
    res = alinear_actas_en_pagina(_AlineadorPorAncho(), img)
    assert len(res) == 3
    assert all(r.confiable for r in res)


def test_dos_copias_lado_a_lado_se_segmentan():
    # 2 actas (200x600) lado a lado → 400x600 (ratio 0.66) → 2 actas.
    img = np.zeros((600, 400), dtype=np.uint8)
    res = alinear_actas_en_pagina(_AlineadorPorAncho(), img)
    assert len(res) == 2 and all(r.confiable for r in res)


def test_nada_alinea_devuelve_intento_no_confiable():
    # Imagen que no casa con ningún corte → 1 resultado no confiable (para revisión).
    img = np.zeros((600, 600), dtype=np.uint8)

    class _Nunca:
        def alinear_pagina(self, pagina, indice=1, solo_layouts=None):
            return ResultadoAlineacion(indice, None, 3, False, None)

    res = alinear_actas_en_pagina(_Nunca(), img)
    assert len(res) == 1 and not res[0].confiable


def test_alinear_actas_en_paginas_aplana():
    # 2 páginas, cada una con 2 copias lado a lado → 4 actas en total.
    pag = np.zeros((600, 400), dtype=np.uint8)
    res = alinear_actas_en_paginas(_AlineadorPorAncho(), [pag, pag])
    assert len(res) == 4
