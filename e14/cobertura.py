"""
Cobertura de un lote (municipio): cuántas mesas del universo oficial tenemos
realmente listas para auditar.

Cruza TRES conjuntos de códigos de mesa (canónicos):
  - esperadas      : universo del catálogo (Excel de la Registraduría) del municipio.
  - testigos        : archivos presentes en <lote>/testigos/.
  - registraduria  : archivos presentes en <lote>/registraduria/.

De ahí se derivan los estados que importan para planear el trabajo y ahorrar OCR:
  - listas              : esperadas con AMBAS fuentes  → se pueden auditar ya.
  - solo_testigo        : esperadas con solo el testigo → falta el oficial.
  - solo_registraduria  : esperadas con solo el oficial → falta el del testigo.
  - faltan_ambas        : esperadas sin ningún archivo  → falta todo.
  - fuera_de_catalogo   : archivos cuyo código NO está en el catálogo → ALERTA
                          (nombre mal puesto, o mesa que no corresponde al municipio).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from e14.catalogo import Catalogo, nombre_carpeta_lote
from e14.mesa import filtrar_por_zona_puesto, listar_codigos_en_carpeta


@dataclass
class Cobertura:
    """Resultado de cruzar catálogo vs archivos presentes para un municipio."""

    municipio: str
    municipio_nombre: str
    esperadas: set[str]
    testigos: set[str]
    registraduria: set[str]

    @property
    def listas(self) -> set[str]:
        """Esperadas con testigo Y registraduría: listas para auditar."""
        return self.esperadas & self.testigos & self.registraduria

    @property
    def solo_testigo(self) -> set[str]:
        return (self.esperadas & self.testigos) - self.registraduria

    @property
    def solo_registraduria(self) -> set[str]:
        return (self.esperadas & self.registraduria) - self.testigos

    @property
    def faltan_ambas(self) -> set[str]:
        return self.esperadas - self.testigos - self.registraduria

    @property
    def fuera_de_catalogo(self) -> set[str]:
        """Archivos presentes cuyo código no está en el universo esperado (alerta)."""
        return (self.testigos | self.registraduria) - self.esperadas

    @property
    def pct_listas(self) -> float:
        """Porcentaje de mesas del universo listas para auditar (0..100)."""
        if not self.esperadas:
            return 0.0
        return 100.0 * len(self.listas) / len(self.esperadas)

    def resumen(self) -> dict[str, int]:
        """Conteos para tablero/reportes."""
        return {
            "esperadas": len(self.esperadas),
            "listas": len(self.listas),
            "solo_testigo": len(self.solo_testigo),
            "solo_registraduria": len(self.solo_registraduria),
            "faltan_ambas": len(self.faltan_ambas),
            "fuera_de_catalogo": len(self.fuera_de_catalogo),
        }

    def texto(self) -> str:
        """Resumen legible para consola."""
        r = self.resumen()
        lineas = [
            f"Lote {self.municipio} · {self.municipio_nombre}",
            f"  Universo (catálogo):   {r['esperadas']:>6}",
            f"  Listas para auditar:   {r['listas']:>6}  ({self.pct_listas:.1f}%)",
            f"  Solo testigo:          {r['solo_testigo']:>6}",
            f"  Solo registraduría:    {r['solo_registraduria']:>6}",
            f"  Faltan ambas fuentes:  {r['faltan_ambas']:>6}",
        ]
        if r["fuera_de_catalogo"]:
            lineas.append(f"  ⚠ Fuera de catálogo:   {r['fuera_de_catalogo']:>6}  (revisar nombres)")
        return "\n".join(lineas)


def cobertura_lote(catalogo: Catalogo, municipio: str | int,
                   base_datos: str | Path = "datos", *,
                   zona: str | int | None = None,
                   puesto: str | int | None = None) -> Cobertura:
    """
    Calcula la cobertura de un municipio leyendo su carpeta de lote:
        <base_datos>/<NN_nombre>/testigos/
        <base_datos>/<NN_nombre>/registraduria/
    Si la carpeta no existe aún, testigos/registraduría quedan vacíos.

    `zona`/`puesto` acotan los tres conjuntos a esa zona (o zona+puesto) del
    municipio antes de cruzarlos — ver `filtrar_por_zona_puesto` (nunca admite
    puesto sin zona).
    """
    mun = str(int(str(municipio)))  # normaliza '01' -> '1'
    lote = Path(base_datos) / nombre_carpeta_lote(catalogo, mun)
    testigos = listar_codigos_en_carpeta(lote / "testigos", normalizar=True)
    registraduria = listar_codigos_en_carpeta(lote / "registraduria", normalizar=True)
    esperadas = catalogo.codigos_de(mun)
    if zona is not None:
        esperadas = set(filtrar_por_zona_puesto(esperadas, zona, puesto))
        testigos = set(filtrar_por_zona_puesto(testigos, zona, puesto))
        registraduria = set(filtrar_por_zona_puesto(registraduria, zona, puesto))
    return Cobertura(
        municipio=mun,
        municipio_nombre=catalogo.nombre_municipio(mun),
        esperadas=esperadas,
        testigos=testigos,
        registraduria=registraduria,
    )
