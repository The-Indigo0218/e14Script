"""
SCRIPT 1 — Lector de E-14 de los TESTIGOS.

Dos modos según la entrada:
  • CSV  → el testigo entregó los números en una tabla (sin OCR).
  • PDF/carpeta → el testigo entregó foto/escaneo del E-14
                  → mismo pipeline que el oficial (capa 1 + OCR), fuente='testigo'.

Uso:
    python leer_testigos.py <archivo.csv>            (modo tabla)
    python leer_testigos.py <acta.pdf|carpeta/>      (modo OCR)
    python leer_testigos.py                          (usa datos/testigos/)
    [actas.db] [--codigo MESA] [--tipo claveros|delegados|transmision]

IMPORTANTE: el testigo debe indicar de qué COPIA tomó el dato (--tipo, o la
columna 'tipo_acta' del CSV). Sin ello queda como 'desconocido'.
"""

import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from e14.almacen import Almacen
from e14.modelo import (ActaE14, FUENTE_TESTIGO, columnas_voto,
                        normalizar_tipo_acta, etiqueta_tipo_acta, serializar_copias,
                        parsear_copias)
from e14.alineacion import Alineador
from e14.ocr import backend_por_defecto
from e14.informe import imprimir_contenido_acta, imprimir_siguiente_paso_testigo
from e14.lectura import leer_acta_pdf, listar_documentos, imprimir_trazabilidad
from e14.evidencia import validar_lectura_vs_evidencia
from cli_args import parsear_args

PLANTILLA = "plantillas/muestra-formulario-e14-segunda-vuelta.pdf"
CARPETA_DEFECTO = "datos/testigos"


def _int(valor):
    valor = (valor or "").strip()
    if valor == "":
        return None
    try:
        return int(float(valor))
    except ValueError:
        return None


def cargar_csv(ruta_csv: str, db: str, tipo: str | None) -> int:
    alm = Almacen(db)
    n = 0
    campos_int = columnas_voto() + ["suma_total", "total_votos_urna", "total_votantes_e11"]
    with open(ruta_csv, newline="", encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f):
            codigo = (fila.get("codigo_mesa") or "").strip()
            if not codigo:
                continue
            # El tipo por fila del CSV manda; si no viene, usa el --tipo global.
            tipo_fila = (fila.get("tipo_acta") or "").strip() or tipo
            copias_fila = (fila.get("copias_en_evidencia") or "").strip()
            copias = parsear_copias(copias_fila) if copias_fila else []
            acta = ActaE14(
                codigo_mesa=codigo, fuente=FUENTE_TESTIGO, archivo_origen=ruta_csv,
                tipo_acta=normalizar_tipo_acta(tipo_fila),
                copias_en_evidencia=serializar_copias(copias) or None,
            )
            ok, nota = validar_lectura_vs_evidencia(acta.tipo_acta, copias)
            if not ok:
                acta.necesita_revision = True
                acta.notas = nota
            for meta in ("departamento", "municipio", "zona", "puesto", "mesa"):
                v = (fila.get(meta) or "").strip()
                if v:
                    setattr(acta, meta, v)
            for col in campos_int:
                if col in fila:
                    setattr(acta, col, _int(fila[col]))
            if acta.cuadra_internamente() is False:
                acta.necesita_revision = True
                acta.notas = (f"La suma de votos ({acta.suma_calculada()}) no cuadra "
                              f"con el total declarado.")
            alm.guardar(acta)
            n += 1
    alm.cerrar()
    return n


def cargar_pdfs(entrada: Path, db: str, codigo: str | None, tipo: str | None,
                layouts: list[str] | None, paralelo: int = 1) -> int:
    if not Path(PLANTILLA).exists():
        print(f"❌ Falta la plantilla oficial: {PLANTILLA}")
        sys.exit(1)
    pdfs = listar_documentos(entrada)
    if not pdfs:
        print(f"❌ No se encontraron PDF/imágenes en {entrada}")
        sys.exit(1)
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

    alm = Almacen(db)

    def _leer(pdf: Path):
        cod = codigo if len(pdfs) == 1 else None
        return pdf, leer_acta_pdf(str(pdf), alineador, ocr, FUENTE_TESTIGO, cod,
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
            imprimir_siguiente_paso_testigo(acta.codigo_mesa)

    if paralelo <= 1:
        for pdf in pdfs:
            _reportar(*_leer(pdf))
    else:
        with ThreadPoolExecutor(max_workers=paralelo) as ex:
            futuros = [ex.submit(_leer, pdf) for pdf in pdfs]
            for fut in as_completed(futuros):
                _reportar(*fut.result())
    alm.cerrar()
    if ocr.nombre == "manual":
        print("   ⚠️  OCR en modo manual: define GEMINI_API_KEY en .env para leer de verdad.")
    return len(pdfs)


def main():
    entrada, db, codigo, tipo, layouts, _solo_p1, paralelo, _forzar = parsear_args(CARPETA_DEFECTO)

    if not entrada.exists():
        print(f"❌ No existe: {entrada}")
        sys.exit(1)

    if entrada.is_file() and entrada.suffix.lower() == ".csv":
        n = cargar_csv(str(entrada), db, tipo)
        print(f"✅ {n} actas de testigos cargadas en {db} (fuente='testigo', modo CSV).")
    else:
        n = cargar_pdfs(entrada, db, codigo, tipo, layouts, paralelo)
        print(f"\n✅ Procesados {n} E-14 de testigos en {db} (fuente='testigo', modo OCR).")


if __name__ == "__main__":
    main()
