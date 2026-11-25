# Algunos Indios AI Director

Panel local de dirección de escenas para OBS Studio, con selección automática, recomendaciones de IA y un modo de simulación para probar la interfaz sin OBS.

## Inicio rápido en Windows

1. Instala **Python 3.11 o superior** desde [python.org](https://www.python.org/downloads/) (marca «Add python.exe to PATH» si no usas el lanzador `py`). Necesitas conexión a Internet la primera vez para descargar dependencias.
2. Descomprime o clona el proyecto en una carpeta local. Haz doble clic en **`INICIAR.bat`** desde la raíz del proyecto.
3. El lanzador crea `.venv` si falta, comprueba Python, instala solo las dependencias ausentes/incompatibles mediante pip y ejecuta `python -m backend.main`. El servidor se limita a `127.0.0.1:8765` y abre la interfaz en el navegador predeterminado; si no se abre, visita `http://127.0.0.1:8765/` manualmente.
4. Mantén abierta la consola mientras uses la aplicación. Para detenerla, pulsa **Ctrl+C**. Si el inicio falla, la consola se queda abierta para que puedas leer el error.

No necesitas Node.js ni instalar paquetes globales: la interfaz se sirve desde el backend y las dependencias se instalan en `.venv`. No expongas el servidor en Internet ni cambies su dirección de escucha sin valorar la seguridad de OBS y de la clave de IA.

### Ejecución manual

En Windows, desde la carpeta del proyecto:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m backend.main
```

En Linux/macOS (para desarrollo):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m backend.main
```

## OBS WebSocket v5

En OBS Studio activa el servidor WebSocket en **Herramientas → Ajustes del servidor WebSocket** (en algunas versiones, «Herramientas → obs-websocket Settings»). Anota el puerto y la contraseña configurados allí; el puerto habitual es **4455**. En el panel, en **Ajustes de cabina → Conexión OBS**, escribe el host (normalmente `localhost`), el puerto y la contraseña y pulsa **Conectar OBS**. Debe ser **WebSocket v5** (integrado en OBS Studio moderno), no el protocolo v4 antiguo. La contraseña se envía solo para establecer la conexión; no la guardes en el repositorio.

Tras conectarte, sincroniza las escenas; revisa sus pesos y tiempos antes de iniciar los cambios automáticos. OBS debe estar abierto y el servidor WebSocket habilitado. No habilites el servidor WebSocket de OBS hacia redes no confiables.

## Modo simulación (mock)

En **Ajustes de cabina → Conexión OBS**, pulsa **Modo simulación** para usar escenas ficticias sin OBS. Puedes probar selección, pausa, cambios manuales y configuración sin cambiar ninguna escena real. La simulación no verifica la conexión ni el comportamiento de OBS en producción.

## IA y credenciales

El modo automático local no requiere ninguna clave. En **Dirección inteligente** elige el **proveedor de la clave** y su **tipo de plan**: «Go (suscripción)», «Pago por uso (Console)» o «Detectar automáticamente». Con Go, la app llama directamente a `/inference/go/openai/v1` y envía `x-opencode-session`; con pago por uso usa `/inference/openai/v1`; en automático prueba el catálogo y, si recibe 401/402/403/404, reintenta una vez en la otra ruta y recuerda la que funciona. Un **HTTP 402 «Insufficient balance»** significa que la petición se envió a la vía pay-as-you-go teniendo clave Go: selecciona «Go (suscripción)». Guarda la clave en el formulario sin publicarla en chats, capturas ni issues. Pulsa «Modelos disponibles» para obtener el catálogo en directo (de tu cuenta si hay clave); los modelos `-free` de OpenCode no funcionan desde clientes externos. En Windows las claves se almacenan por proveedor en Credential Manager mediante `keyring`; en Linux/macOS se guardan en `data/.secrets.json` con permisos `0600` (ignorado por Git), salvo que uses `DEEPSEEK_API_KEY` u `OPENCODE_API_KEY` en el entorno, que tienen prioridad. El panel no devuelve nunca la clave ni la escribe en `data/settings.json`. Los errores del panel muestran el estado HTTP y el mensaje del proveedor, nunca la clave. `.env.example` documenta las variables, pero `INICIAR.bat` no carga `.env` automáticamente. La IA recibe metadatos de escenas, **no analiza vídeo ni audio**. Las peticiones reales precisan Internet y una cuenta con acceso al modelo y pueden generar costes. Consulta [el estudio de modelos y latencia](docs/LATENCIA_MODELOS.md).

## Servidor Linux de ensayo

El servicio `ai-director.service` está instalado y habilitado para arrancar como usuario `eduardo`. Escucha en la interfaz privada `10.208.99.128:8765` y se publica en **`http://10.208.99.128/`** mediante una `IngressRoute` de Traefik en el puerto 80 (namespace `ai-director`), sin tocar otras rutas del clúster. El servidor es headless: ábrelo desde otro equipo de la red privada. Aquí no hay OBS: conecta «Modo simulación» para probar IA con cinco escenas y la realización **detenida**. Comandos: `systemctl status ai-director`, `journalctl -u ai-director -n 100 --no-pager`, `systemctl restart ai-director`; manifiesto en `deploy/traefik-private.yaml`. El panel no tiene autenticación propia y viaja en HTTP sin TLS: úsalo solo en la red privada de confianza. El servicio nunca activa cortes al arrancar. En Windows, `INICIAR.bat` conserva el valor local predeterminado `127.0.0.1:8765`.

## Pruebas

```powershell
.venv\Scripts\python.exe -m pytest -q
```

En Linux/macOS sustituye la ruta por `.venv/bin/python`. Las pruebas automatizadas usan simulaciones de OBS y respuestas HTTP simuladas para DeepSeek; no demuestran que una instalación real de OBS o una clave real de DeepSeek funcionen. **La conexión real OBS WebSocket v5 y las solicitudes reales de DeepSeek no se han validado en Windows/OBS con credenciales reales**; haz una prueba supervisada con OBS antes de usarlo en un directo. No uses una emisión crítica como primer ensayo.

## Uso en un ensayo

1. Abre OBS, activa WebSocket y arranca `INICIAR.bat`. Si OBS no está abierto, el panel indica «OBS desconectado» y reintenta cada cinco segundos; **no comienza a cortar por sí solo**.
2. En **Ajustes de cabina**, conecta a OBS con la contraseña de WebSocket. Pulsa **Sincronizar** si acabas de cambiar de colección. Las escenas aparecen por nombre y UUID cuando OBS lo proporciona; la aplicación no crea ni modifica escenas.
3. En **Escenas & cortes**, cada tarjeta muestra directamente «Ajustes de escena»: el interruptor activa/desactiva y **guarda inmediatamente** sin botón; peso, categoría y duraciones se guardan con «Guardar ajustes», **sin recargar la tarjeta**. Peso cero excluye la escena del motor. «Cortar a escena» ejecuta un cambio manual en **programa**; funciona tanto con modo estudio como sin él.
4. Elige **Automático** y un perfil **Concierto**, **Charla** o **Personalizado**. Configura tiempos mínimo/máximo, tiempo preferido, memoria e intensidad; pulsa «Guardar ritmo». Los cambios de ajustes se aplican sin reiniciar. Para un ejemplo, usa 8–20 s, preferido 12 s, memoria 2 y peso 5 para general, 4 para voz, 3 para guitarra. Los pesos son relativos entre candidatos, no porcentajes.
5. Pulsa **Iniciar director**. «Siguiente corte» adelanta una decisión; «Pausar» congela los cambios; «Reanudar» programa un nuevo intervalo; «Detener» cancela decisiones y deja la escena de OBS intacta. Cerrar la consola con Ctrl+C tampoco cierra OBS.
6. En «Perfiles de show», guarda el perfil actual, duplica uno seleccionándolo y escribiendo el nombre de la copia, carga otro o elimina uno propio. Los perfiles de fábrica no se pueden eliminar. El simulador muestra 20 decisiones con duración estimada sin tocar OBS y siempre utiliza el motor automático.
7. Un corte desde OBS/Stream Deck pausa automáticamente durante 30 s por defecto. Cambia la política a pausa indefinida, tiempo personalizado o continuar (respetando el mínimo antes del siguiente corte). Las escenas externas no se sobrescriben inmediatamente.

## AI Director experimental

Selecciona «DeepSeek directo» o «OpenCode Console», introduce una clave del **mismo proveedor**, pulsa «Modelos disponibles» y elige el modelo de tu cuenta. OpenCode suele ofrecer `deepseek-v4.1-flash` para clientes externos de pago; DeepSeek directo usa `deepseek-flash`. «Probar conexión IA» guarda primero los ajustes del proveedor/modelo y hace una **petición real** con metadatos actuales; muestra escena, motivo, duración y latencia sin cambiar OBS. Un HTTP 401 indica normalmente clave equivocada para ese proveedor; HTTP 403 puede indicar modelo sin acceso, plan sin saldo o intento de usar `-free` desde un cliente externo. El modo «Solo recomendaciones» consulta sin aplicar cortes. En modo ejecución se validan escena, permiso y duración. Si la llamada tarda más que el timeout configurado (puedes probar con **2 s** para un presupuesto estricto), conserva el plano o usa el motor local; **no garantiza** que toda petición responda en 1–2 s. La IA recibe solo metadatos, no ve ni oye el directo. Véase [latencia y modelos](docs/LATENCIA_MODELOS.md).

## Configuración y archivos

`data/settings.json` se guarda automáticamente con host/puerto OBS, escenas habilitadas, pesos, categorías, tiempos, política manual, perfiles, último modo y proveedor/modelo no sensibles; las claves **no** se incluyen. Se recupera al reiniciar, pero el realizador **siempre arranca detenido** para no cortar OBS accidentalmente. Si cierras el servidor, el historial y contador de esa sesión se reinician; no se restaura un directo en marcha. Para una copia de seguridad, copia ese JSON **con el servidor detenido**. Ejemplo de campos no sensibles (el archivo completo incluye más):

```json
{
  "settings": {
    "obs": {"host": "127.0.0.1", "port": 4455},
    "timing": {"min_seconds": 8, "max_seconds": 20, "preferred_seconds": 12, "memory": 2, "intensity": 0.7},
    "manual": {"policy": "temporary", "pause_seconds": 30},
    "ai": {"provider": "opencode", "model": "deepseek-v4.1-flash", "model_base_url": "https://opencode.ai/inference/openai/v1", "timeout_seconds": 2},
    "mode": "automatic",
    "active_profile": "Concierto"
  },
  "scenes": {},
  "profiles": {}
}
```

La contraseña OBS introducida desde el panel permanece en memoria del servidor durante la sesión (o se puede suministrar con `OBS_WEBSOCKET_PASSWORD` en el entorno). No se guarda en `settings.json`; tras cerrar el proceso, vuelve a introducirla para conectarte si OBS exige autenticación. Una escena retirada aparece como «NO ENCONTRADA» y se omite del motor, pero sus preferencias se conservan por si vuelve a la colección.

## Problemas frecuentes

- **«No se encuentra Python»**: instala Python 3.11+ con `py` o `python` disponible en PATH; vuelve a abrir `INICIAR.bat`.
- **Falla `venv` o pip**: instala Python con el componente `pip` y `venv` y verifica conexión a Internet en la primera instalación; si `.venv` quedó incompleto, bórralo y vuelve a ejecutar el lanzador.
- **Puerto 8765 ocupado**: cierra la otra instancia del servidor. El panel se sirve solo en `127.0.0.1:8765`.
- **OBS desconectado**: revisa que OBS esté abierto, WebSocket v5 activado, puerto/host correctos y contraseña válida. El botón «Desconectar» cancela los reintentos; vuelve a «Conectar OBS» para reactivarlos.
- **Escena no aparece**: pulsa «Sincronizar», revisa la colección abierta en OBS y comprueba si la tarjeta indica «NO ENCONTRADA».
- **No hay cortes**: activa al menos dos escenas con peso positivo; con una sola escena no hay transiciones útiles. Tras una reconexión pulsa «Iniciar director» explícitamente.
- **IA no responde**: comprueba clave, Internet, modelo y timeout. El modo automático continúa sin IA ni Internet. `deepseek-flash` puede cambiar según el proveedor; revisa la documentación oficial si devuelve error de modelo.

## Arquitectura

`backend/core.py` separa registro, configuración, adaptadores OBS (real/simulado), motor ponderado, cliente DeepSeek y planificador/controlador. `backend/main.py` expone FastAPI y un WebSocket de estado; `frontend/` es HTML/CSS/JavaScript sin compilación. Las cámaras, audio y análisis visual son posibles puntos de extensión, **no funcionalidades presentes** en esta versión.

## Datos locales y seguridad

`.venv`, `.env`, archivos de estado local, registros y credenciales están excluidos por `.gitignore`; `.env.example` solo contiene marcadores sin secretos. No almacenes claves en `README.md` ni en `settings.json`. El servicio está pensado para uso local en `127.0.0.1`; quien pueda usar el equipo durante la sesión puede operar el panel. Cierra la aplicación al terminar el directo.
