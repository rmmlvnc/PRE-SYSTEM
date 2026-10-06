"""
Django settings for denguewatch project.

DengueWatch:
AI-Assisted Predictive Dengue Surveillance and
Hotspot Analytics System in Iligan City
"""

from pathlib import Path
import os


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# SECURITY
# ============================================================

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-development-only-change-before-deployment'
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        'DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1'
    ).split(',')
    if host.strip()
]

# A development server is commonly reached by an Expo app on another device on
# the same Wi-Fi network.  Keep production host validation explicit, while
# allowing that local development workflow without a code edit.
if DEBUG and not os.environ.get('DJANGO_ALLOWED_HOSTS'):
    ALLOWED_HOSTS = ['*']


# ============================================================
# APPLICATIONS
# ============================================================

INSTALLED_APPS = [

    # Django built-in apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    

    # DengueWatch application
    'monitoring.apps.MonitoringConfig',
]


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',

    'monitoring.middleware.DevelopmentCorsMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',

    'django.middleware.common.CommonMiddleware',

    'django.middleware.csrf.CsrfViewMiddleware',

    'django.contrib.auth.middleware.AuthenticationMiddleware',

    'django.contrib.messages.middleware.MessageMiddleware',

    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Expo web runs on a separate localhost origin during development.
CORS_ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get(
        'CORS_ALLOWED_ORIGINS', 'http://localhost:8081,http://127.0.0.1:8081'
    ).split(',')
    if origin.strip()
}


# ============================================================
# URL CONFIGURATION
# ============================================================

ROOT_URLCONF = 'denguewatch.urls'


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        'DIRS': [
            BASE_DIR / 'templates',
        ],

        'APP_DIRS': True,

        'OPTIONS': {
            'context_processors': [

                'django.template.context_processors.request',

                'django.contrib.auth.context_processors.auth',

                'django.contrib.messages.context_processors.messages',
                'monitoring.context_processors.current_account',
            ],
        },
    },
]


# ============================================================
# WSGI
# ============================================================

WSGI_APPLICATION = 'denguewatch.wsgi.application'


# ============================================================
# DATABASE
# ============================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# ============================================================
# PASSWORD VALIDATION
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME':
        'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },

    {
        'NAME':
        'django.contrib.auth.password_validation.MinimumLengthValidator',
    },

    {
        'NAME':
        'django.contrib.auth.password_validation.CommonPasswordValidator',
    },

    {
        'NAME':
        'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ============================================================
# INTERNATIONALIZATION
# ============================================================

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Manila'

USE_I18N = True

USE_TZ = True


# ============================================================
# STATIC FILES
# ============================================================

STATIC_URL = 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

AUTH_USER_MODEL = 'monitoring.UserAccount'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

STATIC_ROOT = BASE_DIR / 'staticfiles'


# ============================================================
# MEDIA FILES
# ============================================================

MEDIA_URL = 'media/'

MEDIA_ROOT = BASE_DIR / 'media'


# ============================================================
# DJANGO AUTHENTICATION
# ============================================================

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'


# ============================================================
# SESSION SETTINGS
# ============================================================

SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours

SESSION_EXPIRE_AT_BROWSER_CLOSE = False


# ============================================================
# DEFAULT PRIMARY KEY
# ============================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============================================================
# DENGUEWATCH APPLICATION SETTINGS
# ============================================================

# Google Maps API Key
# Replace this with your actual key later.
GOOGLE_MAPS_API_KEY = os.environ.get(
    'GOOGLE_MAPS_API_KEY',
    ''
)


# ============================================================
# FIREBASE SETTINGS
# ============================================================

# Firebase service account file
FIREBASE_CREDENTIALS = BASE_DIR / 'firebase' / 'serviceAccountKey.json'


# Firebase project ID
FIREBASE_PROJECT_ID = os.environ.get(
    'FIREBASE_PROJECT_ID',
    ''
)


# ============================================================
# MACHINE LEARNING SETTINGS
# ============================================================

ML_MODEL_PATH = (
    BASE_DIR
    / 'monitoring'
    / 'ml'
    / 'random_forest.pkl'
)


# ============================================================
# DENGUE RISK LEVELS
# ============================================================

DENGUE_RISK_LEVELS = {
    'LOW': 'Low',
    'MODERATE': 'Moderate',
    'HIGH': 'High',
}


# ============================================================
# EMAIL SETTINGS
# ============================================================

EMAIL_BACKEND = (
    'django.core.mail.backends.console.EmailBackend'
)


# ============================================================
# SECURITY SETTINGS FOR DEVELOPMENT
# ============================================================

CSRF_COOKIE_HTTPONLY = False

SESSION_COOKIE_HTTPONLY = True

X_FRAME_OPTIONS = 'SAMEORIGIN'
