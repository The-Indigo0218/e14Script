"""
Lectura compartida de un E-14 en PDF → ActaE14.

Tanto el lado oficial (Registraduría) como el del testigo leen el MISMO tipo de
documento (un E-14 escaneado); lo único que cambia es la etiqueta de `fuente`.
Por eso la lógica vive aquí una sola vez y los dos scripts la reutilizan.

    PDF → Capa 1 (alineación por plantilla) → Capa 2 (OCR) → ActaE14
"""

from __future__ import annotations

from pathlib import Path

from e14.modelo import ActaE14, normalizar_tipo_acta
from e14.alineacion import Alineador, columnas_de_layout


def leer_acta_pdf(pdf_path: str, alineador: Alineador, ocr, fuente: str,
                  codigo_mesa: str | None = None, tipo_acta: str | None = None) -> ActaE14:
    """Lee un PDF E-14 completo y devuelve un ActaE14 para la fuente dada."""
    codigo = codigo_mesa or Path(pdf_path).stem
    acta = ActaE14(codigo_mesa=codigo, fuente=fuente, archivo_origen=pdf_path,
                   tipo_acta=normalizar_tipo_acta(tipo_acta))

    resultados = alineador.alinear_pdf(pdf_path)
    confianzas: list[float] = []
    notas: list[str] = []

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

    if acta.cuadra_internamente() is False:
        acta.necesita_revision = True
        acta.notas = (acta.notas or "") + " | La suma no cuadra con el total."
    return acta


def listar_pdfs(entrada: str | Path) -> list[Path]:
    p = Path(entrada)
    return sorted(p.glob("*.pdf")) if p.is_dir() else [p]
