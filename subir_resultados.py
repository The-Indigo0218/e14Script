"""
SCRIPT: sube tu actas.db local a Drive y registra un resumen en el panel
maestro de Google Sheets, para que el equipo vea qué se auditó y lo apruebe.

No mergea nada por sí mismo: solo sube el archivo y agrega una fila con
estado "Pendiente" en la hoja "Panel". La fusión a la base maestra la hace
`consolidar_resultados.py`, y SOLO de las filas que alguien marque "Aprobado"
a mano en la hoja (edición normal de Sheets, en tiempo real).

Primera vez: ver README → "Traer los E-14 desde Google Drive" / "Centralizar
resultados" para crear drive_credentials.json y la hoja de cálculo maestra.

Uso:
    python subir_resultados.py actas.db --persona "juan" \
        --carpeta-drive <ID_CARPETA_RESULTADOS> --hoja <ID_HOJA_MAESTRA> \
        [--municipio 1] [--zona 1] [--puesto 1]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from e14.almacen import Almacen
from e14.comparador import comparar, resumen
from e14.modelo import FUENTE_REGISTRADURIA, FUENTE_TESTIGO
from e14.ocr import UMBRAL_REVISION


def _slug(texto: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in texto.strip().lower()).strip("_")


def resumen_local(ruta_db: str) -> dict:
    """Resumen de comparación + cantidad de casillas con confianza baja, leyendo la DB local."""
    alm = Almacen(ruta_db)
    testigo = alm.leer_por_fuente(FUENTE_TESTIGO)
    registraduria = alm.leer_por_fuente(FUENTE_REGISTRADURIA)
    alm.cerrar()
    comparaciones = comparar(testigo, registraduria)
    r = resumen(comparaciones)
    r["confianza_baja"] = sum(
        1 for fila in list(testigo.values()) + list(registraduria.values())
        if fila.get("confianza") is not None and fila["confianza"] < UMBRAL_REVISION
    )
    return r


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("db", help="Base SQLite local a subir (ej. actas.db)")
    p.add_argument("--persona", required=True, help="Tu nombre (identifica la fila en el panel)")
    p.add_argument("--carpeta-drive", required=True, help="ID de la carpeta de resultados en Drive")
    p.add_argument("--hoja", required=True, help="ID de la hoja de cálculo maestra (de su URL)")
    p.add_argument("--municipio", default="")
    p.add_argument("--zona", default="")
    p.add_argument("--puesto", default="")
    p.add_argument("--credenciales", default="drive_credentials.json")
    p.add_argument("--token", default=".drive_token.json")
    args = p.parse_args(argv)

    if not Path(args.db).exists():
        print(f"Error: no existe la base {args.db}", file=sys.stderr)
        return 1

    r = resumen_local(args.db)
    print(f"Resumen local: {r['total']} mesas · {r['COINCIDE']} coinciden · "
          f"{r['DISCREPANCIA']} discrepancia · {r['confianza_baja']} casillas confianza baja")

    from e14.drive import autenticar, construir_servicio as construir_drive, subir_archivo
    from e14.sheets import agregar_fila, asegurar_encabezado, construir_servicio as construir_sheets

    try:
        creds = autenticar(args.credenciales, args.token)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    drive = construir_drive(creds)
    sheets = construir_sheets(creds)

    nombre_archivo = f"{_slug(args.persona)}.db"
    print(f"Subiendo {args.db} -> Drive/{nombre_archivo} ...")
    archivo_id = subir_archivo(drive, args.db, args.carpeta_drive, nombre_archivo)
    print(f"   ✓ Subido (id Drive: {archivo_id})")

    asegurar_encabezado(sheets, args.hoja)
    fila = [
        args.persona, datetime.now().strftime("%Y-%m-%d %H:%M"),
        args.municipio, args.zona, args.puesto,
        r["total"], r["COINCIDE"], r["DISCREPANCIA"], r["confianza_baja"],
        archivo_id, "", "Pendiente",
    ]
    agregar_fila(sheets, args.hoja, fila)
    print("   ✓ Fila agregada al panel maestro (estado: Pendiente de aprobación)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
