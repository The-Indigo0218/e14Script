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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from e14.almacen import Almacen
from e14.mesa import codigo_mesa_desde_archivo
from e14.modelo import FUENTE_REGISTRADURIA, TIPO_DELEGADOS, etiqueta_tipo_acta
from e14.alineacion import Alineador
from e14.ocr import backend_por_defecto
from e14.informe import imprimir_contenido_acta, imprimir_siguiente_paso_registraduria
from e14.lectura import leer_acta_pdf, listar_documentos, imprimir_trazabilidad
from cli_args import parsear_args

PLANTILLA = "plantillas/muestra-formulario-e14-segunda-vuelta.pdf"
CARPETA_DEFECTO = "datos/registraduria"


def main():
    entrada, db, codigo, tipo, layouts, _solo_p1, paralelo, forzar = parsear_args(
        CARPETA_DEFECTO, tipo_defecto=TIPO_DELEGADOS)

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

    alm = Almacen(db)
    if not forzar and len(pdfs) > 1:
        ya_ok = {
            cod for cod, fila in alm.leer_por_fuente(FUENTE_REGISTRADURIA).items()
            if not fila.get("necesita_revision")
        }
        pendientes = [p for p in pdfs if codigo_mesa_desde_archivo(p) not in ya_ok]
        saltadas = len(pdfs) - len(pendientes)
        if saltadas:
            print(f"Saltando {saltadas} ya guardadas y OK (usa --forzar para reprocesar todo).")
        pdfs = pendientes
    if not pdfs:
        print("✅ No hay nada pendiente: todo ya estaba guardado y OK.")
        alm.cerrar()
        return

    print(f"Plantilla: {PLANTILLA}")
    print(f"Tipo de ejemplar: {etiqueta_tipo_acta(tipo)}")
    alineador = Alineador(PLANTILLA, dpi=150)
    ocr = backend_por_defecto()
    print(f"Motor OCR: {ocr.nombre}")
    if layouts:
        print("Modo: solo página de candidatos/totales (sin firmas)\n")
    else:
        print()

    if paralelo > 1:
        print(f"Paralelo: {paralelo} lecturas OCR a la vez\n")

    def _leer(pdf: Path):
        cod = codigo if len(pdfs) == 1 else None
        return pdf, leer_acta_pdf(str(pdf), alineador, ocr, FUENTE_REGISTRADURIA, cod,
                                  tipo_acta=tipo, layouts=layouts)

    def _reportar(pdf: Path, acta) -> None:
        alm.guardar(acta)  # siempre en el hilo principal (sqlite no es multi-escritor)
        estado = "REVISAR" if acta.necesita_revision else "OK"
        conf = f"{acta.confianza:.0%}" if acta.confianza is not None else "—"
        print(f"  {pdf.name}: mesa={acta.codigo_mesa}  confianza={conf}  -> {estado}")
        imprimir_trazabilidad(acta)
        if acta.notas:
            print(f"      notas: {acta.notas}")
        imprimir_contenido_acta(acta)
        if len(pdfs) == 1:
            imprimir_siguiente_paso_registraduria(acta.codigo_mesa)

    if paralelo <= 1:
        for pdf in pdfs:
            _reportar(*_leer(pdf))
    else:
        with ThreadPoolExecutor(max_workers=paralelo) as ex:
            futuros = [ex.submit(_leer, pdf) for pdf in pdfs]
            for fut in as_completed(futuros):
                _reportar(*fut.result())
    alm.cerrar()
    print(f"✅ Procesados {len(pdfs)} PDF(s) en {db} (fuente='registraduria').")
    if ocr.nombre == "manual":
        print("   ⚠️  OCR en modo manual: define GEMINI_API_KEY en .env para leer de verdad.")


if __name__ == "__main__":
    main()
