# 🤖 LicitAI: Radar Inteligente de Licitaciones

LicitAI es una solución avanzada de **automatización e inteligencia de datos** diseñada para optimizar la búsqueda y análisis de oportunidades en **Mercado Público** (Chile). El sistema combina la precisión del Web Scraping, la agilidad de la API oficial y el poder semántico de **Google Gemini AI** para calificar licitaciones según su relevancia estratégica.

---

## 🚀 Propuesta de Valor
Tradicionalmente, revisar el portal de Mercado Público requiere horas de lectura manual. **LicitAI** reduce este proceso a segundos mediante:

* **Filtrado Inteligente:** Ignora el ruido y se enfoca solo en lo que coincide con tu perfil de negocio.
* **Análisis Predictivo:** La IA detecta fortalezas, riesgos y comportamientos de pago del organismo.
* **Gestión Centralizada:** Dashboard intuitivo para administrar favoritas, archivadas y notas técnicas.

---

## 🛠️ Stack Tecnológico
* **Lenguaje:** Python 3.10+
* **Frontend:** Streamlit
* **Base de Datos:** SQLite3 (Persistencia single-tenant).
* **Automatización:** Selenium WebDriver (Extracción profunda).
* **IA Generativa:** Google Gemini Pro (Análisis semántico).
* **Infraestructura:** Soporte híbrido (Local / Streamlit Cloud).

---

## 🏗️ Arquitectura del Sistema
El proyecto sigue una arquitectura modular y desacoplada:

1. **Core Scraper:** Estrategia híbrida de recolección (API Rest + Selenium).
2. **Database Manager:** Capa de persistencia con gestión de estados.
3. **AI Analyst:** Motor de NLP que evalúa la viabilidad técnica de cada licitación.
4. **Dashboard:** Interfaz de usuario para la toma de decisiones.

---

## 🔧 Instalación y Configuración

### 1. Clonar el repositorio
git clone https://github.com/tu-usuario/licitai.git
cd licitai

### 2. Configurar entorno virtual
#### Crear entorno virtual
python -m venv venv

#### Activar entorno (Windows)
venv\Scripts\activate

#### Activar entorno (Linux/Mac)
source venv/bin/activate

#### Instalar dependencias
pip install -r requirements.txt

### 3. Variables de Entorno (Secrets)
Crea un archivo .env en la raíz del proyecto:
GEMINI_API_KEY=tu_api_key_de_gemini
MP_TICKET=tu_ticket_api_mercado_público

---

## 📊 Flujo de Trabajo (Pipeline)

1. **Sincronización:** El sistema consulta la API buscando nuevas publicaciones.
2. **Extracción:** Selenium navega para extraer el texto completo de la ficha técnica.
3. **Evaluación:** La IA analiza el texto y asigna un score estratégico.
4. **Decisión:** El usuario gestiona las oportunidades desde el Dashboard.

---

## 👤 Autor
randradev.
Desarrollado con enfoque en **Ingeniería de Software y Automatización**.
