# -*- coding: utf-8 -*-
"""
Módulo: Configuración Central (config)
-------------------------------------
Reúne en un solo lugar las variables de entorno y las constantes de negocio
que antes estaban dispersas (o fijas) en distintos módulos.

Todas las rutas relativas se resuelven contra la raíz del proyecto, de modo
que el comportamiento no depende del directorio desde el que se ejecute.
"""

import logging
import os
import sys
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
    return str(_resolver_ruta(os.getenv("DATABASE_PATH") or "data/mp_database.db"))


def _resolver_ruta(valor):
    ruta = Path(valor)
    return ruta if ruta.is_absolute() else PROJECT_ROOT / ruta


class _ConsolaHandler(logging.StreamHandler):
    """Escribe en el sys.stdout vigente (pytest y Streamlit lo reemplazan en tiempo de ejecución)."""

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, _valor):
        pass


def configurar_logging():
    """
    Configurar (una sola vez) el logger 'licitai'.

    - Consola: solo el mensaje, igual que la salida histórica del CLI.
    - Archivo opcional (LICITAI_LOG_FILE): con fecha y nivel, útil en tareas programadas.

    Returns:
        logging.Logger: Logger raíz de la aplicación.
    """
    raiz = logging.getLogger("licitai")
    # Solo cuentan los handlers propios (otras herramientas, como pytest, añaden los suyos)
    if any(getattr(h, "_licitai", False) for h in raiz.handlers):
        return raiz

    # Evitar UnicodeEncodeError al imprimir emojis cuando la salida se redirige a un
    # archivo con codificación cp1252 (p. ej. tareas programadas en Windows)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    raiz.setLevel(logging.INFO)
    raiz.propagate = False
    consola = _ConsolaHandler()
    consola.setFormatter(logging.Formatter("%(message)s"))
    consola._licitai = True
    raiz.addHandler(consola)

    archivo = os.getenv("LICITAI_LOG_FILE")
    if archivo:
        ruta = _resolver_ruta(archivo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(ruta, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler._licitai = True
        raiz.addHandler(handler)
    return raiz


# --- Pipeline ---
MAX_PROCESAR = _env_int("LICITAI_MAX_PROCESAR", 5)    # Intentos de procesamiento por ejecución
MAX_INTENTOS = _env_int("LICITAI_MAX_INTENTOS", 3)    # Fallos tolerados antes de pasar a 'error'
PAUSA_ENTRE_LICITACIONES = _env_int("LICITAI_PAUSA_SEGUNDOS", 5)
BLOQUEO_MAX_MINUTOS = _env_int("LICITAI_BLOQUEO_MAX_MINUTOS", 120)  # Un bloqueo más antiguo se considera huérfano

# --- Red / Selenium ---
HTTP_TIMEOUT = _env_int("LICITAI_HTTP_TIMEOUT", 30)
SELENIUM_HEADLESS = _env_bool("LICITAI_HEADLESS", True)
SELENIUM_PAGE_TIMEOUT = _env_int("LICITAI_PAGE_TIMEOUT", 60)
SELENIUM_ESPERA_MAX = _env_int("LICITAI_ESPERA_TEXTO", 15)  # Máx. segundos esperando que el texto de la ficha se estabilice

# --- IA ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3-flash-preview"
IA_MAX_CHARS = _env_int("LICITAI_IA_MAX_CHARS", 40000)  # Límite del corpus enviado al modelo
GEMINI_TEMPERATURE = 0.0  # Reduce la variación del score entre ejecuciones sobre la misma ficha

# --- Escala del score (única para prompt, BD, consola y UI) ---
SCORE_MIN = 1
SCORE_MAX = 10
UMBRAL_DESCARTE = 5   # score < UMBRAL_DESCARTE => la IA debe justificar el descarte
UMBRAL_ALTO = 7       # score >= UMBRAL_ALTO => 🟢
UMBRAL_MEDIO = 4      # score >= UMBRAL_MEDIO => 🟡, menor => 🔴
