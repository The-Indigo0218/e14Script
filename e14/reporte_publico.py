"""
Agregación para el tablero PÚBLICO de inversores (solo lectura).

A diferencia del `dashboard.py` local (que muestra imágenes alineadas de los
E-14, panel de aprobación y cola de revisión con datos de jurados), este módulo
produce SOLO números agregados, seguros para publicar en una URL pública:

    global → municipio → zona → puesto

Por cada nivel: total de mesas auditadas, cuántas coinciden / discrepan /
faltan / quedan en revisión, y los totales de votos por candidato según el
acta del testigo (auditoría ciudadana) y la de la Registraduría (oficial).

Es una función pura sobre `list[ComparacionMesa]`: no toca la DB, ni la red, ni
archivos. Por eso es 100% testeable de forma aislada, igual que `comparador.py`.
"""

from __future__ import annotations

from datetime import datetime

from e14.comparador import ComparacionMesa
from e14.mesa import municipio_zona_puesto_mesa_desde_codigo
from e14.modelo import CANDIDATOS, columnas_voto

# Estado de comparación → clave del acumulador (los nombres internos son cortos
# para que el JSON publicado pese poco).
_ESTADO_A_CLAVE = {
    "COINCIDE": "coincide",
    "DISCREPANCIA": "discrepancia",
    "FALTA_FUENTE": "falta_fuente",
    "SIN_LECTURA": "incompleta",
    "LECTURA_INCOMPLETA": "incompleta",
}


def _nuevo_acumulador() -> dict:
    cols = columnas_voto()
    return {
        "mesas": 0,
        "coincide": 0,
        "discrepancia": 0,
        "falta_fuente": 0,
        "incompleta": 0,
        "confianza_baja": 0,
        "votos_t": {c: 0 for c in cols},
        "votos_r": {c: 0 for c in cols},
    }


def _ordinal(valor: str) -> tuple[int, str]:
    """Orden natural: numérico cuando se puede, alfabético si no."""
    return (int(valor), "") if str(valor).isdigit() else (10**9, str(valor))


def _acumular(acc: dict, comp: ComparacionMesa, umbral_revision: float) -> None:
    acc["mesas"] += 1
    acc[_ESTADO_A_CLAVE.get(comp.estado, "incompleta")] += 1
    for dif in comp.diferencias:
        if dif.valor_testigo is not None:
            acc["votos_t"][dif.columna] += dif.valor_testigo
        if dif.valor_registraduria is not None:
            acc["votos_r"][dif.columna] += dif.valor_registraduria
    for conf in (comp.confianza_testigo, comp.confianza_registraduria):
        if conf is not None and conf < umbral_revision:
            acc["confianza_baja"] += 1


def _salida(acc: dict, extra: dict) -> dict:
    """Acumulador interno → dict de salida (% de coincidencia ya calculado)."""
    comparables = acc["coincide"] + acc["discrepancia"]
    pct = round(100 * acc["coincide"] / comparables, 1) if comparables else None
    return {
        **extra,
        "mesas": acc["mesas"],
        "coincide": acc["coincide"],
        "discrepancia": acc["discrepancia"],
        "falta_fuente": acc["falta_fuente"],
        "incompleta": acc["incompleta"],
        "confianza_baja": acc["confianza_baja"],
        "pct_coincidencia": pct,
        "votos_t": acc["votos_t"],
        "votos_r": acc["votos_r"],
    }


def construir_reporte(
    comparaciones: list[ComparacionMesa],
    *,
    umbral_revision: float,
    nombre_municipio=None,
    generado: datetime | None = None,
) -> dict:
    """
    Arma el reporte agregado y seguro para publicar.

    `nombre_municipio` es un callable opcional `codigo_mun -> nombre` (ej.
    `Catalogo.nombre_municipio`); si no se pasa, se rotula "Municipio N".
    """
    cols = columnas_voto()
    candidatos = {n: CANDIDATOS[n][0] for n in CANDIDATOS}

    glob = _nuevo_acumulador()
    # municipio -> {"acc":..., "nombre":..., "zonas": {zona -> {"acc":..., "puestos": {puesto: acc}}}}
    arbol: dict[str, dict] = {}

    for comp in comparaciones:
        meta = municipio_zona_puesto_mesa_desde_codigo(comp.codigo_mesa)
        if not meta:
            continue
        mun, zona, puesto = meta["municipio"], meta["zona"], meta["puesto"]

        nodo_mun = arbol.setdefault(mun, {"acc": _nuevo_acumulador(), "zonas": {}})
        nodo_zona = nodo_mun["zonas"].setdefault(zona, {"acc": _nuevo_acumulador(), "puestos": {}})
        acc_puesto = nodo_zona["puestos"].setdefault(puesto, _nuevo_acumulador())

        for acc in (glob, nodo_mun["acc"], nodo_zona["acc"], acc_puesto):
            _acumular(acc, comp, umbral_revision)

    municipios = []
    for mun in sorted(arbol, key=_ordinal):
        nodo_mun = arbol[mun]
        nombre = nombre_municipio(mun) if nombre_municipio else f"Municipio {mun}"
        zonas = []
        for zona in sorted(nodo_mun["zonas"], key=_ordinal):
            nodo_zona = nodo_mun["zonas"][zona]
            puestos = [
                _salida(nodo_zona["puestos"][p], {"puesto": p})
                for p in sorted(nodo_zona["puestos"], key=_ordinal)
            ]
            zonas.append(_salida(nodo_zona["acc"], {"zona": zona, "puestos": puestos}))
        municipios.append(
            _salida(nodo_mun["acc"], {"id": mun, "nombre": str(nombre), "zonas": zonas})
        )

    cuando = generado or datetime.now()
    return {
        "generado": cuando.strftime("%Y-%m-%d %H:%M"),
        "eleccion": "Segunda vuelta presidencial 2026",
        "departamento": "Bolívar",
        "candidatos": candidatos,
        "columnas_voto": cols,
        "global": _salida(glob, {}),
        "municipios": municipios,
    }
