# -*- coding: utf-8 -*-
"""
Módulo: Gestor de Persistencia (DatabaseManager)
-----------------------------------------------
Este módulo centraliza la lógica de interacción con la base de datos SQLite.
Implementa el patrón Data Access Object (DAO) para desacoplar la lógica de
negocio de los detalles de almacenamiento.

Responsabilidades:
1. Garantizar la integridad estructural del esquema de datos.
2. Gestionar el ciclo de vida de las conexiones mediante gestores de contexto.
3. Almacenar perfiles de usuario y resultados del análisis de IA.

Ciclo de vida de una licitación (columna `estado`):
    pendiente  -> registrada desde la API, aún sin texto de la ficha.
    extraido   -> texto de la ficha guardado, aún sin análisis válido.
    analizado  -> análisis de IA validado y guardado.
    favorita / archivada -> estados de gestión elegidos por el usuario.
    error      -> agotó los reintentos o cerró antes de procesarse.
                  Visible en la UI y recuperable con `reintentar()`.
"""

import sqlite3
import json
import os
from contextlib import contextmanager
from datetime import datetime

from core import config
from core.parsing import es_valor_util

ESTADOS_EN_COLA = ("pendiente", "extraido")

# Columnas agregadas después de la versión inicial del esquema.
# Se añaden con ALTER TABLE si faltan; nunca se eliminan ni reescriben datos.
COLUMNAS_NUEVAS = {
    "intentos": "INTEGER DEFAULT 0",   # Fallos consecutivos de extracción/análisis
    "ultimo_error": "TEXT",            # Último motivo de fallo (para la UI)
    "reclamos_pago_n": "INTEGER",      # Reclamos de pago extraídos de la ficha (fuente MP)
    "region": "TEXT",                  # Región extraída de la ficha
    "notas": "TEXT",                   # Notas internas del usuario
    "checklist_json": "TEXT",          # Checklist de gestión del usuario (JSON)
    # Trazabilidad del análisis vigente
    "analisis_modelo": "TEXT",         # Modelo de IA que generó el análisis
    "analisis_prompt_version": "TEXT", # Versión del prompt (core/ai_analyst.py)
    "analisis_fecha": "TEXT",          # Momento del análisis (ISO, hora local)
    "analisis_perfil_version": "TEXT", # Versión del perfil usada (core.parsing.version_perfil)
    # Score de idoneidad según la rúbrica (core/rubrica.py). NULL en análisis históricos
    "score_idoneidad": "INTEGER",      # 0-100 (NULL si no_elegible o evaluacion_insuficiente)
    "score_estado": "TEXT",            # definitivo | provisional | no_elegible | evaluacion_insuficiente
    "score_cobertura": "INTEGER",      # % del peso de la rúbrica con nota
    "rubrica_version": "TEXT",         # NULL = análisis histórico con score_ia en escala 1-10
    "ficha_fecha": "TEXT",             # Momento en que se leyó la ficha (fecha de los datos de la fuente)
    # Evaluación humana del análisis (dataset para medir la calidad del score)
    "eval_score": "TEXT",              # 'acertado' | 'muy_alto' | 'muy_bajo'
    "eval_postularia": "TEXT",         # 'si' | 'tal_vez' | 'no'
    "eval_comentario": "TEXT",
    "eval_fecha": "TEXT",
}

# Columnas que se copian a `analisis_historial` antes de reemplazar un análisis
COLUMNAS_HISTORIAL = {
    "score_ia": "INTEGER", "score_idoneidad": "INTEGER", "score_estado": "TEXT", "score_cobertura": "INTEGER",
    "rubrica_version": "TEXT", "analisis_ia_json": "TEXT", "motivo_archivo": "TEXT", "analisis_modelo": "TEXT",
    "analisis_prompt_version": "TEXT", "analisis_fecha": "TEXT", "analisis_perfil_version": "TEXT",
    "eval_score": "TEXT", "eval_postularia": "TEXT", "eval_comentario": "TEXT", "eval_fecha": "TEXT",
}

