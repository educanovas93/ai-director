# Informe de entrega — Algunos Indios AI Director

> Este documento corresponde a la primera entrega. La revisión de escenas, OpenCode y servicio Linux se documenta en [`docs/RELEASE_V2.md`](docs/RELEASE_V2.md).

## Alcance verificado

- Aplicación local FastAPI en `127.0.0.1:8765`, interfaz web sin Node y WebSocket de estado en `/ws/status`.
- Modo automático offline: selección aleatoria ponderada, memoria, límites de tiempo por escena, categorías, perfiles y simulación de 20 cortes.
- Cliente OBS WebSocket v5 mediante `obsws-python`: lectura de escenas/programa, cambio de **programa** por UUID o nombre, eventos de cambios/colección, reconexión y protección ante intervenciones externas. Se incluye OBS simulado.
- Modo DeepSeek experimental: petición HTTP real a `/chat/completions`, respuesta JSON validada, timeout, límites, recomendaciones sin aplicar, registro y fallback seguro.
- Persistencia de JSON no sensible. La API key en Windows usa Credential Manager mediante `keyring`; en Linux/macOS, solo entorno o sesión. Las credenciales no se devuelven en GET ni se guardan en el JSON general.
- `INICIAR.bat` prepara Python/venv/dependencias y abre el navegador tras el arranque. La compatibilidad de doble clic en Windows aún necesita ensayo en un Windows real.

## Estructura

```text
algunos-indios-ai-director/
├── INICIAR.bat
├── requirements.txt
├── README.md
├── INFORME_ENTREGA.md
├── .env.example
├── .gitattributes
├── .gitignore
├── LICENSE
├── docs/PLAN.md
├── src/.gitkeep (esqueleto anterior, no usado)
├── backend/
│   ├── __init__.py
│   ├── core.py
│   └── main.py
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── data/.gitkeep
└── tests/
    ├── test_core.py
    ├── test_api.py
    ├── test_recovery.py
    ├── test_regressions.py
    ├── test_events.py
    ├── test_profiles.py
    ├── test_scene_sync.py
    ├── test_concurrency.py
    ├── test_ai_history.py
    ├── test_ai_context.py
    ├── test_secrets.py
    └── test_timer.py
```

## Comprobaciones ejecutadas

- `PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`: **26 passed**, una advertencia de obsolescencia en `fastapi.testclient`/Starlette, sin fallos.
- `node --check frontend/js/app.js`: sin errores de sintaxis.
- `.venv/bin/python -m compileall -q backend`: sin errores de sintaxis.
- Servidor real lanzado en Linux: estado inicial desconectado/detenido; conexión simulada; cinco escenas; primer corte; simulación de 20 cortes; estado WebSocket recibido; parada sin modificar la escena al detener. HTML y JS servidos con HTTP 200.
- Navegador Chromium: controles y escenas simuladas renderizados, cortes y registro visibles, simulador muestra 20 filas; a 390 px no hubo desbordamiento horizontal.
- El proceso de prueba fue detenido y `data/settings.json` de simulación eliminado; el proyecto queda en estado limpio para el primer arranque.

## Validación pendiente

- Este host no tiene ejecutable OBS ni puerto WebSocket 4455 abierto; **no se han comprobado cortes en OBS real**, con modo estudio activado/desactivado, ni eventos de una Stream Deck real.
- No hay `DEEPSEEK_API_KEY` disponible; la ruta HTTP y las respuestas se han probado con transporte simulado, **no** con una cuenta DeepSeek real.
- El anfitrión es Linux: `INICIAR.bat`, Windows Credential Manager y apertura automática del navegador en Windows quedan **sin ensayo de plataforma**.

Antes de un directo, prueba en Windows con una colección OBS no crítica, verifica programa en modo estudio y pulsa detener para confirmar que OBS conserva su escena. Consulta `README.md` para la guía de instalación y resolución de problemas.
