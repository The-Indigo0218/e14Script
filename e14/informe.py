"""
Informe legible en consola de lo que contiene un acta leída (sin gastar API).
"""

from __future__ import annotations

from e14.comparador import etiqueta_columna
from e14.modelo import (
    ActaE14,
    FUENTE_REGISTRADURIA,
    FUENTE_TESTIGO,
    columnas_voto,
    copias_a_texto,
    etiqueta_tipo_acta,
)
from e14.mesa import etiqueta_mesa


def _get(obj: ActaE14 | dict, key: str):
    if isinstance(obj, ActaE14):
        return getattr(obj, key, None)
    return obj.get(key)


def imprimir_contenido_acta(acta: ActaE14 | dict, *, titulo: str | None = None) -> None:
    """Muestra votos leídos, confianza y trazabilidad de un acta en la base."""
    codigo = _get(acta, "codigo_mesa")
    fuente = _get(acta, "fuente")
    etiqueta_fuente = "Registraduría" if fuente == FUENTE_REGISTRADURIA else "Testigo"
    if titulo:
        print(f"\n{'═' * 60}")
        print(f"  {titulo}")
    else:
        print(f"\n{'═' * 60}")
        print(f"  CONTENIDO — {etiqueta_fuente} · mesa {codigo}")
    print(f"{'═' * 60}")
    print(f"  {etiqueta_mesa(codigo)}")
    print(f"  Archivo    : {_get(acta, 'archivo_origen') or '—'}")
    print(f"  Ejemplar   : {etiqueta_tipo_acta(_get(acta, 'tipo_acta'))}")
    copias = _get(acta, "copias_en_evidencia")
    if copias:
        print(f"  Copias vis.: {copias_a_texto(copias)}")
    conf = _get(acta, "confianza")
    revision = _get(acta, "necesita_revision")
    if isinstance(revision, int):
        revision = bool(revision)
    conf_txt = f"{conf:.0%}" if conf is not None else "—"
    estado = "REVISAR" if revision else "OK"
    print(f"  Confianza  : {conf_txt}  → {estado}")
    print(f"{'─' * 60}")
    print(f"  {'Candidato / categoría':<42} {'Votos':>8}")
    print(f"{'─' * 60}")

    hay_alguno = False
    for col in columnas_voto():
        val = _get(acta, col)
        if val is None:
            continue
        hay_alguno = True
        print(f"  {etiqueta_columna(col):<42} {val:>8}")

    if not hay_alguno:
        print("  (sin votos leídos — OCR manual, error API o aún no procesado)")

    suma = _get(acta, "suma_total")
    urna = _get(acta, "total_votos_urna")
    if suma is not None or urna is not None:
        print(f"{'─' * 60}")
        if suma is not None:
            print(f"  {'SUMA TOTAL':<42} {suma:>8}")
        if urna is not None:
            print(f"  {'Total votos en urna':<42} {urna:>8}")

    notas = _get(acta, "notas")
    if notas:
        print(f"{'─' * 60}")
        print(f"  Notas: {notas}")
    print(f"{'═' * 60}\n")


def imprimir_siguiente_paso_registraduria(codigo: str) -> None:
    """Indica al usuario el flujo: oficial primero, luego testigo, luego comparar."""
    print("📋 Siguiente paso (cuando tengas cuota API disponible):")
    print(f"   1) Ver sin re-OCR:  python ver_acta.py actas.db --fuente registraduria")
    print(f"   2) Leer testigo:    python leer_testigos.py datos/testigos/{codigo}_testigo.pdf actas.db --tipo claveros --solo-pagina-1")
    print(f"   3) Comparar:        python comparar.py actas.db comparacion_{codigo}.xlsx")


def imprimir_siguiente_paso_testigo(codigo: str) -> None:
    print("📋 Siguiente paso:")
    print(f"   python comparar.py actas.db comparacion_{codigo}.xlsx")
