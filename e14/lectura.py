"""
Lectura compartida de un E-14 en PDF/imagen → ActaE14.

Tanto el lado oficial (Registraduría) como el del testigo leen el MISMO tipo de
documento; lo que cambia es `fuente`. Antes del OCR se detecta qué ejemplares
(CLAVEROS / DELEGADOS / TRANSMISIÓN) aparecen en la evidencia y de cuál se leen
los votos (`tipo_acta`).

    documento → detectar copias en evidencia → Capa 1 → Capa 2 (OCR) → ActaE14
"""

from __future__ import annotations

from pathlib import Path

import cv2

from e14.modelo import (
    ActaE14,
    TIPO_DESCONOCIDO,
    normalizar_tipo_acta,
    serializar_copias,
    resumen_trazabilidad_e14,
)
from e14.alineacion import Alineador, columnas_de_layout, render_pdf_gris
from e14.evidencia import detectar_copias_en_evidencia, validar_lectura_vs_evidencia


def cargar_paginas(ruta: str | Path, dpi: int = 150) -> list:
    """PDF o imagen (jpg/png) → lista de páginas en escala de grises."""
    p = Path(ruta)
    if p.suffix.lower() == ".pdf":
        return render_pdf_gris(p, dpi=dpi)
    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    return [img] if img is not None else []


def leer_acta_pdf(pdf_path: str, alineador: Alineador, ocr, fuente: str,
                  codigo_mesa: str | None = None, tipo_acta: str | None = None) -> ActaE14:
    """Lee un E-14 (PDF o foto) y devuelve un ActaE14 con trazabilidad de ejemplares."""
    codigo = codigo_mesa or Path(pdf_path).stem
    copias_visibles, nota_det = detectar_copias_en_evidencia(pdf_path)
    copia_leida = normalizar_tipo_acta(tipo_acta)

    # Si hay una sola copia visible y no indicaron --tipo, usar esa.
    if copia_leida == TIPO_DESCONOCIDO and len(copias_visibles) == 1:
        copia_leida = copias_visibles[0]

    ok_traz, nota_val = validar_lectura_vs_evidencia(copia_leida, copias_visibles)

    acta = ActaE14(
        codigo_mesa=codigo,
        fuente=fuente,
        archivo_origen=pdf_path,
        tipo_acta=copia_leida,
        copias_en_evidencia=serializar_copias(copias_visibles) or None,
    )
    if not ok_traz:
        acta.necesita_revision = True

    notas: list[str] = []
    if nota_det:
        notas.append(nota_det)
    if nota_val:
        notas.append(nota_val)

    paginas = cargar_paginas(pdf_path, dpi=alineador.dpi)
    if not paginas:
        acta.necesita_revision = True
        notas.append("No se pudieron cargar páginas del archivo.")
        acta.notas = " | ".join(notas)
        return acta

    resultados = alineador.alinear_paginas(paginas)
    confianzas: list[float] = []

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


def imprimir_trazabilidad(acta: ActaE14) -> None:
    """Muestra en consola de qué parte del E-14 salió la evidencia."""
    print(f"      📷 {resumen_trazabilidad_e14(acta.fuente, acta.copias_en_evidencia, acta.tipo_acta)}")


def listar_documentos(entrada: str | Path) -> list[Path]:
    """PDF o imágenes de evidencia en una carpeta o archivo."""
    p = Path(entrada)
    if p.is_file():
        return [p]
    exts = ("*.pdf", "*.png", "*.jpg", "*.jpeg", "*.PDF", "*.PNG", "*.JPG")
    archivos: list[Path] = []
    for pat in exts:
        archivos.extend(p.glob(pat))
    return sorted(set(archivos))


# Alias para compatibilidad
listar_pdfs = listar_documentos
