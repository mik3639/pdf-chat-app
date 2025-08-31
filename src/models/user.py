from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

# ===============================
# MODELO USUARIO
# ===============================
class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    profile_picture = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Token de Google Drive (JSON serializado)
    google_drive_token = db.Column(db.Text)

    # Relaciones
    folders = db.relationship('Folder', backref='user', lazy=True, cascade='all, delete-orphan')
    conversations = db.relationship('Conversation', backref='user', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self, include_drive_token=False):
        data = {
            'id': self.id,
            'google_id': self.google_id,
            'username': self.username,
            'email': self.email,
            'profile_picture': self.profile_picture,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_drive_token and self.google_drive_token:
            data['google_drive_token'] = json.loads(self.google_drive_token)
        return data

    # ===============================
    # MÉTODOS DRIVE
    # ===============================
    def set_drive_credentials(self, creds_dict):
        """Guarda las credenciales de Google Drive en la base de datos"""
        self.google_drive_token = json.dumps(creds_dict)

    def get_drive_credentials(self):
        """Devuelve las credenciales de Google Drive como dict"""
        if self.google_drive_token:
            return json.loads(self.google_drive_token)
        return None


# ===============================
# MODELO CARPETA
# ===============================
class Folder(db.Model):
    __tablename__ = "folder"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    drive_folder_id = db.Column(db.String(255))

    pdfs = db.relationship('PDF', backref='folder', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Folder {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'pdf_count': len(self.pdfs),
            'drive_folder_id': self.drive_folder_id
        }


# ===============================
# MODELO PDF
# ===============================
class PDF(db.Model):
    __tablename__ = "pdf"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(500), nullable=False)
    file_path = db.Column(db.String(1000), nullable=False)
    content = db.Column(db.Text)
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_size = db.Column(db.Integer)
    drive_file_id = db.Column(db.String(255))

    def __repr__(self):
        return f'<PDF {self.original_filename}>'

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'folder_id': self.folder_id,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'file_size': self.file_size,
            'drive_file_id': self.drive_file_id
        }


# ===============================
# MODELO CONVERSACIÓN
# ===============================
class Conversation(db.Model):
    __tablename__ = "conversation"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(250), default='Nueva conversación')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Conversation {self.title}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'message_count': len(self.messages)
        }


# ===============================
# MODELO MENSAJE
# ===============================
class Message(db.Model):
    __tablename__ = "message"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_user = db.Column(db.Boolean, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    folder_ids = db.Column(db.String(1000))

    def __repr__(self):
        return f'<Message {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'content': self.content,
            'is_user': self.is_user,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'folder_ids': self.folder_ids.split(',') if self.folder_ids else []
        }
