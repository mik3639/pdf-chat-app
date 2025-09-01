from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin
from src.models.user import User, Folder, db
from src.google_drive import (
    create_drive_folder,
    delete_drive_folder,
    list_drive_folders,
    list_pdfs_in_folder,
    get_file_metadata,
)
from src.routes.pdfs import ensure_upload_directory, extract_text_from_pdf
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime, timedelta

folders_bp = Blueprint("folders", __name__)

# =========================
# Listar carpetas del usuario
# =========================
@folders_bp.route("/folders", methods=["GET"])
@cross_origin(supports_credentials=True)
def list_folders():
    try:
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "No autenticado"}), 401
        user = User.query.get(user_id)
        folders = Folder.query.filter_by(user_id=user_id).all()

        # Auto-sync Drive para carpetas vinculadas (throttle)
        now = datetime.utcnow()
        min_interval = timedelta(minutes=3)
        default_max_files = 5

        for folder in folders:
            try:
                if not folder.drive_folder_id:
                    continue
                if folder.last_drive_sync_at and (now - folder.last_drive_sync_at) < min_interval:
                    continue
                # Ajustar límite: primera vez (sincronización inicial) trae más archivos
                max_files_per_folder = 200 if not folder.last_drive_sync_at else default_max_files
                # Mapear existentes por drive_file_id
                existing_ids = {
                    p.drive_file_id for p in folder.pdfs if p.drive_file_id
                }
                drive_files = list_pdfs_in_folder(user, folder.drive_folder_id) or []
                imported_count = 0
                for f in drive_files:
                    if imported_count >= max_files_per_folder:
                        break
                    drive_id = f.get('id')
                    name = f.get('name') or 'archivo.pdf'
                    if not drive_id or drive_id in existing_ids:
                        continue

                    # Descargar y registrar
                    from src.google_drive import download_file_to_path
                    original_filename = secure_filename(name)
                    if not original_filename.lower().endswith('.pdf'):
                        original_filename = f"{original_filename}.pdf"
                    unique_filename = f"{uuid.uuid4().hex}.pdf"
                    upload_path = ensure_upload_directory()
                    file_path = os.path.join(upload_path, unique_filename)

                    if not download_file_to_path(user, drive_id, file_path):
                        # Limpieza si falló descarga
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except OSError:
                                pass
                        continue

                    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None
                    extracted_text = extract_text_from_pdf(file_path)
                    from src.models.user import PDF
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

                folder.last_drive_sync_at = now
                db.session.commit()
            except Exception as sync_err:
                # No romper listado por fallos de sync
                print(f"[AutoSync] Carpeta {folder.id} error: {sync_err}")

        return jsonify([f.to_dict() for f in folders])
    except Exception as e:
        # Log del error para Render
        print(f"[Folders][GET] Error listando carpetas: {e}")
        return jsonify({"error": str(e)}), 500

