"""
Detección de ejemplares del E-14 visibles en la evidencia (foto/PDF del jurado).

En una misma imagen pueden aparecer 1, 2 o 3 copias (CLAVEROS, DELEGADOS,
TRANSMISIÓN) lado a lado. Registrar cuáles están permite detectar si hubo cambio
entre copias aunque los votos se lean solo de una.
"""

from __future__ import annotations

import json
import os
import time
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
    # Dos actas apiladas (foto vertical de celular con Claveros + Delegados).
    # PDF oficial de una sola copia suele ser muy estrecho (ratio < 0.45); no confundir.
    if 0.45 <= ratio <= 0.82 and h >= 700:
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


def _prompt_copias_visibles() -> str:
    return (
        "Acta electoral colombiana E-14. En la parte superior de cada bloque puede "
        "decir CLAVEROS, DELEGADOS o TRANSMISIÓN (a veces hay 1, 2 o 3 copias en "
        "la misma foto, una al lado de la otra).\n"
        "Responde SOLO JSON: "
        '{"copias_visibles":["claveros","delegados"], "notas":"breve"} '
        "Valores permitidos en copias_visibles: claveros, delegados, transmision."
    )


def _parsear_copias_json(texto: str) -> tuple[list[str], str | None]:
    data = json.loads(texto)
    copias = [
        normalizar_tipo_acta(c)
        for c in data.get("copias_visibles", [])
        if normalizar_tipo_acta(c) != TIPO_DESCONOCIDO
    ]
    return _ordenar(set(copias)), data.get("notas")


def _detectar_copias_gemini_key(imagen_gris: np.ndarray, api_key: str, modelo: str) -> tuple[list[str], str | None]:
    import base64
    import requests
    ok, buf = cv2.imencode(".png", imagen_gris)
    if not ok:
        return [], "No se pudo codificar la imagen."
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    cuerpo = {
        "contents": [{"parts": [
            {"text": _prompt_copias_visibles()},
            {"inline_data": {"mime_type": "image/png", "data": b64}},
        ]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0},
    }
    r = requests.post(url, params={"key": api_key}, json=cuerpo, timeout=45)
    r.raise_for_status()
    texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parsear_copias_json(texto)


def _detectar_copias_openrouter_key(imagen_gris: np.ndarray, api_key: str, modelo: str) -> tuple[list[str], str | None]:
    import base64
    import requests
    ok, buf = cv2.imencode(".png", imagen_gris)
    if not ok:
        return [], "No se pudo codificar la imagen."
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    cuerpo = {
        "model": modelo,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _prompt_copias_visibles()},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
    }
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "X-Title": "Auditoria E14"},
        json=cuerpo, timeout=45,
    )
    r.raise_for_status()
    texto = r.json()["choices"][0]["message"]["content"]
    return _parsear_copias_json(texto)


def detectar_copias_con_gemini(imagen_gris: np.ndarray) -> tuple[list[str], str | None]:
    """
    Usa visión (Gemini, con respaldo OpenRouter) para listar ejemplares visibles
    en la foto.

    Independiente del backend OCR principal: rota por TODAS las keys de Gemini
    disponibles y, si todas fallan (cuota agotada o lo que sea), cae a TODAS las
    de OpenRouter — así forzar OCR_BACKEND=openrouter en el lector principal no
    apaga esta detección, que antes dependía únicamente de la key singular
    GEMINI_API_KEY sin rotación ni respaldo.
    """
    cargar_env()
    modelo_gem = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    modelo_or = os.environ.get("OPENROUTER_MODEL", "google/gemini-3.5-flash")

    gem_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEYS", "").split(",") if k.strip()]
    gem_unica = os.environ.get("GEMINI_API_KEY")
    if gem_unica and gem_unica not in gem_keys:
        gem_keys.append(gem_unica)

    or_keys = [k.strip() for k in os.environ.get("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
    or_unica = os.environ.get("OPENROUTER_API_KEY")
    if or_unica and or_unica not in or_keys:
        or_keys.append(or_unica)

    if not gem_keys and not or_keys:
        return [], "Sin GEMINI_API_KEY/OPENROUTER_API_KEY para detectar copias en imagen."

    ultimo_error = None
    for key in gem_keys:
        try:
            return _detectar_copias_gemini_key(imagen_gris, key, modelo_gem)
        except Exception as e:  # noqa: BLE001
            ultimo_error = f"Detección Gemini falló: {e}"
    # OpenRouter: 2 intentos por key con espera corta — bajo --paralelo alto cada
    # hilo hace esta llamada ADEMÁS de la del OCR principal, así que la cuota se
    # satura más rápido y un corte transitorio (SSL, 429 puntual) es más probable.
    for key in or_keys:
        for intento in range(2):
            try:
                return _detectar_copias_openrouter_key(imagen_gris, key, modelo_or)
            except Exception as e:  # noqa: BLE001
                ultimo_error = f"Detección OpenRouter falló: {e}"
                if intento == 0:
                    time.sleep(3)
    return [], ultimo_error


def _copias_en_primera_pagina_pdf(ruta: Path) -> list[str]:
    """En PDFs oficiales, el título de la pág. 1 indica el ejemplar (DELEGADOS, etc.)."""
    try:
        doc = fitz.open(str(ruta))
        if doc.page_count == 0:
            doc.close()
            return []
        texto = doc[0].get_text()
        doc.close()
        return detectar_copias_en_texto(texto)
    except Exception:  # noqa: BLE001
        return []


def detectar_copias_en_evidencia(ruta: str | Path, usar_gemini: bool = True,
                                 fuente: str | None = None) -> tuple[list[str], str | None]:
    """
    Detecta qué ejemplares del E-14 aparecen en el archivo de evidencia.
    Devuelve (lista de tipos canónicos, nota opcional del detector).
    """
    ruta = Path(ruta)
    es_oficial = fuente == "registraduria"

    if ruta.suffix.lower() == ".pdf":
        if es_oficial:
            copias = _copias_en_primera_pagina_pdf(ruta)
            if copias:
                return copias, "Ejemplar según título en página 1 del PDF oficial."
        else:
            copias = detectar_copias_en_pdf_texto(ruta)
            if copias:
                return copias, "Detectado por texto en el documento."

    paginas = _paginas_de_archivo(ruta)
    if not paginas:
        return [], "No se pudo abrir el archivo."

    if es_oficial:
        return [], None

    hay_clave_vision = bool(
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEYS")
        or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEYS")
    )
    nota: str | None = None
    if usar_gemini and hay_clave_vision:
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
