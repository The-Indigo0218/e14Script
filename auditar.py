"""
SCRIPT: auditoría de un LOTE (municipio) de punta a punta.

Orquesta el flujo completo sobre las mesas de un municipio, sin reescribir lógica:
  1. Lee el catálogo (Excel) y calcula la cobertura del lote.
  2. Selecciona las mesas LISTAS (testigo + registraduría presentes).
  3. Lee cada par con el pipeline existente (Capa 1 + OCR) y lo guarda en la DB,
     usando el código canónico NuMunicipio-zona-puesto-mesa.
  4. Compara testigo vs oficial (solo las mesas del lote) y genera el Excel.

Por defecto NO reprocesa mesas ya leídas (ahorra OCR); usa --reauditar para forzar.
`--limite N` procesa solo las primeras N (control de volumen / costo en una instancia).
`--paralelo N` lee N actas a la vez (varios hilos llamando a Gemini en simultáneo)
para acelerar el lote; el guardado en SQLite siempre es secuencial (un hilo a la
vez), así que es seguro. Default 1 (secuencial, igual que antes). Si ves muchos
errores 429, bajá el número; Google AI Studio muestra tu límite real de RPM en
https://aistudio.google.com/rate-limit.

`--zona`/`--puesto` acotan el lote dentro del municipio (jerarquía
municipio→zona→puesto, nunca se admite puesto sin zona: el número de puesto se
repite en muchas zonas distintas). Útil para repartir un municipio grande en
bloques de trabajo (por zona) o apuntar a un lugar de votación puntual (zona +
puesto).

`--verificar-baja-confianza` activa la doble lectura con GPT (requiere
OPENAI_API_KEY), pero SOLO para esa corrida y solo en las casillas con
confianza < 80% — apagado salvo que se pida explícitamente con este flag (o
con OCR_VERIFICAR_BAJA_CONFIANZA=1 en .env si se prefiere dejarlo siempre
prendido).

Uso:
    python auditar.py "<excel>" --municipio 1 [--zona N [--puesto N]]
        [--datos datos] [--db actas.db] [--salida comparacion_lote.xlsx]
        [--limite N] [--reauditar] [--paralelo N] [--verificar-baja-confianza]
        [--tipo-testigo claveros|delegados|transmision] [--solo-pagina-1] [--plan]
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from e14.almacen import Almacen
from e14.catalogo import cargar_catalogo, nombre_carpeta_lote
from e14.cobertura import Cobertura, cobertura_lote
from e14.mesa import filtrar_por_zona_puesto, mapa_codigo_archivo
from e14.modelo import ActaE14, FUENTE_TESTIGO, FUENTE_REGISTRADURIA, TIPO_DELEGADOS

# Tipo del lector inyectable: (ruta, fuente, codigo_canonico) -> ActaE14
Lector = Callable[[Path, str, str], ActaE14]


def seleccionar_mesas(cobertura: Cobertura, incluir_parciales: bool = False, *,
                      zona: str | int | None = None,
                      puesto: str | int | None = None) -> list[str]:
    """
    Códigos de mesa a auditar (ordenados). Por defecto solo las LISTAS (ambas
    fuentes). Con `incluir_parciales` agrega las que tienen una sola fuente.

    `zona`/`puesto` acotan el lote a una zona (o a un puesto dentro de esa
    zona) del municipio — ver `filtrar_por_zona_puesto` (nunca admite puesto
    sin zona).
    """
    mesas = set(cobertura.listas)
    if incluir_parciales:
        mesas |= cobertura.solo_testigo | cobertura.solo_registraduria
    return filtrar_por_zona_puesto(mesas, zona, puesto)


def procesar_lote(catalogo, municipio: str | int, base_datos: str | Path,
                  alm: Almacen, lector: Lector, *,
                  reauditar: bool = False, limite: int | None = None,
                  incluir_parciales: bool = False, paralelo: int = 1,
                  zona: str | int | None = None, puesto: str | int | None = None) -> dict:
    """
    Lee y guarda las mesas seleccionadas del lote. Devuelve un resumen de conteos.
    No genera el Excel (eso lo hace el caller) para mantenerlo testeable sin OCR.

    `paralelo` > 1 lee varias actas a la vez (hilos) — útil porque cada lectura
    pasa la mayor parte del tiempo esperando la respuesta de la API de OCR. El
    guardado en la base (`alm.guardar`) siempre ocurre en el hilo principal, uno
    a la vez, así que no hay riesgo de escritura concurrente en SQLite.

    `zona`/`puesto` acotan el lote (ver `seleccionar_mesas`).
    """
    cob = cobertura_lote(catalogo, municipio, base_datos)
    lote = Path(base_datos) / nombre_carpeta_lote(catalogo, municipio)
    archivos_t = mapa_codigo_archivo(lote / "testigos")
    archivos_r = mapa_codigo_archivo(lote / "registraduria")

    ya_t = set(alm.leer_por_fuente(FUENTE_TESTIGO))
    ya_r = set(alm.leer_por_fuente(FUENTE_REGISTRADURIA))

    seleccion = seleccionar_mesas(cob, incluir_parciales, zona=zona, puesto=puesto)
    res = {"seleccionadas": len(seleccion), "leidas": 0, "saltadas": 0, "errores": 0}

    # ── Paso 1: decidir QUÉ actas hay que leer (sin tocar la red ni el OCR aún) ──
    tareas: list[tuple[str, str, Path]] = []  # (codigo, fuente, ruta)
    procesadas = 0
    for codigo in seleccion:
        if limite is not None and procesadas >= limite:
            break
        fuentes = [
            (FUENTE_TESTIGO, archivos_t.get(codigo), ya_t),
            (FUENTE_REGISTRADURIA, archivos_r.get(codigo), ya_r),
        ]
        # Si ya están ambas presentes en DB y no se fuerza, saltar la mesa entera.
        presentes_db = all(codigo in ya for _, ruta, ya in fuentes if ruta is not None)
        tiene_archivos = any(ruta is not None for _, ruta, _ in fuentes)
        if tiene_archivos and presentes_db and not reauditar:
            res["saltadas"] += 1
            continue

        procesadas += 1
        for fuente, ruta, ya in fuentes:
            if ruta is None:
                continue
            if codigo in ya and not reauditar:
                continue
            tareas.append((codigo, fuente, ruta))

    # ── Paso 2: leer (en paralelo o no) y guardar siempre en el hilo principal ──
    if paralelo <= 1:
        for codigo, fuente, ruta in tareas:
            _leer_y_guardar(lector, alm, codigo, fuente, ruta, res)
    else:
        with ThreadPoolExecutor(max_workers=paralelo) as ex:
            futuros = {
                ex.submit(lector, ruta, fuente, codigo): (codigo, fuente, ruta)
                for codigo, fuente, ruta in tareas
            }
            for fut in as_completed(futuros):
                codigo, fuente, ruta = futuros[fut]
                try:
                    acta = fut.result()
                    alm.guardar(acta)
                    res["leidas"] += 1
                except Exception as e:  # noqa: BLE001 — un acta mala no debe tumbar el lote
                    res["errores"] += 1
                    print(f"  ⚠ error leyendo {ruta.name}: {e}", file=sys.stderr)
    return res


def _leer_y_guardar(lector: Lector, alm: Almacen, codigo: str, fuente: str,
                    ruta: Path, res: dict) -> None:
    try:
        acta = lector(ruta, fuente, codigo)
        alm.guardar(acta)
        res["leidas"] += 1
    except Exception as e:  # noqa: BLE001 — un acta mala no debe tumbar el lote
        res["errores"] += 1
        print(f"  ⚠ error leyendo {ruta.name}: {e}", file=sys.stderr)


def _lector_real(tipo_testigo: str | None, layouts: list[str] | None,
                 verificar_baja_confianza: bool = False,
                 recortar_votos: bool | None = None) -> Lector:
    """Construye el lector con el pipeline real (Capa 1 + OCR). Importa perezoso."""
    from e14.alineacion import Alineador
    from e14.ocr import backend_por_defecto
    from e14.lectura import leer_acta_pdf

    PLANTILLA = "plantillas/muestra-formulario-e14-segunda-vuelta.pdf"
    if not Path(PLANTILLA).exists():
        print(f"❌ Falta la plantilla oficial: {PLANTILLA}", file=sys.stderr)
        sys.exit(1)
    alineador = Alineador(PLANTILLA, dpi=150)
    # verificar_baja_confianza=True SOLO si se pidió con --verificar-baja-confianza;
    # si no, None deja que decida la variable de entorno (apagado por defecto).
    ocr = backend_por_defecto(verificar_baja_confianza=True if verificar_baja_confianza else None)
    print(f"Motor OCR: {ocr.nombre}")
    if ocr.nombre == "manual":
        print("   ⚠️  OCR en modo manual: define GEMINI_API_KEY en .env para leer de verdad.")

    def lector(ruta: Path, fuente: str, codigo: str) -> ActaE14:
        tipo = tipo_testigo if fuente == FUENTE_TESTIGO else TIPO_DELEGADOS
        return leer_acta_pdf(str(ruta), alineador, ocr, fuente, codigo,
                             tipo_acta=tipo, layouts=layouts,
                             recortar_votos=recortar_votos)

    return lector


def _generar_comparacion(alm: Almacen, esperadas: set[str], salida: str) -> dict:
    """Compara solo las mesas del lote y genera el Excel. Devuelve el resumen."""
    from e14.comparador import comparar, resumen
    from comparar import generar_excel

    testigo = {k: v for k, v in alm.leer_por_fuente(FUENTE_TESTIGO).items() if k in esperadas}
    registraduria = {k: v for k, v in alm.leer_por_fuente(FUENTE_REGISTRADURIA).items() if k in esperadas}
    comparaciones = comparar(testigo, registraduria)
    generar_excel(comparaciones, salida)
    return resumen(comparaciones)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("excel", help="Ruta al Excel 'Mesa a Mesa' de la Registraduría")
    p.add_argument("--municipio", "-m", required=True, help="Código MUN del lote (ej. 1)")
    p.add_argument("--datos", "-d", default="datos", help="Carpeta base de datos (por defecto: datos)")
    p.add_argument("--db", default="actas.db", help="Base SQLite (por defecto: actas.db)")
    p.add_argument("--salida", help="Excel de salida (por defecto: comparacion_lote_<MUN>.xlsx)")
    p.add_argument("--zona", help="Acotar a esta zona dentro del municipio (ej. 1 1 = municipio 1, zona 1)")
    p.add_argument("--puesto", help="Acotar a este puesto dentro de la zona (requiere --zona; "
                                    "ej. 1 1 1 = municipio 1, zona 1, puesto 1)")
    p.add_argument("--limite", type=int, help="Procesar solo las primeras N mesas")
    p.add_argument("--paralelo", type=int, default=1,
                  help="Leer N actas a la vez en hilos (default 1 = secuencial). "
                       "Sube esto para acelerar el lote; si ves errores 429, bajalo.")
    p.add_argument("--verificar-baja-confianza", action="store_true",
                  help="Doble lectura con GPT SOLO en casillas con confianza < 80%% "
                       "(requiere OPENAI_API_KEY en .env). Apagado salvo que se pida con este flag.")
    p.add_argument("--reauditar", action="store_true", help="Reprocesar mesas ya leídas")
    p.add_argument("--incluir-parciales", action="store_true", help="Incluir mesas con una sola fuente")
    p.add_argument("--tipo-testigo", help="Copia del E-14 del testigo (claveros|delegados|transmision)")
    p.add_argument("--solo-pagina-1", action="store_true", help="Solo la página de candidatos/totales")
    p.add_argument("--recortar-votos", action="store_true",
                   help="Recortar a la región de votación antes del OCR (ahorra tokens; "
                        "solo con alineación confiable). También por OCR_RECORTAR_VOTOS=1")
    p.add_argument("--plan", action="store_true", help="Mostrar qué se procesaría y salir (sin OCR)")
    args = p.parse_args(argv)

    try:
        catalogo = cargar_catalogo(args.excel)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.puesto is not None and args.zona is None:
        print("Error: --puesto requiere --zona (no se puede filtrar por puesto solo).", file=sys.stderr)
        return 1

    cob = cobertura_lote(catalogo, args.municipio, args.datos, zona=args.zona, puesto=args.puesto)
    print(cob.texto())
    if args.zona is not None:
        print(f"  Filtro: zona {args.zona}" + (f", puesto {args.puesto}" if args.puesto is not None else ""))
    print()

    seleccion = seleccionar_mesas(cob, args.incluir_parciales)
    if args.limite is not None:
        seleccion = seleccion[: args.limite]
    if not seleccion:
        print("No hay mesas para auditar en este lote (faltan archivos). "
              "Coloca los PDFs en las carpetas del lote y vuelve a correr.")
        return 0

    print(f"Mesas a auditar: {len(seleccion)}"
          + (f" (límite {args.limite})" if args.limite is not None else ""))
    if args.plan:
        for c in seleccion:
            print(f"   • {c}")
        return 0

    layouts = ["acta_completa"] if args.solo_pagina_1 else None
    lector = _lector_real(args.tipo_testigo, layouts, args.verificar_baja_confianza,
                          recortar_votos=True if args.recortar_votos else None)

    alm = Almacen(args.db)
    res = procesar_lote(catalogo, args.municipio, args.datos, alm, lector,
                        reauditar=args.reauditar, limite=args.limite,
                        incluir_parciales=args.incluir_parciales,
                        paralelo=args.paralelo, zona=args.zona, puesto=args.puesto)
    print(f"\nLeídas {res['leidas']} actas · saltadas {res['saltadas']} (ya en DB) "
          f"· errores {res['errores']}")

    # cob ya viene acotado a zona/puesto si se pidió, así el Excel refleja ese
    # subconjunto y no todo el municipio (aunque la DB tenga otras mesas auditadas).
    salida = args.salida or f"comparacion_lote_{int(str(args.municipio)):02d}.xlsx"
    r = _generar_comparacion(alm, cob.esperadas, salida)
    alm.cerrar()
    print(f"\nComparación del lote → {salida}")
    print(f"   ✅ Coinciden {r['COINCIDE']} · ⛔ Discrepancia {r['DISCREPANCIA']} "
          f"· ⚠ Falta fuente {r['FALTA_FUENTE']} · ⏳ Sin lectura {r['SIN_LECTURA']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