# =========================
# Crear carpeta nueva
# =========================
@folders_bp.route("/folders", methods=["POST", "OPTIONS"])
@cross_origin(supports_credentials=True)
def create_folder():
    # Preflight CORS
    if request.method == "OPTIONS":
        return "", 204
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No autenticado"}), 401

    data = request.get_json(silent=True) or {}
    folder_name = data.get("name") or data.get("folderName")
    if not folder_name and request.form:
        folder_name = request.form.get("name") or request.form.get("folderName")
    if folder_name and isinstance(folder_name, str):
        folder_name = folder_name.strip()
    if not folder_name:
        return jsonify({"error": "Nombre de carpeta requerido"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    try:
        drive_id = None
        # Intentar crear en Drive, pero no bloquear si falla
        try:
            drive_id = create_drive_folder(user, folder_name)
        except Exception as drive_err:
            # Log silencioso; continuamos sin Drive
            print(f"[Drive] Aviso: no se pudo crear carpeta en Drive: {drive_err}")

        folder = Folder(name=folder_name, user_id=user_id, drive_folder_id=drive_id)
        db.session.add(folder)
        db.session.commit()
        resp = folder.to_dict()
        if not drive_id:
            resp["drive_warning"] = "Carpeta creada solo localmente. Conecta Google Drive para sincronizar."
        return jsonify(resp), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400


# =========================
# Eliminar carpeta
# =========================
@folders_bp.route("/folders/<int:folder_id>", methods=["DELETE"])
@cross_origin(supports_credentials=True)
def delete_folder(folder_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No autenticado"}), 401

    folder = Folder.query.get(folder_id)
    if not folder or folder.user_id != user_id:
        return jsonify({"error": "No autorizado"}), 403

    # Eliminar carpeta de Google Drive si existe
    if folder.drive_folder_id:
        user = User.query.get(user_id)
        deleted = delete_drive_folder(user, folder.drive_folder_id)
        if not deleted:
            return jsonify({"error": "Error al eliminar carpeta en Google Drive"}), 500

    # Eliminar de DB
    db.session.delete(folder)
    db.session.commit()
    return '', 204


# =========================
# Navegar Drive (carpetas)
# =========================
@folders_bp.route("/drive/folders", methods=["GET", "OPTIONS"])
@cross_origin(supports_credentials=True)
def drive_list_folders():
    if request.method == "OPTIONS":
        return "", 204
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No autenticado"}), 401
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    parent_id = request.args.get("parentId")
    q = request.args.get("q")
    # Política de límite:
    # - Con búsqueda (q no vacío): SIEMPRE 'all' para buscar en todas las carpetas
    # - Sin búsqueda: usar ?limit si viene, o 5 por defecto
    if q and q.strip():
        raw_limit = "all"
    else:
        raw_limit = request.args.get("limit", "5")
    try:
        if isinstance(raw_limit, str) and raw_limit.lower() == "all":
            limit = -1
        else:
            limit = int(raw_limit)
            if limit == -1:
                pass  # ilimitado
            elif limit <= 0:
                limit = 20
    except Exception:
        limit = 20
    try:
        # Si hay búsqueda, forzar modo global para encontrar carpetas aunque no estén en las 5 mostradas
        effective_parent = parent_id
        if q and q.strip():
            effective_parent = 'any'

        # Evitar listar todo el Drive cuando se usa búsqueda global sin término
        if (effective_parent or '').lower() == 'any':
            q_norm = (q or '').strip()
            if len(q_norm) < 1:
                return jsonify({
                    "folders": [],
                    "limit": raw_limit,
                    "parentId": effective_parent,
                    "q": q,
                    "note": "Proporciona al menos 1 caracter para buscar en todo el Drive"
                })
        folders = list_drive_folders(user, parent_id=effective_parent, query_text=q, page_size=limit)
        return jsonify({
            "folders": folders,
            "limit": raw_limit,
            "parentId": (effective_parent or "root"),
            "q": q,
            "note": (None if q and q.strip() else "Mostrando las 5 carpetas más recientes. Usa el buscador para encontrar otras.")
        })
    except Exception as e:
        print(f"[Drive][list_folders] {e}")
        return jsonify({"error": str(e)}), 400


# =========================
# Listar PDFs de una carpeta de Drive
# =========================
@folders_bp.route("/drive/folders/<drive_folder_id>/pdfs", methods=["GET", "OPTIONS"])
@cross_origin(supports_credentials=True)
def drive_list_pdfs(drive_folder_id):
    if request.method == "OPTIONS":
        return "", 204
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No autenticado"}), 401
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    try:
        # Enable recursive listing via query param. Default: true
        recursive_param = (request.args.get("recursive", "1") or "").strip().lower()
        recursive = recursive_param in ("1", "true", "yes", "y")

        if recursive:
            files = list_pdfs_in_folder_recursive(user, drive_folder_id)
        else:
            files = list_pdfs_in_folder(user, drive_folder_id)

        return jsonify({"files": files, "recursive": recursive})
    except Exception as e:
        print(f"[Drive][list_pdfs] {e}")
        return jsonify({"error": str(e)}), 400


# =========================
# Vincular una carpeta local a una carpeta de Drive existente
# =========================
@folders_bp.route("/folders/<int:folder_id>/link-drive", methods=["POST", "OPTIONS"])
@cross_origin(supports_credentials=True)
def link_drive_folder(folder_id):
    if request.method == "OPTIONS":
        return "", 204
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No autenticado"}), 401
    folder = Folder.query.get(folder_id)
    if not folder or folder.user_id != user_id:
        return jsonify({"error": "No autorizado"}), 403
    data = request.get_json(silent=True) or {}
    drive_folder_id = data.get("drive_folder_id") or data.get("driveFolderId")
    if not drive_folder_id:
        return jsonify({"error": "drive_folder_id requerido"}), 400
    try:
        folder.drive_folder_id = drive_folder_id
        db.session.commit()
        return jsonify(folder.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# =========================
# Crear carpeta local desde una carpeta de Drive seleccionada
# =========================
@folders_bp.route("/folders/from-drive", methods=["POST", "OPTIONS"])
@cross_origin(supports_credentials=True)
def create_folder_from_drive():
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
    name = (data.get("name") or data.get("folderName") or '').strip()
    if not drive_folder_id:
        return jsonify({"error": "drive_folder_id requerido"}), 400
    # Si no llega nombre, lo tomamos de Drive
    if not name:
        try:
            meta = get_file_metadata(user, drive_folder_id, fields="id, name, mimeType")
            if not meta or meta.get('mimeType') != 'application/vnd.google-apps.folder':
                return jsonify({"error": "El id no corresponde a una carpeta"}), 400
            name = meta.get('name') or 'Carpeta de Drive'
        except Exception as e:
            print(f"[Drive][metadata] {e}")
            name = 'Carpeta de Drive'
    try:
        folder = Folder(name=name, user_id=user_id, drive_folder_id=drive_folder_id)
        db.session.add(folder)
        db.session.commit()
        return jsonify(folder.to_dict()), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400
