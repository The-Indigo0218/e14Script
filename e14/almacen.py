"""
Almacén SQLite para las actas leídas.

Tabla única `actas` con una fila por (mesa, fuente). El comparador luego cruza
las filas de fuente='testigo' contra fuente='registraduria' por codigo_mesa.

SQLite es ideal aquí: cero servidor, un solo archivo, gratis, y se empaqueta
sin problema en el .exe de Windows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from e14.modelo import ActaE14, columnas_voto

_COLUMNAS_META = [
    "codigo_mesa", "fuente", "tipo_acta", "copias_en_evidencia",
    "departamento", "municipio", "zona", "puesto", "mesa",
]
_COLUMNAS_TOTALES = ["suma_total", "total_votos_urna", "total_votantes_e11"]
_COLUMNAS_AUDIT = ["archivo_origen", "confianza", "necesita_revision", "notas"]

_TODAS = _COLUMNAS_META + columnas_voto() + _COLUMNAS_TOTALES + _COLUMNAS_AUDIT


class Almacen:
    def __init__(self, ruta_db: str | Path = "actas.db"):
        self.ruta = str(ruta_db)
        self.con = sqlite3.connect(self.ruta)
        self.con.row_factory = sqlite3.Row
        self._crear_tabla()
        self._migrar_columnas()

    def _migrar_columnas(self) -> None:
        """Añade columnas nuevas en bases de datos ya existentes."""
        cur = self.con.execute("PRAGMA table_info(actas)")
        existentes = {row[1] for row in cur.fetchall()}
        if "copias_en_evidencia" not in existentes:
            self.con.execute("ALTER TABLE actas ADD COLUMN copias_en_evidencia TEXT")
            self.con.commit()

    def _crear_tabla(self) -> None:
        cols_def = []
        for c in _TODAS:
            if c in ("codigo_mesa", "fuente", "tipo_acta", "copias_en_evidencia",
                     "departamento", "municipio", "zona", "puesto", "mesa",
                     "archivo_origen", "notas"):
                tipo = "TEXT"
            elif c == "confianza":
                tipo = "REAL"
            elif c == "necesita_revision":
                tipo = "INTEGER"
            else:
                tipo = "INTEGER"
            cols_def.append(f"{c} {tipo}")
        sql = (
            "CREATE TABLE IF NOT EXISTS actas (\n  "
            + ",\n  ".join(cols_def)
            + ",\n  PRIMARY KEY (codigo_mesa, fuente)\n)"
        )
        self.con.execute(sql)
        self.con.commit()

    def guardar(self, acta: ActaE14) -> None:
        """Inserta o reemplaza la fila para (codigo_mesa, fuente)."""
        d = acta.como_dict()
        d["necesita_revision"] = 1 if acta.necesita_revision else 0
        valores = [d.get(c) for c in _TODAS]
        marcadores = ",".join("?" for _ in _TODAS)
        cols = ",".join(_TODAS)
        self.con.execute(
            f"INSERT OR REPLACE INTO actas ({cols}) VALUES ({marcadores})", valores
        )
        self.con.commit()

    def leer_por_fuente(self, fuente: str) -> dict[str, dict]:
        """{codigo_mesa: fila_dict} para una fuente."""
        cur = self.con.execute("SELECT * FROM actas WHERE fuente = ?", (fuente,))
        return {row["codigo_mesa"]: dict(row) for row in cur.fetchall()}

    def mesas(self) -> list[str]:
        cur = self.con.execute("SELECT DISTINCT codigo_mesa FROM actas ORDER BY codigo_mesa")
        return [r["codigo_mesa"] for r in cur.fetchall()]

    def cerrar(self) -> None:
        self.con.close()
