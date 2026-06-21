"""Tests del almacén: persistencia y versionado de re-auditoría."""

from __future__ import annotations

import sqlite3

from e14.almacen import Almacen, _TODAS
from e14.modelo import ActaE14, FUENTE_TESTIGO

# Columnas agregadas en este pliego de cambios (las que _migrar_columnas() debe
# poder sumarle a una base vieja que no las tenía).
_COLUMNAS_NUEVAS = {
    "copias_en_evidencia", "verificado_manualmente", "notas_verificacion",
    "numero_kit", "civ", "confianza_kit", "confianza_civ",
}
_COLUMNAS_VIEJAS = [c for c in _TODAS if c not in _COLUMNAS_NUEVAS]


def _acta(c1, c2):
    return ActaE14(codigo_mesa="1_21_1_13", fuente=FUENTE_TESTIGO, c1=c1, c2=c2)


def test_primera_lectura_no_crea_historial(tmp_path):
    alm = Almacen(tmp_path / "t.db")
    alm.guardar(_acta(10, 5))
    assert alm.num_versiones("1_21_1_13", FUENTE_TESTIGO) == 0
    alm.cerrar()


def test_civ_numerico_se_guarda_como_texto_no_como_entero(tmp_path):
    """Bug real: civ puramente numérico (ej. '4098007') caía en columna INTEGER
    en bases nuevas y SQLite lo coercionaba a int, perdiendo que es texto."""
    alm = Almacen(tmp_path / "t.db")
    acta = ActaE14(codigo_mesa="1_21_1_13", fuente=FUENTE_TESTIGO,
                  numero_kit="40,980", civ="4098007")
    alm.guardar(acta)
    fila = alm.leer_por_fuente(FUENTE_TESTIGO)["1_21_1_13"]
    assert fila["civ"] == "4098007"
    assert isinstance(fila["civ"], str)
    alm.cerrar()


def test_archiva_sin_romper_en_db_vieja_sin_columnas_kit_civ(tmp_path):
    """Bug real: actas_historial no se migraba como actas, así que re-auditar una
    mesa de una base creada ANTES de agregar numero_kit/civ rompía al archivar."""
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    cols_actas = ", ".join(f"{c} TEXT" for c in _COLUMNAS_VIEJAS)
    con.execute(
        f"CREATE TABLE actas ({cols_actas}, PRIMARY KEY (codigo_mesa, fuente))"
    )
    cols_hist = ", ".join(f"{c} TEXT" for c in _COLUMNAS_VIEJAS)
    con.execute(
        f"CREATE TABLE actas_historial (version INTEGER, archivado_en TEXT, {cols_hist}, "
        "PRIMARY KEY (codigo_mesa, fuente, version))"
    )
    con.execute("INSERT INTO actas (codigo_mesa, fuente, c1, c2) VALUES (?, ?, ?, ?)",
               ("1_21_1_13", FUENTE_TESTIGO, 10, 5))
    con.commit()
    con.close()

    alm = Almacen(ruta)  # debe migrar ambas tablas sin tocar lo ya guardado
    alm.guardar(_acta(20, 8))  # re-auditar: dispara _archivar() sobre la versión vieja
    hist = alm.historial("1_21_1_13", FUENTE_TESTIGO)
    assert len(hist) == 1
    assert (int(hist[0]["c1"]), int(hist[0]["c2"])) == (10, 5)
    alm.cerrar()


def test_reauditar_archiva_version_anterior(tmp_path):
    alm = Almacen(tmp_path / "t.db")
    alm.guardar(_acta(10, 5))   # v actual: 10/5
    alm.guardar(_acta(20, 8))   # sobrescribe: archiva 10/5

    # La actual quedó con los nuevos valores.
    actual = alm.leer_por_fuente(FUENTE_TESTIGO)["1_21_1_13"]
    assert (actual["c1"], actual["c2"]) == (20, 8)

    # El historial guardó la versión anterior (10/5) como versión 1.
    hist = alm.historial("1_21_1_13", FUENTE_TESTIGO)
    assert len(hist) == 1
    assert hist[0]["version"] == 1
    assert (int(hist[0]["c1"]), int(hist[0]["c2"])) == (10, 5)
    assert hist[0]["archivado_en"]  # timestamp presente
    alm.cerrar()


def test_varias_reauditorias_incrementan_version(tmp_path):
    alm = Almacen(tmp_path / "t.db")
    alm.guardar(_acta(10, 5))
    alm.guardar(_acta(20, 8))
    alm.guardar(_acta(30, 9))
    hist = alm.historial("1_21_1_13", FUENTE_TESTIGO)
    assert [h["version"] for h in hist] == [1, 2]
    assert [(int(h["c1"]), int(h["c2"])) for h in hist] == [(10, 5), (20, 8)]
    assert alm.num_versiones("1_21_1_13", FUENTE_TESTIGO) == 2
    alm.cerrar()


def test_reauditar_conserva_verificacion_manual(tmp_path):
    alm = Almacen(tmp_path / "t.db")
    alm.guardar(_acta(10, 5))
    alm.marcar_verificado("1_21_1_13", FUENTE_TESTIGO, True, nota="revisado a mano")
    alm.guardar(_acta(20, 8))  # re-auditar no debe borrar la verificación
    actual = alm.leer_por_fuente(FUENTE_TESTIGO)["1_21_1_13"]
    assert actual["verificado_manualmente"] == 1
    assert actual["notas_verificacion"] == "revisado a mano"
    alm.cerrar()


def test_historial_persiste_entre_aperturas(tmp_path):
    ruta = tmp_path / "t.db"
    alm = Almacen(ruta)
    alm.guardar(_acta(10, 5))
    alm.guardar(_acta(20, 8))
    alm.cerrar()
    # Reabrir la DB: el historial sigue ahí.
    alm2 = Almacen(ruta)
    assert alm2.num_versiones("1_21_1_13", FUENTE_TESTIGO) == 1
    alm2.cerrar()
