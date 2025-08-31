from flask import Flask
from src.models.user import db, User, Folder, PDF, Conversation, Message

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pdf_chat_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    # Elimina las tablas existentes (solo si quieres reiniciar la DB)
    # db.drop_all()

    # Crear todas las tablas según los modelos
    db.create_all()
    print("✅ Base de datos inicializada con todas las tablas y columnas correctas")
