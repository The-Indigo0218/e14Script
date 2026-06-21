#!/usr/bin/env python3
"""
Pase de TESTIGOS idempotente — pensado para el día de elección.

Mientras llegan los E-14 de la Registraduría (hay un rango de ~2 h tras cerrar
urnas), los testigos sí están disponibles de inmediato. Este script OCRea los
testigos que vas pegando en `datos/.../testigos/` y **ignora los que ya están
cargados** en la base, así lo podés correr una y otra vez sin re-gastar OCR.

Independiente del catálogo y de la Registraduría: es solo la lectura de votos
de los testigos (fuente='testigo'). La comparación contra la Registraduría se
hace después con `auditar.py` cuando lleguen las actas oficiales.

Uso:
    python procesar_testigos.py                 # una pasada sobre datos/**/testigos
    python procesar_testigos.py --vigilar        # bucle: re-escanea cada 20 s
    python procesar_testigos.py --vigilar 10 --paralelo 4 --recortar-votos
    python procesar_testigos.py -d datos --db actas.db [--tipo delegados] [--reauditar]

Escanea `datos/testigos/` y `datos/<NN_municipio>/testigos/`. El código de cada
mesa se deriva del nombre del archivo (`NuMunicipio_zona_puesto_mesa_testigo.ext`)
y se normaliza igual que en el catálogo, así el dedup casa con la base.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from e14.almacen import Almacen
from e14.mesa import mapa_codigo_archivo
from e14.modelo import FUENTE_TESTIGO
from auditar import _lector_real   # reusa el pipeline real (Capa 1 + OCR)

CARPETA_DEFECTO = "datos"


def carpetas_testigos(base: Path) -> list[Path]:
    """Carpetas 'testigos' bajo `base`: datos/testigos y datos/<municipio>/testigos."""
    res: list[Path] = []
    raiz = base / "testigos"
    if raiz.is_dir():
        res.append(raiz)
    res.extend(sorted(p for p in base.glob("*/testigos") if p.is_dir()))
    return res


def pendientes(base: Path, ya: set[str], reauditar: bool) -> tuple[list[tuple[str, Path]], int]:
    """(codigo, ruta) de testigos NO cargados aún; cuenta de saltados (ya cargados)."""
    tareas: list[tuple[str, Path]] = []
    saltadas = 0
    vistos: set[str] = set()
    for carpeta in carpetas_testigos(base):
        for codigo, ruta in mapa_codigo_archivo(carpeta).items():
            if codigo in vistos:
                continue
            vistos.add(codigo)
            if codigo in ya and not reauditar:
                saltadas += 1
                continue
            tareas.append((codigo, ruta))
    return tareas, saltadas


def procesar_una_pasada(base: Path, alm: Almacen, lector, *,
                        reauditar: bool = False, paralelo: int = 1) -> dict:
    """Lee y guarda los testigos pendientes. Devuelve conteos de la pasada."""
    ya = set(alm.leer_por_fuente(FUENTE_TESTIGO))
    tareas, saltadas = pendientes(base, ya, reauditar)
    res = {"nuevas": 0, "saltadas": saltadas, "errores": 0, "pendientes": len(tareas)}

    def _guardar(acta, codigo: str) -> None:
        alm.guardar(acta)
        res["nuevas"] += 1
        estado = "REVISAR" if acta.necesita_revision else "OK"
        conf = f"{acta.confianza:.0%}" if acta.confianza is not None else "—"
        print(f"  {codigo}: confianza={conf} -> {estado}")

    if paralelo <= 1:
        for codigo, ruta in tareas:
            try:
                _guardar(lector(ruta, FUENTE_TESTIGO, codigo), codigo)
            except Exception as e:  # noqa: BLE001 — un acta mala no tumba la pasada
                res["errores"] += 1
                print(f"  ⚠ error {ruta.name}: {e}", file=sys.stderr)
    else:
        with ThreadPoolExecutor(max_workers=paralelo) as ex:
            futuros = {ex.submit(lector, ruta, FUENTE_TESTIGO, codigo): codigo
                       for codigo, ruta in tareas}
            for fut in as_completed(futuros):
                codigo = futuros[fut]
                try:
                    _guardar(fut.result(), codigo)   # guardar siempre en hilo principal
                except Exception as e:  # noqa: BLE001
                    res["errores"] += 1
                    print(f"  ⚠ error {codigo}: {e}", file=sys.stderr)
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--datos", "-d", default=CARPETA_DEFECTO,
                   help="Carpeta base (por defecto: datos)")
    p.add_argument("--db", default="actas.db", help="Base SQLite (por defecto: actas.db)")
    p.add_argument("--paralelo", type=int, default=1,
                   help="Lecturas OCR en paralelo (la espera de la API es lo lento)")
    p.add_argument("--tipo", help="Copia del E-14 del testigo (claveros|delegados|transmision)")
    p.add_argument("--recortar-votos", action="store_true",
                   help="Recortar a la región de votación antes del OCR (ahorra tokens)")
    p.add_argument("--reauditar", action="store_true",
                   help="Re-procesar también los testigos ya cargados (archiva versión previa)")
    p.add_argument("--solo-pagina-1", action="store_true",
                   help="Solo la página de candidatos/totales")
    p.add_argument("--vigilar", nargs="?", type=int, const=20, default=None,
                   metavar="SEG",
                   help="Bucle: re-escanea cada SEG segundos (default 20) y procesa "
                        "solo lo nuevo. Ctrl-C para parar.")
    args = p.parse_args(argv)

    base = Path(args.datos)
    if not base.exists():
        print(f"❌ No existe la carpeta de datos: {base}", file=sys.stderr)
        return 1

    layouts = ["acta_completa"] if args.solo_pagina_1 else None
    lector = _lector_real(args.tipo, layouts,
                          recortar_votos=True if args.recortar_votos else None)
    alm = Almacen(args.db)
    try:
        if args.vigilar is None:
            r = procesar_una_pasada(base, alm, lector,
                                    reauditar=args.reauditar, paralelo=args.paralelo)
            print(f"\n✅ nuevas={r['nuevas']}  ya cargadas (saltadas)={r['saltadas']}  "
                  f"errores={r['errores']}")
        else:
            print(f"👀 Vigilando {base}/**/testigos cada {args.vigilar}s (Ctrl-C para parar).")
            print("   Pegá carpetas de testigos y se procesan solas; las ya cargadas se ignoran.\n")
            try:
                while True:
                    r = procesar_una_pasada(base, alm, lector,
                                            reauditar=args.reauditar, paralelo=args.paralelo)
                    if r["nuevas"] or r["errores"]:
                        print(f"  → ciclo: nuevas={r['nuevas']}  errores={r['errores']}  "
                              f"(ya cargadas={r['saltadas']})")
                    time.sleep(args.vigilar)
            except KeyboardInterrupt:
                print("\n⏹  Vigilancia detenida.")
    finally:
        alm.cerrar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
