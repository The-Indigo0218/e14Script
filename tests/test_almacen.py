"""Tests del almacén: persistencia y versionado de re-auditoría."""

from __future__ import annotations

from e14.almacen import Almacen
from e14.modelo import ActaE14, FUENTE_TESTIGO


def _acta(c1, c2):
    return ActaE14(codigo_mesa="1_21_1_13", fuente=FUENTE_TESTIGO, c1=c1, c2=c2)


def test_primera_lectura_no_crea_historial(tmp_path):
    alm = Almacen(tmp_path / "t.db")
    alm.guardar(_acta(10, 5))
    assert alm.num_versiones("1_21_1_13", FUENTE_TESTIGO) == 0
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
