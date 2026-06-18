"""
Identificación de mesa para emparejar testigo ↔ Registraduría.

Convención de archivos (economiza OCR: solo procesas pares que existen en ambas carpetas):
    datos/testigos/cartagena_21_01_13_testigo.pdf
    datos/registraduria/cartagena_21_01_13_registraduria.pdf
    → codigo_mesa = "cartagena_21_01_13"  (municipio Cartagena, zona 21, puesto 01, mesa 13)

Se incluye el MUNICIPIO en el código porque zona/puesto/mesa se numeran dentro
de cada municipio: dos municipios distintos del mismo departamento pueden tener
ambos una "zona 21, puesto 01, mesa 13". Sin el municipio, el comparador
fusionaría por error mesas de municipios distintos que comparten ese número.

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
    Extrae el código de par (municipio_zona_puesto_mesa) quitando el sufijo de fuente.
    cartagena_21_01_13_testigo.pdf → cartagena_21_01_13
    """
    stem = Path(ruta).stem
    bajo = stem.lower()
    for suf in _SUFIJOS_FUENTE:
        if bajo.endswith(suf):
            return stem[: len(stem) - len(suf)].rstrip("_-")
    return stem


def municipio_zona_puesto_mesa_desde_codigo(codigo: str) -> dict[str, str]:
    """
    cartagena_21_01_13 → municipio=cartagena, zona=21, puesto=01, mesa=13.

    Acepta el municipio como texto (no numérico) seguido de 3 segmentos
    numéricos (zona, puesto, mesa).
    """
    norm = codigo.strip().replace("-", "_")
    partes = norm.split("_")
    if len(partes) >= 4 and all(p.isdigit() for p in partes[-3:]):
        municipio = "_".join(partes[:-3])
        zona, puesto, mesa = partes[-3:]
        return {"municipio": municipio, "zona": zona, "puesto": puesto, "mesa": mesa}
    m = re.match(r"^(.+?)[_\-](\d+)[_\-](\d+)[_\-](\d+)$", norm)
    if m:
        return {
            "municipio": m.group(1), "zona": m.group(2),
            "puesto": m.group(3), "mesa": m.group(4),
        }
    return {}


def etiqueta_mesa(codigo: str, meta: dict[str, str] | None = None) -> str:
    """Texto legible: Cartagena · Zona 21 · Puesto 01 · Mesa 13."""
    meta = meta or municipio_zona_puesto_mesa_desde_codigo(codigo)
    if meta:
        municipio = meta["municipio"].replace("_", " ").title()
        return f"{municipio} · Zona {meta['zona']} · Puesto {meta['puesto']} · Mesa {meta['mesa']}"
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
