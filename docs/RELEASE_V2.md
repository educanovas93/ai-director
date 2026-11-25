# Revisión 2 — interfaz, OpenCode y despliegue en servidor

## Cambios

- Las tarjetas de escena muestran todos los ajustes sin desplegar. El interruptor habilitar/deshabilitar se guarda inmediatamente por `PUT /api/scenes/{id}` y revierte en caso de error. «Guardar ajustes» conserva la tarjeta y el foco; solo actualiza los campos guardados, sin reconstruir la cuadrícula.
- Los ajustes no sensibles (escenas, pesos, categorías, tiempos, perfiles, política, modo y proveedor/modelo) se guardan automáticamente en `data/settings.json` y se recuperan al reiniciar. El motor no se reactiva por seguridad.
- Selector de proveedor **DeepSeek directo / OpenCode Console**. Catálogo real de modelos, filtro de `-free` y de protocolos no compatibles, metadatos de modalidad y precio.
- **Claves OpenCode Go vs Console:** Go vive en `/inference/go/openai/v1` y exige `x-opencode-session`; Console en `/inference/openai/v1`. El panel permite fijar el plan (Go / pago por uso) o dejarlo en automático; en automático o ante 401/402/403/404 se reintenta en la otra ruta y se recuerda la válida. Con plan Go la petición sale directamente por la ruta Go (verificado con clave ficticia; falta la clave real). Si el modelo gasta `max_tokens` en razonamiento y devuelve contenido vacío, reintenta una vez con `reasoning_effort: none`.
- Diagnóstico seguro: se muestra estado HTTP + mensaje del proveedor (p. ej. «Invalid credential»), nunca la clave; el mismo resumen se registra en journal.
- Credenciales en Linux/macOS: `data/.secrets.json` con permisos `0600`, ignorado por Git; las variables de entorno tienen prioridad. En Windows se mantiene Credential Manager.
- Despliegue: `ai-director.service` como `eduardo`, escucha en `10.208.99.128:8765` y se publica en `http://10.208.99.128/` con una `IngressRoute` de Traefik (namespace `ai-director`). No se alteró ninguna ruta previa del clúster.
- Investigación de latencia, modelos y costes en [`LATENCIA_MODELOS.md`](LATENCIA_MODELOS.md).

## Verificación ejecutada

- `PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`: **43 passed**, una advertencia de obsolescencia de `fastapi.testclient`/Starlette.
- `node --check frontend/js/app.js`, `compileall backend`, `systemd-analyze verify`, `kubectl apply --dry-run=server`: sin errores.
- `http://10.208.99.128/` responde **HTTP 200** con el panel y WebSocket nativo funcionando a través de Traefik; `http://10.208.99.128:8765/` sigue disponible en la red privada.
- Prueba con clave ficticia: la API devolvió `502` con `OpenCode respondió HTTP 401` y `Proveedor: «Invalid credential»`, sin filtrar la clave; la clave sobrevivió a un reinicio del servicio (`key_status.opencode = true`) y el fichero quedó `0600`. Después se borró la clave ficticia.
- OBS simulado: cinco escenas, realización `stopped`.

## Pendiente

- Introducir la clave real en el panel y comprobar modelo, latencia y coste reales.
- Validación con OBS real en Windows, especialmente modo estudio y Stream Deck.
