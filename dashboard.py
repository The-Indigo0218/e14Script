"""
Dashboard local de control — progreso, panel de aprobación y cola de revisión,
todo en una sola pantalla que corrés en tu máquina (no se expone a internet).

Pensado para que el jefe vea el estado en tiempo real mirando tu pantalla (o
tu mismo navegador, ej. compartiendo pantalla) mientras corre la auditoría.

No reemplaza nada de lo que ya existe (`cobertura.py`, el panel de Sheets,
`verificar_acta.py`): junta esa misma información en una vista y agrega botones
para "Aprobar" filas del panel y "Confirmar"/"Corregir" casillas de confianza
baja, sin tener que editar la hoja o correr comandos sueltos por cada una.

Uso:
    python dashboard.py --db actas.db [--catalogo "Mesa a Mesa.xlsx"] \
        [--datos datos] [--hoja <ID_HOJA_MAESTRA>] [--puerto 5000]

Si no pasás --hoja, la sección del panel de aprobación simplemente no aparece
(podés usar el dashboard solo para la cola de revisión y cobertura local).
"""

from __future__ import annotations

import argparse

from flask import Flask, redirect, render_template_string, request, url_for

from e14.almacen import Almacen
from e14.catalogo import cargar_catalogo
from e14.cobertura import cobertura_lote
from e14.comparador import comparar, resumen
from e14.mesa import municipio_zona_puesto_mesa_desde_codigo
from e14.modelo import FUENTE_REGISTRADURIA, FUENTE_TESTIGO
from e14.ocr import UMBRAL_REVISION

app = Flask(__name__)
_CFG: dict = {}


def _filas_para_revisar(alm: Almacen) -> list[dict]:
    """Filas con necesita_revision=1 y todavía sin verificar a mano."""
    filas = alm.todas_las_filas()
    pendientes = [
        f for f in filas
        if str(f.get("necesita_revision")) in ("1", "True", "true")
        and str(f.get("verificado_manualmente")) not in ("1", "True", "true")
    ]
    pendientes.sort(key=lambda f: (f.get("codigo_mesa") or "", f.get("fuente") or ""))
    return pendientes


def _cobertura_por_municipio() -> list[dict]:
    """Cobertura de cada municipio que YA tiene carpeta de lote en --datos."""
    if not _CFG.get("catalogo"):
        return []
    catalogo = _CFG["catalogo"]
    datos = _CFG["datos"]
    if not datos.is_dir():
        return []
    filas = []
    for mun in catalogo.municipios():
        from e14.catalogo import nombre_carpeta_lote
        if not (datos / nombre_carpeta_lote(catalogo, mun)).is_dir():
            continue
        cob = cobertura_lote(catalogo, mun, datos)
        r = cob.resumen()
        filas.append({
            "municipio": cob.municipio_nombre, "total": r["esperadas"],
            "listas": r["listas"], "solo_testigo": r["solo_testigo"],
            "solo_registraduria": r["solo_registraduria"],
            "faltan_ambas": r["faltan_ambas"], "fuera_de_catalogo": r["fuera_de_catalogo"],
            "pct": cob.pct_listas(),
        })
    return filas


def _comparacion_por_puesto(testigo: dict, registraduria: dict) -> list[dict]:
    """Igual que el resumen global, pero agrupado por municipio·zona·puesto."""
    comparaciones = comparar(testigo, registraduria)
    grupos: dict[tuple, dict] = {}
    for comp in comparaciones:
        meta = municipio_zona_puesto_mesa_desde_codigo(comp.codigo_mesa)
        if not meta:
            continue
        clave = (meta["municipio"], meta["zona"], meta["puesto"])
        g = grupos.setdefault(clave, {
            "municipio": meta["municipio"], "zona": meta["zona"], "puesto": meta["puesto"],
            "total": 0, "coincide": 0, "discrepancia": 0, "confianza_baja": 0,
        })
        g["total"] += 1
        if comp.estado == "COINCIDE":
            g["coincide"] += 1
        elif comp.estado == "DISCREPANCIA":
            g["discrepancia"] += 1
        for conf in (comp.confianza_testigo, comp.confianza_registraduria):
            if conf is not None and conf < UMBRAL_REVISION:
                g["confianza_baja"] += 1

    def _clave_orden(g: dict):
        def _n(v):
            return int(v) if str(v).isdigit() else v
        return (g["municipio"], _n(g["zona"]), _n(g["puesto"]))

    return sorted(grupos.values(), key=_clave_orden)


