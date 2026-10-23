# Demo pública de LicitAI (rama `demo/streamlit`)

Versión de demostración desplegada en Streamlit Community Cloud. Se puede recorrer toda la interfaz con datos reales capturados de Mercado Público, pero **no se sincroniza ni se ejecutan análisis con IA**. La versión funcional del proyecto es `main` y no se modifica; su respaldo es la etiqueta `prototipo-2026-10-23`.

## Qué cambia respecto de `main`

| Archivo | Cambio |
|---|---|
| `core/config.py` | `MODO_DEMO` (variable `LICITAI_DEMO`), `FECHA_DEMO` (variable `LICITAI_DEMO_FECHA`) y `ahora()` |
| `web/vistas.py` | Con `MODO_DEMO`: aviso de demo en la cabecera y deshabilita «Sincronizar ahora», «Actualizar análisis», «Analizar ahora» y «Actualizar N análisis» |
| `core/parsing.py`, `web/panorama.py` | «Hoy» se obtiene de `config.ahora()` en lugar de `datetime.now()` |
| `tests/test_demo.py` | Pruebas del modo demo (con y sin las variables) |
| `requirements.txt` | Mismo contenido, guardado en UTF-8 en vez de UTF-16 |
| `demo/licitai-demo.db` | Copia de la BD local del 23/10/2026, con los comentarios de evaluación sin prefijos internos |

**Sin las variables, el código se comporta igual que en `main`**: `MODO_DEMO` es `False` por defecto y `ahora()` devuelve `datetime.now()`.

## Variables (Streamlit Cloud → Settings → Secrets)

```toml
LICITAI_DEMO = "true"                    # Aviso de demo y botones de IA/sincronización deshabilitados
LICITAI_DEMO_FECHA = "2026-10-23"        # La app se muestra como si hoy fuera ese día (los datos no "caducan")
DATABASE_PATH = "demo/licitai-demo.db"   # BD de demostración versionada en esta rama
```

**No agregar nunca `GEMINI_API_KEY` ni `MP_TICKET` a la demo.** Sin ellas, aunque un botón se habilitara, la app no puede llamar a Gemini, a Selenium ni a la API de Mercado Público: `AIAnalyst` falla antes de cualquier conexión.

## Despliegue

share.streamlit.io → *Create app* → repo `randradev/licitai-prototipo`, rama `demo/streamlit`, archivo principal `web/app.py`. En *Advanced settings*: Python 3.11 y los Secrets de arriba.

Lo que hacen los visitantes (favoritas, evaluaciones, notas, perfil) queda en la BD del contenedor y lo ven los demás visitantes hasta que la app se reinicia (por un push, un *Reboot* o al despertar tras inactividad). En ese momento vuelve a `demo/licitai-demo.db`. Para limpiar a mano: *Manage app → Reboot app*.

## Apagar o retirar la demo

1. **Apagar solo el modo demo:** borrar `LICITAI_DEMO` y `LICITAI_DEMO_FECHA` de Secrets y reiniciar la app. La app queda como `main`, y sin claves las acciones de IA fallan de forma segura.
2. **Retirar la demo:** *Delete app* en Streamlit Cloud. Después, si se quiere, borrar la rama:
   ```bash
   git switch main
   git branch -D demo/streamlit
   git push origin --delete demo/streamlit
   ```

## Comprobar que el original sigue intacto

```bash
git log --oneline main..demo/streamlit     # Los commits de la demo solo están en esta rama
git diff prototipo-2026-10-23 main --stat  # Vacío mientras main no avance
git switch main
venv/Scripts/python.exe -m pytest          # Suite completa de main
run_app.bat                                # App local con tu .env
```

Regla: la demo se actualiza con `git merge main` desde esta rama. **Nunca** se hace merge de `demo/streamlit` hacia `main`.

## Regenerar la BD de demostración

Desde la raíz, en esta rama, con la BD local actualizada:

```bash
venv/Scripts/python.exe -I -c "import sqlite3; s=sqlite3.connect('file:data/mp_database.db?mode=ro', uri=True); d=sqlite3.connect('demo/licitai-demo.db'); s.backup(d); d.execute(\"UPDATE licitaciones SET eval_comentario = TRIM(SUBSTR(eval_comentario, INSTR(eval_comentario, ']') + 1)) WHERE eval_comentario LIKE '[Simulada%'\"); d.commit(); d.execute('VACUUM'); d.close()"
```

Después, actualizar `LICITAI_DEMO_FECHA` al último día de la captura y las fechas del aviso (`AVISO_DEMO` en `web/vistas.py`).

**Nunca versionar la BD demo como `data/mp_database.db`.** Al cambiar de rama, Git podría sobrescribir la BD local real, porque es un archivo ignorado.
