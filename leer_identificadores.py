"""
SCRIPT: pasada APARTE que solo lee KIT y CIV — no vuelve a tocar los votos.

Pensado como trabajo de fondo: primero corré `correr_puesto.py` (o
`auditar.py`) para tener los votos cargados rápido y barato (sin KIT/CIV), y
cuando haya tiempo/cuota libre corré esto para completar los identificadores
de esas mismas mesas, sin competir por cuota con la lectura urgente de votos.

Re-alinea cada archivo original (Capa 1, sin costo de API) y hace UNA
llamada liviana por mesa — solo pide kit/civ, no los 6 campos de votos — así
que esta pasada es más rápida y barata por llamada que la de votos.

Uso:
    python leer_identificadores.py actas.db --municipio 1 --zona 1 --puesto 1
        [--fuente testigo|registraduria] [--paralelo 3]
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from e14.almacen import Almacen
from e14.mesa import filtrar_por_zona_puesto, municipio_zona_puesto_mesa_desde_codigo
from e14.modelo import FUENTE_REGISTRADURIA, FUENTE_TESTIGO
from e14.ocr import backend_por_defecto

PLANTILLA = "plantillas/muestra-formulario-e14-segunda-vuelta.pdf"


def _filas_del_puesto(alm: Almacen, municipio: str, zona: str | None, puesto: str | None,
                      fuente: str | None) -> list[dict]:
    municipio_norm = str(int(municipio))
    filas = []
    for f in alm.todas_las_filas():
        if fuente and f["fuente"] != fuente:
            continue
        meta = municipio_zona_puesto_mesa_desde_codigo(f["codigo_mesa"])
        if not meta or str(int(meta["municipio"])) != municipio_norm:
            continue
        filas.append(f)
    if zona is not None:
        codigos_ok = set(filtrar_por_zona_puesto([f["codigo_mesa"] for f in filas], zona, puesto))
        filas = [f for f in filas if f["codigo_mesa"] in codigos_ok]
    return filas


def _imagen_alineada(archivo_origen: str, alineador):
    from e14.lectura import cargar_paginas
    from e14.preprocess import mejorar_para_ocr

    paginas = cargar_paginas(archivo_origen, dpi=alineador.dpi)
    if not paginas:
        return None
    for r in alineador.alinear_paginas(paginas[:1]):
        if r.imagen_alineada is not None:
            return mejorar_para_ocr(r.imagen_alineada, escala=1.5)
    return None


def _leer_una(fila: dict, alineador, ocr) -> dict:
    """Hace el trabajo de red/alineación (paralelizable); NO toca la DB."""
    codigo, fuente = fila["codigo_mesa"], fila["fuente"]
    archivo = fila.get("archivo_origen")
    if not archivo:
        return {"codigo": codigo, "fuente": fuente, "ok": False,
                "mensaje": "sin archivo_origen registrado"}
    imagen = _imagen_alineada(archivo, alineador)
    if imagen is None:
        return {"codigo": codigo, "fuente": fuente, "ok": False,
                "mensaje": "no se pudo re-alinear el archivo"}
    lectura = ocr.leer_identificadores(imagen)
    return {
        "codigo": codigo, "fuente": fuente, "ok": True,
        "numero_kit": lectura.numero_kit, "confianza_kit": lectura.confianza_kit,
        "civ": lectura.civ, "confianza_civ": lectura.confianza_civ,
        "necesita_revision": lectura.necesita_revision,
        "detalle": lectura.detalle_api or lectura.notas or "",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("db", help="Base SQLite con las mesas ya leídas (votos)")
    p.add_argument("--municipio", required=True)
    p.add_argument("--zona")
    p.add_argument("--puesto")
    p.add_argument("--fuente", choices=[FUENTE_TESTIGO, FUENTE_REGISTRADURIA],
                  help="Solo esta fuente (default: ambas)")
    p.add_argument("--paralelo", type=int, default=3,
                  help="Llamadas simultáneas (default 3).")
    args = p.parse_args(argv)

    if args.puesto is not None and args.zona is None:
        print("Error: --puesto requiere --zona.", file=sys.stderr)
        return 1
    if not Path(PLANTILLA).exists():
        print(f"❌ Falta la plantilla oficial: {PLANTILLA}", file=sys.stderr)
        return 1

    from e14.alineacion import Alineador
    alineador = Alineador(PLANTILLA, dpi=150)
    ocr = backend_por_defecto()
    print(f"Motor OCR: {ocr.nombre}")

    alm = Almacen(args.db)
    filas = _filas_del_puesto(alm, args.municipio, args.zona, args.puesto, args.fuente)
    if not filas:
        print("No hay mesas que coincidan con ese filtro en la base.")
        alm.cerrar()
        return 0
    print(f"Mesas a procesar: {len(filas)}\n")

    actualizadas = errores = 0
    with ThreadPoolExecutor(max_workers=max(1, args.paralelo)) as ex:
        futuros = [ex.submit(_leer_una, f, alineador, ocr) for f in filas]
        for fut in as_completed(futuros):
            r = fut.result()
            if not r["ok"]:
                print(f"  ⚠ {r['codigo']} ({r['fuente']}): {r['mensaje']}")
                errores += 1
                continue
            alm.actualizar_identificadores(
                r["codigo"], r["fuente"],
                numero_kit=r["numero_kit"], confianza_kit=r["confianza_kit"],
                civ=r["civ"], confianza_civ=r["confianza_civ"],
                necesita_revision=r["necesita_revision"] or None,
                nota=r["detalle"] or None,
            )
            actualizadas += 1
            marca = "⚠" if r["necesita_revision"] else "✓"
            print(f"  {marca} {r['codigo']} ({r['fuente']}): "
                  f"KIT={r['numero_kit'] or '—'} CIV={r['civ'] or '—'}")

    print(f"\nIdentificadores actualizados: {actualizadas} · errores: {errores}")
    alm.cerrar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
