"""Tests de e14/reporte_publico.py — agregación para el tablero público."""

from __future__ import annotations

from e14.comparador import comparar
from e14.reporte_publico import construir_reporte


def _fila(c1, c2, blanco=0, nulos=0, no_marcados=0, confianza=1.0):
    return {
        "c1": c1, "c2": c2, "blanco": blanco, "nulos": nulos,
        "no_marcados": no_marcados, "confianza": confianza,
    }


def _reporte(testigo, registraduria, **kw):
    comps = comparar(testigo, registraduria)
    return construir_reporte(comps, umbral_revision=0.80, **kw)


def test_arbol_municipio_zona_puesto_se_arma_y_ordena():
    t = {
        "1_5_2_1": _fila(10, 5),
        "1_5_10_1": _fila(3, 3),   # puesto 10 debe ir después del 2 (orden numérico)
        "1_1_1_1": _fila(7, 7),    # zona 1 antes que zona 5
        "2_1_1_1": _fila(1, 1),    # municipio 2 después del 1
    }
    rep = _reporte(t, dict(t))
    muns = rep["municipios"]
    assert [m["id"] for m in muns] == ["1", "2"]
    zonas1 = muns[0]["zonas"]
    assert [z["zona"] for z in zonas1] == ["1", "5"]
    puestos_z5 = [z for z in zonas1 if z["zona"] == "5"][0]["puestos"]
    assert [p["puesto"] for p in puestos_z5] == ["2", "10"]


def test_votos_se_suman_por_nivel():
    t = {
        "1_1_1_1": _fila(10, 20),
        "1_1_1_2": _fila(5, 7),    # mismo puesto
        "1_1_2_1": _fila(1, 1),    # otro puesto, misma zona
    }
    rep = _reporte(t, dict(t))
    g = rep["global"]
    assert g["votos_t"]["c1"] == 16 and g["votos_t"]["c2"] == 28
    zona = rep["municipios"][0]["zonas"][0]
    assert zona["votos_t"]["c1"] == 16
    puesto1 = [p for p in zona["puestos"] if p["puesto"] == "1"][0]
    assert puesto1["votos_t"]["c1"] == 15 and puesto1["mesas"] == 2


def test_cuenta_coincidencias_y_discrepancias():
    t = {"1_1_1_1": _fila(10, 5), "1_1_1_2": _fila(10, 5)}
    r = {"1_1_1_1": _fila(10, 5), "1_1_1_2": _fila(99, 5)}  # 2da discrepa
    rep = _reporte(t, r)
    g = rep["global"]
    assert g["coincide"] == 1
    assert g["discrepancia"] == 1
    assert g["pct_coincidencia"] == 50.0


def test_falta_fuente_no_es_comparable():
    t = {"1_1_1_1": _fila(10, 5)}
    r = {}  # falta la registraduría
    rep = _reporte(t, r)
    g = rep["global"]
    assert g["falta_fuente"] == 1
    assert g["coincide"] == 0 and g["discrepancia"] == 0
    assert g["pct_coincidencia"] is None  # sin comparables


def test_confianza_baja_se_cuenta_por_lectura():
    t = {"1_1_1_1": _fila(10, 5, confianza=0.4)}   # baja
    r = {"1_1_1_1": _fila(10, 5, confianza=0.95)}  # alta
    rep = _reporte(t, r)
    assert rep["global"]["confianza_baja"] == 1


def test_nombre_municipio_callable_se_usa():
    t = {"1_1_1_1": _fila(1, 1)}
    rep = _reporte(t, dict(t), nombre_municipio=lambda m: "Cartagena" if m == "1" else m)
    assert rep["municipios"][0]["nombre"] == "Cartagena"


def test_sin_nombre_municipio_usa_codigo():
    t = {"7_1_1_1": _fila(1, 1)}
    rep = _reporte(t, dict(t))
    assert rep["municipios"][0]["nombre"] == "Municipio 7"


def test_candidatos_y_metadatos_en_el_reporte():
    rep = _reporte({"1_1_1_1": _fila(1, 1)}, {"1_1_1_1": _fila(1, 1)})
    assert rep["candidatos"]["1"] and rep["candidatos"]["2"]
    assert rep["departamento"] == "Bolívar"
    assert "generado" in rep
