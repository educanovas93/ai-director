# Latencia, modelos y coste para la realización en vivo

Estado de la investigación: **24 de noviembre de 2026 (UTC)**. Los precios y catálogos son variables; vuelve a consultarlos antes de contratar un proveedor.

## Qué hace esta versión

AI Director **solo envía metadatos** (escenas, historial, tiempo desde el corte e instrucciones). No envía audio ni fotogramas. La elección de un modelo que acepte imágenes no activa por sí sola análisis visual. El planificador mantiene un fallback local y descarta respuestas de una generación anterior tras pausar, detener o cambiar de modo.

## Claves y catálogo

- Una clave **OpenCode Console** debe llamar a `https://opencode.ai/inference/openai/v1/chat/completions` con un ID como `deepseek-v4.1-flash`; una clave **DeepSeek** debe llamar a `https://api.deepseek.com/chat/completions` con `deepseek-flash`. Son servicios y credenciales distintos. OpenCode advierte que sus modelos `-free` no admiten clientes externos, incluso con clave.[1][3]
- OpenCode ofrece un catálogo autenticado por cuenta (`/console/api/v1/models`) y otro público (`/inference/v1/models`); el primero incluye proveedores conectados y metadatos de modalidad y precios.[2]
- En la consulta pública hecha para este proyecto, `deepseek-v4.1-flash` figuraba a **$0.12/M tokens de entrada y $0.48/M de salida**, con entrada de texto e imágenes. Esa disponibilidad no garantiza acceso a la cuenta del usuario ni latencia determinada.[8]
- DeepSeek publica `deepseek-flash` con entrada visual y precios de texto de **$0.15/M entrada y $0.60/M salida fuera de pico**, y **$0.30/M y $1.20/M en pico**; los cachés tienen otro precio.[3]

## Orden de preferencia para un directo

1. **MVP más estable y barato:** motor local como árbitro de seguridad; llamadas de texto cortas a DeepSeek Flash (directo u OpenCode) solo cuando hay una decisión útil. Recomendación de diseño: limitar el prompt al contexto incremental, desactivar razonamiento largo, `max_tokens` bajo, timeout objetivo de 1–2 s y fallback local. Se debe medir **p50, p95 y tasa de timeout** con la clave, región y red reales; ninguna documentación garantiza 1–2 s para cada petición.[1][3]
2. **Próximo paso audiovisual eficiente:** detectar eventos en local (actividad de audio, VAD, cambios de intensidad) y enviar **solo una instantánea** de OBS cuando el evento lo justifique, no todos los fotogramas. El catálogo actual de OpenCode declara entrada de imagen para Flash; DeepSeek también declara visión para `deepseek-flash`. Falta implementar captura, redacción de datos, sincronización y presupuesto de tokens.[8][3]
3. **Si hace falta escuchar y mirar de forma continua:** Gemini Live procesa flujos de audio e imágenes por WebSocket, con imágenes JPEG limitadas a **1 FPS** según su especificación; el modelo Live nativo de Gemini 2.5 Flash figura a **$3/M tokens de entrada de audio/vídeo** y **$12/M de salida de audio** en la tarifa de pago consultada. Requiere otra integración, gestión de sesiones y prueba de latencia real.[4][5]
4. **Alternativa multimodal:** OpenAI Realtime admite audio e imagen de entrada y respuestas textuales mediante una sesión WebRTC/WebSocket. Su modelo `gpt-realtime-2.1-mini` figura a **$10/M tokens de audio de entrada**, **$0.80/M de imagen de entrada** y **$0.60/M de texto de entrada** en la tarifa consultada. Es una opción a evaluar si Gemini Live no cumple, no una función de esta versión.[6][7]

## Presupuesto orientativo solo de texto

Supuesto hipotético de **5 decisiones/minuto**, **500 tokens de entrada + 80 de salida por petición**, sin imágenes/audio, descuentos de caché, impuestos ni coste de infraestructura:

- OpenCode `deepseek-v4.1-flash`: aproximadamente **$0.0295/h** a los precios del catálogo público consultado.[8]
- DeepSeek `deepseek-flash`: aproximadamente **$0.0369/h fuera de pico** o **$0.0738/h en pico**.[3]

Son cálculos, **no mediciones de consumo real**. El panel muestra la latencia y el `usage`/`cost` que devuelva el proveedor cuando estén disponibles; prueba varios modelos con tu clave antes de elegir. Las peticiones que excedan el timeout no deben retrasar un corte: se conserva el plano o interviene el motor automático, según la política configurada.

## Prueba de latencia recomendada

1. Conecta OBS simulado, selecciona proveedor/modelo y guarda su clave en el panel; no envíes la clave por chat ni la incluyas en capturas.
2. Repite «Probar conexión IA» en momentos distintos y anota latencia, errores HTTP, coste y motivo. Un solo acierto no demuestra p95 < 2 s.
3. Para un ensayo serio, registra 50–100 decisiones con audio/vídeo de prueba y mide tiempo desde **evento visual/acústico → decisión validada → escena en programa**, no solo tiempo HTTP.
4. Si p95 o timeout incumplen el objetivo, mantén el corte local y usa la IA solo para ajustar pesos/estilo fuera de la ventana crítica. **No retrases la emisión esperando al modelo.**

## Sources

[1] https://opencode.ai/docs/console/api/inference
[2] https://opencode.ai/docs/console/api/models
[3] https://api-docs.deepseek.com/quick_start/pricing
[4] https://aistudio.google.com/docs/live-api
[5] https://aistudio.google.com/docs/pricing
[6] https://developers.openai.com/api/docs/guides/realtime-conversations
[7] https://developers.openai.com/api/docs/pricing
[8] https://opencode.ai/inference/v1/models
