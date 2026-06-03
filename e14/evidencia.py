"""
Detección de ejemplares del E-14 visibles en la evidencia (foto/PDF del jurado).

En una misma imagen pueden aparecer 1, 2 o 3 copias (CLAVEROS, DELEGADOS,
TRANSMISIÓN) lado a lado. Registrar cuáles están permite detectar si hubo cambio
entre copias aunque los votos se lean solo de una.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import cv2
import fitz
import numpy as np

from e14.alineacion import render_pdf_gris
from e14.modelo import (
    TIPO_CLAVEROS,
    TIPO_DELEGADOS,
    TIPO_TRANSMISION,
    TIPO_DESCONOCIDO,
    normalizar_tipo_acta,
    serializar_copias,
)
from e14.ocr import cargar_env

# Palabras que identifican cada ejemplar en texto embebido u OCR
_MARCAS_TEXTO: dict[str, list[str]] = {
    TIPO_CLAVEROS: ["claveros", "clavero"],
    TIPO_DELEGADOS: ["delegados", "delegado"],
    TIPO_TRANSMISION: ["transmisión", "transmision", "transmis", "preconteo", "pre-conteo"],
}

_ORDEN = [TIPO_CLAVEROS, TIPO_DELEGADOS, TIPO_TRANSMISION]


def _ordenar(copias: set[str]) -> list[str]:
    return [c for c in _ORDEN if c in copias]


def detectar_copias_en_texto(texto: str) -> list[str]:
    """Busca marcas CLAVEROS / DELEGADOS / TRANSMISIÓN en un bloque de texto."""
    t = (texto or "").lower()
    encontradas: set[str] = set()
    for tipo, palabras in _MARCAS_TEXTO.items():
        if any(p in t for p in palabras):
            encontradas.add(tipo)
    return _ordenar(encontradas)


def _heuristica_layout_foto(paginas_gris: list[np.ndarray]) -> list[str]:
    """
    Fotos de jurados suelen mostrar 2 o 3 ejemplares en la misma imagen:
      • lado a lado (imagen ancha), o
      • uno sobre otro (imagen alta, como muchas fotos de celular).
    No lee las etiquetas; solo infiere que hay varias copias en evidencia.
    """
    if not paginas_gris:
        return []
    pag = paginas_gris[0]
    h, w = pag.shape[:2]
    if min(h, w) < 400:
        return []
    ratio = w / h  # >1 horizontal, <1 vertical
    if ratio >= 2.2:
        return list(_ORDEN)
    if ratio >= 1.35:
        return [TIPO_CLAVEROS, TIPO_DELEGADOS]
    # Dos actas apiladas (foto vertical de celular con Claveros + Delegados)
    if ratio <= 0.82 and h >= 700:
        return [TIPO_CLAVEROS, TIPO_DELEGADOS]
    return []


def _paginas_de_archivo(ruta: str | Path, dpi: int = 120) -> list[np.ndarray]:
    p = Path(ruta)
    if p.suffix.lower() == ".pdf":
        return render_pdf_gris(p, dpi=dpi)
    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    return [img] if img is not None else []


def detectar_copias_en_pdf_texto(ruta: str | Path) -> list[str]:
    """Extrae texto embebido del PDF (si existe capa de texto)."""
    encontradas: set[str] = set()
    try:
        doc = fitz.open(str(ruta))
        for page in doc:
            encontradas.update(detectar_copias_en_texto(page.get_text()))
        doc.close()
    except Exception:  # noqa: BLE001
        pass
    return _ordenar(encontradas)


def detectar_copias_con_gemini(imagen_gris: np.ndarray) -> tuple[list[str], str | None]:
    """Usa visión (Gemini) para listar ejemplares visibles en la foto."""
    import base64
    import requests

    cargar_env()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return [], "Sin GEMINI_API_KEY para detectar copias en imagen."

    modelo = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    ok, buf = cv2.imencode(".png", imagen_gris)
    if not ok:
        return [], "No se pudo codificar la imagen."
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    prompt = (
        "Acta electoral colombiana E-14. En la parte superior de cada bloque puede "
        "decir CLAVEROS, DELEGADOS o TRANSMISIÓN (a veces hay 1, 2 o 3 copias en "
        "la misma foto, una al lado de la otra).\n"
        "Responde SOLO JSON: "
        '{"copias_visibles":["claveros","delegados"], "notas":"breve"} '
        "Valores permitidos en copias_visibles: claveros, delegados, transmision."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    cuerpo = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": b64}},
        ]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0},
    }
    try:
        r = requests.post(url, params={"key": api_key}, json=cuerpo, timeout=45)
        r.raise_for_status()
        texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(texto)
        copias = [
            normalizar_tipo_acta(c)
            for c in data.get("copias_visibles", [])
            if normalizar_tipo_acta(c) != TIPO_DESCONOCIDO
        ]
        notas = data.get("notas")
        return _ordenar(set(copias)), notas
    except Exception as e:  # noqa: BLE001
        return [], f"Detección Gemini falló: {e}"


def detectar_copias_en_evidencia(ruta: str | Path, usar_gemini: bool = True) -> tuple[list[str], str | None]:
    """
    Detecta qué ejemplares del E-14 aparecen en el archivo de evidencia.
    Devuelve (lista de tipos canónicos, nota opcional del detector).
    """
    ruta = Path(ruta)
    copias = detectar_copias_en_pdf_texto(ruta) if ruta.suffix.lower() == ".pdf" else []
    nota: str | None = None

    if copias:
        return copias, "Detectado por texto en el documento."

    paginas = _paginas_de_archivo(ruta)
    if not paginas:
        return [], "No se pudo abrir el archivo."

    if usar_gemini and os.environ.get("GEMINI_API_KEY"):
        copias, nota = detectar_copias_con_gemini(paginas[0])
        if copias:
            return copias, nota

    copias_h = _heuristica_layout_foto(paginas)
    if copias_h:
        return copias_h, (
            "La foto parece incluir varios ejemplares del E-14 en la misma imagen "
            "(confirme con --tipo de cuál tomó los votos; con API Gemini se leen las etiquetas)."
        )
    return [], "No se identificaron etiquetas de ejemplar en la evidencia."


def validar_lectura_vs_evidencia(
    copia_leida: str | None,
    copias_visibles: list[str],
) -> tuple[bool, str | None]:
    """
    Comprueba coherencia entre la copia de la que se leyeron votos y lo visible.
    """
    leida = normalizar_tipo_acta(copia_leida)
    visibles = [normalizar_tipo_acta(c) for c in copias_visibles]
    visibles = [c for c in visibles if c != TIPO_DESCONOCIDO]

    if leida == TIPO_DESCONOCIDO:
        if len(visibles) == 1:
            return True, f"Se asumió lectura desde {visibles[0]} (única copia visible)."
        if len(visibles) >= 2:
            return False, (
                f"Evidencia con {len(visibles)} copias ({serializar_copias(visibles)}); "
                "indique --tipo cuál se leyó."
            )
        return False, "No se indicó de qué copia se tomaron los votos (--tipo)."

    if visibles and leida not in visibles:
        return False, (
            f"Votos leídos desde '{leida}' pero en la evidencia solo aparece: "
            f"{serializar_copias(visibles)}."
        )
    if len(visibles) >= 2:
        return True, (
            f"Evidencia con {len(visibles)} copias visibles; votos tomados de '{leida}'. "
            "Revise si los números coinciden entre copias en la foto."
        )
    return True, None
