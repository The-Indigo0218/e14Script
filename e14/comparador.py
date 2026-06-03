"""
Lógica de comparación (script 3, parte central).

Cruza las actas del testigo contra las de la Registraduría por codigo_mesa y
detecta discrepancias columna por columna. No depende de OCR ni de red:
trabaja sobre la tabla común, así que es 100% testeable de forma aislada.
"""

from __future__ import annotations

from dataclasses import dataclass

from e14.modelo import (
    CANDIDATOS,
    CATEGORIAS_NO_CANDIDATO,
    columnas_voto,
    resumen_trazabilidad_e14,
    FUENTE_TESTIGO,
    FUENTE_REGISTRADURIA,
)


def etiqueta_columna(col: str) -> str:
    """Nombre legible de una columna de voto."""
    if col.startswith("c") and col[1:].isdigit():
        num = col[1:]
        nombre, _ = CANDIDATOS.get(num, (f"Candidato {num}", ""))
        return f"{num}. {nombre}"
    return {
        "blanco": "Votos en blanco",
        "nulos": "Votos nulos",
        "no_marcados": "Votos no marcados",
    }.get(col, col)


@dataclass
class DiferenciaCelda:
    columna: str
    etiqueta: str
    valor_testigo: int | None
    valor_registraduria: int | None

    @property
    def diferencia(self) -> int | None:
        if self.valor_testigo is None or self.valor_registraduria is None:
            return None
        return self.valor_registraduria - self.valor_testigo

    @property
    def coincide(self) -> bool:
        return self.valor_testigo == self.valor_registraduria


@dataclass
class ComparacionMesa:
    codigo_mesa: str
    presente_testigo: bool
    presente_registraduria: bool
    diferencias: list[DiferenciaCelda]
    tipo_testigo: str | None = None
    copias_testigo: str | None = None       # copias visibles en evidencia jurados
    tipo_registraduria: str | None = None
    copias_registraduria: str | None = None

    @property
    def trazabilidad_testigo(self) -> str:
        return resumen_trazabilidad_e14(
            FUENTE_TESTIGO, self.copias_testigo, self.tipo_testigo)

    @property
    def trazabilidad_registraduria(self) -> str:
        return resumen_trazabilidad_e14(
            FUENTE_REGISTRADURIA, self.copias_registraduria, self.tipo_registraduria)

    @property
    def alerta_copias_en_foto(self) -> bool:
        """Hay 2+ copias en evidencia del testigo → conviene revisar si coinciden."""
        from e14.modelo import parsear_copias
        return len(parsear_copias(self.copias_testigo)) >= 2

    @property
    def estado(self) -> str:
        if not (self.presente_testigo and self.presente_registraduria):
            return "FALTA_FUENTE"
        if all(d.coincide for d in self.diferencias):
            return "COINCIDE"
        return "DISCREPANCIA"

    @property
    def celdas_discrepantes(self) -> list[DiferenciaCelda]:
        return [d for d in self.diferencias if not d.coincide]


def _valor(fila: dict | None, col: str) -> int | None:
    if fila is None:
        return None
    return fila.get(col)


def comparar_mesa(codigo: str, fila_t: dict | None, fila_r: dict | None) -> ComparacionMesa:
    diffs: list[DiferenciaCelda] = []
    for col in columnas_voto():
        diffs.append(
            DiferenciaCelda(
                columna=col,
                etiqueta=etiqueta_columna(col),
                valor_testigo=_valor(fila_t, col),
                valor_registraduria=_valor(fila_r, col),
            )
        )
    return ComparacionMesa(
        codigo_mesa=codigo,
        presente_testigo=fila_t is not None,
        presente_registraduria=fila_r is not None,
        diferencias=diffs,
        tipo_testigo=_valor(fila_t, "tipo_acta"),
        copias_testigo=_valor(fila_t, "copias_en_evidencia"),
        tipo_registraduria=_valor(fila_r, "tipo_acta"),
        copias_registraduria=_valor(fila_r, "copias_en_evidencia"),
    )


def comparar(testigo: dict[str, dict], registraduria: dict[str, dict]) -> list[ComparacionMesa]:
    """Compara los dos diccionarios {codigo_mesa: fila}. Devuelve una comparación por mesa."""
    codigos = sorted(set(testigo) | set(registraduria))
    return [comparar_mesa(c, testigo.get(c), registraduria.get(c)) for c in codigos]


def resumen(comparaciones: list[ComparacionMesa]) -> dict[str, int]:
    r = {"total": len(comparaciones), "COINCIDE": 0, "DISCREPANCIA": 0, "FALTA_FUENTE": 0}
    for c in comparaciones:
        r[c.estado] += 1
    return r
