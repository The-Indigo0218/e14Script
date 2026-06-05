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
from e14.mesa import codigo_mesa_desde_archivo, zona_puesto_mesa_desde_codigo, etiqueta_mesa
from e14.preprocess import mejorar_para_ocr


def cargar_paginas(ruta: str | Path, dpi: int = 150) -> list:
    """PDF o imagen (jpg/png) → lista de páginas en escala de grises."""
    p = Path(ruta)
    if p.suffix.lower() == ".pdf":
        return render_pdf_gris(p, dpi=dpi)
    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    return [img] if img is not None else []


def leer_acta_pdf(pdf_path: str, alineador: Alineador, ocr, fuente: str,
                  codigo_mesa: str | None = None, tipo_acta: str | None = None,
                  layouts: list[str] | None = None) -> ActaE14:
    """Lee un E-14 (PDF o foto) y devuelve un ActaE14 con trazabilidad de ejemplares."""
    codigo = codigo_mesa or codigo_mesa_desde_archivo(pdf_path)
    meta = zona_puesto_mesa_desde_codigo(codigo)
    copias_visibles, nota_det = detectar_copias_en_evidencia(pdf_path, fuente=fuente)
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
        **meta,
    )
    if not ok_traz:
        acta.necesita_revision = True

    notas: list[str] = []
    if nota_det:
        notas.append(nota_det)
    if nota_val:
        notas.append(nota_val)

    paginas = cargar_paginas(pdf_path, dpi=alineador.dpi)
    # Modo prueba / pág 1: el PDF oficial suele traer 3 hojas; solo leemos la primera.
    if layouts and len(paginas) > 1:
        paginas = paginas[:1]
        notas.append("Solo se procesó la página 1 del PDF (--solo-pagina-1).")
    if not paginas:
        acta.necesita_revision = True
        notas.append("No se pudieron cargar páginas del archivo.")
        acta.notas = " | ".join(notas)
        return acta

    resultados = alineador.alinear_paginas(paginas, solo_layouts=layouts)
    confianzas: list[float] = []

    for r in resultados:
        if layouts and r.layout_id not in layouts:
            continue
        cols_layout = columnas_de_layout(r.layout_id) if r.layout_id else []
        if r.imagen_alineada is None or not cols_layout:
            continue
        if not r.confiable:
            acta.necesita_revision = True
            notas.append(f"pág {r.indice_pagina}: alineación pobre ({r.inliers} inliers)")
            continue
        notas.append(f"pág {r.indice_pagina}: alineación OK ({r.inliers} inliers, layout={r.layout_id})")
        img_ocr = mejorar_para_ocr(r.imagen_alineada, escala=1.5)
        lectura = ocr.reconocer_votos(img_ocr, r.layout_id)
        # Si la API dejó casillas en null (dígitos con puntos '..3'), reintenta con más zoom.
        faltan = [c for c in cols_layout if lectura.valores.get(c) is None]
        rate_limit = "429" in (lectura.notas or "")
        parcial = any(lectura.valores.get(c) is not None for c in cols_layout)
        if faltan and parcial and not rate_limit:
            img_zoom = mejorar_para_ocr(r.imagen_alineada, escala=2.5)
            lectura2 = ocr.reconocer_votos(img_zoom, r.layout_id)
            for c in faltan:
                if lectura2.valores.get(c) is not None:
                    lectura.valores[c] = lectura2.valores[c]
                    lectura.confianzas[c] = lectura2.confianzas.get(c, 0.0)
            presentes = [lectura.confianzas[c] for c in cols_layout if lectura.valores[c] is not None]
            lectura.confianza_global = min(presentes) if presentes else 0.0
            lectura.necesita_revision = (not presentes) or any(
                lectura.confianzas[c] < 0.80 for c in cols_layout if lectura.valores[c] is not None
            )
            if any(lectura2.valores.get(c) is not None for c in faltan):
                notas.append(f"pág {r.indice_pagina}: re-OCR zoom recuperó {len(faltan)} casilla(s)")
        for col in cols_layout:
            if lectura.valores.get(col) is not None:
                setattr(acta, col, lectura.valores[col])
        # Solo promediar confianza de lecturas que sí extrajeron algo (evita diluir con páginas basura).
        if any(lectura.valores.get(c) is not None for c in cols_layout):
            confianzas.append(lectura.confianza_global)
        if lectura.necesita_revision:
            acta.necesita_revision = True
        if lectura.detalle_api:
            notas.append(f"OCR pág {r.indice_pagina}: {lectura.detalle_api}")
        elif lectura.notas:
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
    print(f"      🔑 Par: {acta.codigo_mesa}  ({etiqueta_mesa(acta.codigo_mesa)})")
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
