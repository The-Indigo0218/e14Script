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

from e14.modelo import FUENTE_TESTIGO, FUENTE_REGISTRADURIA

# Sufijos que se quitan del nombre de archivo para obtener el código común
_SUFIJOS_TESTIGO = ("_testigo", "_testigos", "_jurado", "_jurados")
_SUFIJOS_REGISTRADURIA = ("_registraduria", "_reg", "_oficial", "_delegados")
_SUFIJOS_FUENTE = _SUFIJOS_TESTIGO + _SUFIJOS_REGISTRADURIA


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


def fuente_desde_archivo(ruta: str | Path) -> str | None:
    """
    FUENTE_TESTIGO o FUENTE_REGISTRADURIA según el sufijo del nombre de archivo;
    None si no calza con ninguno (no se puede clasificar, ej. nombre suelto sin
    convención — útil para detectar archivos que llegan mal nombrados a Drive).
    """
    bajo = Path(ruta).stem.lower()
    if bajo.endswith(_SUFIJOS_TESTIGO):
        return FUENTE_TESTIGO
    if bajo.endswith(_SUFIJOS_REGISTRADURIA):
        return FUENTE_REGISTRADURIA
    return None


def _segmento_canonico(valor: str | int) -> str:
    """Un segmento del código: si es numérico, sin ceros a la izquierda; si no, en minúscula."""
    s = str(valor).strip()
    return str(int(s)) if s.lstrip("-").isdigit() else s.lower()


def codigo_canonico(municipio: str | int, zona: str | int,
                    puesto: str | int, mesa: str | int) -> str:
    """
    Construye el código canónico de la nomenclatura NuMunicipio-zona-puesto-mesa.

    Los segmentos numéricos se normalizan SIN ceros a la izquierda, para que
    `1_21_01_13` (de un nombre de archivo) y `1_21_1_13` (del catálogo/Excel)
    representen la MISMA mesa y crucen correctamente.
        codigo_canonico(1, 21, 1, 13) -> "1_21_1_13"
    """
    return "_".join(_segmento_canonico(x) for x in (municipio, zona, puesto, mesa))


def normalizar_codigo(codigo: str) -> str:
    """
    Lleva cualquier código (con `_` o `-`, con o sin ceros) a su forma canónica.
        "1-21-01-13" -> "1_21_1_13"   ;   "1_21_01_13" -> "1_21_1_13"
    Si no calza el patrón municipio-zona-puesto-mesa, devuelve el texto en minúscula.
    """
    meta = municipio_zona_puesto_mesa_desde_codigo(codigo)
    if meta:
        return codigo_canonico(meta["municipio"], meta["zona"], meta["puesto"], meta["mesa"])
    return str(codigo).strip().lower()


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


def listar_codigos_en_carpeta(carpeta: str | Path, normalizar: bool = False) -> set[str]:
    """
    Códigos de par detectados en los nombres de archivo de una carpeta.

    Con `normalizar=True` devuelve los códigos en forma canónica (sin ceros a la
    izquierda), para que crucen contra los códigos del catálogo.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return set()
    codigos: set[str] = set()
    for ext in ("*.pdf", "*.png", "*.jpg", "*.jpeg"):
        for f in carpeta.glob(ext):
            cod = codigo_mesa_desde_archivo(f)
            codigos.add(normalizar_codigo(cod) if normalizar else cod)
    return codigos


def mapa_codigo_archivo(carpeta: str | Path, normalizar: bool = True) -> dict[str, Path]:
    """
    {codigo_mesa: ruta} de los documentos de una carpeta. Con `normalizar=True`
    la clave es el código canónico (para cruzar con el catálogo). Si dos archivos
    comparten código, gana el primero en orden alfabético (estable).
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return {}
    mapa: dict[str, Path] = {}
    archivos: list[Path] = []
    for ext in ("*.pdf", "*.png", "*.jpg", "*.jpeg"):
        archivos.extend(carpeta.glob(ext))
    for f in sorted(archivos):
        cod = codigo_mesa_desde_archivo(f)
        clave = normalizar_codigo(cod) if normalizar else cod
        mapa.setdefault(clave, f)
    return mapa


def filtrar_por_zona_puesto(codigos, zona: str | int | None = None,
                           puesto: str | int | None = None) -> list[str]:
    """
    Filtra códigos de mesa (ya del municipio del lote) por zona y, opcionalmente,
    puesto dentro de esa zona. Sin filtros, devuelve todo ordenado.

    NUNCA se admite `puesto` sin `zona`: el mismo número de puesto se repite en
    decenas de zonas distintas dentro de un mismo municipio (ej. en Cartagena el
    "puesto 1" existe en 22 zonas), así que saltarse ese nivel de la jerarquía
    municipio→zona→puesto→mesa sería ambiguo, no un alias válido.
    """
    if puesto is not None and zona is None:
        raise ValueError(
            "--puesto requiere --zona (no se puede filtrar por puesto solo: "
            "el número de puesto se repite en distintas zonas del municipio)."
        )
    if zona is None:
        return sorted(codigos)
    zona_norm = _segmento_canonico(zona)
    puesto_norm = _segmento_canonico(puesto) if puesto is not None else None
    seleccionados = []
    for c in codigos:
        meta = municipio_zona_puesto_mesa_desde_codigo(c)
        if not meta or _segmento_canonico(meta["zona"]) != zona_norm:
            continue
        if puesto_norm is not None and _segmento_canonico(meta["puesto"]) != puesto_norm:
            continue
        seleccionados.append(c)
    return sorted(seleccionados)


def pares_disponibles(carpeta_testigos: str | Path, carpeta_reg: str | Path) -> tuple[set[str], set[str], set[str]]:
    """
    Devuelve (pares_en_ambas, solo_testigo, solo_registraduria).
    Solo los de `pares_en_ambas` deberían pasar por OCR si quieres ahorrar API.
    """
    t = listar_codigos_en_carpeta(carpeta_testigos)
    r = listar_codigos_en_carpeta(carpeta_reg)
    ambos = t & r
    return ambos, t - r, r - t
