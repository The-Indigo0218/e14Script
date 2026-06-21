"""
Segmentación de imágenes con VARIAS copias del E-14.

Un testigo puede subir en UNA sola imagen los 2-3 ejemplares (claveros,
delegados, transmisión) juntos: lado a lado o apilados (lo más probable en la
práctica). Alinear la imagen COMPLETA contra la plantilla falla cuando hay
varias actas en el cuadro (la homografía no puede casar todas a la vez). Acá:

  1. Se intenta alinear el folio COMPLETO (caso de una sola acta / PDF de 1 copia).
  2. Si no casa, se CORTA la imagen en columnas (lado a lado) o filas (apiladas)
     y se alinea cada pedazo; nos quedamos con el esquema de corte que produce
     MÁS actas alineadas confiablemente (y, a igualdad, más inliers).

Cada acta detectada se devuelve como un `ResultadoAlineacion` independiente, así
el lector saca votos de cada copia. Todas las copias traen los MISMOS votos → con
leer una basta; si 2+ se leen y discrepan, es una señal de revisión.

La propia alineación es el validador: una región con exactamente un acta alinea
bien (inliers altos); una con varias o media acta alinea mal. Por eso no hace
falta detectar bordes: probamos cortes y dejamos que los inliers decidan.
"""

from __future__ import annotations

import numpy as np

from e14.alineacion import ResultadoAlineacion, LAYOUT_ACTA_COMPLETA


def _cortes(total: int, n: int) -> list[tuple[int, int]]:
    """n tramos ~iguales de [0,total); el último absorbe el resto."""
    paso = max(1, total // n)
    return [(i * paso, (i + 1) * paso if i < n - 1 else total) for i in range(n)]


def subregiones(pagina: np.ndarray, filas: int, columnas: int) -> list[np.ndarray]:
    """Corta la página en una grilla filas×columnas y devuelve los recortes."""
    h, w = pagina.shape[:2]
    out: list[np.ndarray] = []
    for y0, y1 in _cortes(h, filas):
        for x0, x1 in _cortes(w, columnas):
            out.append(pagina[y0:y1, x0:x1])
    return out


def _esquemas_por_forma(pagina: np.ndarray) -> list[tuple[int, int]]:
    """
    Esquemas de corte (filas, columnas) a probar, ORDENADOS por la proporción de
    la imagen (lo más probable primero). Un acta sola es alta y angosta (ratio
    ~0.33); 2 lado a lado dan ~0.66; 3 lado a lado dan ~1.0 (casi cuadrada);
    apiladas dan ratios cada vez más bajos. Se prueban todos los esquemas porque
    fotos reales (márgenes, ángulo) desplazan el ratio; el orden solo decide cuál
    se intenta primero (se corta al hallar 2+ actas).
    """
    h, w = pagina.shape[:2]
    ratio = w / h if h else 1.0
    if ratio >= 0.95:            # ~cuadrada o más ancha → 3 o 2 copias lado a lado
        return [(1, 3), (1, 2), (2, 1), (3, 1)]
    if ratio >= 0.5:             # 2 copias lado a lado
        return [(1, 2), (1, 3), (2, 1), (3, 1)]
    if ratio >= 0.28:            # 1 acta, o 2 (poco probable cortar) → tanteo suave
        return [(1, 2), (2, 1), (1, 3), (3, 1)]
    if ratio >= 0.14:            # alta → 2 copias apiladas
        return [(2, 1), (3, 1), (1, 2), (1, 3)]
    return [(3, 1), (2, 1), (1, 2), (1, 3)]   # muy alta → 3 copias apiladas


def alinear_actas_en_pagina(alineador, pagina: np.ndarray, indice: int = 1,
                            solo_layouts: list[str] | None = None) -> list[ResultadoAlineacion]:
    """
    Devuelve las regiones de `pagina` que alinean confiablemente como acta.
    Prueba el folio completo y, si no casa, los esquemas de corte; se queda con
    el que más actas confiables produce. Si nada casa, devuelve el intento
    completo (no confiable) para que el lector lo registre como revisión.
    """
    solo = solo_layouts or [LAYOUT_ACTA_COMPLETA]
    entero = alineador.alinear_pagina(pagina, indice, solo)
    if entero.confiable:
        return [entero]

    # No casó como folio único → puede haber varias copias en el cuadro. Probar
    # esquemas de corte (ordenados por forma) y quedarse con el mejor. Cortar en
    # cuanto un esquema dé 2+ actas confiables (ya hallamos las copias).
    mejor: list[ResultadoAlineacion] = []
    mejor_score = (0, 0)
    for filas, columnas in _esquemas_por_forma(pagina):
        confiables = [
            r for r in (alineador.alinear_pagina(sub, indice, solo)
                        for sub in subregiones(pagina, filas, columnas))
            if r.confiable
        ]
        score = (len(confiables), sum(r.inliers for r in confiables))
        if score > mejor_score:
            mejor_score = score
            mejor = confiables
        if len(confiables) >= 2:
            break
    return mejor if mejor else [entero]


def alinear_actas_en_paginas(alineador, paginas: list[np.ndarray],
                             solo_layouts: list[str] | None = None) -> list[ResultadoAlineacion]:
    """Aplana todas las páginas en la lista de actas detectadas (1+ por página)."""
    out: list[ResultadoAlineacion] = []
    for i, pag in enumerate(paginas):
        out.extend(alinear_actas_en_pagina(alineador, pag, i + 1, solo_layouts))
    return out
