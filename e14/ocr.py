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
import time
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
    detalle_api: str | None = None   # informe legible de lo que respondió la API
    numero_kit: str | None = None    # número de KIT impreso en el formulario (no es voto)
    civ: str | None = None           # código CIV impreso en el formulario (no es voto)
    confianza_kit: float = 0.0
    confianza_civ: float = 0.0


# ─── Utilidades comunes ───────────────────────────────────────────────────────
def _mensaje_error_api(exc: Exception) -> str:
    """Evita filtrar la API key en mensajes de error."""
    msg = str(exc).split("?key=")[0].split("key=")[0].strip()
    if "429" in msg:
        return "Error Gemini: 429 Too Many Requests (cuota/rate limit; espera un momento y reintenta)."
    return f"Error Gemini: {msg}"


def _post_gemini_con_reintento(url: str, api_key: str, cuerpo: dict, intentos: int = 4):
    import requests
    esperas = (3, 8, 20, 45)
    ultimo = None
    for n in range(intentos):
        r = requests.post(url, params={"key": api_key}, json=cuerpo, timeout=90)
        ultimo = r
        if r.status_code == 429 and n < intentos - 1:
            time.sleep(esperas[min(n, len(esperas) - 1)])
            continue
        r.raise_for_status()
        return r
    if ultimo is not None:
        ultimo.raise_for_status()
    raise RuntimeError("Sin respuesta de Gemini")


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
            "no_marcados": "Votos no marcados",
            "suma_total": "TOTAL VOTOS DE LA MESA"}.get(col, col)


def _prompt(cols: list[str]) -> str:
    lineas = "\n".join(f'  - "{c}" = {_etiqueta(c)}' for c in cols)
    return (
        "Eres un lector de actas electorales colombianas E-14 (segunda vuelta "
        "presidencial 2026, solo 2 candidatos). En la imagen, cada candidato/categoría "
        "tiene casillas "
        "con un dígito manuscrito por cajita (ej. '1','0','6' = 106).\n\n"
        "Lee el NÚMERO de votos de cada uno de estos campos:\n"
        f"{lineas}\n\n"
        "Reglas:\n"
        "- Cada número tiene hasta 3 casillas. Puntos '•' o marcas a la izquierda "
        "son ceros vacíos, NO son dígitos (ej. '..3' = 3, '.77' = 77, '130' = 130).\n"
        "- Si una casilla está vacía, el valor es 0 solo si no hay ningún dígito.\n"
        "- No inventes. Si no puedes leerlo con seguridad, devuelve null y confianza baja.\n"
        "- Además, buscá en el encabezado del formulario (fuera de las casillas de "
        "votos) un número de \"KIT\" y un código \"CIV\" — son identificadores "
        "impresos en el E-14, NO son votos. Si los ves, transcribilos tal cual están "
        "escritos (pueden tener letras y números) y dame tu confianza 0..1 de esa "
        "lectura igual que con los votos (el CIV suele estar impreso muy chico, así "
        "que si no se ve nítido, confianza baja). Si no aparecen, valor null y "
        "confianza 0.\n"
        "- Devuelve SOLO un JSON con esta forma exacta:\n"
        '{ "campos": { "<clave>": { "valor": <entero|null>, '
        '"confianza": <numero 0..1> }, ... }, '
        '"kit": { "valor": <texto|null>, "confianza": <numero 0..1> }, '
        '"civ": { "valor": <texto|null>, "confianza": <numero 0..1> } }'
    )


def _informe_api(campos: dict, cols: list[str]) -> str:
    """Texto legible de lo que devolvió Gemini/GPT por casilla."""
    partes: list[str] = []
    ok: list[str] = []
    for c in cols:
        celda = campos.get(c) or {}
        v = celda.get("valor")
        try:
            cf = float(celda.get("confianza", 0.0))
        except (TypeError, ValueError):
            cf = 0.0
        et = _etiqueta(c)
        if v is None:
            partes.append(f"{et}: sin leer (API conf={cf:.0%})")
        elif cf < UMBRAL_REVISION:
            partes.append(f"{et}={v} (conf baja {cf:.0%})")
        else:
            ok.append(f"{et}={v}")
    trozos = []
    if ok:
        trozos.append("OK: " + ", ".join(ok))
    if partes:
        trozos.append("REVISAR: " + " | ".join(partes))
    return " — ".join(trozos) if trozos else "API: todos los campos OK"


