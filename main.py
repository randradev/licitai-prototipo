# -*- coding: utf-8 -*-
"""
Módulo: Orquestador Principal (Main Pipeline)
--------------------------------------------
Este script coordina el flujo de trabajo completo de LicitAI.
Actúa como el pegamento entre el descubrimiento (API), la extracción
técnica (Selenium), el análisis estratégico (IA) y la persistencia (SQLite).

Flujo de ejecución:
1. Validación: Comprueba perfil (keywords) y credenciales antes de empezar.
2. Descubrimiento: Identifica licitaciones del día vía API y registra todas las
   nuevas que pasan el filtro (estado 'pendiente').
3. Procesamiento: Toma de la BD la cola de pendientes/extraídas (incluidas las
   de ejecuciones anteriores) y procesa hasta MAX_PROCESAR intentos.
4. Resumen: Devuelve un diccionario con lo que realmente ocurrió.
"""

import argparse
import sys
import time
from core import config
from core.database_mgr import DatabaseManager
from core.scraper import LicitacionScraper, DriverNoDisponible
from core.ai_analyst import AIAnalyst, AnalisisFallido, CuotaAgotada
from core.parsing import esta_cerrada, normalizar_keywords

# Evitar UnicodeEncodeError al imprimir emojis cuando la salida se redirige a un
# archivo con codificación cp1252 (p. ej. tareas programadas en Windows)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass


def _nuevo_resumen():
    """Estructura del resumen devuelto por el pipeline."""
    return {
        "descubiertas": 0,          # Nuevas que pasaron el filtro en el listado del día
        "registradas": 0,           # Insertadas en la BD en esta ejecución
        "descartadas_cerradas": 0,  # Del listado, ya cerradas
        "cerradas_en_cola": 0,      # De la cola, cerraron antes de procesarse (-> 'error')
        "intentadas": 0,
        "analizadas": 0,
        "fallidas": 0,
        "en_cola": 0,               # Siguen esperando para la próxima ejecución
        "error_descubrimiento": None,
        "detenido_por": None,       # Motivo de parada anticipada, si la hubo
    }


