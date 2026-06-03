"""
SCRIPT 1 — Lector de E-14 de los TESTIGOS.

El testigo de mesa anota los votos que vio y los entrega como una tabla (CSV).
Este script lee ese CSV y lo carga a la tabla común (fuente='testigo').

Es la vía más confiable para el dato del testigo: captura directa, sin OCR.
(Si en el futuro el testigo manda foto del acta, se puede añadir un modo OCR
reutilizando la misma capa 1 + e14/ocr.py, igual que leer_registraduria.py.)

Formato del CSV (encabezados; las columnas de voto que falten quedan vacías):
    codigo_mesa,departamento,municipio,zona,puesto,mesa,
    c1,c2,...,c13,blanco,nulos,no_marcados,suma_total,total_votos_urna

Uso:
    python leer_testigos.py <archivo.csv> [actas.db]
"""

import csv
import sys
from pathlib import Path

from e14.almacen import Almacen
from e14.modelo import ActaE14, FUENTE_TESTIGO, columnas_voto


def _int(valor):
    valor = (valor or "").strip()
    if valor == "":
        return None
    try:
        return int(float(valor))
    except ValueError:
        return None


def cargar_csv(ruta_csv: str, db: str = "actas.db") -> int:
    alm = Almacen(db)
    n = 0
    campos_int = columnas_voto() + ["suma_total", "total_votos_urna", "total_votantes_e11"]
    with open(ruta_csv, newline="", encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f):
            codigo = (fila.get("codigo_mesa") or "").strip()
            if not codigo:
                continue
            acta = ActaE14(codigo_mesa=codigo, fuente=FUENTE_TESTIGO,
                           archivo_origen=ruta_csv)
            for meta in ("departamento", "municipio", "zona", "puesto", "mesa"):
                v = (fila.get(meta) or "").strip()
                if v:
                    setattr(acta, meta, v)
            for col in campos_int:
                if col in fila:
                    setattr(acta, col, _int(fila[col]))
            cuadra = acta.cuadra_internamente()
            if cuadra is False:
                acta.necesita_revision = True
                acta.notas = (f"La suma de votos ({acta.suma_calculada()}) no cuadra "
                              f"con el total declarado.")
            alm.guardar(acta)
            n += 1
    alm.cerrar()
    return n


def main():
    if len(sys.argv) < 2:
        print("Uso: python leer_testigos.py <archivo.csv> [actas.db]")
        sys.exit(1)
    ruta = sys.argv[1]
    db = sys.argv[2] if len(sys.argv) > 2 else "actas.db"
    if not Path(ruta).exists():
        print(f"❌ No existe el archivo: {ruta}")
        sys.exit(1)
    n = cargar_csv(ruta, db)
    print(f"✅ {n} actas de testigos cargadas en {db} (fuente='testigo').")


if __name__ == "__main__":
    main()
