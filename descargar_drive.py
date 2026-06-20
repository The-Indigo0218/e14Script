"""
SCRIPT: trae los E-14 desde Google Drive a las carpetas locales del lote.

No importa cómo el equipo organice las carpetas dentro de Drive: busca
recursivamente bajo la carpeta raíz que le pasés y clasifica cada archivo por
SU NOMBRE (misma convención NuMunicipio_zona_puesto_mesa_<testigo|registraduria>
de siempre). Cada archivo se coloca en datos/<NN_nombre>/{testigos,registraduria}/
según el municipio que el catálogo (el Excel "Mesa a Mesa") dice que le corresponde.

Es idempotente: si el archivo ya está local con el mismo tamaño, no se vuelve a
descargar. Los que no calzan con la nomenclatura se listan al final para que el
equipo los renombre en Drive — no se inventan códigos de mesa.

Primera vez: necesitás drive_credentials.json (OAuth Client ID tipo "Aplicación
de escritorio" de Google Cloud Console). Ver README → "Traer los E-14 desde
Google Drive". Abre el navegador una sola vez para autorizar con tu cuenta de
Google; después queda cacheado en .drive_token.json y no vuelve a pedirlo.

Uso:
    python descargar_drive.py "<excel_catalogo>" --carpeta-drive <ID_CARPETA>
        [--datos datos] [--credenciales drive_credentials.json] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from e14.catalogo import cargar_catalogo, nombre_carpeta_lote
from e14.mesa import codigo_mesa_desde_archivo, fuente_desde_archivo, municipio_zona_puesto_mesa_desde_codigo
from e14.modelo import FUENTE_TESTIGO


def planear_destinos(catalogo, archivos: list, base_datos: Path) -> tuple[list, list]:
    """
    Decide la ruta local de cada ArchivoDrive según su nombre y el catálogo.
    Devuelve (ubicados, sin_clasificar). Función pura (sin red), testeable sola.

    `ubicados` es una lista de (ArchivoDrive, ruta_destino_local).
    `sin_clasificar` son archivos que no calzan con la nomenclatura esperada
    (sin sufijo testigo/registraduria, sin municipio_zona_puesto_mesa, o con un
    municipio que no está en el catálogo) — no se inventan códigos de mesa.
    """
    ubicados: list[tuple[object, Path]] = []
    sin_clasificar: list = []
    for archivo in archivos:
        fuente = fuente_desde_archivo(archivo.nombre)
        codigo = codigo_mesa_desde_archivo(archivo.nombre)
        meta = municipio_zona_puesto_mesa_desde_codigo(codigo)
        if fuente is None or not meta:
            sin_clasificar.append(archivo)
            continue
        try:
            municipio = str(int(meta["municipio"]))  # normaliza ceros a la izquierda
        except ValueError:
            sin_clasificar.append(archivo)
            continue
        if municipio not in catalogo.nombres_municipio:
            sin_clasificar.append(archivo)  # municipio que no existe en el catálogo
            continue
        nombre_lote = nombre_carpeta_lote(catalogo, municipio)
        carpeta_fuente = "testigos" if fuente == FUENTE_TESTIGO else "registraduria"
        destino = base_datos / nombre_lote / carpeta_fuente / archivo.nombre
        ubicados.append((archivo, destino))
    return ubicados, sin_clasificar


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("excel", help="Ruta al Excel 'Mesa a Mesa' de la Registraduría (catálogo)")
    p.add_argument("--carpeta-drive", required=True, help="ID de la carpeta raíz en Drive (de la URL)")
    p.add_argument("--datos", default="datos", help="Carpeta base local (por defecto: datos)")
    p.add_argument("--credenciales", default="drive_credentials.json",
                  help="client_secret.json de OAuth (por defecto: drive_credentials.json)")
    p.add_argument("--token", default=".drive_token.json", help="Caché local de la sesión")
    p.add_argument("--dry-run", action="store_true", help="Solo mostrar qué se descargaría, sin bajar nada")
    args = p.parse_args(argv)

    try:
        catalogo = cargar_catalogo(args.excel)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    from e14.drive import autenticar, construir_servicio, descargar_archivo, listar_archivos_recursivo

    try:
        creds = autenticar(args.credenciales, args.token)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    servicio = construir_servicio(creds)

    print("Buscando archivos en Drive (recursivo, sin importar cómo estén organizadas las carpetas)...")
    archivos = listar_archivos_recursivo(servicio, args.carpeta_drive)
    print(f"  {len(archivos)} archivos encontrados en Drive.")

    base_datos = Path(args.datos)
    ubicados, sin_clasificar = planear_destinos(catalogo, archivos, base_datos)

    nuevos = saltados = errores = 0
    for archivo, destino in ubicados:
        ya_esta = destino.exists() and (archivo.tamano is None or destino.stat().st_size == archivo.tamano)
        if ya_esta:
            saltados += 1
            continue
        if args.dry_run:
            print(f"   [dry-run] {archivo.nombre} -> {destino}")
            nuevos += 1
            continue
        try:
            descargar_archivo(servicio, archivo.id, destino)
            print(f"   ✓ {archivo.nombre} -> {destino}")
            nuevos += 1
        except Exception as e:  # noqa: BLE001 — un archivo malo no debe tumbar el resto
            errores += 1
            print(f"   ⚠ error descargando {archivo.nombre}: {e}", file=sys.stderr)

    print(f"\nNuevos{'(simulados)' if args.dry_run else ''}: {nuevos} · ya estaban: {saltados} · errores: {errores}")
    if sin_clasificar:
        print(f"\n⚠️  {len(sin_clasificar)} archivo(s) en Drive no calzan con la nomenclatura "
              "NuMunicipio_zona_puesto_mesa_<testigo|registraduria> (o el municipio no está "
              "en el catálogo) y se ignoraron — hay que renombrarlos en Drive:")
        for a in sin_clasificar[:30]:
            print(f"   • {a.nombre}")
        if len(sin_clasificar) > 30:
            print(f"   ... y {len(sin_clasificar) - 30} más")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
