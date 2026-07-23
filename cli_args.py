"""
Parseo de argumentos común para los lectores (testigos / registraduría).

Formato:
    <script> [entrada] [actas.db] [--codigo MESA] [--tipo claveros|delegados|transmision]
              [--solo-pagina-1]

  • entrada : archivo o carpeta (PDF/CSV). Si no se da, usa la carpeta por defecto.
  • actas.db: cualquier posicional que termine en .db (o el 2º posicional).
  • --codigo: fuerza el código de mesa (solo si la entrada es un único archivo).
  • --tipo  : de qué COPIA del E-14 viene (claveros, delegados, transmisión).
  • --solo-pagina-1 : solo la página de candidatos/totales, sin firmas
                       (1 llamada OCR por acta; evita procesar la hoja de firmas).
  • --paralelo N : N lecturas OCR en paralelo (la espera de la API es lo lento;
                    combinar con varias claves en GEMINI_API_KEYS multiplica el
                    cupo efectivo — ver e14/ocr.py:BackendGeminiMultiKey).
  • --forzar : reprocesa TODO aunque ya esté guardado y OK (gasta cuota/saldo
               de nuevo). Sin esto, las mesas ya guardadas y sin necesita_revision
               se saltan — solo se (re)leen las nuevas y las que quedaron en REVISAR.
"""

from __future__ import annotations

import sys
from pathlib import Path

from e14.alineacion import LAYOUT_ACTA_COMPLETA


def parsear_args(carpeta_defecto: str, tipo_defecto: str | None = None):
    entrada: Path | None = None
    db = "actas.db"
    codigo: str | None = None
    tipo: str | None = tipo_defecto
    solo_pagina_1 = False
    paralelo = 1
    forzar = False

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
        elif a == "--paralelo" and i + 1 < len(args):
            paralelo = int(args[i + 1])
            i += 2
        elif a in ("--solo-pagina-1", "--solo-p1"):
            solo_pagina_1 = True
            i += 1
        elif a == "--forzar":
            forzar = True
            i += 1
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

    layouts = [LAYOUT_ACTA_COMPLETA] if solo_pagina_1 else None
    return entrada, db, codigo, tipo, layouts, solo_pagina_1, paralelo, forzar
