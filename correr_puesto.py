"""
SCRIPT: corre el reconocimiento de TODO un puesto de votación con un solo
comando interactivo — pide la nomenclatura (municipio zona puesto) y hace lo
mismo que `auditar.py --municipio M --zona Z --puesto P`, pero esta es la
pasada de SOLO VOTOS (sin KIT/CIV — eso es un pase aparte, ver
`leer_identificadores.py`), para que esta corrida sea más rápida y barata.

Uso:
    python correr_puesto.py
    (te pide: "Nomenclatura del puesto (municipio zona puesto, ej. 1 1 1): ")
    (te pide la ruta del Excel "Mesa a Mesa" — Enter usa CATALOGO_DEFECTO)

    python correr_puesto.py --paralelo 5 --db actas.db
    (los flags son opcionales; lo único que SIEMPRE se pregunta es la
    nomenclatura y el catálogo)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import auditar

# Cambiá esto si tu Excel "Mesa a Mesa" vive en otra ruta de forma permanente.
CATALOGO_DEFECTO = "catalogo/mesa_a_mesa.xlsx"


def _pedir_nomenclatura() -> tuple[str, str, str]:
    texto = input("Nomenclatura del puesto (municipio zona puesto, ej. '1 1 1'): ").strip()
    partes = texto.split()
    if len(partes) != 3 or not all(p.isdigit() for p in partes):
        print("❌ Formato inválido. Escribí 3 números separados por espacio, ej: 1 1 1")
        sys.exit(1)
    municipio, zona, puesto = partes
    return municipio, zona, puesto


def _pedir_catalogo() -> str:
    ruta = input(f"Ruta del Excel 'Mesa a Mesa' [{CATALOGO_DEFECTO}]: ").strip() or CATALOGO_DEFECTO
    if not Path(ruta).exists():
        print(f"❌ No existe el catálogo: {ruta}")
        print("   Poné ahí el Excel 'Mesa a Mesa' de la Registraduría, o escribí la ruta correcta.")
        sys.exit(1)
    return ruta


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--datos", default="datos")
    p.add_argument("--db", default="actas.db")
    p.add_argument("--paralelo", type=int, default=3,
                  help="Llamadas simultáneas (default 3; con una sola cuenta de Gemini "
                       "no conviene subir mucho más, ver --paralelo en auditar.py).")
    args = p.parse_args(argv)

    municipio, zona, puesto = _pedir_nomenclatura()
    catalogo = _pedir_catalogo()

    print(f"\n→ Corriendo puesto {municipio}-{zona}-{puesto} (solo votos, sin KIT/CIV)...\n")
    return auditar.main([
        catalogo, "--municipio", municipio, "--zona", zona, "--puesto", puesto,
        "--datos", args.datos, "--db", args.db,
        "--paralelo", str(args.paralelo), "--solo-pagina-1",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