def _panel_sheets() -> list[dict]:
    if not _CFG.get("hoja"):
        return []
    from e14.drive import autenticar, construir_servicio as construir_drive
    from e14.sheets import construir_servicio as construir_sheets, leer_filas
    creds = autenticar(_CFG["credenciales"], _CFG["token"])
    servicio = construir_sheets(creds)
    return leer_filas(servicio, _CFG["hoja"])


_PLANTILLA = """
<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Auditoría E-14 — Dashboard</title>
<style>
body { font-family: system-ui, sans-serif; margin: 2rem; color: #222; }
h1 { margin-bottom: 0; } h2 { margin-top: 2.5rem; border-bottom: 2px solid #ddd; padding-bottom: .3rem; }
table { border-collapse: collapse; width: 100%; margin-top: .5rem; }
th, td { border: 1px solid #ddd; padding: .4rem .6rem; text-align: left; font-size: .92rem; }
th { background: #f4f4f4; }
.ok { color: #1a7f37; font-weight: 600; }
.warn { color: #b35900; font-weight: 600; }
.bad { color: #c0392b; font-weight: 600; }
.muted { color: #888; }
button { cursor: pointer; padding: .25rem .7rem; border-radius: 4px; border: 1px solid #ccc; background: #fafafa; }
button:hover { background: #eee; }
.vacio { color: #888; font-style: italic; padding: .5rem 0; }
</style></head><body>

<h1>Auditoría E-14 — Dashboard</h1>
<p class="muted">Se refresca al recargar la página (no es automático). Corriendo solo en tu máquina.</p>

<h2>Cobertura por municipio</h2>
{% if cobertura %}
<table><tr><th>Municipio</th><th>Total mesas</th><th>Listas</th><th>Solo testigo</th>
<th>Solo registraduría</th><th>Faltan ambas</th><th>Fuera de catálogo</th><th>% listas</th></tr>
{% for c in cobertura %}
<tr><td>{{ c.municipio }}</td><td>{{ c.total }}</td><td class="ok">{{ c.listas }}</td>
<td class="warn">{{ c.solo_testigo }}</td><td class="warn">{{ c.solo_registraduria }}</td>
<td class="bad">{{ c.faltan_ambas }}</td><td class="bad">{{ c.fuera_de_catalogo }}</td>
<td>{{ "%.0f"|format(c.pct) }}%</td></tr>
{% endfor %}</table>
{% else %}<p class="vacio">Sin --catalogo, o todavía no hay carpetas de lote en --datos.</p>{% endif %}

<h2>Comparación (base local: {{ db }})</h2>
<p>Total mesas: <b>{{ comp.total }}</b> ·
<span class="ok">Coinciden: {{ comp.COINCIDE }}</span> ·
<span class="bad">Discrepancia: {{ comp.DISCREPANCIA }}</span> ·
Falta fuente: {{ comp.FALTA_FUENTE }} ·
Confianza baja: <span class="warn">{{ confianza_baja }}</span></p>

<h2>Comparación por puesto</h2>
{% if por_puesto %}
<table><tr><th>Municipio</th><th>Zona</th><th>Puesto</th><th>Total</th>
<th>Coinciden</th><th>Discrepancia</th><th>Confianza baja</th></tr>
{% for g in por_puesto %}
<tr><td>{{ g.municipio }}</td><td>{{ g.zona }}</td><td>{{ g.puesto }}</td><td>{{ g.total }}</td>
<td class="ok">{{ g.coincide }}</td><td class="bad">{{ g.discrepancia }}</td>
<td class="warn">{{ g.confianza_baja }}</td></tr>
{% endfor %}</table>
{% else %}<p class="vacio">Sin mesas cargadas todavía en la base local.</p>{% endif %}

<h2>Panel maestro (Sheets)</h2>
{% if panel %}
<table><tr><th>Persona</th><th>Fecha</th><th>Municipio</th><th>Zona</th><th>Puesto</th>
<th>Mesas</th><th>Coinciden</th><th>Discrepancia</th><th>Conf. baja</th>
<th>Aprobado</th><th>Estado</th><th></th></tr>
{% for f in panel %}
<tr><td>{{ f.Persona }}</td><td>{{ f.Fecha }}</td><td>{{ f.Municipio }}</td><td>{{ f.Zona }}</td>
<td>{{ f.Puesto }}</td><td>{{ f["Mesas leídas"] }}</td><td>{{ f.Coinciden }}</td>
<td>{{ f.Discrepancia }}</td><td>{{ f["Confianza baja"] }}</td>
<td>{{ f.Aprobado }}</td><td>{{ f.Estado }}</td>
<td>{% if f.Aprobado != "Sí" %}
<form method="post" action="{{ url_for('aprobar', indice_fila=f._indice_fila) }}">
<button type="submit">Aprobar</button></form>{% endif %}</td></tr>
{% endfor %}</table>
{% else %}<p class="vacio">Sin --hoja, o todavía no hay filas subidas.</p>{% endif %}

<h2>Cola de revisión manual ({{ revision|length }} pendientes)</h2>
{% if revision %}
{% for r in revision %}
<div style="border:1px solid #ddd; border-radius:6px; padding:.7rem 1rem; margin-bottom:.7rem;">
<b>{{ r.codigo_mesa }}</b> · {{ r.fuente }} · confianza {{ "%.0f"|format((r.confianza|float) * 100) }}%
{% if r.archivo_origen %} · <a href="file://{{ r.archivo_origen }}" target="_blank">abrir archivo original</a>{% endif %}
<p class="muted" style="margin:.3rem 0;">{{ r.notas or "(sin notas)" }}</p>
<form method="post" action="{{ url_for('verificar') }}">
<input type="hidden" name="codigo_mesa" value="{{ r.codigo_mesa }}">
<input type="hidden" name="fuente" value="{{ r.fuente }}">
<input type="text" name="nota" placeholder="Nota de la verificación (opcional)" style="width:50%;">
<button type="submit">Confirmar / corregido</button>
</form></div>
{% endfor %}
{% else %}<p class="vacio">Nada pendiente de revisión manual.</p>{% endif %}

</body></html>
"""


