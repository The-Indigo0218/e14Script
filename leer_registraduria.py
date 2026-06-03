"""
SCRIPT 2 — Lector de E-14 OFICIALES (Registraduría).

    PDF oficial → Capa 1 (alineación) → Capa 2 (OCR) → tabla (fuente='registraduria')

La capa 1 ya está lista. La capa 2 (e14/ocr.py) usa Gemini/GPT si hay clave en .env,
o el backend manual si no (para probar el flujo sin gastar).

Uso:
    python leer_registraduria.py <acta.pdf|carpeta/> [actas.db] [--codigo MESA] [--tipo delegados]
    python leer_registraduria.py                      (usa datos/registraduria/)

La copia oficial publicada suele ser la de DELEGADOS; por eso es el valor por
defecto, pero puedes indicar --tipo claveros|delegados|transmision.
"""

import sys
from pathlib import Path

from e14.almacen import Almacen
from e14.modelo import FUENTE_REGISTRADURIA, TIPO_DELEGADOS, etiqueta_tipo_acta
from e14.alineacion import Alineador
from e14.ocr import backend_por_defecto
from e14.lectura import leer_acta_pdf, listar_documentos, imprimir_trazabilidad
from cli_args import parsear_args

PLANTILLA = "plantillas/muestra-formulario-e-14.pdf"
CARPETA_DEFECTO = "datos/registraduria"


def main():
    entrada, db, codigo, tipo = parsear_args(CARPETA_DEFECTO, tipo_defecto=TIPO_DELEGADOS)

    if not Path(PLANTILLA).exists():
        print(f"❌ Falta la plantilla oficial: {PLANTILLA}")
        sys.exit(1)
    if not entrada.exists():
        print(f"❌ No existe: {entrada}")
        sys.exit(1)

    pdfs = listar_documentos(entrada)
    if not pdfs:
        print(f"❌ No se encontraron PDF/imágenes en {entrada}")
        sys.exit(1)

    print(f"Plantilla: {PLANTILLA}")
    print(f"Tipo de ejemplar: {etiqueta_tipo_acta(tipo)}")
    alineador = Alineador(PLANTILLA, dpi=150)
    ocr = backend_por_defecto()
    print(f"Motor OCR: {ocr.nombre}\n")

    alm = Almacen(db)
    for pdf in pdfs:
        cod = codigo if len(pdfs) == 1 else None
        acta = leer_acta_pdf(str(pdf), alineador, ocr, FUENTE_REGISTRADURIA, cod, tipo_acta=tipo)
        alm.guardar(acta)
        estado = "REVISAR" if acta.necesita_revision else "OK"
        conf = f"{acta.confianza:.0%}" if acta.confianza is not None else "—"
        print(f"  {pdf.name}: mesa={acta.codigo_mesa}  confianza={conf}  -> {estado}")
        imprimir_trazabilidad(acta)
        if acta.notas:
            print(f"      notas: {acta.notas}")
    alm.cerrar()
    print(f"\n✅ Procesados {len(pdfs)} PDF(s) en {db} (fuente='registraduria').")
    if ocr.nombre == "manual":
        print("   ⚠️  OCR en modo manual: define GEMINI_API_KEY en .env para leer de verdad.")


if __name__ == "__main__":
    main()
