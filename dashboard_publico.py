"""
Generador del tablero PÚBLICO de inversores (sitio estático, solo lectura).

Lee la base local (`actas.db`), agrega los resultados con
`e14.reporte_publico` y escribe un sitio estático autocontenido (un solo
`index.html`, sin servidor ni dependencias de red) listo para publicar en
Netlify u otro hosting estático.

A diferencia de `dashboard.py` (control local, con imágenes de los E-14 y panel
de aprobación — NUNCA público), aquí solo salen NÚMEROS agregados por
municipio · zona · puesto: votos por candidato y conteo de discrepancias. No se
publica ninguna imagen, ruta de archivo, KIT/CIV, ni dato de jurados.

Uso:
    python dashboard_publico.py --db actas.db \
        [--catalogo "Mesa a Mesa.xlsx"] [--salida sitio]

Después:
    netlify deploy --prod --dir sitio      # (o arrastrar la carpeta a Netlify)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from e14.almacen import Almacen
from e14.comparador import comparar
from e14.modelo import FUENTE_REGISTRADURIA, FUENTE_TESTIGO
from e14.ocr import UMBRAL_REVISION
from e14.reporte_publico import construir_reporte

PLANTILLA_HTML = Path(__file__).parent / "plantillas" / "tablero_publico.html"
MARCADOR_DATOS = "/*__DATOS__*/"


def _datos_demo() -> tuple[dict, dict, object]:
    """
    Dataset SINTÉTICO y determinista para mostrarles a los inversores cómo se ve
    el tablero lleno mientras llegan los datos reales. NO son resultados reales:
    el reporte se marca `demo=True` y la página muestra un aviso bien visible.
    """
    import random

    rng = random.Random(2026)
    nombres = {
        "1": "Cartagena", "2": "Magangué", "5": "El Carmen de Bolívar",
        "8": "Turbaco", "30": "Arjona",
    }
    testigo: dict[str, dict] = {}
    registraduria: dict[str, dict] = {}
    for mun in nombres:
        for zona in range(1, rng.randint(3, 6)):
            for puesto in range(1, rng.randint(3, 7)):
                for mesa in range(1, rng.randint(5, 11)):
                    cod = f"{mun}_{zona}_{puesto}_{mesa}"
                    c1, c2 = rng.randint(60, 190), rng.randint(60, 190)
                    bl, nu = rng.randint(0, 7), rng.randint(0, 5)
                    conf = 0.96 if rng.random() > 0.07 else 0.5  # ~7% en revisión
                    base = {"c1": c1, "c2": c2, "blanco": bl, "nulos": nu,
                            "no_marcados": 0, "confianza": conf}
                    testigo[cod] = base
                    if rng.random() < 0.11:  # ~11% con discrepancia
                        d = rng.choice([1, 2, 3, 5])
                        registraduria[cod] = {**base, "c1": c1 + d, "confianza": 0.96}
                    else:
                        registraduria[cod] = {**base, "confianza": 0.96}
    return testigo, registraduria, lambda m: nombres.get(m, f"Municipio {m}")


def generar_reporte(db: str, catalogo_excel: str | None = None, demo: bool = False) -> dict:
    """Lee la DB (o genera datos demo) y devuelve el reporte agregado (dict JSON)."""
    if demo:
        testigo, registraduria, nombre_municipio = _datos_demo()
    else:
        alm = Almacen(str(db))
        testigo = alm.leer_por_fuente(FUENTE_TESTIGO)
        registraduria = alm.leer_por_fuente(FUENTE_REGISTRADURIA)
        alm.cerrar()

        nombre_municipio = None
        if catalogo_excel:
            from e14.catalogo import cargar_catalogo
            nombre_municipio = cargar_catalogo(catalogo_excel).nombre_municipio

    reporte = construir_reporte(
        comparar(testigo, registraduria),
        umbral_revision=UMBRAL_REVISION,
        nombre_municipio=nombre_municipio,
        generado=datetime.now(),
    )
    if demo:
        reporte["demo"] = True
    return reporte


def renderizar(reporte: dict) -> str:
    """Inyecta el reporte (JSON) en la plantilla HTML autocontenida."""
    plantilla = PLANTILLA_HTML.read_text(encoding="utf-8")
    datos_json = json.dumps(reporte, ensure_ascii=False)
    return plantilla.replace(MARCADOR_DATOS, datos_json)


def escribir_sitio(reporte: dict, salida: str | Path) -> Path:
    """Escribe el sitio estático en `salida/` y devuelve la ruta del index."""
    carpeta = Path(salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    index = carpeta / "index.html"
    index.write_text(renderizar(reporte), encoding="utf-8")
    # También dejamos el JSON crudo por si se quiere consumir aparte.
    (carpeta / "datos.json").write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return index


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--db", default="actas.db")
    p.add_argument("--catalogo", help="Excel 'Mesa a Mesa' (para nombres de municipio)")
    p.add_argument("--salida", default="sitio", help="Carpeta de salida del sitio estático")
    p.add_argument("--demo", action="store_true",
                   help="Genera datos sintéticos de demostración (con aviso visible en la página)")
    args = p.parse_args(argv)

    reporte = generar_reporte(args.db, args.catalogo, demo=args.demo)
    index = escribir_sitio(reporte, args.salida)

    g = reporte["global"]
    print(f"Sitio generado en {index}" + ("  [DEMO]" if args.demo else ""))
    print(
        f"  {g['mesas']} mesas · {g['coincide']} coinciden · "
        f"{g['discrepancia']} discrepancias · {g['confianza_baja']} en revisión"
    )
    print(f"\nPublicar:  netlify deploy --prod --dir {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
