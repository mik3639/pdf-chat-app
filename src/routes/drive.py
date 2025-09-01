# src/routes/drive.py
import os
import uuid
import os.path
from flask import Blueprint, jsonify, request, session, redirect
from flask_cors import cross_origin

from src.models.user import User, db
from src.models.user import PDF, Folder  # ajusta import si tus modelos están en otro módulo

from src.routes.auth import login as auth_login, client_config, SCOPES, GOOGLE_REDIRECT_URI  # reutiliza generación de auth_url
from google_auth_oauthlib.flow import Flow

from src.google_drive import (
    get_file_metadata,
    list_pdfs_in_folder,
    download_file_to_path,
)

# Reutiliza utilidades de PDFs (ya las tienes)
from src.routes.pdfs import ensure_upload_directory, extract_text_from_pdf

drive_bp = Blueprint("drive", __name__)

@drive_bp.route("/status", methods=["GET"])
@cross_origin(supports_credentials=True)
def drive_status():
    # conectado si hay sesión y credenciales de Drive guardadas
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"connected": False}), 200
    user = User.query.get(user_id)
    creds = user.get_drive_credentials() if user else None
    return jsonify({"connected": bool(creds)}), 200

@drive_bp.route("/auth", methods=["GET"])
@cross_origin(supports_credentials=True)
def drive_auth():
    # Si es navegación directa (no fetch), redirige a Google inmediatamente.
    accept = request.headers.get("Accept", "")
    sec_fetch_mode = request.headers.get("Sec-Fetch-Mode", "")
    wants_redirect = (
        request.args.get("redirect") == "1"
        or "text/html" in accept
        or sec_fetch_mode == "navigate"
    )

    if wants_redirect:
        flow = Flow.from_client_config(client_config, scopes=SCOPES)
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        session["oauth_state"] = state
        return redirect(auth_url)

    # Caso AJAX: devolver { auth_url }
    return auth_login()

@drive_bp.route("/import-folder", methods=["POST", "OPTIONS"])
@cross_origin(supports_credentials=True)
def import_folder():
    if request.method == "OPTIONS":
        return "", 204

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No autenticado"}), 401
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    data = request.get_json(silent=True) or {}
    drive_folder_id = data.get("drive_folder_id") or data.get("driveFolderId")
    overwrite = bool(data.get("overwrite", True))
    if not drive_folder_id:
        return jsonify({"error": "drive_folder_id requerido"}), 400

    # Nombre desde Drive si no llega
    name = (data.get("name") or data.get("folderName") or "").strip()
    if not name:
        meta = get_file_metadata(user, drive_folder_id, fields="id, name, mimeType")
        if not meta or meta.get("mimeType") != "application/vnd.google-apps.folder":
            return jsonify({"error": "El id no corresponde a una carpeta"}), 400
        name = meta.get("name") or "Carpeta de Drive"

    # Crear o reutilizar carpeta local vinculada
    folder = Folder.query.filter_by(user_id=user_id, drive_folder_id=drive_folder_id).first()
    if not folder:
        folder = Folder(name=name, user_id=user_id, drive_folder_id=drive_folder_id)
        db.session.add(folder)
        db.session.commit()

    # Evitar duplicados por drive_file_id
    existing_ids = {p.drive_file_id for p in folder.pdfs if p.drive_file_id}
    drive_files = list_pdfs_in_folder(user, drive_folder_id) or []

    imported_count = 0
    for f in drive_files:
        drive_id = f.get("id")
        file_name = (f.get("name") or "archivo.pdf").strip() or "archivo.pdf"
        if not drive_id:
            continue
        if not overwrite and drive_id in existing_ids:
            continue
        if drive_id in existing_ids:
            continue  # si quieres sobreescribir, aquí podrías eliminar y recrear

        # Descargar y registrar
        original_filename = file_name if file_name.lower().endswith(".pdf") else f"{file_name}.pdf"
        unique_filename = f"{uuid.uuid4().hex}.pdf"
        upload_path = ensure_upload_directory()
        file_path = os.path.join(upload_path, unique_filename)

        if not download_file_to_path(user, drive_id, file_path):
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            continue

        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None
        extracted_text = extract_text_from_pdf(file_path)

        pdf = PDF(
            filename=unique_filename,
            original_filename=original_filename,
            file_path=file_path,
            content=extracted_text,
            folder_id=folder.id,
            file_size=file_size,
            drive_file_id=drive_id,
        )
        db.session.add(pdf)
        db.session.commit()
        imported_count += 1

    resp = folder.to_dict()
    resp["imported_count"] = imported_count
    return jsonify(resp), 200