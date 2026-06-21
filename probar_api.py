"""
Verifica que la clave del .env funcione ANTES de procesar actas.

Hace una llamada mínima (texto, sin imagen) al modelo configurado y reporta si
respondió. Útil para confirmar que la API key de Gemini (capa gratis) quedó bien
pegada en .env.

Uso:
    python probar_api.py
"""

import os
import sys

import requests

from e14.ocr import cargar_env


def probar_gemini(api_key: str, modelo: str) -> tuple[bool, str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    cuerpo = {"contents": [{"parts": [{"text": "Responde solo: OK"}]}]}
    try:
        r = requests.post(url, params={"key": api_key}, json=cuerpo, timeout=30)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        texto = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return True, texto
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def probar_gpt(api_key: str, modelo: str) -> tuple[bool, str]:
    url = "https://api.openai.com/v1/chat/completions"
    cuerpo = {"model": modelo, "messages": [{"role": "user", "content": "Responde solo: OK"}]}
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {api_key}"},
                          json=cuerpo, timeout=30)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        return True, r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def probar_openrouter(api_key: str, modelo: str) -> tuple[bool, str]:
    url = "https://openrouter.ai/api/v1/chat/completions"
    cuerpo = {"model": modelo, "messages": [{"role": "user", "content": "Responde solo: OK"}]}
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {api_key}", "X-Title": "Auditoria E14"},
                          json=cuerpo, timeout=30)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        return True, r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def main():
    cargar_env()
    backend = (os.environ.get("OCR_BACKEND") or "").lower()
    gem = os.environ.get("GEMINI_API_KEY")
    gpt = os.environ.get("OPENAI_API_KEY")
    openrouter = os.environ.get("OPENROUTER_API_KEY")

    if (backend == "gemini" or (not backend and gem)) and gem:
        modelo = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
        print(f"Probando Gemini ({modelo})...")
        ok, msg = probar_gemini(gem, modelo)
    elif (backend == "gpt" or (not backend and gpt)) and gpt:
        modelo = os.environ.get("OPENAI_MODEL", "gpt-4o")
        print(f"Probando GPT ({modelo})...")
        ok, msg = probar_gpt(gpt, modelo)
    elif (backend == "openrouter" or (not backend and openrouter)) and openrouter:
        modelo = os.environ.get("OPENROUTER_MODEL", "google/gemini-3.5-flash")
        print(f"Probando OpenRouter ({modelo})...")
        ok, msg = probar_openrouter(openrouter, modelo)
    else:
        print("❌ No hay clave configurada en .env "
              "(GEMINI_API_KEY, OPENAI_API_KEY u OPENROUTER_API_KEY).")
        print("   Pega tu clave en .env y vuelve a correr este script.")
        sys.exit(1)

    if ok:
        print(f"✅ La API respondió correctamente: {msg!r}")
        print("   Ya puedes procesar actas reales con leer_registraduria.py / leer_testigos.py")
    else:
        print(f"❌ La API no respondió bien: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
