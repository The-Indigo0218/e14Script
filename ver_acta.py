"""
Ver qué contiene la base de datos SIN volver a llamar a la API.

Útil después de leer solo la Registraduría: revisas los votos guardados y luego
cargas el testigo para comparar.

Uso:
    python ver_acta.py [actas.db]
    python ver_acta.py actas.db --fuente registraduria
    python ver_acta.py actas.db --fuente testigo --mesa 21_01_13
"""

import sys
from pathlib import Path

from e14.almacen import Almacen
from e14.informe import imprimir_contenido_acta
from e14.modelo import FUENTE_REGISTRADURIA, FUENTE_TESTIGO


def _parsear():
    db = "actas.db"
    fuente: str | None = None
    mesa: str | None = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--fuente" and i + 1 < len(args):
            fuente = args[i + 1].lower()
            i += 2
        elif a == "--mesa" and i + 1 < len(args):
            mesa = args[i + 1]
            i += 2
        elif a.endswith(".db"):
            db = a
            i += 1
        else:
            i += 1
    return db, fuente, mesa


def main():
    db, fuente, mesa = _parsear()
    if not Path(db).exists():
        print(f"❌ No existe {db}. Primero corre leer_registraduria.py")
        sys.exit(1)

    alm = Almacen(db)
    fuentes = [fuente] if fuente else [FUENTE_REGISTRADURIA, FUENTE_TESTIGO]
    encontradas = 0

    for f in fuentes:
        if f not in (FUENTE_REGISTRADURIA, FUENTE_TESTIGO):
            print(f"❌ Fuente inválida: {f} (usa registraduria o testigo)")
            alm.cerrar()
            sys.exit(1)
        filas = alm.leer_por_fuente(f)
        if mesa:
            filas = {k: v for k, v in filas.items() if k == mesa}
        if not filas:
            etiqueta = "Registraduría" if f == FUENTE_REGISTRADURIA else "Testigo"
            print(f"⚠️  Sin actas de {etiqueta} en {db}" + (f" para mesa {mesa}" if mesa else ""))
            continue
        for codigo in sorted(filas):
            encontradas += 1
            titulo = (
                f"REGISTRADURÍA — mesa {codigo}"
                if f == FUENTE_REGISTRADURIA
                else f"TESTIGO — mesa {codigo}"
            )
            imprimir_contenido_acta(filas[codigo], titulo=titulo)

    reg = alm.leer_por_fuente(FUENTE_REGISTRADURIA)
    test = alm.leer_por_fuente(FUENTE_TESTIGO)
    alm.cerrar()

    if encontradas == 0:
        sys.exit(1)

    if reg and not test:
        print("💡 Ya tienes la oficial. Cuando puedas gastar 1 llamada OCR:")
        for c in sorted(reg):
            print(f"   python leer_testigos.py datos/testigos/{c}_testigo.pdf actas.db --tipo claveros --solo-pagina-1")
        print("   python comparar.py actas.db comparacion.xlsx")
    elif reg and test:
        print("💡 Ambas fuentes en la base. Comparar con:")
        print("   python comparar.py actas.db comparacion.xlsx")


if __name__ == "__main__":
    main()
