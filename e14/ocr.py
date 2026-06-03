"""
Capa 2 — OCR de dígitos manuscritos (punto de conexión de las APIs).

Está TODO listo para "solo conectar la API": cuando definas la variable de entorno
con la clave (GEMINI_API_KEY o OPENAI_API_KEY), la fábrica `crear_backend()` elige
automáticamente el motor y empieza a leer. Sin clave, usa el backend manual
(no gasta nada) para poder probar el flujo completo.

Backends:
  • BackendManual  : no lee; deja todo en None y marca para revisión.
  • BackendGemini  : llama a la API de Gemini (REST). RECOMENDADO.
  • BackendGPT     : llama a la API de OpenAI/GPT (visión, REST). Verificador opcional.

Contrato:
    backend.reconocer_votos(imagen_alineada_gris, layout_id) -> LecturaOCR

El umbral de confianza para revisión manual está en UMBRAL_REVISION (0.80).
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from e14.modelo import CANDIDATOS, columnas_voto
from e14.alineacion import columnas_de_layout

# Confianza mínima por casilla; por debajo → revisión humana.
UMBRAL_REVISION = 0.80


# ─── Config: leer claves desde entorno o archivo .env ─────────────────────────
def cargar_env(ruta: str | Path = ".env") -> None:
    """Carga variables simples KEY=VALUE de un .env (si existe) al entorno."""
    p = Path(ruta)
    if not p.exists():
        return
    for linea in p.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
        os.environ.setdefault(clave, valor)


@dataclass
class LecturaOCR:
    valores: dict[str, int | None]
    confianzas: dict[str, float]
    confianza_global: float = 0.0
    necesita_revision: bool = True
    notas: str | None = None


# ─── Utilidades comunes ───────────────────────────────────────────────────────
def _imagen_a_base64_png(imagen_gris: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", imagen_gris)
    if not ok:
        raise RuntimeError("No se pudo codificar la imagen.")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _etiqueta(col: str) -> str:
    if col.startswith("c") and col[1:].isdigit():
        nombre, _ = CANDIDATOS.get(col[1:], (col, ""))
        return f"{col[1:]}. {nombre}"
    return {"blanco": "Votos en blanco", "nulos": "Votos nulos",
            "no_marcados": "Votos no marcados"}.get(col, col)


def _prompt(cols: list[str]) -> str:
    lineas = "\n".join(f'  - "{c}" = {_etiqueta(c)}' for c in cols)
    return (
        "Eres un lector de actas electorales colombianas E-14 (primera vuelta "
        "presidencial 2026). En la imagen, cada candidato/categoría tiene casillas "
        "con un dígito manuscrito por cajita (ej. '1','0','6' = 106).\n\n"
        "Lee el NÚMERO de votos de cada uno de estos campos:\n"
        f"{lineas}\n\n"
        "Reglas:\n"
        "- Si una casilla está vacía, el valor del campo es 0 sólo si claramente no "
        "hay nada escrito; si dudas si hay algo escrito, devuelve null.\n"
        "- No inventes. Si no puedes leerlo con seguridad, baja la confianza.\n"
        "- Devuelve SOLO un JSON con esta forma exacta:\n"
        '{ "campos": { "<clave>": { "valor": <entero|null>, '
        '"confianza": <numero 0..1> }, ... } }'
    )


def _parsear_respuesta(texto: str, cols: list[str]) -> LecturaOCR:
    valores = {c: None for c in cols}
    confianzas = {c: 0.0 for c in cols}
    try:
        # tolerar texto alrededor del JSON
        ini, fin = texto.find("{"), texto.rfind("}")
        data = json.loads(texto[ini:fin + 1])
        campos = data.get("campos", data)
        for c in cols:
            celda = campos.get(c) or {}
            v = celda.get("valor")
            valores[c] = int(v) if isinstance(v, (int, float)) else None
            try:
                confianzas[c] = float(celda.get("confianza", 0.0))
            except (TypeError, ValueError):
                confianzas[c] = 0.0
    except (json.JSONDecodeError, ValueError, AttributeError):
        return LecturaOCR(valores, confianzas, 0.0, True, "Respuesta OCR no parseable.")

    presentes = [confianzas[c] for c in cols if valores[c] is not None]
    glob = min(presentes) if presentes else 0.0
    revisar = (not presentes) or any(cf < UMBRAL_REVISION for cf in presentes)
    return LecturaOCR(valores, confianzas, glob, revisar)


# ─── Backend manual (sin costo) ───────────────────────────────────────────────
class BackendManual:
    nombre = "manual"

    def reconocer_votos(self, imagen_alineada, layout_id: str) -> LecturaOCR:
        cols = columnas_de_layout(layout_id)
        return LecturaOCR(
            valores={c: None for c in cols},
            confianzas={c: 0.0 for c in cols},
            confianza_global=0.0,
            necesita_revision=True,
            notas="Backend manual: sin OCR (define una API key para activar la lectura).",
        )


# ─── Backend Gemini (REST) — RECOMENDADO ──────────────────────────────────────
class BackendGemini:
    nombre = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

    def __init__(self, api_key: str, modelo: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.modelo = modelo

    def reconocer_votos(self, imagen_alineada, layout_id: str) -> LecturaOCR:
        import requests
        cols = columnas_de_layout(layout_id)
        if not cols:
            return LecturaOCR({}, {}, 0.0, False, "Layout sin casillas de voto.")
        b64 = _imagen_a_base64_png(imagen_alineada)
        cuerpo = {
            "contents": [{
                "parts": [
                    {"text": _prompt(cols)},
                    {"inline_data": {"mime_type": "image/png", "data": b64}},
                ]
            }],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0},
        }
        try:
            r = requests.post(
                self.URL.format(modelo=self.modelo),
                params={"key": self.api_key},
                json=cuerpo, timeout=60,
            )
            r.raise_for_status()
            texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:  # noqa: BLE001 — fallo de red/API → marcar revisión
            return LecturaOCR({c: None for c in cols}, {c: 0.0 for c in cols},
                              0.0, True, f"Error Gemini: {e}")
        return _parsear_respuesta(texto, cols)


# ─── Backend GPT (OpenAI, REST) — verificador opcional ────────────────────────
class BackendGPT:
    nombre = "gpt"
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, modelo: str = "gpt-4o"):
        self.api_key = api_key
        self.modelo = modelo

    def reconocer_votos(self, imagen_alineada, layout_id: str) -> LecturaOCR:
        import requests
        cols = columnas_de_layout(layout_id)
        if not cols:
            return LecturaOCR({}, {}, 0.0, False, "Layout sin casillas de voto.")
        b64 = _imagen_a_base64_png(imagen_alineada)
        cuerpo = {
            "model": self.modelo,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": _prompt(cols)},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
        }
        try:
            r = requests.post(
                self.URL, headers={"Authorization": f"Bearer {self.api_key}"},
                json=cuerpo, timeout=60,
            )
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001
            return LecturaOCR({c: None for c in cols}, {c: 0.0 for c in cols},
                              0.0, True, f"Error GPT: {e}")
        return _parsear_respuesta(texto, cols)


# ─── Fábrica: elige el backend según el entorno ───────────────────────────────
def crear_backend(preferido: str | None = None):
    """
    Devuelve el backend a usar.
      • OCR_BACKEND=gemini|gpt|manual fuerza uno.
      • Si no, usa Gemini si hay GEMINI_API_KEY, luego GPT si hay OPENAI_API_KEY.
      • Si no hay claves, BackendManual.
    """
    cargar_env()
    elegido = (preferido or os.environ.get("OCR_BACKEND") or "").lower()

    gem = os.environ.get("GEMINI_API_KEY")
    gpt = os.environ.get("OPENAI_API_KEY")

    if elegido == "manual":
        return BackendManual()
    if elegido == "gemini" or (not elegido and gem):
        if gem:
            return BackendGemini(gem, os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    if elegido == "gpt" or (not elegido and gpt):
        if gpt:
            return BackendGPT(gpt, os.environ.get("OPENAI_MODEL", "gpt-4o"))
    return BackendManual()


def backend_por_defecto():
    return crear_backend()