def _texto_o_none(valor) -> str | None:
    """Coerciona un campo JSON de texto libre (kit/civ) a str limpio o None."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _campo_texto_confianza(data: dict, clave: str) -> tuple[str | None, float]:
    """Lee un campo {valor, confianza} de texto libre (kit/civ) del JSON de la API."""
    celda = data.get(clave)
    if not isinstance(celda, dict):
        return _texto_o_none(celda), 0.0  # tolerancia si la API devuelve el texto suelto
    try:
        conf = float(celda.get("confianza", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return _texto_o_none(celda.get("valor")), conf


def _parsear_respuesta(texto: str, cols: list[str]) -> LecturaOCR:
    valores = {c: None for c in cols}
    confianzas = {c: 0.0 for c in cols}
    try:
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
        detalle = _informe_api(campos, cols)
        numero_kit, confianza_kit = _campo_texto_confianza(data, "kit")
        civ, confianza_civ = _campo_texto_confianza(data, "civ")
    except (json.JSONDecodeError, ValueError, AttributeError):
        return LecturaOCR(valores, confianzas, 0.0, True,
                          "Respuesta OCR no parseable.", texto[:300])

    presentes = [confianzas[c] for c in cols if valores[c] is not None]
    glob = min(presentes) if presentes else 0.0
    revisar = (not presentes) or any(cf < UMBRAL_REVISION for cf in presentes)
    notas_id = []
    if numero_kit is not None and confianza_kit < UMBRAL_REVISION:
        revisar = True
        notas_id.append(f"KIT={numero_kit} (conf baja {confianza_kit:.0%})")
    if civ is not None and confianza_civ < UMBRAL_REVISION:
        revisar = True
        notas_id.append(f"CIV={civ} (conf baja {confianza_civ:.0%})")
    if notas_id:
        detalle = f"{detalle} — REVISAR identificadores: " + ", ".join(notas_id)
    return LecturaOCR(valores, confianzas, glob, revisar, detalle_api=detalle,
                      numero_kit=numero_kit, civ=civ,
                      confianza_kit=confianza_kit, confianza_civ=confianza_civ)


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

    def __init__(self, api_key: str, modelo: str = "gemini-3.5-flash"):
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
            r = _post_gemini_con_reintento(
                self.URL.format(modelo=self.modelo), self.api_key, cuerpo)
            texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:  # noqa: BLE001 — fallo de red/API → marcar revisión
            return LecturaOCR({c: None for c in cols}, {c: 0.0 for c in cols},
                              0.0, True, _mensaje_error_api(e))
        lectura = _parsear_respuesta(texto, cols)
        if lectura.detalle_api:
            lectura.notas = lectura.detalle_api
        return lectura


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


# ─── Verificador: segunda lectura con OTRO modelo, solo para casillas dudosas ──
class BackendVerificado:
    """
    Envuelve un backend PRINCIPAL con un VERIFICADOR (otro modelo) que solo se
    consulta cuando el principal devolvió alguna casilla con confianza
    < UMBRAL_REVISION. Dos lecturas independientes coincidiendo es una señal
    fuerte de que el valor es correcto; si discrepan, queda marcado para
    revisión humana con ambos valores en las notas — nunca se promedia ni se
    inventa un valor.

    Costo acotado a propósito: la llamada extra al verificador solo se dispara
    si hay al menos una casilla dudosa (no en cada acta), así que el costo
    adicional cae justo donde más sirve.
    """

    def __init__(self, principal, verificador):
        self.principal = principal
        self.verificador = verificador
        self.nombre = f"{principal.nombre}+verificador_{verificador.nombre}"

    def reconocer_votos(self, imagen_alineada, layout_id: str) -> LecturaOCR:
        lectura = self.principal.reconocer_votos(imagen_alineada, layout_id)
        cols = columnas_de_layout(layout_id)
        dudosas = [c for c in cols if lectura.confianzas.get(c, 0.0) < UMBRAL_REVISION]
        if not dudosas:
            return lectura

        lectura2 = self.verificador.reconocer_votos(imagen_alineada, layout_id)
        notas_verif: list[str] = []
        for c in dudosas:
            v1, v2 = lectura.valores.get(c), lectura2.valores.get(c)
            et = _etiqueta(c)
            if v1 is None and v2 is not None:
                lectura.valores[c] = v2
                lectura.confianzas[c] = lectura2.confianzas.get(c, 0.0)
                notas_verif.append(f"{et}: recuperado por verificador ({v2})")
            elif v1 is not None and v2 is not None and v1 == v2:
                lectura.confianzas[c] = max(
                    lectura.confianzas[c], lectura2.confianzas.get(c, 0.0), UMBRAL_REVISION
                )
                notas_verif.append(f"{et}: verificador confirma ({v1})")
            elif v1 is not None and v2 is not None and v1 != v2:
                notas_verif.append(
                    f"{et}: DISCREPANCIA principal={v1} verificador={v2} (queda para revisión)"
                )
            # v1 None y v2 None: ninguno pudo leerla, sigue dudosa tal cual.

        presentes = [lectura.confianzas[c] for c in cols if lectura.valores.get(c) is not None]
        lectura.confianza_global = min(presentes) if presentes else 0.0
        lectura.necesita_revision = (not presentes) or any(
            lectura.confianzas[c] < UMBRAL_REVISION for c in cols if lectura.valores.get(c) is not None
        )
        if notas_verif:
            prefijo = f"Verificador ({self.verificador.nombre}): " + " | ".join(notas_verif)
            lectura.notas = f"{lectura.notas} | {prefijo}" if lectura.notas else prefijo
        return lectura


# ─── Fábrica: elige el backend según el entorno ───────────────────────────────
def crear_backend(preferido: str | None = None, verificar_baja_confianza: bool | None = None):
    """
    Devuelve el backend a usar.
      • OCR_BACKEND=gemini|gpt|manual fuerza uno.
      • Si no, usa Gemini si hay GEMINI_API_KEY, luego GPT si hay OPENAI_API_KEY.
      • Si no hay claves, BackendManual.
      • Doble verificación con GPT (cuando el principal es Gemini): SOLO si se
        pide explícitamente, nunca por defecto — `verificar_baja_confianza=True`
        (ej. desde --verificar-baja-confianza en auditar.py) o, si no se pasa
        nada (None), la variable de entorno OCR_VERIFICAR_BAJA_CONFIANZA=1.
        Envuelve con BackendVerificado: GPT solo se consulta en casillas con
        confianza < 80%, no en cada acta. Requiere también OPENAI_API_KEY.
    """
    cargar_env()
    elegido = (preferido or os.environ.get("OCR_BACKEND") or "").lower()

    gem = os.environ.get("GEMINI_API_KEY")
    gpt = os.environ.get("OPENAI_API_KEY")
    if verificar_baja_confianza is None:
        verificar = os.environ.get("OCR_VERIFICAR_BAJA_CONFIANZA", "").lower() in ("1", "true", "yes")
    else:
        verificar = verificar_baja_confianza

    if elegido == "manual":
        return BackendManual()
    if elegido == "gemini" or (not elegido and gem):
        if gem:
            principal = BackendGemini(gem, os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"))
            if verificar and gpt:
                verificador = BackendGPT(gpt, os.environ.get("OPENAI_MODEL", "gpt-4o"))
                return BackendVerificado(principal, verificador)
            return principal
    if elegido == "gpt" or (not elegido and gpt):
        if gpt:
            return BackendGPT(gpt, os.environ.get("OPENAI_MODEL", "gpt-4o"))
    return BackendManual()


def backend_por_defecto(verificar_baja_confianza: bool | None = None):
    return crear_backend(verificar_baja_confianza=verificar_baja_confianza)
