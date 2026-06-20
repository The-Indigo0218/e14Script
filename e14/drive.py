"""
Cliente de Google Drive — trae los E-14 a las carpetas locales del lote.

No importa cómo el equipo organice las carpetas en Drive: se busca
recursivamente bajo una carpeta raíz y cada archivo se clasifica por SU
NOMBRE (misma convención NuMunicipio_zona_puesto_mesa_<testigo|registraduria>
de siempre, ver `e14/mesa.py`). La estructura de subcarpetas en Drive no se
usa para nada — es solo para que el equipo que sube los archivos se organice
como quiera.

Autenticación: OAuth de escritorio. Cada persona entra con SU PROPIA cuenta
de Google (no se comparte ninguna clave); el dueño del Drive simplemente
comparte la carpeta como cualquier carpeta de Drive (Editor para quien sube
archivos, Lector para quien solo los descarga). La primera vez abre el
navegador para autorizar; después el token queda cacheado localmente y se
refresca solo — no vuelve a pedir login.

Requiere las librerías de Google (ver requirements.txt):
    google-api-python-client, google-auth-httplib2, google-auth-oauthlib
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Solo lectura: este programa nunca necesita escribir en el Drive de nadie.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_MIME_CARPETA = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class ArchivoDrive:
    id: str
    nombre: str
    tamano: int | None  # bytes; None si Drive no lo reporta (poco común en PDFs/fotos)


def autenticar(credenciales: str | Path = "drive_credentials.json",
              token: str | Path = ".drive_token.json"):
    """
    Devuelve credenciales OAuth válidas, refrescando o pidiendo login si hace falta.

    `credenciales` es el client_secret.json de un OAuth Client ID tipo
    "Aplicación de escritorio" (Google Cloud Console → APIs y servicios →
    Credenciales). `token` es el caché local de la sesión ya autorizada — se
    crea solo en el primer login, NO se versiona (ver .gitignore).
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    ruta_token = Path(token)
    creds = None
    if ruta_token.exists():
        creds = Credentials.from_authorized_user_file(str(ruta_token), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            ruta_cred = Path(credenciales)
            if not ruta_cred.exists():
                raise FileNotFoundError(
                    f"Falta {ruta_cred}: descargá el client_secret.json de tu OAuth "
                    "Client ID (Google Cloud Console → Credenciales → Crear "
                    "credenciales → ID de cliente de OAuth → tipo 'Aplicación de "
                    "escritorio') y guardalo con ese nombre. Ver README → "
                    "'Traer los E-14 desde Google Drive'."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(ruta_cred), SCOPES)
            creds = flow.run_local_server(port=0)
        ruta_token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def construir_servicio(creds):
    """Cliente de la API de Drive v3 ya autenticado."""
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def listar_archivos_recursivo(servicio, carpeta_id: str) -> list[ArchivoDrive]:
    """
    Todos los archivos (no carpetas) bajo `carpeta_id`, bajando por cualquier
    nivel de subcarpetas — el equipo del scrapper puede organizar Drive como
    quiera, esto los encuentra igual.
    """
    archivos: list[ArchivoDrive] = []
    pendientes = [carpeta_id]
    while pendientes:
        actual = pendientes.pop()
        token_pagina = None
        while True:
            resp = servicio.files().list(
                q=f"'{actual}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=token_pagina,
                pageSize=1000,
            ).execute()
            for f in resp.get("files", []):
                if f.get("mimeType") == _MIME_CARPETA:
                    pendientes.append(f["id"])
                else:
                    tam = int(f["size"]) if f.get("size") else None
                    archivos.append(ArchivoDrive(id=f["id"], nombre=f["name"], tamano=tam))
            token_pagina = resp.get("nextPageToken")
            if not token_pagina:
                break
    return archivos


def descargar_archivo(servicio, archivo_id: str, destino: Path) -> None:
    """Descarga un archivo de Drive al disco local, creando carpetas si hace falta."""
    from googleapiclient.http import MediaIoBaseDownload

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "wb") as fh:
        peticion = servicio.files().get_media(fileId=archivo_id)
        descargador = MediaIoBaseDownload(fh, peticion)
        listo = False
        while not listo:
            _, listo = descargador.next_chunk()
