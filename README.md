# PDF Chat - Conversa con tus documentos

Una aplicación web que permite a los usuarios subir documentos PDF, organizarlos en carpetas y hacer preguntas sobre su contenido usando inteligencia artificial.

## Características

- 🔐 **Autenticación con Google OAuth**: Inicio de sesión seguro con tu cuenta de Google
- 📁 **Gestión de carpetas**: Organiza tus PDFs en carpetas personalizadas
- 📄 **Subida de PDFs**: Sube y procesa documentos PDF automáticamente
- 🤖 **Chat inteligente**: Haz preguntas sobre el contenido de tus documentos
- 🎯 **Selección de contexto**: Elige qué carpetas consultar para cada conversación
- 💬 **Historial de conversaciones**: Guarda y revisa tus conversaciones anteriores
- ⚙️ **IA configurable**: Soporta OpenAI GPT y Google Gemini

## Tecnologías utilizadas

### Backend
- **Flask**: Framework web de Python
- **SQLAlchemy**: ORM para base de datos
- **SQLite**: Base de datos ligera
- **PyPDF2**: Extracción de texto de PDFs
- **Google OAuth**: Autenticación de usuarios
- **OpenAI API / Gemini API**: Inteligencia artificial

### Frontend
- **React**: Biblioteca de interfaz de usuario
- **Tailwind CSS**: Framework de estilos
- **shadcn/ui**: Componentes de interfaz
- **Axios**: Cliente HTTP
- **Lucide React**: Iconos

## Instalación y configuración

### Prerrequisitos
- Python 3.11+
- Node.js 18+
- Cuenta de Google Cloud (para OAuth)
- API Key de OpenAI o Gemini

### Configuración del backend

1. **Clona el repositorio**:
   ```bash
   git clone <url-del-repositorio>
   cd pdf-chat-app
   ```

2. **Crea un entorno virtual**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. **Instala las dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configura las variables de entorno**:
   Crea un archivo `.env` en la raíz del proyecto:
   ```env
   # Google OAuth Configuration
   GOOGLE_CLIENT_ID=tu_google_client_id
   GOOGLE_CLIENT_SECRET=tu_google_client_secret

   # AI Configuration
   AI_PROVIDER=openai
   # Opciones: openai, gemini

   # OpenAI Configuration
   OPENAI_API_KEY=tu_openai_api_key
   OPENAI_API_BASE=https://api.openai.com/v1

   # Gemini Configuration
   GEMINI_API_KEY=tu_gemini_api_key

   # Flask Configuration
   SECRET_KEY=tu_clave_secreta_segura
   FLASK_ENV=development
   ```

5. **Ejecuta la aplicación**:
   ```bash
   python src/main.py
   ```

### Configuración del frontend (desarrollo)

1. **Navega al directorio del frontend**:
   ```bash
   cd ../pdf-chat-frontend
   ```

2. **Instala las dependencias**:
   ```bash
   pnpm install
   ```

3. **Ejecuta el servidor de desarrollo**:
   ```bash
   pnpm run dev
   ```

### Configuración de Google OAuth

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto o selecciona uno existente
3. Habilita la Google+ API
4. Crea credenciales OAuth 2.0:
   - Tipo de aplicación: Aplicación web
   - URIs de redirección autorizados: `http://localhost:5000/api/auth/callback`
5. Copia el Client ID y Client Secret al archivo `.env`

### Configuración de APIs de IA

#### OpenAI
1. Ve a [OpenAI Platform](https://platform.openai.com/)
2. Crea una cuenta y obtén tu API key
3. Agrega la API key al archivo `.env`

#### Gemini
1. Ve a [Google AI Studio](https://makersuite.google.com/)
2. Crea una cuenta y obtén tu API key
3. Agrega la API key al archivo `.env`
4. Cambia `AI_PROVIDER=gemini` en el archivo `.env`

## Estructura del proyecto

```
pdf-chat-app/
├── src/
│   ├── models/          # Modelos de base de datos
│   ├── routes/          # Rutas de la API
│   ├── services/        # Servicios (IA, etc.)
│   ├── static/          # Archivos estáticos del frontend
│   └── main.py          # Punto de entrada de la aplicación
├── uploads/             # Archivos PDF subidos
├── requirements.txt     # Dependencias de Python
└── .env                # Variables de entorno
```

## API Endpoints

### Autenticación
- `GET /api/auth/login` - Iniciar sesión con Google
- `GET /api/auth/callback` - Callback de OAuth
- `POST /api/auth/logout` - Cerrar sesión
- `GET /api/auth/user` - Obtener usuario actual
- `GET /api/auth/check` - Verificar autenticación

### Carpetas
- `GET /api/folders` - Listar carpetas del usuario
- `POST /api/folders` - Crear nueva carpeta
- `GET /api/folders/{id}` - Obtener carpeta específica
- `PUT /api/folders/{id}` - Actualizar carpeta
- `DELETE /api/folders/{id}` - Eliminar carpeta

### PDFs
- `POST /api/folders/{id}/pdfs` - Subir PDF a carpeta
- `GET /api/pdfs/{id}` - Obtener información de PDF
- `DELETE /api/pdfs/{id}` - Eliminar PDF
- `POST /api/folders/{id}/search` - Buscar en PDFs de carpeta

### Chat
- `GET /api/conversations` - Listar conversaciones
- `POST /api/conversations` - Crear conversación
- `GET /api/conversations/{id}` - Obtener conversación
- `POST /api/conversations/{id}/messages` - Enviar mensaje
- `DELETE /api/conversations/{id}` - Eliminar conversación
- `GET /api/ai-info` - Información del proveedor de IA
- `GET /api/folders-summary` - Resumen de carpetas para chat

## Despliegue

### Despliegue local
La aplicación incluye el frontend construido en el directorio `static/`, por lo que solo necesitas ejecutar el backend:

```bash
python src/main.py
```

### Despliegue en producción
Para despliegue en producción, considera usar:
- **Gunicorn** como servidor WSGI
- **Nginx** como proxy reverso
- **PostgreSQL** en lugar de SQLite
- Variables de entorno de producción

## Contribuir

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## Licencia

Este proyecto está bajo la Licencia MIT. Ver `LICENSE` para más detalles.

## Soporte

Si tienes problemas o preguntas:
1. Revisa la documentación
2. Busca en los issues existentes
3. Crea un nuevo issue con detalles del problema

## Roadmap

- [ ] Soporte para más formatos de documentos (Word, PowerPoint)
- [ ] Búsqueda avanzada en documentos
- [ ] Compartir conversaciones
- [ ] API para integraciones externas
- [ ] Modo offline
- [ ] Análisis de documentos con gráficos

