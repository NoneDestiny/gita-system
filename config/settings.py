import os
import dj_database_url
from pathlib import Path
from dotenv import load_dotenv

# Cargar las variables del archivo .env
load_dotenv()



# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Reemplazar la SECRET_KEY quemada por la variable de entorno:
SECRET_KEY = os.getenv('SECRET_KEY', 'una-clave-insegura-por-defecto-para-desarrollo')

# Reemplazar DEBUG por la variable de entorno:
DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost,testserver').split(',') if h.strip()
]

RENDER_EXTERNAL_HOSTNAME = os.getenv('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

    # Permitir el dominio de Render para que no te bloquee los POST (CSRF)
CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cloudinary_storage',
    'cloudinary',
    'users',
    'catalogos',
    'tickets',
    'equipos',
    'inventario',

]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database Configuration (Local y Producción)
DATABASES = {
    'default': dj_database_url.config(
        # 1. Si existe DATABASE_URL (en Render), la usa (Supabase).
        # 2. Si NO existe (en tu PC local), usa sqlite3 por defecto.
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=0 
    )
}

# 2. Esta línea es OBLIGATORIA para Supabase Transaction Pooler
DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es-ve'
TIME_ZONE = 'America/Caracas'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles') # Render necesita esto para collectstatic



# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Indicar a Django que use nuestro CustomUser en todo el sistema
AUTH_USER_MODEL = 'users.CustomUser'

# Backends de autenticación (soporta Username, Correo y Cédula con control de bloqueo)
AUTHENTICATION_BACKENDS = [
    'users.backends.MultiFieldAuthBackend',
]

LOGIN_REDIRECT_URL = '/admin/'
LOGOUT_REDIRECT_URL = '/login/'

# Configuración para archivos multimedia subidos por los usuarios (Evidencias)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ==============================================================================
# CONFIGURACIÓN DE CORREO ELECTRÓNICO (SMTP GMAIL)
# ==============================================================================
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'GITA System <manuelp67werewolf@gmail.com>')

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ==============================================================================
# CONFIGURACIÓN DE CLOUDINARY (EVIDENCIAS MULTIMEDIA)
# ==============================================================================
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
}

# Configuración moderna de Django 4.2+ para usar Cloudinary como almacenamiento por defecto
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

