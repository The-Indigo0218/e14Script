"""
SCRIPT 3 — Comparador de actas E-14: testigo vs Registraduría.

Lee la tabla común (SQLite), cruza por mesa, detecta discrepancias y genera:
  • Un resumen en consola.
  • Un Excel con: hoja "Resumen", hoja "Comparación" (todas las columnas lado a lado)
    y hoja "Discrepancias" (solo lo que no cuadra).

Uso:
    python comparar.py [actas.db] [salida.xlsx]
"""

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from e14.almacen import Almacen
from e14.modelo import FUENTE_TESTIGO, FUENTE_REGISTRADURIA, columnas_voto
from e14.comparador import comparar, resumen, etiqueta_columna

VERDE = "C6EFCE"
ROJO = "FFC7CE"
AMARILLO = "FFEB9C"
AZUL = "1F4E78"
GRIS = "F2F2F2"
BLANCO = "FFFFFF"


def _borde():
    b = Side(style="thin", color="BFBFBF")
    return Border(left=b, right=b, top=b, bottom=b)


def _h(cell, txt, bg=AZUL, fg=BLANCO, bold=True):
    cell.value = txt
    cell.fill = PatternFill("solid", start_color=bg)
    cell.font = Font(bold=bold, color=fg, name="Arial", size=10)
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = _borde()


def generar_excel(comparaciones, salida):
    wb = Workbook()

    # ── Hoja Resumen ──
    ws = wb.active
    ws.title = "Resumen"
    r = resumen(comparaciones)
    ws.merge_cells("A1:B1")
    _h(ws["A1"], "COMPARACIÓN E-14 — TESTIGO vs REGISTRADURÍA")
    filas = [
        ("Mesas comparadas", r["total"]),
        ("✅ Coinciden", r["COINCIDE"]),
        ("⛔ Con discrepancia", r["DISCREPANCIA"]),
        ("⚠️ Falta una fuente", r["FALTA_FUENTE"]),
    ]
    for i, (etq, val) in enumerate(filas, start=3):
        ws.cell(i, 1, etq).font = Font(bold=True, name="Arial", size=10)
        ws.cell(i, 2, val).alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 14

    # ── Hoja Comparación (todas las columnas, testigo | reg | dif) ──
    ws2 = wb.create_sheet("Comparación")
    cols = columnas_voto()
    encabezados = ["Mesa", "Estado"]
    for col in cols:
        et = etiqueta_columna(col)
        encabezados += [f"{et}\n(Testigo)", f"{et}\n(Registr.)", "Δ"]
    for j, h in enumerate(encabezados, 1):
        _h(ws2.cell(1, j), h)
    ws2.row_dimensions[1].height = 42

    fila = 2
    for comp in comparaciones:
        ws2.cell(fila, 1, comp.codigo_mesa).font = Font(bold=True, name="Arial", size=9)
        est = ws2.cell(fila, 2, comp.estado)
        est_bg = {"COINCIDE": VERDE, "DISCREPANCIA": ROJO, "FALTA_FUENTE": AMARILLO}[comp.estado]
        est.fill = PatternFill("solid", start_color=est_bg)
        est.font = Font(bold=True, name="Arial", size=9)
        est.alignment = Alignment(horizontal="center")
        # mapa columna -> diferencia
        dmap = {d.columna: d for d in comp.diferencias}
        j = 3
        for col in cols:
            dc = dmap[col]
            vt, vr, d, coincide = dc.valor_testigo, dc.valor_registraduria, dc.diferencia, dc.coincide
            c_t = ws2.cell(fila, j, vt if vt is not None else "—")
            c_r = ws2.cell(fila, j + 1, vr if vr is not None else "—")
            c_d = ws2.cell(fila, j + 2, d if d is not None else "—")
            for c in (c_t, c_r, c_d):
                c.alignment = Alignment(horizontal="center")
                c.font = Font(name="Arial", size=9)
                c.border = _borde()
            if not coincide:
                for c in (c_t, c_r, c_d):
                    c.fill = PatternFill("solid", start_color=ROJO)
                c_d.font = Font(bold=True, name="Arial", size=9, color="9C0006")
            j += 3
        fila += 1
    ws2.freeze_panes = "C2"
    ws2.column_dimensions["A"].width = 18

    # ── Hoja Discrepancias (solo lo que no cuadra) ──
    ws3 = wb.create_sheet("Discrepancias")
    for j, h in enumerate(["Mesa", "Columna", "Testigo", "Registraduría", "Diferencia"], 1):
        _h(ws3.cell(1, j), h)
    fila = 2
    for comp in comparaciones:
        if comp.estado != "DISCREPANCIA":
            continue
        for d in comp.celdas_discrepantes:
            ws3.cell(fila, 1, comp.codigo_mesa)
            ws3.cell(fila, 2, d.etiqueta)
            ws3.cell(fila, 3, d.valor_testigo if d.valor_testigo is not None else "—")
            ws3.cell(fila, 4, d.valor_registraduria if d.valor_registraduria is not None else "—")
            ws3.cell(fila, 5, d.diferencia if d.diferencia is not None else "—")
            for j in range(1, 6):
                cc = ws3.cell(fila, j)
                cc.border = _borde()
                cc.font = Font(name="Arial", size=10)
                if j >= 3:
                    cc.alignment = Alignment(horizontal="center")
            fila += 1
    for col, w in zip("ABCDE", [18, 32, 12, 14, 12]):
        ws3.column_dimensions[col].width = w

    wb.save(salida)


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else "actas.db"
    salida = sys.argv[2] if len(sys.argv) > 2 else "comparacion_E14.xlsx"

    if not Path(db).exists():
        print(f"❌ No existe la base de datos: {db}")
        print("   Primero corre leer_testigos.py y leer_registraduria.py.")
        sys.exit(1)

    alm = Almacen(db)
    testigo = alm.leer_por_fuente(FUENTE_TESTIGO)
    registraduria = alm.leer_por_fuente(FUENTE_REGISTRADURIA)
    alm.cerrar()

    comparaciones = comparar(testigo, registraduria)
    r = resumen(comparaciones)

    print("=" * 60)
    print("  COMPARACIÓN E-14 — TESTIGO vs REGISTRADURÍA")
    print("=" * 60)
    print(f"  Mesas comparadas : {r['total']}")
    print(f"  ✅ Coinciden      : {r['COINCIDE']}")
    print(f"  ⛔ Discrepancia   : {r['DISCREPANCIA']}")
    print(f"  ⚠️  Falta fuente   : {r['FALTA_FUENTE']}")
    print("-" * 60)
    for comp in comparaciones:
        if comp.estado == "DISCREPANCIA":
            print(f"  Mesa {comp.codigo_mesa}: DISCREPANCIA")
            for d in comp.celdas_discrepantes:
                print(f"     - {d.etiqueta}: testigo={d.valor_testigo} "
                      f"registraduría={d.valor_registraduria} (Δ {d.diferencia})")
        elif comp.estado == "FALTA_FUENTE":
            falta = "registraduría" if comp.presente_testigo else "testigo"
            print(f"  Mesa {comp.codigo_mesa}: falta fuente '{falta}'")

    generar_excel(comparaciones, salida)
    print("-" * 60)
    print(f"  📊 Excel generado: {salida}")
    print("=" * 60)


if __name__ == "__main__":
    main()
