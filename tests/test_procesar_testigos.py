"""Tests del pase de testigos idempotente (procesar_testigos)."""

from __future__ import annotations

from pathlib import Path

from e14.almacen import Almacen
from e14.modelo import ActaE14, FUENTE_TESTIGO
from procesar_testigos import carpetas_testigos, pendientes, procesar_una_pasada


def _lector_falso(ruta, fuente, codigo) -> ActaE14:
    """No toca disco ni red: devuelve un acta leída con votos de ejemplo."""
    return ActaE14(codigo_mesa=codigo, fuente=fuente, c1=10, c2=5,
                   confianza=0.99, archivo_origen=str(ruta))


def _tocar(carpeta: Path, nombre: str) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre).write_bytes(b"x")


def test_carpetas_testigos_encuentra_raiz_y_municipios(tmp_path):
    _tocar(tmp_path / "testigos", "1_1_1_1_testigo.png")
    _tocar(tmp_path / "01_cartagena" / "testigos", "1_2_3_4_testigo.png")
    (tmp_path / "01_cartagena" / "registraduria").mkdir(parents=True)
    carpetas = carpetas_testigos(tmp_path)
    assert (tmp_path / "testigos") in carpetas
    assert (tmp_path / "01_cartagena" / "testigos") in carpetas
    assert all("registraduria" not in str(c) for c in carpetas)


def test_segunda_pasada_salta_las_ya_cargadas(tmp_path):
    base = tmp_path / "datos"
    _tocar(base / "01_cartagena" / "testigos", "1_1_3_2_testigo.png")
    _tocar(base / "01_cartagena" / "testigos", "1_1_3_3_testigo.png")
    alm = Almacen(tmp_path / "t.db")

    r1 = procesar_una_pasada(base, alm, _lector_falso)
    assert r1["nuevas"] == 2 and r1["saltadas"] == 0

    # Sin archivos nuevos: todo ya está en la base → nada que hacer.
    r2 = procesar_una_pasada(base, alm, _lector_falso)
    assert r2["nuevas"] == 0 and r2["saltadas"] == 2

    # Llega una mesa nueva: solo esa se procesa, las otras se ignoran.
    _tocar(base / "01_cartagena" / "testigos", "1_1_3_4_testigo.png")
    r3 = procesar_una_pasada(base, alm, _lector_falso)
    assert r3["nuevas"] == 1 and r3["saltadas"] == 2
    alm.cerrar()


def test_reauditar_reprocesa_las_ya_cargadas(tmp_path):
    base = tmp_path / "datos"
    _tocar(base / "testigos", "1_1_3_2_testigo.png")
    alm = Almacen(tmp_path / "t.db")
    procesar_una_pasada(base, alm, _lector_falso)
    r = procesar_una_pasada(base, alm, _lector_falso, reauditar=True)
    assert r["nuevas"] == 1 and r["saltadas"] == 0
    alm.cerrar()


def test_pendientes_dedup_por_codigo_normalizado(tmp_path):
    base = tmp_path / "datos"
    # Mismo código con/sin ceros a la izquierda → debe colapsar a una sola tarea.
    _tocar(base / "testigos", "1_21_01_13_testigo.png")
    _tocar(base / "01_cartagena" / "testigos", "1_21_1_13_testigo.png")
    tareas, _ = pendientes(base, ya=set(), reauditar=False)
    assert len(tareas) == 1
