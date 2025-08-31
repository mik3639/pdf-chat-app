from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin
from werkzeug.utils import secure_filename
from src.models.user import User, Folder, PDF, db
from src.google_drive import (
    upload_file_to_drive,
    delete_drive_file,
    list_pdfs_in_folder,
    download_file_to_path,
    get_file_metadata,
)
import os
import uuid
import PyPDF2
from io import BytesIO

pdfs_bp = Blueprint('pdfs', __name__)

# Configuración de subida de archivos
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

def require_auth():
    """Decorador para verificar autenticación"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    return None

def allowed_file(filename):
    """Verifica si el archivo tiene una extensión permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
    """Extrae texto de un archivo PDF"""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n"
            
            return text.strip()
    except Exception as e:
        print(f"Error extrayendo texto del PDF: {str(e)}")
        return ""

def ensure_upload_directory():
    """Asegura que el directorio de subida existe"""
    upload_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), UPLOAD_FOLDER)
    if not os.path.exists(upload_path):
        os.makedirs(upload_path)
    return upload_path

@pdfs_bp.route('/folders/<int:folder_id>/pdfs', methods=['POST', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def upload_pdf(folder_id):
    """Sube un PDF a una carpeta específica"""
    # Responder preflight CORS sin requerir autenticación
    if request.method == 'OPTIONS':
        return '', 204
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    user_id = session['user_id']
    
    # Verificar que la carpeta existe y pertenece al usuario
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first()
    if not folder:
        return jsonify({'error': 'Carpeta no encontrada'}), 404
    
    # Verificar que se envió un archivo
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Solo se permiten archivos PDF'}), 400
    
    # Verificar tamaño del archivo
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({'error': 'El archivo es demasiado grande (máximo 16MB)'}), 400
    
    try:
        # Generar nombre único para el archivo
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        
        # Asegurar que el directorio de subida existe
        upload_path = ensure_upload_directory()
        file_path = os.path.join(upload_path, unique_filename)
        
        # Guardar el archivo
        file.save(file_path)
        
        # Extraer texto del PDF
        extracted_text = extract_text_from_pdf(file_path)
        
        # Crear registro en la base de datos
        pdf = PDF(
            filename=unique_filename,
            original_filename=original_filename,
            file_path=file_path,
            content=extracted_text,
            folder_id=folder_id,
            file_size=file_size
        )

        db.session.add(pdf)
        db.session.commit()

        # Subir a Google Drive si la carpeta tiene drive_folder_id
        try:
            if folder.drive_folder_id:
                user = User.query.get(user_id)
                drive_id = upload_file_to_drive(user, folder.drive_folder_id, file_path, filename=original_filename)
                if drive_id:
                    pdf.drive_file_id = drive_id
                    db.session.commit()
        except Exception as e:
            # No fallar toda la operación si la subida a Drive falla
            print(f"Advertencia: No se pudo subir el PDF a Drive: {str(e)}")

        return jsonify(pdf.to_dict()), 201
        
    except Exception as e:
        # Limpiar archivo si hubo error
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        
        return jsonify({'error': f'Error procesando el archivo: {str(e)}'}), 500

@pdfs_bp.route('/pdfs/<int:pdf_id>', methods=['GET'])
def get_pdf(pdf_id):
    """Obtiene información de un PDF específico"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    user_id = session['user_id']
    
    # Verificar que el PDF pertenece al usuario
    pdf = db.session.query(PDF).join(Folder).filter(
        PDF.id == pdf_id,
        Folder.user_id == user_id
    ).first()
    
    if not pdf:
        return jsonify({'error': 'PDF no encontrado'}), 404
    
    pdf_data = pdf.to_dict()
    pdf_data['content_preview'] = pdf.content[:500] + '...' if len(pdf.content) > 500 else pdf.content
    
    return jsonify(pdf_data)

@pdfs_bp.route('/pdfs/<int:pdf_id>', methods=['DELETE'])
def delete_pdf(pdf_id):
    """Elimina un PDF"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    user_id = session['user_id']
    
    # Verificar que el PDF pertenece al usuario
    pdf = db.session.query(PDF).join(Folder).filter(
        PDF.id == pdf_id,
        Folder.user_id == user_id
    ).first()
    
    if not pdf:
        return jsonify({'error': 'PDF no encontrado'}), 404
    
    # Eliminar archivo físico
    if os.path.exists(pdf.file_path):
        try:
            os.remove(pdf.file_path)
        except OSError:
            pass  # Continuar aunque no se pueda eliminar el archivo
    
    # Eliminar de Google Drive si existe
    try:
        if pdf.drive_file_id:
            user = User.query.get(user_id)
            delete_drive_file(user, pdf.drive_file_id)
    except Exception as e:
        print(f"Advertencia: No se pudo eliminar el archivo en Drive: {str(e)}")
    
    db.session.delete(pdf)
    db.session.commit()
    
    return '', 204

@pdfs_bp.route('/folders/<int:folder_id>/search', methods=['POST'])
def search_in_folder(folder_id):
    """Busca texto en los PDFs de una carpeta"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    user_id = session['user_id']
    
    # Verificar que la carpeta pertenece al usuario
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first()
    if not folder:
        return jsonify({'error': 'Carpeta no encontrada'}), 404
    
    data = request.json
    if not data or 'query' not in data:
        return jsonify({'error': 'Consulta de búsqueda requerida'}), 400
    
    query = data['query'].lower()
    results = []
    
    for pdf in folder.pdfs:
        if query in pdf.content.lower():
            # Encontrar contexto alrededor de la coincidencia
            content_lower = pdf.content.lower()
            index = content_lower.find(query)
            
            start = max(0, index - 100)
            end = min(len(pdf.content), index + len(query) + 100)
            context = pdf.content[start:end]
            
            results.append({
                'pdf_id': pdf.id,
                'pdf_name': pdf.original_filename,
                'context': context,
                'match_position': index
            })
    
    return jsonify({
        'query': data['query'],
        'folder_name': folder.name,
        'results': results,
        'total_matches': len(results)
    })


@pdfs_bp.route('/folders/<int:folder_id>/sync-drive', methods=['POST', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def sync_drive_pdfs(folder_id):
    """Importa/sincroniza PDFs desde la carpeta de Drive vinculada a esta carpeta local."""
    if request.method == 'OPTIONS':
        return '', 204
    auth_error = require_auth()
    if auth_error:
        return auth_error

    user_id = session['user_id']
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first()
    if not folder:
        return jsonify({'error': 'Carpeta no encontrada'}), 404
    if not folder.drive_folder_id:
        return jsonify({'error': 'La carpeta no está vinculada a Google Drive'}), 400

    # Obtener usuario para credenciales de Drive
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    try:
        drive_files = list_pdfs_in_folder(user, folder.drive_folder_id) or []
        imported = []
        skipped = []

        # Mapear por drive_file_id existentes para evitar duplicados
        existing_by_drive_id = {p.drive_file_id: p for p in PDF.query.filter(PDF.folder_id == folder.id, PDF.drive_file_id.isnot(None)).all()}

        for f in drive_files:
            drive_id = f.get('id')
            name = f.get('name') or 'archivo.pdf'
            if drive_id in existing_by_drive_id:
                skipped.append({'id': drive_id, 'name': name, 'reason': 'already_imported'})
                continue

            # Descargar archivo a uploads con nombre único
            original_filename = secure_filename(name)
            if not original_filename.lower().endswith('.pdf'):
                original_filename = f"{original_filename}.pdf"
            unique_filename = f"{uuid.uuid4().hex}.pdf"
            upload_path = ensure_upload_directory()
            file_path = os.path.join(upload_path, unique_filename)

            ok = download_file_to_path(user, drive_id, file_path)
            if not ok:
                skipped.append({'id': drive_id, 'name': name, 'reason': 'download_failed'})
                # Limpieza si corresponde
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                continue

            # Calcular tamaño
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None

            # Extraer texto e insertar en DB
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
            imported.append(pdf.to_dict())

        return jsonify({
            'imported_count': len(imported),
            'skipped_count': len(skipped),
            'imported': imported,
            'skipped': skipped
        })
    except Exception as e:
        db.session.rollback()
        print(f"[Drive Sync] Error: {e}")
        return jsonify({'error': str(e)}), 500

