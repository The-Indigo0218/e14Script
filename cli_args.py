"""
Parseo de argumentos común para los lectores (testigos / registraduría).

Formato:
    <script> [entrada] [actas.db] [--codigo MESA] [--tipo claveros|delegados|transmision]

  • entrada : archivo o carpeta (PDF/CSV). Si no se da, usa la carpeta por defecto.
  • actas.db: cualquier posicional que termine en .db (o el 2º posicional).
  • --codigo: fuerza el código de mesa (solo si la entrada es un único archivo).
  • --tipo  : de qué COPIA del E-14 viene (claveros, delegados, transmisión).
"""

from __future__ import annotations

import sys
from pathlib import Path


def parsear_args(carpeta_defecto: str, tipo_defecto: str | None = None):
    entrada: Path | None = None
    db = "actas.db"
    codigo: str | None = None
    tipo: str | None = tipo_defecto

    posicionales: list[str] = []
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--codigo" and i + 1 < len(args):
            codigo = args[i + 1]
            i += 2
        elif a == "--tipo" and i + 1 < len(args):
            tipo = args[i + 1]
            i += 2
        else:
            posicionales.append(a)
            i += 1

    for p in posicionales:
        if p.endswith(".db"):
            db = p
        elif entrada is None:
            entrada = Path(p)
        else:
            db = p

    if entrada is None:
        entrada = Path(carpeta_defecto)
    return entrada, db, codigo, tipo