MAX_RESPUESTA_FALLIDA = 20000   # Caracteres guardados de una respuesta de IA rechazada

EVAL_SCORE_OPCIONES =("acertado", "muy_alto", "muy_bajo")
EVAL_POSTULARIA_OPCIONES = ("si", "tal_vez", "no")


def _ahora_iso():
    """Momento actual en ISO (hora local, sin microsegundos)."""
    return datetime.now().isoformat(timespec="seconds")


class DatabaseManager:
    """
    Clase encargada de la persistencia de datos del sistema LicitAI.

    Centraliza las interacciones con SQLite para mantener el resto del sistema
    desacoplado de la base de datos.
    """

    def __init__(self, db_path=None):
        """
        Inicializar la clase y garantizar la existencia del directorio base.

        Args:
            db_path (str, optional): Ruta al archivo SQLite. Por defecto se usa
                                     DATABASE_PATH (ver core/config.py).
        """
        self.db_path = db_path or config.ruta_db()
        # Asegurar que la carpeta contenedora exista antes de intentar crear la DB
        directorio = os.path.dirname(self.db_path)
        if directorio:
            os.makedirs(directorio, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """
        Gestionar la conexión a la base de datos mediante un Context Manager.

        Garantiza que la conexión se cierre automáticamente tras completar
        la operación, evitando bloqueos (deadlocks) o corrupción de archivos.

        Yields:
            sqlite3.Connection: Objeto de conexión configurado con Row Factory.
        """
        conn = sqlite3.connect(self.db_path, timeout=10)
        # Configurar Row Factory para permitir acceso a columnas por nombre
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """
        Inicializar las tablas base siguiendo el modelo de datos relacional.

        Define las entidades de Perfil de Usuario (Single-tenant) y Licitaciones.
        Utiliza restricciones (CHECK, UNIQUE) para garantizar la integridad.
        """
        with self._get_connection() as conn:
            # ENTIDAD 1: PERFIL DE USUARIO
            # El CHECK (id = 1) garantiza un único perfil activo en el sistema.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS perfil_usuario (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    keywords_pos TEXT,   -- Palabras clave de inclusión
                    keywords_neg TEXT,   -- Filtros de exclusión (ruido)
                    regiones TEXT,       -- Reservado: no se usa en el filtrado
                    bio_estrategica TEXT -- Contexto del negocio para el modelo LLM
                )
            """)

            # ENTIDAD 2: LICITACIÓN
            # Almacena el ciclo de vida completo: desde el descubrimiento hasta el análisis de IA.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS licitaciones (
                    id_externo TEXT PRIMARY KEY, -- ID único de Mercado Público
                    titulo TEXT NOT NULL,
                    organismo TEXT,
                    fecha_cierre TEXT,           -- ISO 8601 (tal como la entrega la API)
                    fecha_publicacion TEXT,      -- ISO YYYY-MM-DD extraída de la ficha (NULL si se desconoce)
                    reclamo_pago TEXT,           -- Interpretación de la IA sobre pagos (no verificada)
                    link TEXT,
                    descripcion_pro TEXT,        -- Cuerpo extraído para análisis semántico
                    score_ia INTEGER,            -- Score histórico de la IA (escala 1-10); ver score_idoneidad
                    analisis_ia_json TEXT,       -- Estructura JSON con riesgos y veredicto
                    estado TEXT DEFAULT 'pendiente', -- Ver ciclo de vida en el encabezado del módulo
                    motivo_archivo TEXT,         -- Feedback de la IA en caso de descarte
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- UTC
                )
            """)
            # ENTIDAD 3: EJECUCIÓN DEL PIPELINE
            # Registro de cada sincronización (embudo de filtrado y observabilidad).
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ejecuciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inicio TEXT,                 -- ISO, hora local
                    fin TEXT,
                    fecha_consulta TEXT,         -- Fecha del listado consultado (ISO)
                    total_listado INTEGER,       -- Licitaciones en el listado de la API
                    relevantes INTEGER,          -- Nuevas que pasaron el filtro
                    registradas INTEGER,
                    analizadas INTEGER,
                    fallidas INTEGER,
                    detenido_por TEXT,
                    error_descubrimiento TEXT
                )
            """)
            # ENTIDAD 4: HISTORIAL DE ANÁLISIS
            # Copia de cada análisis reemplazado por un re-análisis (solo inserción),
            # junto con la evaluación humana que se hizo sobre él.
            columnas = ", ".join(f"{col} {tipo}" for col, tipo in COLUMNAS_HISTORIAL.items())
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS analisis_historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_externo TEXT NOT NULL,
                    reemplazado TEXT,            -- Momento en que se reemplazó (ISO, hora local)
                    {columnas}
                )
            """)
            # ENTIDAD 5: RESPUESTAS DE IA RECHAZADAS
            # Texto crudo de cada respuesta que no pasó la validación (solo inserción):
            # permite diagnosticar sin repetir la llamada y medir la tasa de fallos por versión del prompt.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS respuestas_fallidas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_externo TEXT NOT NULL,
                    fecha TEXT,                  -- ISO, hora local
                    modelo TEXT,
                    prompt_version TEXT,
                    error TEXT,                  -- Motivo del rechazo
                    respuesta TEXT               -- Texto crudo (recortado a MAX_RESPUESTA_FALLIDA)
                )
            """)
            self._migrar_esquema(conn)
            conn.commit()

    def _migrar_esquema(self, conn):
        """
        Agregar de forma idempotente las columnas nuevas a bases existentes.
        """
        existentes = {fila["name"] for fila in conn.execute("PRAGMA table_info(licitaciones)")}
        for columna, definicion in COLUMNAS_NUEVAS.items():
            if columna not in existentes:
                conn.execute(f"ALTER TABLE licitaciones ADD COLUMN {columna} {definicion}")

    # ===================================================================
    # GESTIÓN DE PERFIL (Configuración de Negocio)
    # ===================================================================

    def guardar_perfil(self, keywords_pos, keywords_neg, regiones, bio):
        """
        Crear o actualizar el perfil estratégico del usuario.
        """
        query = """
            INSERT OR REPLACE INTO perfil_usuario (id, keywords_pos, keywords_neg, regiones, bio_estrategica)
            VALUES (1, ?, ?, ?, ?)
        """
        with self._get_connection() as conn:
            conn.execute(query, (keywords_pos, keywords_neg, regiones, bio))
            conn.commit()

    def obtener_perfil(self):
        """
        Recuperar la configuración del perfil para el Scraper y la IA.

        Returns:
            dict: Datos del perfil o None si no se ha configurado.
        """
        with self._get_connection() as conn:
            res = conn.execute("SELECT * FROM perfil_usuario WHERE id = 1").fetchone()
            return dict(res) if res else None

    # ===================================================================
    # GESTIÓN DE LICITACIONES (Operaciones CRUD)
    # ===================================================================

    def guardar_licitacion(self, data):
        """
        Registrar una licitación descubierta mediante la API.
        Evita duplicados mediante la cláusula INSERT OR IGNORE.

        Returns:
            bool: True si se insertó un registro nuevo.
        """
        query = """
            INSERT OR IGNORE INTO licitaciones
            (id_externo, titulo, organismo, fecha_cierre, fecha_publicacion)
            VALUES (?, ?, ?, ?, ?)
        """
        titulo = data.get('titulo') if es_valor_util(data.get('titulo')) else f"Licitación {data['id_externo']}"
        with self._get_connection() as conn:
            cur = conn.execute(query, (
                data['id_externo'],
                titulo,
                data.get('organismo') if es_valor_util(data.get('organismo')) else None,
                data.get('fecha_cierre') if es_valor_util(data.get('fecha_cierre')) else None,
                data.get('fecha_publicacion') if es_valor_util(data.get('fecha_publicacion')) else None,
            ))
            conn.commit()
            return cur.rowcount > 0

    def actualizar_detalle_profundo(self, id_externo, link, texto_pro):
        """
        Actualizar la licitación con datos extendidos capturados del navegador.

        Cambia el estado de la licitación a 'extraido' para indicar que está
        lista para el análisis de IA, y reinicia el contador de intentos para
        que la fase de IA disponga de sus propios reintentos.
        """
        query = """
            UPDATE licitaciones
            SET link = ?, descripcion_pro = ?, ficha_fecha = ?, estado = 'extraido', intentos = 0, ultimo_error = NULL
            WHERE id_externo = ?
        """
        with self._get_connection() as conn:
            conn.execute(query, (link, texto_pro, _ahora_iso(), id_externo))
            conn.commit()

    def obtener_licitaciones(self, estado=None):
        """
        Recuperar el conjunto de licitaciones filtrado por estado.

        Args:
            estado (str | tuple, optional): Estado o estados (pendiente, analizado, etc.)

        Returns:
            list: Lista de diccionarios representando las licitaciones.
        """
        query = "SELECT * FROM licitaciones"
        params = ()

        if estado:
            estados = (estado,) if isinstance(estado, str) else tuple(estado)
            query += f" WHERE estado IN ({', '.join('?' * len(estados))})"
            params = estados

        # Orden cronológico real (fechas ISO); las fechas desconocidas van al final
        query += " ORDER BY fecha_publicacion IS NULL, fecha_publicacion DESC, score_idoneidad DESC, score_ia DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def obtener_licitacion(self, id_externo):
        """
        Recuperar una única licitación por su ID externo.

        Returns:
            dict | None
        """
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM licitaciones WHERE id_externo = ?", (id_externo,)).fetchone()
            return dict(row) if row else None

    def existe_licitacion(self, id_externo):
        """
        Verificar la existencia de un ID externo para evitar reprocesamiento.
        """
        with self._get_connection() as conn:
            res = conn.execute("SELECT 1 FROM licitaciones WHERE id_externo = ?", (id_externo,)).fetchone()
            return res is not None

    def obtener_cola_procesamiento(self, max_intentos):
        """
        Recuperar las licitaciones pendientes de extracción o análisis que aún
        tienen reintentos disponibles.

        Orden: primero las que cierran antes (para no perder oportunidades
        esperando en la cola; sin fecha de cierre, al final); a igual cierre, las
        que fallaron menos veces; luego de la más antigua a la más reciente.
        `fecha_cierre` se guarda en ISO, así que se ordena como texto.
        """
        query = f"""
            SELECT * FROM licitaciones
            WHERE estado IN ({', '.join('?' * len(ESTADOS_EN_COLA))})
              AND COALESCE(intentos, 0) < ?
            ORDER BY fecha_cierre IS NULL, fecha_cierre ASC, COALESCE(intentos, 0) ASC, fecha_creacion ASC, id_externo ASC
        """
        with self._get_connection() as conn:
            rows = conn.execute(query, (*ESTADOS_EN_COLA, max_intentos)).fetchall()
            return [dict(row) for row in rows]

    def contar_en_cola(self, max_intentos):
        """Contar las licitaciones que siguen esperando procesamiento."""
        return len(self.obtener_cola_procesamiento(max_intentos))

    def registrar_fallo(self, id_externo, motivo, max_intentos):
        """
        Registrar un fallo recuperable de extracción o análisis.

        Incrementa `intentos`; al alcanzar `max_intentos` la licitación pasa a
        'error'. El estado previo (pendiente/extraido) se conserva mientras
        queden reintentos, de modo que no se repite trabajo ya hecho.

        Returns:
            str | None: Estado resultante.
        """
        query = """
            UPDATE licitaciones
            SET intentos = COALESCE(intentos, 0) + 1,
                ultimo_error = ?,
                estado = CASE
                    WHEN estado IN ('pendiente', 'extraido') AND COALESCE(intentos, 0) + 1 >= ? THEN 'error'
                    ELSE estado
                END
            WHERE id_externo = ?
        """
        with self._get_connection() as conn:
            conn.execute(query, (str(motivo)[:500], max_intentos, id_externo))
            conn.commit()
            row = conn.execute("SELECT estado FROM licitaciones WHERE id_externo = ?", (id_externo,)).fetchone()
            return row["estado"] if row else None

    def marcar_error(self, id_externo, motivo):
        """Mover una licitación de la cola a 'error' con un motivo visible."""
        query = "UPDATE licitaciones SET estado = 'error', ultimo_error = ? WHERE id_externo = ?"
        with self._get_connection() as conn:
            conn.execute(query, (str(motivo)[:500], id_externo))
            conn.commit()

    def reintentar(self, id_externo):
        """
        Devolver una licitación en 'error' a la cola, reiniciando sus intentos.
        Si ya tiene texto extraído vuelve a 'extraido' (solo falta la IA).
        """
        query = """
            UPDATE licitaciones
            SET estado = CASE WHEN COALESCE(descripcion_pro, '') != '' THEN 'extraido' ELSE 'pendiente' END,
                intentos = 0,
                ultimo_error = NULL
            WHERE id_externo = ? AND estado = 'error'
        """
        with self._get_connection() as conn:
            conn.execute(query, (id_externo,))
            conn.commit()

    def guardar_analisis_ia(self, id_externo, score, analisis_json, motivo=None, modelo=None, prompt_version=None,
                            perfil_version=None, rubrica=None):
        """
        Persistir los resultados generados por el modelo de IA.

        Las licitaciones favoritas o archivadas conservan su estado al
        re-analizarse; el resto pasa a 'analizado'. Se registra con qué modelo,
        versión de prompt y en qué momento se generó el análisis.

        Una evaluación humana previa se conserva: describe el análisis
        anterior, por lo que la UI la marca como desactualizada comparando
        `eval_fecha` con `analisis_fecha`.

        El análisis vigente (con su evaluación) se copia antes a
        `analisis_historial` en la misma transacción: re-analizar nunca borra.

        Args:
            id_externo (str): ID de la licitación.
            score (int | None): Score histórico 1-10 (None en análisis con rúbrica).
            analisis_json (dict): Estructura de riesgos y oportunidades.
            motivo (str, optional): Justificación de archivo en scores bajos.
            modelo (str, optional): Modelo de IA utilizado.
            prompt_version (str, optional): Versión del prompt utilizado.
            perfil_version (str, optional): Versión del perfil de negocio utilizado.
            rubrica (dict, optional): Resultado de core.rubrica.calcular (score, estado, cobertura, versión).
        """
        rubrica = rubrica or {}
        columnas = ", ".join(COLUMNAS_HISTORIAL)
        respaldo = f"""
            INSERT INTO analisis_historial (id_externo, reemplazado, {columnas})
            SELECT id_externo, ?, {columnas} FROM licitaciones
            WHERE id_externo = ? AND analisis_ia_json IS NOT NULL
        """
        query = """
            UPDATE licitaciones
            SET score_ia = ?, analisis_ia_json = ?, motivo_archivo = ?,
                analisis_modelo = ?, analisis_prompt_version = ?, analisis_fecha = ?, analisis_perfil_version = ?,
                score_idoneidad = ?, score_estado = ?, score_cobertura = ?, rubrica_version = ?,
                estado = CASE WHEN estado IN ('favorita', 'archivada') THEN estado ELSE 'analizado' END,
                intentos = 0, ultimo_error = NULL
            WHERE id_externo = ?
        """
        ahora = _ahora_iso()
        with self._get_connection() as conn:
            conn.execute(respaldo, (ahora, id_externo))
            conn.execute(query, (score, json.dumps(analisis_json, ensure_ascii=False), motivo,
                                 modelo, prompt_version, ahora, perfil_version,
                                 rubrica.get("score"), rubrica.get("estado"), rubrica.get("cobertura"),
                                 rubrica.get("version"), id_externo))
            conn.commit()

    def registrar_respuesta_fallida(self, id_externo, error, respuesta, modelo=None, prompt_version=None):
        """Guardar el texto crudo de una respuesta de IA rechazada por la validación."""
        query = """
            INSERT INTO respuestas_fallidas (id_externo, fecha, modelo, prompt_version, error, respuesta)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        with self._get_connection() as conn:
            conn.execute(query, (id_externo, _ahora_iso(), modelo, prompt_version, str(error)[:500],
                                 (respuesta or "")[:MAX_RESPUESTA_FALLIDA]))
            conn.commit()

    def obtener_respuestas_fallidas(self, id_externo=None):
        """Respuestas rechazadas (todas o de una licitación), de la más reciente a la más antigua."""
        query = "SELECT * FROM respuestas_fallidas"
        params = ()
        if id_externo:
            query += " WHERE id_externo = ?"
            params = (id_externo,)
        with self._get_connection() as conn:
            return [dict(r) for r in conn.execute(query + " ORDER BY id DESC", params).fetchall()]

    def obtener_historial(self, id_externo):
        """Análisis anteriores de una licitación, del más reciente al más antiguo."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM analisis_historial WHERE id_externo = ? ORDER BY id DESC",
                                (id_externo,)).fetchall()
            return [dict(row) for row in rows]

    def guardar_evaluacion(self, id_externo, eval_score, postularia, comentario=None):
        """
        Guardar la evaluación humana del análisis vigente.

        Args:
            eval_score (str): 'acertado', 'muy_alto' o 'muy_bajo'.
            postularia (str): 'si', 'tal_vez' o 'no'.
            comentario (str, optional): Observación libre.

        Raises:
            ValueError: Si alguna opción no es válida.
        """
        if eval_score not in EVAL_SCORE_OPCIONES:
            raise ValueError(f"eval_score inválido: {eval_score!r}")
        if postularia not in EVAL_POSTULARIA_OPCIONES:
            raise ValueError(f"postularia inválido: {postularia!r}")
        query = """
            UPDATE licitaciones
            SET eval_score = ?, eval_postularia = ?, eval_comentario = ?, eval_fecha = ?
            WHERE id_externo = ?
        """
        with self._get_connection() as conn:
            conn.execute(query, (eval_score, postularia, (comentario or "").strip() or None, _ahora_iso(), id_externo))
            conn.commit()

    # ===================================================================
    # REGISTRO DE EJECUCIONES
    # ===================================================================

    def registrar_ejecucion(self, resumen, inicio, fin, fecha_consulta=None):
        """
        Guardar el resultado de una ejecución del pipeline.

        Args:
            resumen (dict): Resumen devuelto por el pipeline.
            inicio, fin (datetime): Momentos de inicio y término.
            fecha_consulta (str, optional): Fecha del listado consultado (ISO).
        """
        query = """
            INSERT INTO ejecuciones (inicio, fin, fecha_consulta, total_listado, relevantes, registradas,
                                     analizadas, fallidas, detenido_por, error_descubrimiento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._get_connection() as conn:
            conn.execute(query, (
                inicio.isoformat(timespec="seconds"), fin.isoformat(timespec="seconds"), fecha_consulta,
                resumen.get("total_listado", 0), resumen.get("descubiertas", 0), resumen.get("registradas", 0),
                resumen.get("analizadas", 0), resumen.get("fallidas", 0),
                resumen.get("detenido_por"), resumen.get("error_descubrimiento"),
            ))
            conn.commit()

    def obtener_ejecuciones(self):
        """Recuperar todas las ejecuciones registradas, de la más reciente a la más antigua."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM ejecuciones ORDER BY inicio DESC, id DESC").fetchall()
            return [dict(row) for row in rows]

    def cambiar_estado(self, id_externo, nuevo_estado):
        """
        Actualizar el estado de gestión de una licitación (ej: Favorita, Archivada).
        """
        query = "UPDATE licitaciones SET estado = ? WHERE id_externo = ?"
        with self._get_connection() as conn:
            conn.execute(query, (nuevo_estado, id_externo))
            conn.commit()

    def guardar_notas(self, id_externo, notas, checklist):
        """
        Persistir las notas internas y el checklist de gestión del usuario.

        Args:
            notas (str): Texto libre.
            checklist (dict): Ítems de gestión, ej. {"bases_leidas": True}.
        """
        query = "UPDATE licitaciones SET notas = ?, checklist_json = ? WHERE id_externo = ?"
        with self._get_connection() as conn:
            conn.execute(query, (notas, json.dumps(checklist or {}), id_externo))
            conn.commit()

    def actualizar_datos_maestros(self, id_externo, titulo=None, organismo=None, fecha_pub=None,
                                  reclamo_pago=None, reclamos_pago_n=None, region=None, fecha_cierre=None):
        """
        Actualizar metadatos oficiales recuperados durante la navegación profunda.

        Los valores vacíos o marcadores de posición ("Sin título", "No detectado"...)
        se ignoran para no sobrescribir datos reales.
        """
        campos = {
            "titulo": titulo,
            "organismo": organismo,
            "fecha_publicacion": fecha_pub,
            "reclamo_pago": reclamo_pago,
            "region": region,
            "fecha_cierre": fecha_cierre,
        }
        updates = [(col, val) for col, val in campos.items() if es_valor_util(val)]
        if reclamos_pago_n is not None:
            updates.append(("reclamos_pago_n", int(reclamos_pago_n)))
        if not updates:
            return

        sql = f"UPDATE licitaciones SET {', '.join(f'{col} = ?' for col, _ in updates)} WHERE id_externo = ?"
        with self._get_connection() as conn:
            conn.execute(sql, [val for _, val in updates] + [id_externo])
            conn.commit()

    def reparar_datos_licitacion(self, id_externo, titulo_ia, organismo_ia, reclamos_ia):
        """
        Completar información faltante usando la inferencia semántica de la IA.

        Solo rellena título y organismo si el valor actual es un marcador de
        posición o está vacío, y nunca escribe valores vacíos. La interpretación
        de pagos de la IA se guarda en `reclamo_pago` y la UI la etiqueta como
        tal; el dato verificado de la fuente vive en `reclamos_pago_n`.
        """
        query_select = "SELECT titulo, organismo, reclamo_pago FROM licitaciones WHERE id_externo = ?"

        with self._get_connection() as conn:
            current = conn.execute(query_select, (id_externo,)).fetchone()

            if not current:
                return

            updates = []
            params = []

            titulo_actual = current['titulo'] or ""
            if (not es_valor_util(titulo_actual) or titulo_actual == f"Licitación {id_externo}") and es_valor_util(titulo_ia):
                updates.append("titulo = ?")
                params.append(titulo_ia)

            if not es_valor_util(current['organismo']) and es_valor_util(organismo_ia):
                updates.append("organismo = ?")
                params.append(organismo_ia)

            if es_valor_util(reclamos_ia):
                updates.append("reclamo_pago = ?")
                params.append(reclamos_ia)

            if updates:
                sql_update = f"UPDATE licitaciones SET {', '.join(updates)} WHERE id_externo = ?"
                params.append(id_externo)
                conn.execute(sql_update, params)
                conn.commit()
