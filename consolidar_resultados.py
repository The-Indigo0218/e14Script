"""
SCRIPT: mergea a la base maestra SOLO los resultados que alguien aprobó en el
panel de Google Sheets (columna "Aprobado"). Por cada fila aprobada y todavía
no mergeada: descarga el actas.db de esa persona desde Drive, integra sus
filas a la base maestra local (`Almacen.guardar` conserva el versionado de
siempre — si una mesa ya existía, archiva la versión anterior en vez de
perderla) y marca la fila como "Mergeado" para no repetirla en la próxima
corrida.

Nunca mergea una fila sin aprobar: si no está marcada, queda afuera hasta que
alguien la apruebe (o se corrija y se vuelva a subir).

Uso:
    python consolidar_resultados.py actas_maestra.db --carpeta-drive <ID> \
        --hoja <ID_HOJA_MAESTRA> [--dry-run]
"""

from __future__ import annotations

import argparse
import dataclasses
import tempfile
from pathlib import Path

from e14.almacen import Almacen
from e14.modelo import ActaE14

_CAMPOS_ACTA = {f.name for f in dataclasses.fields(ActaE14)}
_APROBADOS = {"si", "sí", "s", "x", "true", "1", "aprobado"}


def _es_aprobado(valor: str) -> bool:
    return valor.strip().lower() in _APROBADOS


def fila_a_acta(fila: dict) -> ActaE14:
    """Reconstruye un ActaE14 desde una fila cruda de `actas` (de cualquier Almacen)."""
    datos = {k: v for k, v in fila.items() if k in _CAMPOS_ACTA}
    datos["necesita_revision"] = bool(fila.get("necesita_revision"))
    datos["verificado_manualmente"] = bool(fila.get("verificado_manualmente"))
    return ActaE14(**datos)


def mergear_db_descargada(alm_maestro: Almacen, ruta_db: Path) -> int:
    """Lee TODAS las filas de un actas.db y las guarda en la base maestra. Devuelve cuántas."""
    alm_origen = Almacen(ruta_db)
    filas = alm_origen.todas_las_filas()
    alm_origen.cerrar()
    for fila in filas:
        alm_maestro.guardar(fila_a_acta(fila))
    return len(filas)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("db", help="Base SQLite maestra donde consolidar (se crea si no existe)")
    p.add_argument("--carpeta-drive", required=True, help="ID de la carpeta de resultados en Drive")
    p.add_argument("--hoja", required=True, help="ID de la hoja de cálculo maestra")
    p.add_argument("--credenciales", default="drive_credentials.json")
    p.add_argument("--token", default=".drive_token.json")
    p.add_argument("--dry-run", action="store_true", help="Solo mostrar qué se mergearía, sin tocar nada")
    args = p.parse_args(argv)

    from e14.drive import autenticar, construir_servicio as construir_drive, descargar_archivo
    from e14.sheets import construir_servicio as construir_sheets, leer_filas, marcar_estado

    try:
        creds = autenticar(args.credenciales, args.token)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    drive = construir_drive(creds)
    sheets = construir_sheets(creds)

    filas = leer_filas(sheets, args.hoja)
    pendientes = [
        f for f in filas
        if _es_aprobado(f.get("Aprobado", "")) and f.get("Estado", "").strip().lower() != "mergeado"
    ]
    if not pendientes:
        print("No hay filas aprobadas pendientes de mergear.")
        return 0

    print(f"{len(pendientes)} fila(s) aprobada(s) pendiente(s) de mergear:")
    for f in pendientes:
        print(f"   • {f['Persona']} ({f['Fecha']}) — {f['Mesas leídas']} mesas, "
              f"{f['Discrepancia']} discrepancias")

    if args.dry_run:
        print("\n[dry-run] No se mergeó nada.")
        return 0

    alm_maestro = Almacen(args.db)
    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        for f in pendientes:
            destino = Path(tmp) / f"{f['Persona']}.db"
            descargar_archivo(drive, f["Archivo Drive (ID)"], destino)
            n = mergear_db_descargada(alm_maestro, destino)
            total += n
            marcar_estado(sheets, args.hoja, f["_indice_fila"], "Mergeado")
            print(f"   ✓ {f['Persona']}: {n} filas mergeadas")
    alm_maestro.cerrar()
    print(f"\nTotal: {total} filas mergeadas de {len(pendientes)} subida(s) aprobada(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
