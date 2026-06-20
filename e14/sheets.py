"""
Cliente de Google Sheets — panel maestro de resultados subidos por el equipo.

Reutiliza las mismas credenciales OAuth de `e14/drive.py` (`autenticar()`);
aísla las llamadas a la API de Sheets igual que `e14/drive.py` aísla Drive y
`e14/ocr.py` aísla los modelos de OCR.

La hoja "Panel" funciona como cola de revisión: `subir_resultados.py` agrega
una fila por cada subida (estado "Pendiente"); una persona marca la columna
"Aprobado" a mano en la hoja (edición normal de Sheets, en tiempo real); y
`consolidar_resultados.py` solo mergea las filas aprobadas, marcándolas luego
como "Mergeado" para no repetir el trabajo.
"""

from __future__ import annotations

ENCABEZADO = [
    "Persona", "Fecha", "Municipio", "Zona", "Puesto", "Mesas leídas",
    "Coinciden", "Discrepancia", "Confianza baja", "Archivo Drive (ID)",
    "Aprobado", "Estado",
]
_HOJA = "Panel"


def construir_servicio(creds):
    """Cliente de la API de Sheets v4 ya autenticado."""
    from googleapiclient.discovery import build
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def asegurar_encabezado(servicio, hoja_id: str) -> None:
    """Crea la fila de encabezado en la hoja 'Panel' si todavía no existe (idempotente)."""
    resp = servicio.spreadsheets().values().get(
        spreadsheetId=hoja_id, range=f"{_HOJA}!A1:L1",
    ).execute()
    if resp.get("values"):
        return
    servicio.spreadsheets().values().update(
        spreadsheetId=hoja_id, range=f"{_HOJA}!A1",
        valueInputOption="RAW", body={"values": [ENCABEZADO]},
    ).execute()


def agregar_fila(servicio, hoja_id: str, fila: list) -> None:
    """Agrega una fila nueva al final de la hoja 'Panel' (una subida = una fila)."""
    servicio.spreadsheets().values().append(
        spreadsheetId=hoja_id, range=f"{_HOJA}!A1",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [fila]},
    ).execute()


def leer_filas(servicio, hoja_id: str) -> list[dict]:
    """
    Todas las filas de datos (sin el encabezado) como dicts {columna: valor}.
    Cada dict trae además "_indice_fila" (el número de fila real en la hoja,
    1-based, para poder escribirle de vuelta con `marcar_estado`).
    """
    resp = servicio.spreadsheets().values().get(
        spreadsheetId=hoja_id, range=f"{_HOJA}!A2:L",
    ).execute()
    filas = []
    for i, valores in enumerate(resp.get("values", [])):
        valores = list(valores) + [""] * (len(ENCABEZADO) - len(valores))
        fila = dict(zip(ENCABEZADO, valores))
        fila["_indice_fila"] = i + 2  # +2: la hoja empieza en 1 y la fila 1 es el encabezado
        filas.append(fila)
    return filas


def marcar_estado(servicio, hoja_id: str, indice_fila: int, estado: str) -> None:
    """Escribe la columna 'Estado' de una fila específica (ej. 'Mergeado')."""
    col = chr(ord("A") + ENCABEZADO.index("Estado"))
    servicio.spreadsheets().values().update(
        spreadsheetId=hoja_id, range=f"{_HOJA}!{col}{indice_fila}",
        valueInputOption="RAW", body={"values": [[estado]]},
    ).execute()
