"""
Almacén SQLite para las actas leídas.

Tabla única `actas` con una fila por (mesa, fuente). El comparador luego cruza
las filas de fuente='testigo' contra fuente='registraduria' por codigo_mesa.

SQLite es ideal aquí: cero servidor, un solo archivo, gratis, y se empaqueta
sin problema en el .exe de Windows.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from e14.modelo import ActaE14, columnas_voto

_COLUMNAS_META = [
    "codigo_mesa", "fuente", "tipo_acta", "copias_en_evidencia",
    "departamento", "municipio", "zona", "puesto", "mesa",
    "numero_kit", "civ", "confianza_kit", "confianza_civ",
]
_COLUMNAS_TOTALES = ["suma_total", "total_votos_urna", "total_votantes_e11"]
_COLUMNAS_AUDIT = ["archivo_origen", "confianza", "necesita_revision", "notas"]
_COLUMNAS_VERIFICACION = ["verificado_manualmente", "notas_verificacion"]

_TODAS = (
    _COLUMNAS_META + columnas_voto() + _COLUMNAS_TOTALES + _COLUMNAS_AUDIT
    + _COLUMNAS_VERIFICACION
)


class Almacen:
    def __init__(self, ruta_db: str | Path = "actas.db"):
        self.ruta = str(ruta_db)
        self.con = sqlite3.connect(self.ruta)
        self.con.row_factory = sqlite3.Row
        self._crear_tabla()
        self._crear_tabla_historial()
        self._migrar_columnas()

    def _migrar_columnas(self) -> None:
        """Añade a `actas` y `actas_historial` las columnas que falten en bases ya existentes."""
        tipos = {
            "copias_en_evidencia": "TEXT", "verificado_manualmente": "INTEGER",
            "notas_verificacion": "TEXT", "numero_kit": "TEXT", "civ": "TEXT",
            "confianza_kit": "REAL", "confianza_civ": "REAL",
        }
        cur = self.con.execute("PRAGMA table_info(actas)")
        existentes = {row[1] for row in cur.fetchall()}
        for col, tipo in tipos.items():
            if col not in existentes:
                self.con.execute(f"ALTER TABLE actas ADD COLUMN {col} {tipo}")

        # `actas_historial` guarda todo como TEXT (es solo histórico, ver _crear_tabla_historial).
        cur_h = self.con.execute("PRAGMA table_info(actas_historial)")
        existentes_h = {row[1] for row in cur_h.fetchall()}
        for col in tipos:
            if col not in existentes_h:
                self.con.execute(f"ALTER TABLE actas_historial ADD COLUMN {col} TEXT")
        self.con.commit()

    def _crear_tabla(self) -> None:
        cols_def = []
        for c in _TODAS:
            if c in ("codigo_mesa", "fuente", "tipo_acta", "copias_en_evidencia",
                     "departamento", "municipio", "zona", "puesto", "mesa",
                     "archivo_origen", "notas", "notas_verificacion",
                     "numero_kit", "civ"):
                tipo = "TEXT"
            elif c in ("confianza", "confianza_kit", "confianza_civ"):
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

    def _crear_tabla_historial(self) -> None:
        """
        Historial de versiones: cada vez que se SOBREESCRIBE una mesa/fuente, la
        versión anterior se archiva aquí antes de ser reemplazada. Mismas columnas
        que `actas`, más `version` (1, 2, 3…) y `archivado_en` (cuándo se superó).
        """
        cols_def = [f"{c} TEXT" for c in _TODAS]  # tipos laxos: es solo histórico
        sql = (
            "CREATE TABLE IF NOT EXISTS actas_historial (\n  version INTEGER,\n  "
            "archivado_en TEXT,\n  "
            + ",\n  ".join(cols_def)
            + ",\n  PRIMARY KEY (codigo_mesa, fuente, version)\n)"
        )
        self.con.execute(sql)
        self.con.commit()

    def _archivar(self, fila: sqlite3.Row) -> None:
        """Copia la fila actual de `actas` al historial con la siguiente versión."""
        sig = self.con.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM actas_historial "
            "WHERE codigo_mesa = ? AND fuente = ?",
            (fila["codigo_mesa"], fila["fuente"]),
        ).fetchone()[0]
        valores = [sig, datetime.now().isoformat(timespec="seconds")] + [fila[c] for c in _TODAS]
        marcadores = ",".join("?" for _ in valores)
        cols = "version,archivado_en," + ",".join(_TODAS)
        self.con.execute(
            f"INSERT INTO actas_historial ({cols}) VALUES ({marcadores})", valores
        )

    def guardar(self, acta: ActaE14) -> None:
        """
        Inserta o reemplaza la fila para (codigo_mesa, fuente).

        Conserva la verificación manual si la fila ya existía: re-correr el OCR
        sobre una mesa ya verificada no debe borrar esa verificación.

        Si la mesa/fuente ya existía, la versión anterior se archiva en el
        historial ANTES de sobrescribir (trazabilidad de la re-auditoría).
        """
        d = acta.como_dict()
        d["necesita_revision"] = 1 if acta.necesita_revision else 0
        existente = self.con.execute(
            "SELECT * FROM actas WHERE codigo_mesa = ? AND fuente = ?",
            (acta.codigo_mesa, acta.fuente),
        ).fetchone()
        if existente is not None:
            d["verificado_manualmente"] = existente["verificado_manualmente"]
            d["notas_verificacion"] = existente["notas_verificacion"]
            self._archivar(existente)
        valores = [d.get(c) for c in _TODAS]
        marcadores = ",".join("?" for _ in _TODAS)
        cols = ",".join(_TODAS)
        self.con.execute(
            f"INSERT OR REPLACE INTO actas ({cols}) VALUES ({marcadores})", valores
        )
        self.con.commit()

    def marcar_verificado(self, codigo_mesa: str, fuente: str,
                          verificado: bool = True, nota: str | None = None) -> bool:
        """Marca/desmarca la verificación manual de una fila ya existente.

        Devuelve False si (codigo_mesa, fuente) no existe en la base.
        """
        cur = self.con.execute(
            "UPDATE actas SET verificado_manualmente = ?, notas_verificacion = ? "
            "WHERE codigo_mesa = ? AND fuente = ?",
            (1 if verificado else 0, nota, codigo_mesa, fuente),
        )
        self.con.commit()
        return cur.rowcount > 0

    def leer_por_fuente(self, fuente: str) -> dict[str, dict]:
        """{codigo_mesa: fila_dict} para una fuente."""
        cur = self.con.execute("SELECT * FROM actas WHERE fuente = ?", (fuente,))
        return {row["codigo_mesa"]: dict(row) for row in cur.fetchall()}

    def todas_las_filas(self) -> list[dict]:
        """Todas las filas de `actas`, sin filtrar por fuente (para mergear entre bases)."""
        cur = self.con.execute("SELECT * FROM actas")
        return [dict(row) for row in cur.fetchall()]

    def mesas(self) -> list[str]:
        cur = self.con.execute("SELECT DISTINCT codigo_mesa FROM actas ORDER BY codigo_mesa")
        return [r["codigo_mesa"] for r in cur.fetchall()]

    def historial(self, codigo_mesa: str, fuente: str) -> list[dict]:
        """Versiones anteriores de una mesa/fuente, de la más vieja a la más nueva."""
        cur = self.con.execute(
            "SELECT * FROM actas_historial WHERE codigo_mesa = ? AND fuente = ? "
            "ORDER BY version",
            (codigo_mesa, fuente),
        )
        return [dict(row) for row in cur.fetchall()]

    def num_versiones(self, codigo_mesa: str, fuente: str) -> int:
        """Cuántas versiones anteriores hay archivadas (0 = nunca se re-auditó)."""
        cur = self.con.execute(
            "SELECT COUNT(*) FROM actas_historial WHERE codigo_mesa = ? AND fuente = ?",
            (codigo_mesa, fuente),
        )
        return cur.fetchone()[0]

    def cerrar(self) -> None:
        self.con.close()
