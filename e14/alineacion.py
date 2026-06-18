"""
Capa 1 — Alineación por plantilla (registro de imagen).

Estrategia validada: en vez de adivinar la orientación con heurísticas frágiles,
alineamos cada página escaneada contra la PLANTILLA OFICIAL en blanco del E-14
(el PDF "muestra") usando features (SIFT) + homografía.

Ventajas:
  • Corrige orientación (incluido 180°), inclinación, escala y perspectiva de una vez.
  • Es 100% offline y gratis (solo OpenCV).
  • Deja el acta alineada píxel a píxel con la plantilla, así que las casillas de
    votos quedan SIEMPRE en las mismas coordenadas → recorte exacto para el OCR.
  • El número de inliers sirve como control de calidad (poca coincidencia = revisar).

La plantilla de SEGUNDA VUELTA, con solo 2 candidatos, entra completa en una
sola página lógica (a diferencia de primera vuelta, que necesitaba 2 páginas
para 13 candidatos). Layouts:
  • LAYOUT_ACTA_COMPLETA (muestra pág 1): candidatos 1-2 + blanco/nulos/no
    marcados + nivelación de la mesa + suma, todo en la misma hoja.
  • LAYOUT_FIRMAS        (muestra pág 2): constancias y firmas/cédulas de jurados

NOTA: si la plantilla oficial real de segunda vuelta resulta tener más de una
página de votos, ajustar `_LAYOUT_POR_PAGINA_MUESTRA` y `_COLUMNAS_POR_LAYOUT`
abajo para que coincidan con el PDF real.

Cada página del PDF escaneado se compara contra los layouts y se queda con el
de mayor coincidencia (así no importa el orden ni la orientación de las páginas).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np

from e14.modelo import columnas_voto

# Identificadores de layout
LAYOUT_ACTA_COMPLETA = "acta_completa"
LAYOUT_FIRMAS = "firmas"

# Orden de las páginas en el PDF de muestra (plantilla oficial)
_LAYOUT_POR_PAGINA_MUESTRA = {
    0: LAYOUT_ACTA_COMPLETA,
    1: LAYOUT_FIRMAS,
}

# Umbral mínimo de inliers para considerar la alineación confiable.
INLIERS_MIN_CONFIABLE = 25

# Qué columnas de voto aporta cada layout (qué casillas hay en cada página).
_COLUMNAS_POR_LAYOUT = {
    LAYOUT_ACTA_COMPLETA: columnas_voto(),
    LAYOUT_FIRMAS:        [],
}


def columnas_de_layout(layout_id: str) -> list[str]:
    """Columnas de voto que se pueden leer en un layout dado."""
    return list(_COLUMNAS_POR_LAYOUT.get(layout_id, []))


# ─── Render de PDF a escala de grises ─────────────────────────────────────────
def render_pdf_gris(pdf_path: str | Path, dpi: int = 150) -> list[np.ndarray]:
    doc = fitz.open(str(pdf_path))
    out: list[np.ndarray] = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            gris = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
        elif pix.n == 3:
            gris = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            gris = img[:, :, 0]
        out.append(gris)
    doc.close()
    return out


# ─── Plantilla con features precalculados ─────────────────────────────────────
@dataclass
class _LayoutPlantilla:
    layout_id: str
    imagen: np.ndarray            # plantilla en gris
    keypoints: tuple
    descriptores: np.ndarray
    alto: int
    ancho: int


@dataclass
class ResultadoAlineacion:
    indice_pagina: int            # página del PDF escaneado (1-based)
    layout_id: str | None         # layout reconocido o None si no se pudo
    inliers: int                  # calidad de la alineación
    confiable: bool               # inliers >= umbral
    imagen_alineada: np.ndarray | None  # acta alineada a la plantilla (gris)


class Alineador:
    """Carga la plantilla oficial una sola vez y alinea escaneos contra ella."""

    def __init__(self, plantilla_pdf: str | Path, dpi: int = 150, nfeatures: int = 8000):
        self.dpi = dpi
        self._sift = cv2.SIFT_create(nfeatures=nfeatures)
        self._bf = cv2.BFMatcher(cv2.NORM_L2)
        self._layouts: list[_LayoutPlantilla] = []

        paginas = render_pdf_gris(plantilla_pdf, dpi=dpi)
        for idx, gris in enumerate(paginas):
            layout_id = _LAYOUT_POR_PAGINA_MUESTRA.get(idx, f"pagina_{idx}")
            kp, des = self._sift.detectAndCompute(gris, None)
            h, w = gris.shape[:2]
            self._layouts.append(
                _LayoutPlantilla(layout_id, gris, kp, des, h, w)
            )

    def _alinear_contra(self, kp_scan, des_scan, scan_gris, layout: _LayoutPlantilla):
        if des_scan is None or layout.descriptores is None:
            return 0, None
        matches = self._bf.knnMatch(des_scan, layout.descriptores, k=2)
        buenos = [m for m, n in matches if m.distance < 0.75 * n.distance]
        if len(buenos) < 12:
            return len(buenos), None
        src = np.float32([kp_scan[m.queryIdx].pt for m in buenos]).reshape(-1, 1, 2)
        dst = np.float32([layout.keypoints[m.trainIdx].pt for m in buenos]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None or mask is None:
            return 0, None
        inliers = int(mask.sum())
        alineada = cv2.warpPerspective(scan_gris, H, (layout.ancho, layout.alto))
        return inliers, alineada

    def alinear_pagina(self, scan_gris: np.ndarray, indice_pagina: int,
                       solo_layouts: list[str] | None = None) -> ResultadoAlineacion:
        kp_scan, des_scan = self._sift.detectAndCompute(scan_gris, None)
        mejor = ResultadoAlineacion(indice_pagina, None, 0, False, None)
        candidatos = self._layouts
        if solo_layouts:
            candidatos = [l for l in self._layouts if l.layout_id in solo_layouts]
        for layout in candidatos:
            inliers, alineada = self._alinear_contra(kp_scan, des_scan, scan_gris, layout)
            if inliers > mejor.inliers:
                mejor = ResultadoAlineacion(
                    indice_pagina=indice_pagina,
                    layout_id=layout.layout_id,
                    inliers=inliers,
                    confiable=inliers >= INLIERS_MIN_CONFIABLE,
                    imagen_alineada=alineada,
                )
        return mejor

    def alinear_pdf(self, scan_pdf: str | Path,
                    solo_layouts: list[str] | None = None) -> list[ResultadoAlineacion]:
        paginas = render_pdf_gris(scan_pdf, dpi=self.dpi)
        return [self.alinear_pagina(g, i + 1, solo_layouts) for i, g in enumerate(paginas)]

    def alinear_paginas(self, paginas_gris: list[np.ndarray],
                        solo_layouts: list[str] | None = None) -> list[ResultadoAlineacion]:
        """Alinea páginas ya cargadas (PDF o imagen JPG/PNG)."""
        return [self.alinear_pagina(g, i + 1, solo_layouts) for i, g in enumerate(paginas_gris)]
