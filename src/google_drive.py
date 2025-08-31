import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

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
