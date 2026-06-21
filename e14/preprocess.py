"""Preprocesamiento de imágenes antes de alinear u OCR."""

from __future__ import annotations

import cv2
import numpy as np


def recortar_margenes_negros(imagen_gris: np.ndarray, umbral: int = 25,
                             margen_pct: float = 0.02) -> np.ndarray:
    """
    Quita bandas negras (p. ej. tras alinear un PDF muy alto a plantilla cuadrada).
    Deja solo el rectángulo con contenido útil para que el OCR no pierda resolución.
    """
    if imagen_gris is None or imagen_gris.size == 0:
        return imagen_gris
    mask = imagen_gris > umbral
    if not mask.any():
        return imagen_gris
    ys, xs = np.where(mask)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    h, w = imagen_gris.shape[:2]
    my = max(2, int((y1 - y0) * margen_pct))
    mx = max(2, int((x1 - x0) * margen_pct))
    y0 = max(0, y0 - my)
    y1 = min(h - 1, y1 + my)
    x0 = max(0, x0 - mx)
    x1 = min(w - 1, x1 + mx)
    recorte = imagen_gris[y0:y1 + 1, x0:x1 + 1]
    # Descartar recortes degenerados (casi todo el lienzo).
    if recorte.size < imagen_gris.size * 0.15:
        return imagen_gris
    return recorte


def recortar_region(imagen_gris: np.ndarray,
                    roi: tuple[float, float, float, float]) -> np.ndarray:
    """
    Recorta a la región de interés (x0, y0, x1, y1) dada en FRACCIONES [0,1] del
    ancho/alto. Pensado para usarse SOBRE la imagen ya alineada a la plantilla:
    como la alineación deja el folio en coordenadas fijas de la plantilla, un
    mismo `roi` cae siempre sobre la misma zona (ej. la tabla de votación), así
    se descarta todo lo demás (fotos, cabecera, constancias/firmas con cédulas)
    antes del OCR → menos tokens y lectura más enfocada.

    El `roi` debe calibrarse contra la plantilla que se usó para alinear (un
    formulario de otro año puede tener proporciones distintas).
    """
    if imagen_gris is None or imagen_gris.size == 0:
        return imagen_gris
    h, w = imagen_gris.shape[:2]
    x0, y0, x1, y1 = roi
    a = int(round(max(0.0, x0) * w))
    b = int(round(min(1.0, x1) * w))
    c = int(round(max(0.0, y0) * h))
    d = int(round(min(1.0, y1) * h))
    if b <= a or d <= c:
        return imagen_gris
    return imagen_gris[c:d, a:b]


def ampliar_para_ocr(imagen_gris: np.ndarray, escala: float = 1.5) -> np.ndarray:
    """Escala la imagen para que dígitos pequeños (..3, .77) se lean mejor."""
    if imagen_gris is None or imagen_gris.size == 0 or escala <= 1.0:
        return imagen_gris
    h, w = imagen_gris.shape[:2]
    nw, nh = int(w * escala), int(h * escala)
    return cv2.resize(imagen_gris, (nw, nh), interpolation=cv2.INTER_CUBIC)


def mejorar_para_ocr(imagen_gris: np.ndarray, recortar: bool = True,
                     escala: float = 1.5) -> np.ndarray:
    """Contraste local + recorte de negro + zoom para la API de visión."""
    if imagen_gris is None or imagen_gris.size == 0:
        return imagen_gris
    img = recortar_margenes_negros(imagen_gris) if recortar else imagen_gris
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img = clahe.apply(img)
    return ampliar_para_ocr(img, escala=escala) if escala > 1.0 else img
