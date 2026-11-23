# Plan y estado — Algunos Indios AI Director

Este repositorio comenzó como un esqueleto. La primera implementación utilizable está en la raíz: `backend/`, `frontend/`, `tests/`, `INICIAR.bat` y `README.md`. `src/.gitkeep` queda únicamente como vestigio del esqueleto inicial; no se usa para ejecutar el proyecto.

## Fases entregadas

1. **Base:** FastAPI local, panel HTML/CSS/JS sin Node, OBS WebSocket v5 y adaptador simulado.
2. **Automático:** selección ponderada, memoria, duraciones, planificación cancelable, pausa por intervención externa, perfiles persistentes.
3. **Interfaz:** monitor en tiempo real por WebSocket, edición de escenas, historial y simulador de 20 cambios.
4. **DeepSeek experimental:** peticiones reales a Chat Completions con metadatos, JSON validado, modo recomendación, timeout y fallback.
5. **Verificación:** pruebas pytest con OBS y HTTP simulados, smoke HTTP/WebSocket y navegador local. Consulta `INFORME_ENTREGA.md`.

## Validación en entorno de producción pendiente

- Prueba supervisada con OBS real, tanto con modo estudio activado como desactivado, y una Stream Deck real.
- Prueba en Windows del doble clic de `INICIAR.bat` y de Credential Manager.
- Prueba con una API key real de DeepSeek; el modelo no recibe vídeo ni audio.

## Extensiones futuras

Los contratos de decisión permiten añadir proveedores de metadatos de audio/vídeo, detección de voz o músicos, reconocimiento de secciones musicales y zoom dinámico sin modificar la política básica de validación y cortes. Ninguna de esas capacidades de análisis está presente en el MVP.
