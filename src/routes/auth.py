import os
from flask import Blueprint, request, jsonify, session, redirect
from google.auth.transport import requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from urllib.parse import quote
from src.models.user import User, db

auth_bp = Blueprint("auth", __name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

client_config = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [GOOGLE_REDIRECT_URI],
    }
}

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    # Read all files in Drive (to list PDFs not created by the app)
    "https://www.googleapis.com/auth/drive.readonly",
    # Create/update files the app owns (for optional uploads to the selected folder)
    "https://www.googleapis.com/auth/drive.file"
]

@auth_bp.route("/login", methods=["GET"])
def login():
    """Inicia el flujo de login.
    - Por defecto devuelve JSON con auth_url.
    - Si ?mode=redirect o ?navigate=1, redirige directamente (mejor en móvil).
    """
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    session["oauth_state"] = state
    mode = request.args.get("mode")
    navigate = request.args.get("navigate")
    if (mode and mode.lower() in ("redirect", "navigate")) or navigate == "1":
        return redirect(auth_url)
    return jsonify({"auth_url": auth_url})

@auth_bp.route("/callback", methods=["GET"])
def callback():
    try:
        state = session.get("oauth_state", None)
        request_state = request.args.get("state", None)

        # Algunos navegadores móviles bloquean cookies en redirecciones (pierden la sesión/estado).
        # Si hay mismatch de estado pero tenemos un 'code' de Google, intentamos continuar.
        if state != request_state:
            has_code = bool(request.args.get("code"))
            if not has_code:
                return jsonify({"error": "Estado inválido"}), 400

        flow = Flow.from_client_config(client_config, scopes=SCOPES, state=request_state or state)
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        flow.fetch_token(authorization_response=request.url)

        credentials = flow.credentials
        id_info = id_token.verify_oauth2_token(credentials.id_token, requests.Request(), GOOGLE_CLIENT_ID)

        google_id = id_info["sub"]
        email = id_info.get("email")
        name = id_info.get("name", "Usuario")
        picture = id_info.get("picture", "")

        user = User.query.filter_by(google_id=google_id).first()
        if not user:
            user = User(google_id=google_id, username=name, email=email, profile_picture=picture)
            db.session.add(user)
            db.session.commit()

        # Guardar credenciales de Drive
        user.set_drive_credentials({
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes
        })
        db.session.commit()

        # Guardar sesión
        session["user_id"] = user.id
        session["user_email"] = user.email
        session["user_name"] = user.username

        # Redirigir al frontend (cliente) con HTML/JS para mejorar compatibilidad móvil
        frontend_url = os.getenv("FRONTEND_URL") or ""
        target = (frontend_url.rstrip("/") or "") + "/?login=success"
        html = f"""
        <!DOCTYPE html>
        <html lang=\"es\">
        <head>
          <meta charset=\"utf-8\" />
          <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
          <title>Iniciando sesión…</title>
          <meta http-equiv=\"refresh\" content=\"0;url={target}\" />
          <script>
            // Fallback JS redirect
            window.location.replace('{target}');
          </script>
        </head>
        <body>
          <p>Inicio de sesión correcto. Si no eres redirigido, haz clic <a href=\"{target}\">aquí</a>.</p>
        </body>
        </html>
        """
        return html

    except Exception as e:
        msg_encoded = quote(str(e))
        frontend_url = os.getenv("FRONTEND_URL")
        if "insecure_transport" in str(e):
            if frontend_url:
                return redirect(f"{frontend_url}/?login=success")
            return redirect("/?login=success")
        if frontend_url:
            target = f"{frontend_url.rstrip('/')}/?login=error&message={msg_encoded}"
        else:
            target = f"/?login=error&message={msg_encoded}"
        html = f"""
        <!DOCTYPE html>
        <html lang=\"es\">
        <head>
          <meta charset=\"utf-8\" />
          <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
          <title>Error de autenticación</title>
          <meta http-equiv=\"refresh\" content=\"0;url={target}\" />
          <script>window.location.replace('{target}');</script>
        </head>
        <body>
          <p>No se pudo iniciar sesión. Continúa <a href=\"{target}\">aquí</a>.</p>
        </body>
        </html>
        """
        return html

@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Sesión cerrada exitosamente"})

@auth_bp.route("/check", methods=["GET"])
def check_auth():
    if "user_id" in session:
        return jsonify({
            "authenticated": True,
            "user_id": session["user_id"],
            "user_email": session["user_email"],
            "user_name": session["user_name"]
        })
    else:
        return jsonify({"authenticated": False})
