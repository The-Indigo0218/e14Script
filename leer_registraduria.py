"""
SCRIPT 2 — Lector de E-14 OFICIALES (Registraduría).

Flujo:
    PDF oficial  ─►  Capa 1 (alineación por plantilla)  ─►  Capa 2 (OCR)  ─►  tabla común
                     e14/alineacion.py                     e14/ocr.py        (fuente='registraduria')

La capa 1 ya está lista y probada: alinea cada página contra la plantilla oficial,
resuelve orientación y deja las casillas en posición conocida. La capa 2 (OCR) es
un punto de conexión: hoy usa el backend manual (no gasta API); cuando tengas la
clave de nube, se cambia el backend y todo lo demás sigue igual.

Uso:
    python leer_registraduria.py <acta_oficial.pdf> [actas.db] [--codigo MESA]
    python leer_registraduria.py <carpeta_con_pdfs/> [actas.db]
"""

import sys
from pathlib import Path

from e14.almacen import Almacen
from e14.modelo import ActaE14, FUENTE_REGISTRADURIA
from e14.alineacion import Alineador, columnas_de_layout
from e14.ocr import backend_por_defecto

PLANTILLA = "plantillas/muestra-formulario-e-14.pdf"


def procesar_pdf(pdf_path: str, alineador: Alineador, ocr, codigo_mesa: str | None) -> ActaE14:
    codigo = codigo_mesa or Path(pdf_path).stem
    acta = ActaE14(codigo_mesa=codigo, fuente=FUENTE_REGISTRADURIA,
                   archivo_origen=pdf_path)

    resultados = alineador.alinear_pdf(pdf_path)
    confianzas = []
    notas = []
    for r in resultados:
        cols_layout = columnas_de_layout(r.layout_id) if r.layout_id else []
        if r.imagen_alineada is None or not cols_layout:
            continue
        if not r.confiable:
            acta.necesita_revision = True
            notas.append(f"pág {r.indice_pagina}: alineación pobre ({r.inliers} inliers)")
            continue
        lectura = ocr.reconocer_votos(r.imagen_alineada, r.layout_id)
        for col in cols_layout:
            if lectura.valores.get(col) is not None:
                setattr(acta, col, lectura.valores[col])
        confianzas.append(lectura.confianza_global)
        if lectura.necesita_revision:
            acta.necesita_revision = True
        if lectura.notas:
            notas.append(f"pág {r.indice_pagina}: {lectura.notas}")

    if confianzas:
        acta.confianza = sum(confianzas) / len(confianzas)
    if notas:
        acta.notas = " | ".join(notas)

    cuadra = acta.cuadra_internamente()
    if cuadra is False:
        acta.necesita_revision = True
        acta.notas = (acta.notas or "") + " | La suma no cuadra con el total."
    return acta


def main():
    if len(sys.argv) < 2:
        print("Uso: python leer_registraduria.py <pdf|carpeta> [actas.db] [--codigo MESA]")
        sys.exit(1)

    entrada = Path(sys.argv[1])
    db = "actas.db"
    codigo = None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--codigo" and i + 1 < len(args):
            codigo = args[i + 1]
            i += 2
        else:
            db = args[i]
            i += 1

    if not Path(PLANTILLA).exists():
        print(f"❌ Falta la plantilla oficial: {PLANTILLA}")
        sys.exit(1)
    if not entrada.exists():
        print(f"❌ No existe: {entrada}")
        sys.exit(1)

    pdfs = sorted(entrada.glob("*.pdf")) if entrada.is_dir() else [entrada]
    if not pdfs:
        print("❌ No se encontraron PDFs.")
        sys.exit(1)

    print(f"Plantilla: {PLANTILLA}")
    alineador = Alineador(PLANTILLA, dpi=150)
    ocr = backend_por_defecto()
    print(f"Motor OCR: {ocr.nombre}\n")

    alm = Almacen(db)
    for pdf in pdfs:
        cod = codigo if (len(pdfs) == 1) else None
        acta = procesar_pdf(str(pdf), alineador, ocr, cod)
        alm.guardar(acta)
        estado = "REVISAR" if acta.necesita_revision else "OK"
        print(f"  {pdf.name}: mesa={acta.codigo_mesa}  -> {estado}")
        if acta.notas:
            print(f"      notas: {acta.notas}")
    alm.cerrar()
    print(f"\n✅ Procesados {len(pdfs)} PDF(s) en {db} (fuente='registraduria').")
    if ocr.nombre == "manual":
        print("   ⚠️  OCR en modo manual: los votos quedan vacíos hasta conectar la nube.")


if __name__ == "__main__":
    main()
