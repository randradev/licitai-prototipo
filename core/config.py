# -*- coding: utf-8 -*-
"""
Módulo: Configuración Central (config)
-------------------------------------
Reúne en un solo lugar las variables de entorno y las constantes de negocio
que antes estaban dispersas (o fijas) en distintos módulos.

Todas las rutas relativas se resuelven contra la raíz del proyecto, de modo
que el comportamiento no depende del directorio desde el que se ejecute.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Raíz del proyecto (carpeta que contiene main.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Cargar .env desde la raíz, independiente del directorio de trabajo
load_dotenv(PROJECT_ROOT / ".env")


def _env_int(nombre, por_defecto):
    """Leer un entero desde el entorno, usando el valor por defecto si es inválido."""
    try:
        return int(os.getenv(nombre, por_defecto))
    except (TypeError, ValueError):
        return por_defecto


def _env_bool(nombre, por_defecto):
    """Leer un booleano desde el entorno ('true', '1', 'si', 'yes')."""
    valor = os.getenv(nombre)
    if valor is None or valor.strip() == "":
        return por_defecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes")


def ruta_db():
    """
    Resolver la ruta de la base de datos SQLite.

    Se lee en cada llamada (no al importar) para que las pruebas puedan
    redefinir DATABASE_PATH.
    """
    ruta = Path(os.getenv("DATABASE_PATH") or "data/mp_database.db")
    if not ruta.is_absolute():
        ruta = PROJECT_ROOT / ruta
    return str(ruta)


# --- Pipeline ---
MAX_PROCESAR = _env_int("LICITAI_MAX_PROCESAR", 5)    # Intentos de procesamiento por ejecución
MAX_INTENTOS = _env_int("LICITAI_MAX_INTENTOS", 3)    # Fallos tolerados antes de pasar a 'error'
PAUSA_ENTRE_LICITACIONES = _env_int("LICITAI_PAUSA_SEGUNDOS", 5)

# --- Red / Selenium ---
HTTP_TIMEOUT = _env_int("LICITAI_HTTP_TIMEOUT", 30)
SELENIUM_HEADLESS = _env_bool("LICITAI_HEADLESS", True)
SELENIUM_PAGE_TIMEOUT = _env_int("LICITAI_PAGE_TIMEOUT", 60)

# --- IA ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3-flash-preview"
IA_MAX_CHARS = _env_int("LICITAI_IA_MAX_CHARS", 40000)  # Límite del corpus enviado al modelo

# --- Escala del score (única para prompt, BD, consola y UI) ---
SCORE_MIN = 1
SCORE_MAX = 10
UMBRAL_DESCARTE = 5   # score < UMBRAL_DESCARTE => la IA debe justificar el descarte
UMBRAL_ALTO = 7       # score >= UMBRAL_ALTO => 🟢
UMBRAL_MEDIO = 4      # score >= UMBRAL_MEDIO => 🟡, menor => 🔴
