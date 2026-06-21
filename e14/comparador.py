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

# Columnas de candidato en orden (["c1", "c2"]) y categorías no candidato
# (["blanco", "nulos", "no_marcados"]), para los agregados de margen/totales.
_COLS_CANDIDATOS = [f"c{n}" for n in sorted(int(k) for k in CANDIDATOS)]


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
    confianza_testigo: float | None = None
    confianza_registraduria: float | None = None
    suma_total_testigo: int | None = None       # "TOTAL VOTOS DE LA MESA" declarado en el acta
    total_votos_urna_testigo: int | None = None
    suma_total_registraduria: int | None = None
    total_votos_urna_registraduria: int | None = None
    revisar_testigo: bool = False         # necesita_revision interno (ej. suma no cuadra)
    revisar_registraduria: bool = False
    verificado_testigo: bool = False      # un humano ya confirmó esta lectura
    verificado_registraduria: bool = False
    nota_verificacion_testigo: str | None = None
    nota_verificacion_registraduria: str | None = None
    kit_testigo: str | None = None
    kit_registraduria: str | None = None
    civ_testigo: str | None = None
    civ_registraduria: str | None = None
    confianza_kit_testigo: float | None = None
    confianza_kit_registraduria: float | None = None
    confianza_civ_testigo: float | None = None
    confianza_civ_registraduria: float | None = None

    @property
    def kit_coincide(self) -> bool | None:
        """None si falta alguno de los dos; True/False si hay ambos para comparar."""
        if not self.kit_testigo or not self.kit_registraduria:
            return None
        return self.kit_testigo.strip().lower() == self.kit_registraduria.strip().lower()

    @property
    def civ_coincide(self) -> bool | None:
        if not self.civ_testigo or not self.civ_registraduria:
            return None
        return self.civ_testigo.strip().lower() == self.civ_registraduria.strip().lower()

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

    def _dic(self, fuente: str) -> dict[str, int | None]:
        """{columna: valor} de una fuente, a partir de las celdas ya comparadas."""
        atributo = "valor_testigo" if fuente == "testigo" else "valor_registraduria"
        return {d.columna: getattr(d, atributo) for d in self.diferencias}

    def _suma(self, fuente: str, columnas: list[str]) -> int | None:
        """Suma de `columnas` para una fuente; None si ninguna tiene valor."""
        dic = self._dic(fuente)
        presentes = [dic[c] for c in columnas if dic.get(c) is not None]
        return sum(presentes) if presentes else None

    def _margen(self, fuente: str) -> int | None:
        """votos candidato 1 - votos candidato 2 (positivo = va ganando el 1)."""
        dic = self._dic(fuente)
        if len(_COLS_CANDIDATOS) != 2:
            return None
        v1, v2 = dic.get(_COLS_CANDIDATOS[0]), dic.get(_COLS_CANDIDATOS[1])
        if v1 is None or v2 is None:
            return None
        return v1 - v2

    @property
    def margen_testigo(self) -> int | None:
        return self._margen("testigo")

    @property
    def margen_registraduria(self) -> int | None:
        return self._margen("registraduria")

    @property
    def diferencia_margen(self) -> int | None:
        """
        Δ margen = margen_registraduría - margen_testigo.
        Positivo favorece al candidato 1 (c1); negativo, al candidato 2 (c2).
        """
        mt, mr = self.margen_testigo, self.margen_registraduria
        if mt is None or mr is None:
            return None
        return mr - mt

    @property
    def total_no_validos_testigo(self) -> int | None:
        return self._suma("testigo", CATEGORIAS_NO_CANDIDATO)

    @property
    def total_no_validos_registraduria(self) -> int | None:
        return self._suma("registraduria", CATEGORIAS_NO_CANDIDATO)

    @property
    def diferencia_no_validos(self) -> int | None:
        t, r = self.total_no_validos_testigo, self.total_no_validos_registraduria
        return None if t is None or r is None else r - t

    @property
    def total_testigo(self) -> int | None:
        return self._suma("testigo", columnas_voto())

    @property
    def total_registraduria(self) -> int | None:
        return self._suma("registraduria", columnas_voto())

    @property
    def diferencia_total(self) -> int | None:
        t, r = self.total_testigo, self.total_registraduria
        return None if t is None or r is None else r - t

    @property
    def total_declarado_testigo(self) -> int | None:
        """"TOTAL VOTOS DE LA MESA" leído del acta del testigo (no calculado)."""
        return (
            self.suma_total_testigo
            if self.suma_total_testigo is not None
            else self.total_votos_urna_testigo
        )

    @property
    def total_declarado_registraduria(self) -> int | None:
        return (
            self.suma_total_registraduria
            if self.suma_total_registraduria is not None
            else self.total_votos_urna_registraduria
        )

    @property
    def cuadra_testigo(self) -> bool | None:
        """¿La suma de candidatos+blanco+nulos+no_marcados coincide con el total declarado?"""
        objetivo, t = self.total_declarado_testigo, self.total_testigo
        return None if objetivo is None or t is None else t == objetivo

    @property
    def cuadra_registraduria(self) -> bool | None:
        objetivo, t = self.total_declarado_registraduria, self.total_registraduria
        return None if objetivo is None or t is None else t == objetivo

    @property
    def porcentaje_discrepancia_total(self) -> float | None:
        """Δ total como fracción del total testigo (magnitud del error global de la mesa)."""
        t, d = self.total_testigo, self.diferencia_total
        if not t or d is None:
            return None
        return d / t

    def _tiene_votos(self, fuente: str) -> bool:
        if fuente == "testigo":
            return any(d.valor_testigo is not None for d in self.diferencias)
        return any(d.valor_registraduria is not None for d in self.diferencias)

    @property
    def estado(self) -> str:
        if not (self.presente_testigo and self.presente_registraduria):
            return "FALTA_FUENTE"
        tiene_t = self._tiene_votos("testigo")
        tiene_r = self._tiene_votos("registraduria")
        if not tiene_t and not tiene_r:
            return "SIN_LECTURA"
        if not tiene_t or not tiene_r:
            return "LECTURA_INCOMPLETA"
        comparables = [
            d for d in self.diferencias
            if d.valor_testigo is not None and d.valor_registraduria is not None
        ]
        if not comparables:
            return "LECTURA_INCOMPLETA"
        if any(not d.coincide for d in comparables):
            return "DISCREPANCIA"
        # Algún voto solo en un lado (el otro null) → no es coincidencia real
        if any(
            (d.valor_testigo is None) != (d.valor_registraduria is None)
            for d in self.diferencias
        ):
            return "LECTURA_INCOMPLETA"
        return "COINCIDE"

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
        confianza_testigo=(fila_t or {}).get("confianza"),
        confianza_registraduria=(fila_r or {}).get("confianza"),
        suma_total_testigo=(fila_t or {}).get("suma_total"),
        total_votos_urna_testigo=(fila_t or {}).get("total_votos_urna"),
        suma_total_registraduria=(fila_r or {}).get("suma_total"),
        total_votos_urna_registraduria=(fila_r or {}).get("total_votos_urna"),
        revisar_testigo=bool((fila_t or {}).get("necesita_revision")),
        revisar_registraduria=bool((fila_r or {}).get("necesita_revision")),
        verificado_testigo=bool((fila_t or {}).get("verificado_manualmente")),
        verificado_registraduria=bool((fila_r or {}).get("verificado_manualmente")),
        nota_verificacion_testigo=(fila_t or {}).get("notas_verificacion"),
        nota_verificacion_registraduria=(fila_r or {}).get("notas_verificacion"),
        kit_testigo=_valor(fila_t, "numero_kit"),
        kit_registraduria=_valor(fila_r, "numero_kit"),
        civ_testigo=_valor(fila_t, "civ"),
        civ_registraduria=_valor(fila_r, "civ"),
        confianza_kit_testigo=(fila_t or {}).get("confianza_kit"),
        confianza_kit_registraduria=(fila_r or {}).get("confianza_kit"),
        confianza_civ_testigo=(fila_t or {}).get("confianza_civ"),
        confianza_civ_registraduria=(fila_r or {}).get("confianza_civ"),
    )


def comparar(testigo: dict[str, dict], registraduria: dict[str, dict]) -> list[ComparacionMesa]:
    """Compara los dos diccionarios {codigo_mesa: fila}. Devuelve una comparación por mesa."""
    codigos = sorted(set(testigo) | set(registraduria))
    return [comparar_mesa(c, testigo.get(c), registraduria.get(c)) for c in codigos]


def resumen(comparaciones: list[ComparacionMesa]) -> dict[str, int]:
    r = {
        "total": len(comparaciones),
        "COINCIDE": 0,
        "DISCREPANCIA": 0,
        "FALTA_FUENTE": 0,
        "SIN_LECTURA": 0,
        "LECTURA_INCOMPLETA": 0,
    }
    for c in comparaciones:
        r[c.estado] += 1
    return r
