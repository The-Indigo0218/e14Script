"""
Marca (o desmarca) la verificación manual de una acta ya cargada en actas.db.

No gasta API: solo actualiza la fila existente (codigo_mesa, fuente). Pensado
para el flujo de revisión: alguien abre el Excel, ve "PENDIENTE VERIFICAR" en
Verificación manual OCR, confirma a mano contra el PDF/foto original, y deja
constancia acá. La próxima vez que corras comparar.py, el Excel ya muestra
"Verificado" para esa fuente — el estado queda guardado en la base, no en el
Excel (que se regenera cada vez).

Uso:
    python verificar_acta.py actas.db cartagena_21_01_13 --fuente registraduria \
        --nota "Confirmado contra el PDF original, OCR correcto"

    python verificar_acta.py actas.db cartagena_21_01_13 --fuente testigo --deshacer
"""

import sys

from e14.almacen import Almacen
from e14.modelo import FUENTE_REGISTRADURIA, FUENTE_TESTIGO


def _parsear():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    db, codigo = args[0], args[1]
    fuente: str | None = None
    nota: str | None = None
    deshacer = False
    i = 2
    while i < len(args):
        a = args[i]
        if a == "--fuente" and i + 1 < len(args):
            fuente = args[i + 1].lower()
            i += 2
        elif a == "--nota" and i + 1 < len(args):
            nota = args[i + 1]
            i += 2
        elif a == "--deshacer":
            deshacer = True
            i += 1
        else:
            i += 1
    return db, codigo, fuente, nota, deshacer


def main():
    db, codigo, fuente, nota, deshacer = _parsear()
    if fuente not in (FUENTE_REGISTRADURIA, FUENTE_TESTIGO):
        print("❌ Falta --fuente registraduria|testigo")
        sys.exit(1)

    alm = Almacen(db)
    ok = alm.marcar_verificado(codigo, fuente, verificado=not deshacer, nota=nota)
    alm.cerrar()

    if not ok:
        print(f"❌ No existe la fila (codigo_mesa={codigo}, fuente={fuente}) en {db}.")
        print("   Primero corre leer_testigos.py / leer_registraduria.py para esa mesa.")
        sys.exit(1)

    accion = "desmarcada" if deshacer else "marcada como verificada"
    print(f"✅ Mesa {codigo} ({fuente}) {accion} en {db}.")
    if nota:
        print(f"   Nota: {nota}")
    print("   Vuelve a correr comparar.py para que el Excel refleje el cambio.")


if __name__ == "__main__":
    main()
