"""
Catálogo de mesas a partir del Excel oficial de la Registraduría ("Mesa a Mesa").

El Excel NO trae actas: trae el UNIVERSO de mesas que existen. Según el export
puede venir con 1 fila por mesa (filtrado a un candidato) o varias filas por mesa
(una por candidato); por eso deduplicamos por (MUN, ZONA, PUESTO, MESA). Es el
"manifiesto" del departamento. Lo usamos para:

  1. Saber qué número (`MUN`) le corresponde a cada municipio  → nomenclatura
     NuMunicipio-zona-puesto-mesa (códigos de la REGISTRADURÍA, no DANE; en este
     archivo Bolívar = DEP 5, no 13).
  2. Conocer el universo de mesas de cada municipio (el "lote" a auditar).
  3. Medir cobertura: cruzar mesas esperadas (catálogo) vs archivos presentes.

Columnas esperadas en la hoja: DEP, DEPNOMBRE, MUN, MUNNOMBRE, ZONA, PUESTO, MESA
(las demás —candidato, votos, etc.— se ignoran para el catálogo).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from e14.mesa import codigo_canonico

# Columnas mínimas que el catálogo necesita del Excel
_REQUERIDAS = ("DEP", "DEPNOMBRE", "MUN", "MUNNOMBRE", "ZONA", "PUESTO", "MESA")


def _arreglar_mojibake(texto: str) -> str:
    """
    Repara nombres mal codificados (ej. 'EL PEÃ‘ON' -> 'EL PEÑON') cuando el Excel
    trae UTF-8 leído como Latin-1. Solo se intenta si hay señales de mojibake;
    si la reparación falla, se devuelve el texto original intacto.
    """
    if not isinstance(texto, str) or not any(m in texto for m in ("Ã", "Â", "â€")):
        return texto
    # El mis-decode típico es cp1252 (mapea 0x80–0x9F a comillas tipográficas, etc.);
    # latin-1 sirve de respaldo. Se devuelve la primera reparación que no falle.
    for codec in ("cp1252", "latin-1"):
        try:
            return texto.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return texto


def slug_municipio(nombre: str) -> str:
    """'EL CARMEN DE BOLIVAR' -> 'el_carmen_de_bolivar' (para nombres de carpeta)."""
    nombre = _arreglar_mojibake(nombre)
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c)
    )
    limpio = "".join(c if c.isalnum() or c.isspace() else " " for c in sin_acentos)
    return "_".join(limpio.lower().split())


@dataclass(frozen=True)
class MesaCatalogo:
    """Una mesa del universo oficial (sin votos)."""

    municipio: str   # código MUN (str, sin ceros a la izquierda)
    zona: str
    puesto: str
    mesa: str

    @property
    def codigo(self) -> str:
        """Código canónico NuMunicipio_zona_puesto_mesa (ej. '1_21_1_13')."""
        return codigo_canonico(self.municipio, self.zona, self.puesto, self.mesa)


@dataclass
class Catalogo:
    """Universo de mesas de un departamento, leído del Excel de la Registraduría."""

    departamento: str
    departamento_nombre: str
    nombres_municipio: dict[str, str]          # MUN -> nombre (mojibake reparado)
    mesas: list[MesaCatalogo] = field(default_factory=list)

    def municipios(self) -> list[str]:
        """Códigos MUN presentes, ordenados numéricamente."""
        return sorted(self.nombres_municipio, key=lambda m: int(m))

    def nombre_municipio(self, municipio: str | int) -> str:
        """Nombre legible del municipio (o el propio código si no está)."""
        return self.nombres_municipio.get(str(municipio), str(municipio))

    def mesas_de(self, municipio: str | int) -> list[MesaCatalogo]:
        """Mesas del municipio dado (un lote)."""
        m = str(municipio)
        return [x for x in self.mesas if x.municipio == m]

    def codigos_de(self, municipio: str | int) -> set[str]:
        """Universo esperado del lote: set de códigos canónicos del municipio."""
        return {x.codigo for x in self.mesas_de(municipio)}

    def total_mesas(self) -> int:
        return len(self.mesas)


def cargar_catalogo(ruta_excel: str | Path) -> Catalogo:
    """
    Lee el Excel 'Mesa a Mesa' y arma el catálogo (mesas únicas, sin votos).

    Deduplica por (MUN, ZONA, PUESTO, MESA): si el export trae una fila por
    candidato, la mesa aparece una sola vez en el catálogo igual.
    """
    ruta = Path(ruta_excel)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el Excel del catálogo: {ruta}")

    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    ws = wb.active
    filas = ws.iter_rows(values_only=True)

    try:
        encabezado = next(filas)
    except StopIteration:
        raise ValueError("El Excel del catálogo está vacío (sin encabezado).")

    idx = {str(nombre).strip().upper(): i for i, nombre in enumerate(encabezado) if nombre is not None}
    faltantes = [c for c in _REQUERIDAS if c not in idx]
    if faltantes:
        raise ValueError(
            f"Al Excel le faltan columnas requeridas: {', '.join(faltantes)}. "
            f"Encabezado encontrado: {list(idx)}"
        )

    departamento = ""
    departamento_nombre = ""
    nombres: dict[str, str] = {}
    vistas: set[tuple[str, str, str, str]] = set()
    mesas: list[MesaCatalogo] = []

    def _val(fila, col):
        v = fila[idx[col]]
        return "" if v is None else str(v).strip()

    for fila in filas:
        if fila is None or all(c is None for c in fila):
            continue
        mun = _val(fila, "MUN")
        if not mun:
            continue
        if not departamento:
            departamento = _val(fila, "DEP")
            departamento_nombre = _arreglar_mojibake(_val(fila, "DEPNOMBRE"))

        nombres.setdefault(mun, _arreglar_mojibake(_val(fila, "MUNNOMBRE")))

        zona, puesto, mesa = _val(fila, "ZONA"), _val(fila, "PUESTO"), _val(fila, "MESA")
        clave = (mun, zona, puesto, mesa)
        if clave in vistas:
            continue
        vistas.add(clave)
        mesas.append(MesaCatalogo(municipio=mun, zona=zona, puesto=puesto, mesa=mesa))

    wb.close()
    return Catalogo(
        departamento=departamento,
        departamento_nombre=departamento_nombre,
        nombres_municipio=nombres,
        mesas=mesas,
    )


def nombre_carpeta_lote(catalogo: Catalogo, municipio: str | int) -> str:
    """Nombre de carpeta del lote: '01_cartagena' (MUN con cero + slug del nombre)."""
    mun = str(municipio)
    return f"{int(mun):02d}_{slug_municipio(catalogo.nombre_municipio(mun))}"


def crear_estructura_lote(base_datos: str | Path, catalogo: Catalogo,
                          municipio: str | int) -> Path:
    """
    Crea (si no existen) las carpetas del lote de un municipio:
        <base_datos>/<NN_nombre>/testigos/
        <base_datos>/<NN_nombre>/registraduria/
    Devuelve la ruta de la carpeta del lote. Idempotente: no borra nada.
    """
    base = Path(base_datos)
    lote = base / nombre_carpeta_lote(catalogo, municipio)
    (lote / "testigos").mkdir(parents=True, exist_ok=True)
    (lote / "registraduria").mkdir(parents=True, exist_ok=True)
    return lote
