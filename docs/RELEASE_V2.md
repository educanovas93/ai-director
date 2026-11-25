# Revisión 2 — interfaz, OpenCode y latencia

## Cambios

- Las tarjetas de escena muestran todos los ajustes sin desplegar. El interruptor habilitar/deshabilitar se guarda inmediatamente por `PUT /api/scenes/{id}` y revierte en caso de error. «Guardar ajustes» conserva la tarjeta y el foco; solo actualiza los campos guardados, sin reconstruir la cuadrícula.
- Los ajustes no sensibles (escenas, pesos, categorías, tiempos, perfiles, política, modo y proveedor/modelo) se guardan automáticamente en `data/settings.json` y se recuperan al reiniciar. El motor no se reactiva por seguridad. Claves fuera del JSON, en Credential Manager en Windows o solo entorno/sesión en Linux.
- Selector de proveedor **DeepSeek directo / OpenCode Console**. Una clave OpenCode usa `/inference/openai/v1/chat/completions`, no el endpoint DeepSeek. Catálogo real de modelos, con filtro de modelos `-free` y de protocolos no compatibles; metadatos de modalidad y precios si el proveedor los devuelve. En OpenCode sin clave se muestra el catálogo público, con clave se consulta la cuenta.
- Diagnóstico seguro: HTTP 401/403/404/429 y timeouts explicados, error persistente en la prueba IA y fallback sin cortes no autorizados. Ni clave ni respuesta bruta del proveedor se escriben en logs o configuración.
- Instalado y habilitado `ai-director.service` como usuario `eduardo` en `127.0.0.1:8765`; arranque automático del servicio, **sin iniciar cortes**. La aprobación del host se concedió y el servicio respondió HTTP 200.
- Investigación de latencia, modelos y costes en [`LATENCIA_MODELOS.md`](LATENCIA_MODELOS.md). Audio/vídeo en tiempo real aún no se captura ni analiza: es una propuesta para fase posterior.

## Verificación ejecutada

- `PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`: **34 passed**, una advertencia de obsolescencia de `fastapi.testclient`/Starlette, sin errores.
- `node --check frontend/js/app.js`, `git diff --check` y `systemd-analyze verify deploy/ai-director.service`: sin errores.
- Navegador real con OBS simulado: cinco tarjetas con ajustes siempre visibles; el interruptor persistió inmediatamente; guardar peso/categoría mantuvo el mismo nodo DOM; catálogo público OpenCode cargó 13 modelos compatibles, incluido `deepseek-v4.1-flash`; a 390 px no hubo desbordamiento horizontal.
- Petición HTTP real al catálogo público OpenCode: 13 modelos compatibles. Peticiones de decisión con clave OpenCode/DeepSeek y errores 401 simuladas con transporte HTTP; **no** hay clave real disponible en este host, por lo que no se ha medido latencia de inferencia real.

## Servicio verificado

- `systemctl is-enabled` = `enabled`, `is-active` = `active`; puerto 8765 ligado únicamente a `127.0.0.1`. El adaptador simulado devolvió cinco escenas y el director siguió `stopped`; `data/settings.json` fue escrito por `eduardo` con permisos `600`.

## Pendiente

- Prueba con la clave del usuario introducida directamente en el panel (no por chat) para verificar acceso a modelos y latencia real.
- Validación con OBS real en Windows, especialmente modo estudio y Stream Deck. Las pruebas aquí usan OBS simulado.
