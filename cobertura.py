"""
SCRIPT: cobertura de auditoría a partir del catálogo (Excel de la Registraduría).

Responde "¿cuántas mesas del universo oficial tenemos listas para auditar?",
por municipio (lote). No procesa actas ni gasta OCR: solo lee nombres de archivo.

Uso:
    # Tablero de TODO el departamento (una línea por municipio):
    python cobertura.py "<ruta>/Bolivar_Mesa_Mesa_2026 Presidencial.xlsx"

    # Detalle de un lote (municipio), creando sus carpetas si faltan:
    python cobertura.py "<ruta>/...xlsx" --municipio 1 --crear-carpetas

    # Acotar a una zona (o zona+puesto) antes de auditarla — nunca puesto sin zona:
    python cobertura.py "<ruta>/...xlsx" --municipio 1 --zona 1
    python cobertura.py "<ruta>/...xlsx" --municipio 1 --zona 1 --puesto 1

    # Cambiar la carpeta base de datos (por defecto: datos/):
    python cobertura.py "<ruta>/...xlsx" --municipio 1 --datos datos
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from e14.catalogo import cargar_catalogo, crear_estructura_lote
from e14.cobertura import cobertura_lote


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("excel", help="Ruta al Excel 'Mesa a Mesa' de la Registraduría")
    p.add_argument("--municipio", "-m", help="Código MUN del lote (ej. 1). Sin esto, muestra el tablero completo.")
    p.add_argument("--zona", help="Acotar a esta zona dentro del municipio (requiere --municipio)")
    p.add_argument("--puesto", help="Acotar a este puesto dentro de la zona (requiere --zona)")
    p.add_argument("--datos", "-d", default="datos", help="Carpeta base de datos (por defecto: datos)")
    p.add_argument("--crear-carpetas", action="store_true", help="Crear las carpetas del lote si no existen")
    args = p.parse_args(argv)

    if args.puesto is not None and args.zona is None:
        print("Error: --puesto requiere --zona (no se puede filtrar por puesto solo).", file=sys.stderr)
        return 1
    if args.zona is not None and not args.municipio:
        print("Error: --zona requiere --municipio.", file=sys.stderr)
        return 1

    try:
        catalogo = cargar_catalogo(args.excel)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Departamento {catalogo.departamento} · {catalogo.departamento_nombre} "
          f"· {len(catalogo.municipios())} municipios · {catalogo.total_mesas()} mesas\n")

    if args.municipio:
        if args.crear_carpetas:
            lote = crear_estructura_lote(args.datos, catalogo, args.municipio)
            print(f"Carpetas del lote listas en: {lote}\n")
        print(cobertura_lote(catalogo, args.municipio, args.datos, zona=args.zona, puesto=args.puesto).texto())
        return 0

    # Tablero: una línea por municipio.
    print(f"{'MUN':>4}  {'Municipio':<26}{'Universo':>9}{'Listas':>8}{'Falta':>8}")
    print("-" * 63)
    for mun in catalogo.municipios():
        cob = cobertura_lote(catalogo, mun, args.datos)
        r = cob.resumen()
        falta = r["esperadas"] - r["listas"]
        print(f"{mun:>4}  {cob.municipio_nombre[:26]:<26}{r['esperadas']:>9}{r['listas']:>8}{falta:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