@app.route("/")
def inicio():
    alm = Almacen(str(_CFG["db"]))
    testigo = alm.leer_por_fuente(FUENTE_TESTIGO)
    registraduria = alm.leer_por_fuente(FUENTE_REGISTRADURIA)
    comp = resumen(comparar(testigo, registraduria))
    confianza_baja = sum(
        1 for fila in list(testigo.values()) + list(registraduria.values())
        if fila.get("confianza") is not None and float(fila["confianza"]) < UMBRAL_REVISION
    )
    revision = _filas_para_revisar(alm)
    por_puesto = _comparacion_por_puesto(testigo, registraduria)
    alm.cerrar()
    return render_template_string(
        _PLANTILLA, cobertura=_cobertura_por_municipio(), comp=comp,
        confianza_baja=confianza_baja, panel=_panel_sheets(), revision=revision,
        por_puesto=por_puesto, db=_CFG["db"],
    )


@app.route("/aprobar/<int:indice_fila>", methods=["POST"])
def aprobar(indice_fila: int):
    from e14.drive import autenticar, construir_servicio as construir_drive
    from e14.sheets import construir_servicio as construir_sheets, marcar_aprobado
    creds = autenticar(_CFG["credenciales"], _CFG["token"])
    servicio = construir_sheets(creds)
    marcar_aprobado(servicio, _CFG["hoja"], indice_fila)
    return redirect(url_for("inicio"))


@app.route("/verificar", methods=["POST"])
def verificar():
    alm = Almacen(str(_CFG["db"]))
    alm.marcar_verificado(
        request.form["codigo_mesa"], request.form["fuente"],
        verificado=True, nota=request.form.get("nota") or None,
    )
    alm.cerrar()
    return redirect(url_for("inicio"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default="actas.db")
    p.add_argument("--catalogo", help="Excel 'Mesa a Mesa' (para la sección de cobertura)")
    p.add_argument("--datos", default="datos")
    p.add_argument("--hoja", help="ID de la hoja maestra (para el panel de aprobación)")
    p.add_argument("--credenciales", default="drive_credentials.json")
    p.add_argument("--token", default=".drive_token.json")
    p.add_argument("--host", default="127.0.0.1", help="127.0.0.1 = solo esta máquina")
    p.add_argument("--puerto", type=int, default=5000)
    args = p.parse_args(argv)

    from pathlib import Path
    _CFG["db"] = args.db
    _CFG["catalogo"] = cargar_catalogo(args.catalogo) if args.catalogo else None
    _CFG["datos"] = Path(args.datos)
    _CFG["hoja"] = args.hoja
    _CFG["credenciales"] = args.credenciales
    _CFG["token"] = args.token

    print(f"Dashboard en http://{args.host}:{args.puerto}/  (Ctrl+C para salir)")
    app.run(host=args.host, port=args.puerto, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
