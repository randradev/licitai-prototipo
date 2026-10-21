# -*- coding: utf-8 -*-
import json
import sqlite3

from core.database_mgr import DatabaseManager, COLUMNAS_NUEVAS

ESQUEMA_ANTIGUO = """
CREATE TABLE licitaciones (
    id_externo TEXT PRIMARY KEY, titulo TEXT NOT NULL, organismo TEXT, fecha_cierre TEXT,
    fecha_publicacion TEXT, reclamo_pago TEXT, link TEXT, descripcion_pro TEXT, score_ia INTEGER,
    analisis_ia_json TEXT, estado TEXT DEFAULT 'pendiente', motivo_archivo TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)"""


def _columnas(path):
    conn = sqlite3.connect(path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(licitaciones)")}
    finally:
        conn.close()


def test_inicializacion_crea_tablas_y_columnas(tmp_path):
    path = str(tmp_path / "sub" / "nueva.db")
    DatabaseManager(path)
    assert set(COLUMNAS_NUEVAS) <= _columnas(path)


def test_migracion_desde_esquema_antiguo_sin_perder_filas(tmp_path):
    path = str(tmp_path / "vieja.db")
    conn = sqlite3.connect(path)
    conn.execute(ESQUEMA_ANTIGUO)
    conn.execute("INSERT INTO licitaciones (id_externo, titulo, estado, score_ia) VALUES ('A-1', 'Título', 'analizado', 8)")
    conn.commit()
    conn.close()

    db = DatabaseManager(path)
    DatabaseManager(path)  # Idempotente
    fila = db.obtener_licitacion("A-1")
    assert fila["titulo"] == "Título" and fila["score_ia"] == 8 and fila["estado"] == "analizado"
    assert fila["intentos"] == 0
    assert set(COLUMNAS_NUEVAS) <= _columnas(path)


def test_database_path_desde_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "env.db"))
    db = DatabaseManager()
    assert db.db_path == str(tmp_path / "env.db")


def test_perfil_ausente_y_guardado(db):
    assert db.obtener_perfil() is None
    db.guardar_perfil("a", "b", None, "bio")
    assert db.obtener_perfil()["keywords_pos"] == "a"


def test_guardar_licitacion_sin_duplicados(db):
    data = {"id_externo": "X-1", "titulo": "Reactivos", "fecha_cierre": "2099-01-01T10:00:00"}
    assert db.guardar_licitacion(data) is True
    assert db.guardar_licitacion(data) is False
    assert len(db.obtener_licitaciones()) == 1
    fila = db.obtener_licitacion("X-1")
    assert fila["estado"] == "pendiente"
    assert fila["fecha_publicacion"] is None   # Nunca 'Procesando...'
    assert fila["organismo"] is None


def test_guardar_licitacion_sin_titulo_usa_id(db):
    db.guardar_licitacion({"id_externo": "X-2", "titulo": None})
    assert db.obtener_licitacion("X-2")["titulo"] == "Licitación X-2"


def test_orden_cronologico_y_nulos_al_final(db):
    for id_, fecha in [("A", "2026-09-30"), ("B", "2027-01-10"), ("C", None), ("D", "2026-02-09")]:
        db.guardar_licitacion({"id_externo": id_, "titulo": id_, "fecha_publicacion": fecha})
    assert [l["id_externo"] for l in db.obtener_licitaciones()] == ["B", "A", "D", "C"]


def test_actualizar_datos_maestros_ignora_marcadores(db):
    db.guardar_licitacion({"id_externo": "X", "titulo": "Título API"})
    db.actualizar_datos_maestros("X", titulo="Sin título", organismo="No detectado", fecha_pub=None, reclamos_pago_n=0)
    fila = db.obtener_licitacion("X")
    assert fila["titulo"] == "Título API"
    assert fila["organismo"] is None
    assert fila["reclamos_pago_n"] == 0   # 0 es un dato válido


def test_reparar_no_escribe_none_ni_pisa_datos_reales(db):
    db.guardar_licitacion({"id_externo": "X", "titulo": "Título API", "organismo": "Hospital Real"})
    db.reparar_datos_licitacion("X", None, None, None)
    db.reparar_datos_licitacion("X", "Otro título", "Otro organismo", "Interpretación")
    fila = db.obtener_licitacion("X")
    assert fila["titulo"] == "Título API"
    assert fila["organismo"] == "Hospital Real"
    assert fila["reclamo_pago"] == "Interpretación"


def test_reparar_rellena_huecos(db):
    db.guardar_licitacion({"id_externo": "X", "titulo": None})
    db.reparar_datos_licitacion("X", "Título IA", "Organismo IA", None)
    fila = db.obtener_licitacion("X")
    assert fila["titulo"] == "Título IA" and fila["organismo"] == "Organismo IA"


def test_ciclo_fallos_error_y_reintento(db):
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    assert db.registrar_fallo("X", "falla 1", max_intentos=3) == "pendiente"
    assert db.registrar_fallo("X", "falla 2", max_intentos=3) == "pendiente"
    assert db.registrar_fallo("X", "falla 3", max_intentos=3) == "error"
    fila = db.obtener_licitacion("X")
    assert fila["intentos"] == 3 and fila["ultimo_error"] == "falla 3"
    assert db.obtener_cola_procesamiento(3) == []

    db.reintentar("X")
    fila = db.obtener_licitacion("X")
    assert fila["estado"] == "pendiente" and fila["intentos"] == 0 and fila["ultimo_error"] is None
    assert len(db.obtener_cola_procesamiento(3)) == 1


