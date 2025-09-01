import os
import sys
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# Cargar variables de entorno primero
load_dotenv()

# Añadir directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Importaciones después de configurar el path
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from flask_session import Session
from src.models.user import db
from src.routes.user import user_bp
from src.routes.auth import auth_bp
from src.routes.folders import folders_bp
from src.routes.pdfs import pdfs_bp
from src.routes.chat import chat_bp
from authlib.integrations.flask_client import OAuth

def create_app():
    # Crear aplicación Flask
    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "static")
    )

    # Configuración básica
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "clave-secreta-por-defecto-cambiar-en-produccion")
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_USE_SIGNER"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "None"
    # Asegurar cookies seguras cuando se usa HTTPS (requerido para SameSite=None)
    _frontend_env = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    _base_env = os.getenv("BASE_URL", "").rstrip("/")
    _uses_https = _frontend_env.startswith("https://") or _base_env.startswith("https://")
    app.config["SESSION_COOKIE_SECURE"] = _uses_https
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    
    # Configuración de la base de datos (usar src/database/app.db)
    DB_PATH = os.path.join(os.path.dirname(__file__), "database", "app.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Inicializar extensiones
    db.init_app(app)
    Session(app)
    # Configurar CORS (normalizando FRONTEND_URL para evitar slash final) y asegurar que los preflight incluyan headers
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    allowed_origins = [
        frontend_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://pdf-chat-frontend-v9ud.onrender.com",
    ]
    CORS(
        app,
        supports_credentials=True,
        resources={
            r"/api/*": {
                "origins": allowed_origins,
                "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "expose_headers": ["Content-Type"],
            }
        },
        vary_header=True,
        always_send=True,
    )

    # Configurar OAuth
    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        access_token_url="https://oauth2.googleapis.com/token",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        api_base_url="https://www.googleapis.com/oauth2/v3/",
        client_kwargs={
            "scope": "openid email profile https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/drive.file"
        },
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration"
    )

    # Registrar blueprints (prefijo unificado /api)
    app.register_blueprint(user_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(folders_bp, url_prefix="/api")
    app.register_blueprint(pdfs_bp, url_prefix="/api")
    app.register_blueprint(chat_bp, url_prefix="/api")
    # Registrar Drive con import local seguro para evitar NameError en despliegue
    try:
        from src.routes.drive import drive_bp as _drive_bp
        app.register_blueprint(_drive_bp, url_prefix="/api/drive")
    except Exception as e:
        print(f"[Init] Aviso: no se pudo registrar drive_bp: {e}")

    # Middleware para manejar correctamente los encabezados detrás de un proxy
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )

    return app

# Crear la aplicación
app = create_app()

# Crear tablas de la base de datos
with app.app_context():
    from sqlalchemy import text
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    db_path = db_uri.replace("sqlite:///", "") if db_uri.startswith("sqlite:///") else ""
    if db_path:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db.create_all()
    # Lightweight migration: ensure 'drive_file_id' exists on 'pdf'
    try:
        if db_uri.startswith("sqlite"):
            with db.engine.connect() as conn:
                result = conn.execute(text("PRAGMA table_info(pdf)"))
                col_names = [row[1] for row in result]
                if 'drive_file_id' not in col_names:
                    conn.execute(text("ALTER TABLE pdf ADD COLUMN drive_file_id VARCHAR(255)"))
                    print("[DB Migration] Columna drive_file_id agregada a tabla pdf")
                # Ensure 'last_drive_sync_at' exists on 'folder'
                result2 = conn.execute(text("PRAGMA table_info(folder)"))
                folder_cols = [row[1] for row in result2]
                if 'last_drive_sync_at' not in folder_cols:
                    conn.execute(text("ALTER TABLE folder ADD COLUMN last_drive_sync_at DATETIME"))
                    print("[DB Migration] Columna last_drive_sync_at agregada a tabla folder")
    except Exception as e:
        # Log but do not crash the app
        print(f"[DB Migration] Aviso: no se pudo actualizar la columna drive_file_id: {e}")

# Ruta para servir archivos estáticos
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    static_folder = app.static_folder
    if not static_folder:
        return jsonify({"error": "Static folder not configured"}), 500

    if path != "" and os.path.exists(os.path.join(static_folder, path)):
        return send_from_directory(static_folder, path)

    index_path = os.path.join(static_folder, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(static_folder, "index.html")

    return jsonify({"error": "Not found"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.getenv("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
