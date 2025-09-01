import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from io import BytesIO

def get_drive_service(user):
    creds_data = user.get_drive_credentials()
    if not creds_data:
        raise Exception("El usuario no tiene credenciales de Google Drive - 99.")
    creds = Credentials.from_authorized_user_info(creds_data)
    service = build('drive', 'v3', credentials=creds)
    return service

def create_drive_folder(user, folder_name):
    service = get_drive_service(user)
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    try:
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')
    except HttpError as error:
        print(f"Error al crear carpeta en Drive: {error}")
        return None

def delete_drive_folder(user, folder_id):
    service = get_drive_service(user)
    try:
        service.files().delete(fileId=folder_id).execute()
        return True
    except HttpError as error:
        print(f"Error al eliminar carpeta en Drive: {error}")
        return False

def upload_file_to_drive(user, folder_id, file_path, filename=None):
    service = get_drive_service(user)
    file_metadata = {
        'name': filename if filename else os.path.basename(file_path),
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)
    try:
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except HttpError as error:
        print(f"Error al subir archivo a Drive: {error}")
        return None

def delete_drive_file(user, file_id):
    service = get_drive_service(user)
    try:
        service.files().delete(fileId=file_id).execute()
        return True
    except HttpError as error:
        print(f"Error al eliminar archivo en Drive: {error}")
        return False

def list_drive_folders(user, parent_id=None, query_text=None, page_size=100):
    """Lista carpetas de Drive del usuario. Si parent_id es None, usa 'root'."""
    service = get_drive_service(user)
    q_parts = ["mimeType = 'application/vnd.google-apps.folder'", "trashed = false"]
    if parent_id is None:
        parent_id = 'root'
    if parent_id:
        q_parts.append(f"'{parent_id}' in parents")
    if query_text:
        # Búsqueda por nombre (contains) escapando comillas simples
        safe = query_text.replace("'", "\\'")
        q_parts.append(f"name contains '{safe}'")
    q = ' and '.join(q_parts)
    try:
        results = service.files().list(q=q, spaces='drive', fields="files(id, name)", pageSize=page_size).execute()
        return results.get('files', [])
    except HttpError as error:
        print(f"Error listando carpetas en Drive: {error}")
        return []

def list_pdfs_in_folder(user, folder_id, page_size=200):
    """Lista archivos PDF dentro de una carpeta de Drive."""
    service = get_drive_service(user)
    q = f"'{folder_id}' in parents and mimeType = 'application/pdf' and trashed = false"
    try:
        results = service.files().list(q=q, spaces='drive', fields="files(id, name, mimeType, size)", pageSize=page_size).execute()
        return results.get('files', [])
    except HttpError as error:
        print(f"Error listando PDFs en carpeta de Drive: {error}")
        return []

def list_pdfs_in_folder_recursive(user, folder_id, page_size=200):
    """
    Lista todos los PDFs dentro de una carpeta de Drive y sus subcarpetas (recursivo).
    Devuelve una lista de dicts con al menos: id, name, mimeType, size.
    """
    service = get_drive_service(user)

    def list_children(fid, mime_filter=None):
        q_parts = [f"'{fid}' in parents", "trashed = false"]
        if mime_filter:
            q_parts.append(mime_filter)
        q = ' and '.join(q_parts)
        items = []
        page_token = None
        while True:
            try:
                resp = service.files().list(
                    q=q,
                    spaces='drive',
                    fields="nextPageToken, files(id, name, mimeType, size)",
                    pageSize=page_size,
                    pageToken=page_token,
                ).execute()
                items.extend(resp.get('files', []))
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
            except HttpError as error:
                print(f"Error listando hijos en Drive: {error}")
                break
        return items

    all_pdfs = []
    # PDFs en la carpeta actual
    all_pdfs.extend(list_children(folder_id, "mimeType = 'application/pdf'"))
    # Subcarpetas
    subfolders = list_children(folder_id, "mimeType = 'application/vnd.google-apps.folder'")
    for sf in subfolders:
        sub_id = sf.get('id')
        if not sub_id:
            continue
        all_pdfs.extend(list_pdfs_in_folder_recursive(user, sub_id, page_size))
    return all_pdfs

def get_file_metadata(user, file_id, fields="id, name, mimeType, size"):
    service = get_drive_service(user)
    try:
        return service.files().get(fileId=file_id, fields=fields).execute()
    except HttpError as error:
        print(f"Error obteniendo metadatos del archivo Drive: {error}")
        return None

def download_file_to_path(user, file_id, dest_path):
    """Descarga un archivo de Drive al path indicado."""
    service = get_drive_service(user)
    request = service.files().get_media(fileId=file_id)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    try:
        while not done:
            status, done = downloader.next_chunk()
        with open(dest_path, 'wb') as f:
            f.write(fh.getvalue())
        return True
    except HttpError as error:
        print(f"Error descargando archivo de Drive: {error}")
        return False
