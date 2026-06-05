"""
Identificación de mesa para emparejar testigo ↔ Registraduría.

Convención de archivos (economiza OCR: solo procesas pares que existen en ambas carpetas):
    datos/testigos/21_01_13_testigo.pdf
    datos/registraduria/21_01_13_registraduria.pdf
    → codigo_mesa = "21_01_13"  (zona 21, puesto 01, mesa 13)

El comparador cruza por ese mismo `codigo_mesa`.
"""

from __future__ import annotations

import re
from pathlib import Path

# Sufijos que se quitan del nombre de archivo para obtener el código común
_SUFIJOS_FUENTE = (
    "_testigo", "_testigos", "_jurado", "_jurados",
    "_registraduria", "_reg", "_oficial", "_delegados",
)


def codigo_mesa_desde_archivo(ruta: str | Path) -> str:
    """
    Extrae el código de par (zona_puesto_mesa) quitando el sufijo de fuente.
    21_01_13_testigo.pdf → 21_01_13
    """
    stem = Path(ruta).stem
    bajo = stem.lower()
    for suf in _SUFIJOS_FUENTE:
        if bajo.endswith(suf):
            return stem[: len(stem) - len(suf)].rstrip("_-")
    return stem


def zona_puesto_mesa_desde_codigo(codigo: str) -> dict[str, str]:
    """21_01_13 → zona=21, puesto=01, mesa=13."""
    norm = codigo.strip().replace("-", "_")
    partes = norm.split("_")
    if len(partes) >= 3 and all(p.isdigit() for p in partes[:3]):
        return {"zona": partes[0], "puesto": partes[1], "mesa": partes[2]}
    m = re.match(r"^(\d+)[_\-](\d+)[_\-](\d+)", norm)
    if m:
        return {"zona": m.group(1), "puesto": m.group(2), "mesa": m.group(3)}
    return {}


def etiqueta_mesa(codigo: str, meta: dict[str, str] | None = None) -> str:
    """Texto legible: Zona 21 · Puesto 01 · Mesa 13."""
    meta = meta or zona_puesto_mesa_desde_codigo(codigo)
    if meta:
        return f"Zona {meta['zona']} · Puesto {meta['puesto']} · Mesa {meta['mesa']}"
    return codigo


def listar_codigos_en_carpeta(carpeta: str | Path) -> set[str]:
    """Códigos de par detectados en los nombres de archivo de una carpeta."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return set()
    codigos: set[str] = set()
    for ext in ("*.pdf", "*.png", "*.jpg", "*.jpeg"):
        for f in carpeta.glob(ext):
            codigos.add(codigo_mesa_desde_archivo(f))
    return codigos


def pares_disponibles(carpeta_testigos: str | Path, carpeta_reg: str | Path) -> tuple[set[str], set[str], set[str]]:
    """
    Devuelve (pares_en_ambas, solo_testigo, solo_registraduria).
    Solo los de `pares_en_ambas` deberían pasar por OCR si quieres ahorrar API.
    """
    t = listar_codigos_en_carpeta(carpeta_testigos)
    r = listar_codigos_en_carpeta(carpeta_reg)
    ambos = t & r
    return ambos, t - r, r - t
