from flask import Blueprint, request, jsonify, session
from src.models.user import User, Folder, db
from src.google_drive import create_drive_folder, delete_drive_folder

folders_bp = Blueprint("folders", __name__)

# =========================
# Listar carpetas del usuario
# =========================
@folders_bp.route("/folders", methods=["GET"])
def list_folders():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No autenticado"}), 401
    folders = Folder.query.filter_by(user_id=user_id).all()
    return jsonify([f.to_dict() for f in folders])

# =========================
# Crear carpeta nueva
# =========================
@folders_bp.route("/folders", methods=["POST"])
def create_folder():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No autenticado"}), 401

    data = request.get_json()
    folder_name = data.get("name")
    if not folder_name:
        return jsonify({"error": "Nombre de carpeta requerido"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    try:
        drive_id = create_drive_folder(user, folder_name)
        if not drive_id:
            return jsonify({"error": "Error al crear carpeta en Google Drive -1"}), 500

        folder = Folder(name=folder_name, user_id=user_id, drive_folder_id=drive_id)
        db.session.add(folder)
        db.session.commit()
        return jsonify(folder.to_dict()), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400


# =========================
# Eliminar carpeta
# =========================
@folders_bp.route("/folders/<int:folder_id>", methods=["DELETE"])
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
