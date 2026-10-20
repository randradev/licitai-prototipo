# -*- coding: utf-8 -*-
"""Fixtures compartidas. Ninguna prueba usa la BD real ni la red."""

import pytest

from core.database_mgr import DatabaseManager

# Texto sintético con la misma estructura que las fichas reales de Mercado Público
FICHA_EJEMPLO = """Licitación ID: 1234-5-LP26
Suministro de reactivos para laboratorio clínico
Responsable de esta licitación: HOSPITAL DE PRUEBA
Fecha de Cierre: 18-02-2099 16:00:00
Reclamos recibidos por incumplir plazo de pago: 181
Este número indica los reclamos recibidos por esta institución desde los últimos 12 meses hasta el día de ayer.
Descargar ficha

1. Características de la licitación
Nombre de la licitación: Suministro de reactivos para laboratorio clínico
Estado: Publicada
Descripción: Contrato de suministro de reactivos e insumos de laboratorio por 36 meses.

2. Organismo demandante
Razón social:\tHOSPITAL DE PRUEBA
Región en que se genera la licitación:\tRegión de los Lagos

3. Etapas y plazos
Fecha de Publicación: 05-02-2026 8:34:58
Fecha inicio de preguntas: 05-02-2026 9:00:00
"""


@pytest.fixture
def db(tmp_path):
    return DatabaseManager(str(tmp_path / "test.db"))


@pytest.fixture
def db_con_perfil(db):
    db.guardar_perfil("reactivos, microscopio", "limpieza", None, "Proveedores de laboratorio")
    return db
