# -*- coding: utf-8 -*-
"""
Módulo: Extractor de Licitaciones (LicitacionScraper)
---------------------------------------------------
Este módulo implementa el pipeline de descubrimiento y captura de datos
desde el portal Mercado Público.

Responsabilidades:
1. Consultar la API oficial para el descubrimiento de nuevas oportunidades.
2. Filtrar resultados basados en el perfil de búsqueda del usuario.
3. Ejecutar la navegación automatizada (Selenium) para la extracción de
   detalles técnicos y cláusulas desde la ficha profunda.
"""

import requests
import os
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core import config
from core.parsing import normalizar_keywords, coincide_keywords, esta_cerrada, texto_ficha_valido, extraer_metadatos_ficha


class DriverNoDisponible(Exception):
    """El navegador automatizado no pudo iniciarse (Chrome ausente, sin red, etc.)."""


class LicitacionScraper:
    """
    Clase encargada del descubrimiento y extracción de datos.

    Centraliza la comunicación con la API de Mercado Público y gestiona el
    ciclo de vida del navegador automatizado para el scraping de fichas técnicas.
    """

    def __init__(self, db_manager):
        """
        Inicializar el scraper e inyectar la dependencia de persistencia.

        Args:
            db_manager (DatabaseManager): Instancia para verificar existencia
                                          y perfiles de búsqueda.
        """
        self.db = db_manager
        self.api_ticket = os.getenv("MP_TICKET")
        self.base_url = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
        # Diagnóstico de la última ejecución, consumido por el resumen del pipeline
        self.error_descubrimiento = None
        self.descartadas_cerradas = 0

    # -------------------------------------------------------------------
    # PARTE 1: DESCUBRIMIENTO GENERAL (API REST)
    # -------------------------------------------------------------------

    def obtener_keywords_busqueda(self):
        """
        Consultar las palabras clave configuradas en el perfil del usuario.

        Returns:
            tuple: (positivas, negativas) como listas de términos normalizados
                   (minúsculas, sin tildes, sin términos vacíos).
        """
        perfil = self.db.obtener_perfil() or {}
        positivas = normalizar_keywords(perfil.get('keywords_pos'))
        negativas = normalizar_keywords(perfil.get('keywords_neg'))
        if not positivas:
            print("⚠️ No hay palabras clave configuradas en el perfil.")
        return positivas, negativas

    def descubrir_licitaciones_del_dia(self, fecha=None):
        """
        Consultar la API masiva para obtener las licitaciones de una fecha.

        Args:
            fecha (str, optional): Fecha en formato DDMMAAAA. Por defecto, hoy.

        Returns:
            list: Listado bruto de licitaciones encontradas. Ante un error devuelve
                  [] y deja el motivo en `self.error_descubrimiento`.
        """
        self.error_descubrimiento = None
        if not self.api_ticket:
            self.error_descubrimiento = "MP_TICKET no configurado en .env"
            print(f"❌ Error: {self.error_descubrimiento}")
            return []

        # Formatear la fecha según el estándar requerido por la API (DDMMAAAA)
        fecha_consulta = fecha or datetime.now().strftime("%d%m%Y")
        parametros = {
            'fecha': fecha_consulta,
            'ticket': self.api_ticket
        }

        try:
            print(f"🔍 Buscando licitaciones publicadas el {fecha_consulta}...")
            respuesta = requests.get(self.base_url, params=parametros, timeout=config.HTTP_TIMEOUT)
        except requests.Timeout:
            self.error_descubrimiento = f"La API de Mercado Público no respondió en {config.HTTP_TIMEOUT} s"
        except requests.RequestException as e:
            # No se imprime el mensaje completo: incluye la URL con el ticket
            self.error_descubrimiento = f"Error de conexión con la API ({type(e).__name__})"
        else:
            if respuesta.status_code != 200:
                self.error_descubrimiento = f"La API respondió {respuesta.status_code} {respuesta.reason}"
            else:
                try:
                    datos = respuesta.json()
                except ValueError:
                    self.error_descubrimiento = "La API devolvió una respuesta que no es JSON"
                else:
                    if isinstance(datos, dict) and isinstance(datos.get('Listado'), list):
                        return datos['Listado']
                    mensaje = datos.get('Mensaje') if isinstance(datos, dict) else None
                    self.error_descubrimiento = f"Respuesta de la API sin 'Listado'{': ' + str(mensaje) if mensaje else ''}"

        print(f"❌ {self.error_descubrimiento}")
        return []

    def filtrar_licitaciones_relevantes(self, lista_bruta, ahora=None):
        """
        Aplicar criterios de filtrado técnico y estratégico sobre el listado bruto.

        Criterios:
        - Estado 5: Únicamente licitaciones en estado 'Publicada'.
        - Cierre: Se descartan las que ya cerraron (fecha desconocida => se mantiene).
        - Keywords: Alguna positiva y ninguna negativa en el título (sin distinguir tildes).
        - Unicidad: Exclusión de registros ya existentes en la base de datos
          (las pendientes existentes se retoman desde la cola, no desde aquí).

        Args:
            lista_bruta (list): Listado original de la API.

        Returns:
            list: Licitaciones nuevas aptas para registro y procesamiento.
        """
        positivas, negativas = self.obtener_keywords_busqueda()
        licitaciones_interesantes = []
        self.descartadas_cerradas = 0

        # Estado 5 representa 'Publicada', fase activa para participar
        ESTADOS_VIGENTES = [5]

        print(f"🧐 Filtrando {len(lista_bruta)} licitaciones por estado y relevancia...")

        for licit in lista_bruta:
            codigo = licit.get('CodigoExterno')
            if not codigo or licit.get('CodigoEstado') not in ESTADOS_VIGENTES:
                continue
            if not coincide_keywords(licit.get('Nombre'), positivas, negativas):
                continue
            if esta_cerrada(licit.get('FechaCierre'), ahora):
                self.descartadas_cerradas += 1
                continue
            if not self.db.existe_licitacion(codigo):
                licitaciones_interesantes.append(licit)

        print(f"🎯 Filtro completado: {len(licitaciones_interesantes)} licitaciones nuevas aptas.")
        return licitaciones_interesantes

    def ejecutar_pipeline_descubrimiento(self, fecha=None):
        """
        Orquestar el flujo de descubrimiento y pre-filtrado.

        Returns:
            list: Candidatos nuevos para registrar.
        """
        listado_total = self.descubrir_licitaciones_del_dia(fecha)

        if not listado_total:
            print("👀 No se encontraron licitaciones en el listado general.")
            return []

        print(f"📋 Total de licitaciones en el listado: {len(listado_total)}")
        finales = self.filtrar_licitaciones_relevantes(listado_total)
        return finales

    # -------------------------------------------------------------------
    # PARTE 2: EXTRACCIÓN PROFUNDA (SELENIUM)
    # -------------------------------------------------------------------

    def _crear_driver(self):
        """
        Iniciar Chrome con las opciones configuradas.

        Raises:
            DriverNoDisponible: Si Chrome o el driver no pueden iniciarse.
        """
        chrome_options = Options()
        if config.SELENIUM_HEADLESS:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("window-size=1920,1080")
        # Simulación de User-Agent para minimizar bloqueos por fingerprinting
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            raise DriverNoDisponible(f"No se pudo iniciar Chrome: {type(e).__name__}: {str(e)[:200]}") from e
        driver.set_page_load_timeout(config.SELENIUM_PAGE_TIMEOUT)
        return driver

    def extraer_detalle_licitacion(self, codigo_licitacion):
        """
        Navegar al portal Mercado Público para capturar el contenido técnico detallado.

        Utiliza técnicas de automatización para superar iframes complejos y
        pop-ups del portal oficial.

        Args:
            codigo_licitacion (str): Código externo (ej: 1234-56-LP24).

        Returns:
            dict: link, descripcion_pro (None si falló), error (None si tuvo éxito)
                  y los metadatos de `extraer_metadatos_ficha` (None si no aparecen).

        Raises:
            DriverNoDisponible: Si el navegador no puede iniciarse.
        """
        url_home = "https://www.mercadopublico.cl"
        resultado = {"link": None, "descripcion_pro": None, "error": None, **extraer_metadatos_ficha("")}

        driver = self._crear_driver()
        wait = WebDriverWait(driver, 25)

        try:
            driver.get(url_home)

            # Gestión proactiva de alertas/pop-ups del portal
            try:
                WebDriverWait(driver, 3).until(EC.alert_is_present())
                alert = driver.switch_to.alert
                print(f"⚠️ Alerta de portal detectada ('{alert.text}'), cerrando...")
                alert.accept()
                time.sleep(1)
                driver.refresh()
            except Exception:
                pass  # Lo habitual es que no haya alerta

            # Ejecutar búsqueda por código externo
            search_input = wait.until(EC.visibility_of_element_located((By.ID, "txtBuscar")))
            search_input.clear()
            search_input.send_keys(codigo_licitacion)

            # Clic mediante JavaScript para asegurar interacción en elementos superpuestos
            try:
                boton_buscar = wait.until(EC.element_to_be_clickable((By.ID, "btnBuscar")))
                driver.execute_script("arguments[0].click();", boton_buscar)
            except Exception:
                driver.execute_script("document.getElementById('btnBuscar').click();")

            # Salto al iframe de resultados para acceder al DOM dinámico
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "form-iframe")))

            # Localizar el enlace de la licitación específica mediante el atributo onclick
            selector_xpath = f"//a[contains(@onclick, '{codigo_licitacion}')]"
            enlace_elem = wait.until(EC.presence_of_element_located((By.XPATH, selector_xpath)))
            onclick_txt = enlace_elem.get_attribute("onclick") or ""
            url_match = re.search(r"'(http.*?)'", onclick_txt)

            if not url_match:
                resultado["error"] = "No se encontró el enlace a la ficha en el buscador del portal"
                return resultado

            resultado["link"] = url_match.group(1)

            # Navegar a la ficha técnica final
            driver.get(resultado["link"])

            # Sincronización: Esperar carga real del contenido textual
            wait.until(lambda d: d.find_element(By.TAG_NAME, "body").text.strip() != "")
            time.sleep(4)

            # Extracción robusta: Captura del texto en el nivel principal y sub-iframes
            driver.switch_to.default_content()
            texto_final = driver.execute_script("return document.body.innerText;") or ""

            # Si la captura es insuficiente, iterar sobre iframes internos (anidamiento profundo)
            if len(texto_final.strip()) < 1000:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for i in range(len(iframes)):
                    try:
                        driver.switch_to.default_content()
                        driver.switch_to.frame(i)
                        texto_final += "\n" + (driver.execute_script("return document.body.innerText;") or "")
                    except Exception:
                        continue

            if not texto_ficha_valido(texto_final):
                resultado["error"] = f"Texto de la ficha insuficiente o no reconocido ({len(texto_final.strip())} caracteres)"
                return resultado

            resultado["descripcion_pro"] = texto_final
            # Metadatos verificables tomados literalmente de la ficha
            resultado.update(extraer_metadatos_ficha(texto_final))
            return resultado

        except Exception as e:
            resultado["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"
            print(f"⚠️ Error en extracción de {codigo_licitacion}: {resultado['error']}")
            return resultado
        finally:
            driver.quit()
