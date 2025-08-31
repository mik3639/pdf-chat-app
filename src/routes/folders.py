from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin
from src.models.user import User, Folder, db
from src.google_drive import create_drive_folder, delete_drive_folder

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
        folders = Folder.query.filter_by(user_id=user_id).all()
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
