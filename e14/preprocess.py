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
