"""
Lectura compartida de un E-14 en PDF/imagen → ActaE14.

Tanto el lado oficial (Registraduría) como el del testigo leen el MISMO tipo de
documento; lo que cambia es `fuente`. Antes del OCR se detecta qué ejemplares
(CLAVEROS / DELEGADOS / TRANSMISIÓN) aparecen en la evidencia y de cuál se leen
los votos (`tipo_acta`).

    documento → detectar copias en evidencia → Capa 1 → Capa 2 (OCR) → ActaE14
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2

from e14.modelo import (
    ActaE14,
    TIPO_DESCONOCIDO,
    normalizar_tipo_acta,
    serializar_copias,
    resumen_trazabilidad_e14,
)
from e14.alineacion import (
    Alineador, columnas_de_layout, render_pdf_gris, roi_votos_de_layout,
)
from e14.segmentacion import alinear_actas_en_paginas
from e14.evidencia import detectar_copias_en_evidencia, validar_lectura_vs_evidencia
from e14.mesa import codigo_mesa_desde_archivo, municipio_zona_puesto_mesa_desde_codigo, etiqueta_mesa
from e14.preprocess import mejorar_para_ocr, recortar_region


def _recortar_votos_activo(flag: bool | None) -> bool:
    """¿Recortar a la región de votación antes del OCR? Opt-in: por defecto NO
    (el ROI 2026 es provisional hasta validar con actas reales). Se activa con
    el parámetro o con OCR_RECORTAR_VOTOS=1 en el entorno."""
    if flag is not None:
        return flag
    return os.environ.get("OCR_RECORTAR_VOTOS", "").lower() in ("1", "true", "yes")


def cargar_paginas(ruta: str | Path, dpi: int = 150) -> list:
    """PDF o imagen (jpg/png) → lista de páginas en escala de grises."""
    p = Path(ruta)
    if p.suffix.lower() == ".pdf":
        return render_pdf_gris(p, dpi=dpi)
    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    return [img] if img is not None else []


def leer_acta_pdf(pdf_path: str, alineador: Alineador, ocr, fuente: str,
                  codigo_mesa: str | None = None, tipo_acta: str | None = None,
                  layouts: list[str] | None = None,
                  recortar_votos: bool | None = None) -> ActaE14:
    """Lee un E-14 (PDF o foto) y devuelve un ActaE14 con trazabilidad de ejemplares."""
    recortar = _recortar_votos_activo(recortar_votos)
    codigo = codigo_mesa or codigo_mesa_desde_archivo(pdf_path)
    meta = municipio_zona_puesto_mesa_desde_codigo(codigo)
    usar_gemini_copias = os.environ.get("OCR_DETECTAR_COPIAS_GEMINI", "").lower() in (
        "1", "true", "yes",
    )
    copias_visibles, nota_det = detectar_copias_en_evidencia(
        pdf_path, usar_gemini=usar_gemini_copias, fuente=fuente,
    )
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

    # Una imagen puede traer VARIAS copias (claveros/delegados/transmisión) juntas;
    # la segmentación devuelve un acta por copia detectada (ver e14/segmentacion.py).
    resultados = alinear_actas_en_paginas(alineador, paginas, solo_layouts=layouts)

    # (resultado, lectura, votos_dict) de cada copia que SÍ extrajo votos.
    lecturas_ok: list[tuple] = []

    for idx, r in enumerate(resultados, 1):
        if layouts and r.layout_id not in layouts:
            continue
        cols_layout = columnas_de_layout(r.layout_id) if r.layout_id else []
        if r.imagen_alineada is None or not cols_layout:
            continue
        if not r.confiable:
            acta.necesita_revision = True
            notas.append(f"copia {idx} (pág {r.indice_pagina}): alineación pobre ({r.inliers} inliers)")
            continue
        notas.append(f"copia {idx} (pág {r.indice_pagina}): alineación OK ({r.inliers} inliers)")
        # Recortar a la región de votación (opt-in) ahorra tokens y enfoca el OCR.
        # Solo se recorta con alineación confiable: si el folio quedó mal alineado,
        # el ROI caería sobre la zona equivocada → mejor mandar la hoja completa.
        region = r.imagen_alineada
        roi = roi_votos_de_layout(r.layout_id) if recortar else None
        if roi is not None:
            region = recortar_region(r.imagen_alineada, roi)
            notas.append(f"copia {idx}: recorte región votación activado")
        img_ocr = mejorar_para_ocr(region, escala=1.5)
        lectura = ocr.reconocer_votos(img_ocr, r.layout_id)
        # Si la API dejó casillas en null (dígitos con puntos '..3'), reintenta con más zoom.
        faltan = [c for c in cols_layout if lectura.valores.get(c) is None]
        rate_limit = "429" in (lectura.notas or "")
        parcial = any(lectura.valores.get(c) is not None for c in cols_layout)
        if faltan and parcial and not rate_limit:
            img_zoom = mejorar_para_ocr(region, escala=2.5)
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
                notas.append(f"copia {idx}: re-OCR zoom recuperó {len(faltan)} casilla(s)")
        # KIT/CIV: toma el primero disponible entre las copias.
        if lectura.numero_kit and not acta.numero_kit:
            acta.numero_kit = lectura.numero_kit
            acta.confianza_kit = lectura.confianza_kit
        if lectura.civ and not acta.civ:
            acta.civ = lectura.civ
            acta.confianza_civ = lectura.confianza_civ
        if lectura.detalle_api:
            notas.append(f"OCR copia {idx}: {lectura.detalle_api}")
        elif lectura.notas:
            notas.append(f"copia {idx}: {lectura.notas}")
        votos = {c: lectura.valores.get(c) for c in cols_layout}
        if any(v is not None for v in votos.values()):
            lecturas_ok.append((r, lectura, votos))
        if lectura.necesita_revision:
            acta.necesita_revision = True

    # ── Consolidar: elegir la copia MEJOR leída y cruzar entre copias ──
    # Todas las copias del E-14 traen los mismos votos, así que con leer una bien
    # basta. Si se leyeron 2+ y DISCREPAN, se marca para revisión (señal fuerte).
    if lecturas_ok:
        def _calidad(item):
            res, lec, votos = item
            no_nulas = sum(1 for v in votos.values() if v is not None)
            return (lec.confianza_global, no_nulas, res.inliers)

        _r, principal, votos_p = max(lecturas_ok, key=_calidad)
        for col, val in votos_p.items():
            if val is not None:
                setattr(acta, col, val)
        acta.confianza = principal.confianza_global

        if len(lecturas_ok) >= 2:
            discrepan = [
                c for c in votos_p
                if len({v[c] for _x, _y, v in lecturas_ok if v.get(c) is not None}) > 1
            ]
            if discrepan:
                acta.necesita_revision = True
                notas.append(f"⚠ {len(lecturas_ok)} copias leídas y DISCREPAN en "
                             f"{', '.join(discrepan)} — revisar a mano")
            else:
                notas.append(f"✓ {len(lecturas_ok)} copias leídas y coinciden en los votos")

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