def ejecutar_pipeline(db=None, scraper=None, analyst=None, max_procesar=None,
                      max_intentos=None, pausa=None, fecha=None, ahora=None):
    """
    Ejecuta el ciclo de vida completo de procesamiento de licitaciones.
    Diseñado para ser invocado manualmente desde la UI o mediante tareas cron.

    Los parámetros opcionales permiten inyectar dependencias en las pruebas.

    Returns:
        dict: Resumen de la ejecución (ver `_nuevo_resumen`).
    """
    print("🚀 LicitAI: Iniciando ciclo de procesamiento...")
    resumen = _nuevo_resumen()
    max_procesar = config.MAX_PROCESAR if max_procesar is None else max_procesar
    max_intentos = config.MAX_INTENTOS if max_intentos is None else max_intentos
    pausa = config.PAUSA_ENTRE_LICITACIONES if pausa is None else pausa

    # Inicialización de dependencias e inyección de base de datos
    db = db or DatabaseManager()
    scraper = scraper or LicitacionScraper(db)

    # -------------------------------------------------------
    # FASE 0: VALIDACIÓN DE CONFIGURACIÓN
    # -------------------------------------------------------
    perfil = db.obtener_perfil() or {}
    if not normalizar_keywords(perfil.get('keywords_pos')):
        resumen["detenido_por"] = "No hay palabras clave positivas en el perfil de negocio."
        print(f"⚠️ {resumen['detenido_por']}")
        return resumen

    if analyst is None:
        try:
            analyst = AIAnalyst(db)
        except ValueError as e:
            resumen["detenido_por"] = str(e)
            print(resumen["detenido_por"])
            return resumen

    # -------------------------------------------------------
    # FASE 1: DESCUBRIMIENTO (API) Y REGISTRO
    # -------------------------------------------------------
    # Consulta masiva al endpoint oficial de Mercado Público
    licitaciones_dia = scraper.ejecutar_pipeline_descubrimiento(fecha)
    resumen["error_descubrimiento"] = scraper.error_descubrimiento
    resumen["descartadas_cerradas"] = scraper.descartadas_cerradas
    resumen["descubiertas"] = len(licitaciones_dia)

    # Se registran TODAS las nuevas; el límite solo aplica al procesamiento
    for l in licitaciones_dia:
        insertada = db.guardar_licitacion({
            'id_externo': l['CodigoExterno'],
            'titulo': l.get('Nombre'),
            'organismo': l.get('OrganismoCompleto'),  # El listado por fecha normalmente no lo incluye
            'fecha_cierre': l.get('FechaCierre'),
        })
        resumen["registradas"] += int(insertada)

    if resumen["registradas"]:
        print(f"📦 Se registraron {resumen['registradas']} licitaciones nuevas.")

    # -------------------------------------------------------
    # FASE 2: COLA DE PROCESAMIENTO (desde la BD)
    # -------------------------------------------------------
    lote = []
    for licit in db.obtener_cola_procesamiento(max_intentos):
        if esta_cerrada(licit.get('fecha_cierre'), ahora):
            db.marcar_error(licit['id_externo'], "La licitación cerró antes de poder procesarse")
            resumen["cerradas_en_cola"] += 1
            continue
        lote.append(licit)

    # Control de cuotas: el límite cuenta intentos (éxitos y fallos)
    if len(lote) > max_procesar:
        print(f"✋ {len(lote)} en cola; se procesarán {max_procesar} en esta ejecución.")
    lote = lote[:max_procesar]

    # -------------------------------------------------------
    # FASE 3: EXTRACCIÓN Y ANÁLISIS IA
    # -------------------------------------------------------
    for idx, licit in enumerate(lote):
        id_ext = licit['id_externo']
        print(f"\n--- Procesando ({idx + 1}/{len(lote)}): {id_ext} ---")

        # ---------------------------------
        # A. EXTRACCIÓN PROFUNDA (SELENIUM) — se omite si ya hay texto extraído
        # ---------------------------------
        if licit['estado'] == 'pendiente':
            try:
                detalle = scraper.extraer_detalle_licitacion(id_ext)
            except DriverNoDisponible as e:
                # Problema del entorno, no de la licitación: no consume intentos
                resumen["detenido_por"] = str(e)
                print(f"❌ {e}")
                break

            resumen["intentadas"] += 1
            if detalle.get('error') or not detalle.get('descripcion_pro'):
                motivo = detalle.get('error') or "Extracción sin contenido"
                estado = db.registrar_fallo(id_ext, f"Extracción: {motivo}", max_intentos)
                resumen["fallidas"] += 1
                print(f"❌ Falló la extracción técnica para {id_ext}: {motivo} (estado: {estado})")
                if pausa and idx < len(lote) - 1:
                    time.sleep(pausa)
                continue

            # Datos maestros tomados literalmente de la ficha técnica
            db.actualizar_datos_maestros(
                id_ext,
                titulo=detalle.get('titulo'),
                organismo=detalle.get('organismo'),
                fecha_pub=detalle.get('fecha_publicacion'),
                reclamos_pago_n=detalle.get('reclamos_pago_n'),
                region=detalle.get('region'),
            )
            # Persistencia del corpus textual para su posterior procesamiento por LLM
            db.actualizar_detalle_profundo(id_ext, detalle.get('link'), detalle['descripcion_pro'])
            print("🔍 Extracción web completada.")
        else:
            resumen["intentadas"] += 1

        # ---------------------------------
        # B. ANÁLISIS ESTRATÉGICO (GEMINI)
        # ---------------------------------
        print("🧠 Consultando a la IA...")
        try:
            analis = analyst.analizar_licitacion(id_ext)
        except CuotaAgotada as e:
            # La licitación queda 'extraido' y se reintenta en la próxima ejecución
            resumen["detenido_por"] = str(e)
            print(f"⛔ {e}")
            break
        except AnalisisFallido as e:
            estado = db.registrar_fallo(id_ext, f"IA: {e}", max_intentos)
            resumen["fallidas"] += 1
            print(f"⚠️ La IA no pudo procesar esta licitación: {e} (estado: {estado})")
        else:
            resumen["analizadas"] += 1
            score = analis['score_ia']
            print(f"🎯 ANÁLISIS COMPLETADO - SCORE: {score}/{config.SCORE_MAX}")
            print(f"📝 VEREDICTO: {analis.get('veredicto')}")
            for p in analis.get('puntos_criticos', []): print(f"   • {p}")
            print("⚠️ RIESGOS:")
            for r in analis.get('riesgos', []): print(f"   • {r}")
            if score < config.UMBRAL_DESCARTE:
                print(f"📂 MOTIVO DE ARCHIVO: {analis.get('motivo_archivo')}")

        # Gestión de estabilidad: Evitar bloqueos por parte del servidor destino (Mercado Público)
        if pausa and idx < len(lote) - 1:
            print(f"💤 Esperando {pausa} segundos para estabilizar la siguiente carga...")
            time.sleep(pausa)

    resumen["en_cola"] = db.contar_en_cola(max_intentos)

    nivel, mensaje = describir_resumen(resumen)
    print("\n" + "=" * 50)
    print(f"{'✅' if nivel == 'success' else 'ℹ️' if nivel == 'info' else '⚠️'} {mensaje}")
    print("=" * 50)
    return resumen


def describir_resumen(resumen):
    """
    Traducir el resumen del pipeline a un mensaje para el usuario.

    Returns:
        tuple: (nivel, mensaje) con nivel en 'success', 'info', 'warning' o 'error'.
    """
    partes = [
        f"{resumen['descubiertas']} nuevas relevantes en el listado",
        f"{resumen['analizadas']} analizadas",
    ]
    if resumen["fallidas"]:
        partes.append(f"{resumen['fallidas']} fallidas (se reintentarán)")
    if resumen["cerradas_en_cola"]:
        partes.append(f"{resumen['cerradas_en_cola']} cerradas antes de procesarse")
    if resumen["en_cola"]:
        partes.append(f"{resumen['en_cola']} en cola para la próxima ejecución")
    detalle = "; ".join(partes) + "."

    if resumen["detenido_por"] and not resumen["intentadas"]:
        return "error", f"No se pudo ejecutar: {resumen['detenido_por']}"
    avisos = [a for a in (resumen["detenido_por"], resumen["error_descubrimiento"]) if a]
    if avisos:
        return "warning", f"{detalle} Aviso: {' | '.join(avisos)}"
    if resumen["fallidas"]:
        return "warning", detalle
    if resumen["analizadas"]:
        return "success", detalle
    return "info", f"Sin licitaciones nuevas para analizar. {detalle}"


# Punto de entrada para ejecución directa desde CLI
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecutar el pipeline de LicitAI.")
    parser.add_argument("--fecha", help="Fecha a consultar en formato DDMMAAAA (por defecto, hoy).")
    parser.add_argument("--max", type=int, help="Máximo de licitaciones a procesar en esta ejecución.")
    args = parser.parse_args()
    ejecutar_pipeline(fecha=args.fecha, max_procesar=args.max)
