"""
Validación LOCAL (sin API): Capa 1 solamente.

Endereza el PDF contra la plantilla, reporta calidad (inliers) y guarda imagen
de depuración. Sirve para probar instalación y escaneos sin gastar cuota Gemini.

Uso:
    python validar_alineacion.py datos/registraduria/21_01_13_registraduria.pdf
    python validar_alineacion.py datos/testigos/21_01_13_testigo.pdf --solo-pagina-1
"""

import sys
from pathlib import Path

import cv2

from e14.alineacion import Alineador, LAYOUT_ACTA_COMPLETA
from e14.lectura import cargar_paginas
from e14.mesa import codigo_mesa_desde_archivo, etiqueta_mesa
from e14.preprocess import mejorar_para_ocr

PLANTILLA = "plantillas/muestra-formulario-e14-segunda-vuelta.pdf"
SALIDA_DIR = Path("debug")


def main():
    layouts = None
    entrada: Path | None = None
    for a in sys.argv[1:]:
        if a in ("--solo-pagina-1", "--solo-p1"):
            layouts = [LAYOUT_ACTA_COMPLETA]
        elif not a.startswith("-") and entrada is None:
            entrada = Path(a)
    if entrada is None:
        entrada = Path("datos/registraduria/21_01_13_registraduria.pdf")
    if not entrada.exists():
        print(f"❌ No existe: {entrada}")
        sys.exit(1)
    if not Path(PLANTILLA).exists():
        print(f"❌ Falta plantilla: {PLANTILLA}")
        sys.exit(1)

    codigo = codigo_mesa_desde_archivo(entrada)
    paginas = cargar_paginas(entrada)
    if layouts and len(paginas) > 1:
        paginas = paginas[:1]

    print(f"🔧 Modo local (sin OCR / sin API)")
    print(f"   Archivo: {entrada}")
    print(f"   Mesa:    {codigo}  ({etiqueta_mesa(codigo)})")
    print(f"   Páginas: {len(paginas)}")
    if layouts:
        print(f"   Layout:  solo {layouts[0]}\n")
    else:
        print()

    alineador = Alineador(PLANTILLA, dpi=150)
    SALIDA_DIR.mkdir(exist_ok=True)
    ok = 0

    for r in alineador.alinear_paginas(paginas, solo_layouts=layouts):
        h, w = paginas[r.indice_pagina - 1].shape[:2]
        print(f"  Pág {r.indice_pagina}: original {w}×{h} px")
        print(f"    layout={r.layout_id or '—'}  inliers={r.inliers}  "
              f"{'✅ confiable' if r.confiable else '⚠️ revisar'}")
        if r.imagen_alineada is None:
            print("    ❌ No se pudo alinear")
            continue
        ah, aw = r.imagen_alineada.shape[:2]
        base = SALIDA_DIR / f"{codigo}_p{r.indice_pagina}_{r.layout_id or 'sin_layout'}"
        cv2.imwrite(str(base.with_suffix(".png")), r.imagen_alineada)
        cv2.imwrite(str(base.with_name(base.name + "_ocr").with_suffix(".png")),
                    mejorar_para_ocr(r.imagen_alineada))
        print(f"    💾 debug/{base.name}.png")
        if r.confiable:
            ok += 1

    print()
    if ok:
        print(f"✅ {ok} página(s) alineada(s) con calidad suficiente para OCR.")
        print("   Siguiente paso (cuando tengas cuota API):")
        print(f"   python leer_registraduria.py {entrada} actas.db --solo-pagina-1")
    else:
        print("⚠️  Ninguna página pasó el umbral de inliers. Revise el escaneo o la plantilla.")


if __name__ == "__main__":
    main()
