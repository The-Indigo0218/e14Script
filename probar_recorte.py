#!/usr/bin/env python3
"""
Banco de pruebas: recortar la región de votación antes del OCR para ahorrar
tokens y leer más enfocado (idea "cortar todo lo que no sean los candidatos y
los votos en blanco/nulos/no marcados").

Como tras alinear el folio queda en coordenadas fijas de la plantilla, un
recuadro (ROI) en fracciones cae siempre sobre la misma zona. Este script:

  1. Alinea el E-14 contra la plantilla (Capa 1, gratis, local).
  2. Genera 3 variantes de imagen y las guarda en debug/ para ver a ojo:
       P1 baseline  -> hoja completa alineada (lo de hoy)        ~100% px
       P2 recorte   -> solo región de votación, escala 1.5x      ~ 39% px
       P3 recorte+  -> misma región, escala 2.5x (dígitos grandes)
  3. Estima tokens de visión (Gemini cuenta por tiles de 768x768).
  4. Si hay una API key configurada (.env / entorno), corre el OCR sobre cada
     variante y compara contra la verdad conocida (--verdad), reportando
     aciertos y confianza. Sin clave, solo hace 1+2+3.

Uso:
  python probar_recorte.py datos/01_cartagena/testigos/1_1_3_2_testigo.png \
      --formulario 2022 --verdad 89,90,2,2,0,183

ROIs calibrados (x0,y0,x1,y1 en fracciones de la imagen alineada):
  • 2022  -> formulario 2ª vuelta 2022 (Hernández/Petro), datos de prueba.
  • 2026  -> plantilla oficial 2ª vuelta 2026 (producción). Provisional:
            re-verificar cuando lleguen actas reales 2026.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2

# Importar e14.ocr ya fuerza IPv4 (evita el timeout de ~30s por IPv6 roto).

from e14.alineacion import Alineador, LAYOUT_ACTA_COMPLETA, columnas_de_layout
from e14.lectura import cargar_paginas
from e14.preprocess import mejorar_para_ocr, recortar_region
from e14.ocr import crear_backend

PLANTILLA = "plantillas/muestra-formulario-e14-segunda-vuelta.pdf"

# ROI de la región de votación (candidatos + blanco/nulos/no_marcados + total),
# cortando cabecera, nivelación y constancias/firmas (cédulas de jurados).
ROI_VOTOS = {
    "2022": (0.0, 0.27, 1.0, 0.665),
    "2026": (0.0, 0.36, 1.0, 0.885),
}

COLS = columnas_de_layout(LAYOUT_ACTA_COMPLETA)  # c1,c2,blanco,nulos,no_marcados,suma_total


def tokens_vision_gemini(img) -> int:
    """Aprox tokens de imagen en Gemini: tiles de 768x768, ~258 tokens c/u."""
    h, w = img.shape[:2]
    tiles = math.ceil(w / 768) * math.ceil(h / 768)
    return tiles * 258


def png_bytes(img) -> int:
    ok, buf = cv2.imencode(".png", img)
    return int(buf.nbytes) if ok else 0


def construir_variantes(alineada, roi):
    recorte = recortar_region(alineada, roi)
    return {
        "P1_baseline":   mejorar_para_ocr(alineada, escala=1.5),
        "P2_recorte":    mejorar_para_ocr(recorte, escala=1.5),
        "P3_recorte_2.5x": mejorar_para_ocr(recorte, escala=2.5),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acta", help="ruta al E-14 (PDF o imagen)")
    ap.add_argument("--formulario", choices=sorted(ROI_VOTOS), default="2022",
                    help="qué ROI usar (default 2022 = datos de prueba)")
    ap.add_argument("--plantilla", default=PLANTILLA)
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--verdad", default="",
                    help="votos reales c1,c2,blanco,nulos,no_marcados,suma_total")
    ap.add_argument("--salida", default="debug/recorte")
    args = ap.parse_args()

    verdad = {}
    if args.verdad:
        vals = [int(x) for x in args.verdad.split(",")]
        verdad = dict(zip(COLS, vals))

    Path(args.salida).mkdir(parents=True, exist_ok=True)

    print(f"Alineando {args.acta} contra {args.plantilla} ...")
    ali = Alineador(args.plantilla, dpi=args.dpi)
    pags = cargar_paginas(args.acta, dpi=args.dpi)
    resultados = ali.alinear_paginas(pags, solo_layouts=[LAYOUT_ACTA_COMPLETA])
    mejor = max(resultados, key=lambda r: r.inliers, default=None)
    if mejor is None or mejor.imagen_alineada is None:
        print("✗ No se pudo alinear el acta.")
        return
    print(f"  inliers={mejor.inliers}  confiable={mejor.confiable}  "
          f"alineada={mejor.imagen_alineada.shape[1]}x{mejor.imagen_alineada.shape[0]}")
    if not mejor.confiable:
        print("  ⚠ Alineación poco confiable: el recorte podría caer mal "
              "(en producción conviene NO recortar si no es confiable).")

    roi = ROI_VOTOS[args.formulario]
    variantes = construir_variantes(mejor.imagen_alineada, roi)

    base_tokens = tokens_vision_gemini(variantes["P1_baseline"])
    print(f"\n{'variante':<18}{'dims':>12}{'px':>10}{'PNG KB':>9}"
          f"{'~tokens':>9}{'vs base':>9}")
    for nombre, img in variantes.items():
        h, w = img.shape[:2]
        ruta = f"{args.salida}/{nombre}.png"
        cv2.imwrite(ruta, img)
        tk = tokens_vision_gemini(img)
        print(f"{nombre:<18}{f'{w}x{h}':>12}{w*h:>10}{png_bytes(img)//1024:>9}"
              f"{tk:>9}{f'{tk/base_tokens:.0%}':>9}")
    print(f"\nImágenes guardadas en {args.salida}/ (revisá a ojo el recorte).")

    backend = crear_backend()
    if backend.nombre == "manual":
        print("\nSin API key (.env vacío): omito el OCR. Cargá una clave "
              "(GEMINI_API_KEY / OPENROUTER_API_KEY) para correr la lectura.")
        return

    print(f"\n=== OCR con backend '{backend.nombre}' ===")
    if verdad:
        print("verdad:", {k: verdad[k] for k in COLS})
    for nombre, img in variantes.items():
        lec = backend.reconocer_votos(img, LAYOUT_ACTA_COMPLETA)
        leido = {c: lec.valores.get(c) for c in COLS}
        linea = f"{nombre:<18} {leido}  conf={lec.confianza_global:.2f}"
        if verdad:
            aciertos = sum(1 for c in COLS if leido.get(c) == verdad.get(c))
            linea += f"  aciertos={aciertos}/{len(COLS)}"
        print(linea)
        if lec.notas:
            print(f"   nota: {lec.notas}")


if __name__ == "__main__":
    main()