def test_reintentar_con_texto_vuelve_a_extraido(db):
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    db.actualizar_detalle_profundo("X", "http://x", "texto")
    db.marcar_error("X", "IA caída")
    db.reintentar("X")
    assert db.obtener_licitacion("X")["estado"] == "extraido"


def test_guardar_analisis_conserva_favorita(db):
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    db.cambiar_estado("X", "favorita")
    db.guardar_analisis_ia("X", 9, {"veredicto": "ok"})
    fila = db.obtener_licitacion("X")
    assert fila["estado"] == "favorita" and fila["score_ia"] == 9


def test_guardar_notas_persiste(db, tmp_path):
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    db.guardar_notas("X", "Costos revisados", {"bases_leidas": True, "anexos_preparados": False})
    fila = DatabaseManager(db.db_path).obtener_licitacion("X")   # Nueva instancia = nueva sesión
    assert fila["notas"] == "Costos revisados"
    assert json.loads(fila["checklist_json"]) == {"bases_leidas": True, "anexos_preparados": False}


# --- Rúbrica: compatibilidad con análisis históricos e historial ---

def test_analisis_historico_se_conserva_tal_cual_al_migrar(tmp_path):
    """Un análisis 1-10 de una BD antigua no se recalcula ni se convierte: queda como histórico."""
    from core.rubrica import resultado_guardado
    path = str(tmp_path / "vieja.db")
    conn = sqlite3.connect(path)
    conn.execute(ESQUEMA_ANTIGUO)
    conn.execute("INSERT INTO licitaciones (id_externo, titulo, estado, score_ia, analisis_ia_json)"
                 " VALUES ('A-1', 'Título', 'analizado', 8, '{\"veredicto\": \"ok\"}')")
    conn.commit()
    conn.close()

    fila = DatabaseManager(path).obtener_licitacion("A-1")
    assert fila["score_ia"] == 8 and fila["analisis_ia_json"] == '{"veredicto": "ok"}'
    assert (fila["score_idoneidad"], fila["score_estado"], fila["rubrica_version"], fila["ficha_fecha"]) == (None,) * 4
    assert resultado_guardado(fila)["estado"] == "historico"


def test_reanalisis_archiva_el_analisis_anterior_con_su_evaluacion(db):
    rubrica_v1 = {"version": "v1", "estado": "definitivo", "score": 83, "cobertura": 100}
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    db.guardar_analisis_ia("X", 7, {"veredicto": "histórico"}, prompt_version="viejo")
    assert db.obtener_historial("X") == []   # El primer análisis no reemplaza nada
    db.guardar_evaluacion("X", "muy_alto", "no", "pide experiencia")

    db.guardar_analisis_ia("X", None, {"veredicto": "nuevo"}, prompt_version="nuevo", rubrica=rubrica_v1)
    fila = db.obtener_licitacion("X")
    assert (fila["score_ia"], fila["score_idoneidad"], fila["score_estado"], fila["rubrica_version"]) == (None, 83, "definitivo", "v1")
    historial = db.obtener_historial("X")
    assert len(historial) == 1
    h = historial[0]
    assert (h["score_ia"], h["rubrica_version"], h["analisis_prompt_version"]) == (7, None, "viejo")
    assert json.loads(h["analisis_ia_json"])["veredicto"] == "histórico"
    assert (h["eval_score"], h["eval_postularia"], h["eval_comentario"]) == ("muy_alto", "no", "pide experiencia")
    assert h["reemplazado"]

    db.guardar_analisis_ia("X", None, {"veredicto": "otro"}, rubrica=dict(rubrica_v1, score=60))
    assert [h["score_idoneidad"] for h in db.obtener_historial("X")] == [83, None]   # Más reciente primero


def test_lectura_de_ficha_registra_su_fecha(db):
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    db.actualizar_detalle_profundo("X", "http://x", "texto")
    assert db.obtener_licitacion("X")["ficha_fecha"]


def test_cola_prioriza_las_no_intentadas_sobre_los_reintentos(db):
    """Un reintento no ocupa el cupo de una licitación nueva, aunque sea más antigua."""
    for id_ in ("VIEJA_FALLIDA", "VIEJA_OK", "NUEVA"):
        db.guardar_licitacion({"id_externo": id_, "titulo": id_})
    conn = sqlite3.connect(db.db_path)
    conn.execute("UPDATE licitaciones SET fecha_creacion = '2026-10-01 10:00:00' WHERE id_externo LIKE 'VIEJA%'")
    conn.execute("UPDATE licitaciones SET fecha_creacion = '2026-10-21 10:00:00' WHERE id_externo = 'NUEVA'")
    conn.commit(); conn.close()
    db.registrar_fallo("VIEJA_FALLIDA", "IA: inválida", 3)
    db.registrar_fallo("VIEJA_FALLIDA", "IA: inválida", 3)
    assert [l["id_externo"] for l in db.obtener_cola_procesamiento(3)] == ["VIEJA_OK", "NUEVA", "VIEJA_FALLIDA"]
    db.registrar_fallo("VIEJA_FALLIDA", "IA: inválida", 3)   # Tercer fallo: sale de la cola
    assert [l["id_externo"] for l in db.obtener_cola_procesamiento(3)] == ["VIEJA_OK", "NUEVA"]
    assert db.obtener_licitacion("VIEJA_FALLIDA")["estado"] == "error"
