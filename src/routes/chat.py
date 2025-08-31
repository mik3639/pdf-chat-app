from flask import Blueprint, request, jsonify, session
from src.models.user import User, Folder, PDF, Conversation, Message, db
from src.services.simple_ai_service import ai_service
import os
import json

chat_bp = Blueprint('chat', __name__)

def require_auth():
    """Decorador para verificar autenticación"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    return None

def get_folder_content(folder_ids, user_id):
    """Obtiene el contenido de texto de las carpetas seleccionadas"""
    if not folder_ids:
        return ""
    
    content = []
    folders = Folder.query.filter(
        Folder.id.in_(folder_ids),
        Folder.user_id == user_id
    ).all()
    
    for folder in folders:
        content.append(f"\n=== CARPETA: {folder.name} ===\n")
        for pdf in folder.pdfs:
            content.append(f"\n--- DOCUMENTO: {pdf.original_filename} ---\n")
            content.append(pdf.content)
            content.append("\n")
    
    return "\n".join(content)

@chat_bp.route('/ai-info', methods=['GET'])
def get_ai_info():
    """Obtiene información sobre el proveedor de IA actual"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    return jsonify(ai_service.get_provider_info())

@chat_bp.route('/conversations', methods=['GET'])
def get_conversations():
    """Obtiene todas las conversaciones del usuario"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    user_id = session['user_id']
    conversations = Conversation.query.filter_by(user_id=user_id).order_by(
        Conversation.updated_at.desc()
    ).all()
    
    return jsonify([conv.to_dict() for conv in conversations])

@chat_bp.route('/conversations', methods=['POST'])
def create_conversation():
    """Crea una nueva conversación"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    data = request.json or {}
    user_id = session['user_id']
    
    conversation = Conversation(
        user_id=user_id,
        title=data.get('title', 'Nueva conversación')
    )
    
    db.session.add(conversation)
    db.session.commit()
    
    return jsonify(conversation.to_dict()), 201

@chat_bp.route('/conversations/<int:conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    """Obtiene una conversación específica con sus mensajes"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    user_id = session['user_id']
    conversation = Conversation.query.filter_by(
        id=conversation_id, 
        user_id=user_id
    ).first()
    
    if not conversation:
        return jsonify({'error': 'Conversación no encontrada'}), 404
    
    conversation_data = conversation.to_dict()
    # Ordenar mensajes en memoria
    conversation_data['messages'] = [
        msg.to_dict() for msg in sorted(conversation.messages, key=lambda m: m.timestamp)
    ]
    
    return jsonify(conversation_data)

@chat_bp.route('/conversations/<int:conversation_id>/messages', methods=['POST'])
def send_message(conversation_id):
    """Envía un mensaje en una conversación y obtiene respuesta de IA"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    data = request.json
    if not data or 'content' not in data:
        return jsonify({'error': 'Contenido del mensaje requerido'}), 400
    
    user_id = session['user_id']
    conversation = Conversation.query.filter_by(
        id=conversation_id, 
        user_id=user_id
    ).first()
    
    if not conversation:
        return jsonify({'error': 'Conversación no encontrada'}), 404
    
    try:
        # Crear mensaje del usuario
        user_message = Message(
            conversation_id=conversation_id,
            content=data['content'],
            is_user=True,
            folder_ids=','.join(map(str, data.get('folder_ids', []))) if data.get('folder_ids') else None
        )
        
        db.session.add(user_message)
        
        # Obtener contenido de las carpetas seleccionadas
        folder_ids = data.get('folder_ids', [])
        context = get_folder_content(folder_ids, user_id)
        
        # Obtener historial de la conversación y ordenar en memoria
        conversation_history = sorted(conversation.messages, key=lambda m: m.timestamp)
        
        # Generar respuesta de IA usando el servicio configurable
        ai_response = ai_service.generate_response(
            data['content'], 
            context, 
            conversation_history
        )
        
        # Crear mensaje de IA
        ai_message = Message(
            conversation_id=conversation_id,
            content=ai_response,
            is_user=False,
            folder_ids=','.join(map(str, folder_ids)) if folder_ids else None
        )
        
        db.session.add(ai_message)
        
        # Actualizar título de la conversación si es el primer mensaje
        if len(conversation_history) == 0:
            # Generar título basado en la primera pregunta
            title = data['content'][:50] + '...' if len(data['content']) > 50 else data['content']
            conversation.title = title
        
        # Actualizar timestamp de la conversación
        from datetime import datetime
        conversation.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'user_message': user_message.to_dict(),
            'ai_message': ai_message.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error procesando el mensaje: {str(e)}'}), 500

@chat_bp.route('/conversations/<int:conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    """Elimina una conversación"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    user_id = session['user_id']
    conversation = Conversation.query.filter_by(
        id=conversation_id, 
        user_id=user_id
    ).first()
    
    if not conversation:
        return jsonify({'error': 'Conversación no encontrada'}), 404
    
    db.session.delete(conversation)
    db.session.commit()
    
    return '', 204

@chat_bp.route('/folders-summary', methods=['GET'])
def get_folders_summary():
    """Obtiene un resumen de las carpetas del usuario para el chat"""
    auth_error = require_auth()
    if auth_error:
        return auth_error
    
    user_id = session['user_id']
    folders = Folder.query.filter_by(user_id=user_id).all()
    
    folders_data = []
    for folder in folders:
        folder_info = folder.to_dict()
        folder_info['pdfs'] = [{'id': pdf.id, 'name': pdf.original_filename} 
                              for pdf in folder.pdfs]
        folders_data.append(folder_info)
    
    return jsonify(folders_data)
