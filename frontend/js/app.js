(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const state = { status: null, config: null, scenes: [], profiles: [], aiModels: [], aiCatalogWarning: '', ws: null, retry: null, statusTimer: null, history: [], scenesRevision: null };
  const labels = { automatic: 'Automático', ai: 'Con IA', running: 'En directo', paused: 'En pausa', stopped: 'Detenido', idle: 'En espera', start: 'Iniciado', pause: 'Pausado', resume: 'Reanudado', stop: 'Detenido' };
  const categories = { general: 'General', voice: 'Voz', guitar: 'Guitarra', bass: 'Bajo', drums: 'Batería', zoom: 'Detalle', multi: 'Múltiple', other: 'Otra' };
  const label = value => labels[String(value || '').toLowerCase()] || String(value || '—');
  const safeNumber = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };
  const setText = (selector, value) => { const node = $(selector); if (node) node.textContent = String(value ?? '—'); };

  async function request(path, { method = 'GET', body } = {}) {
    const options = { method, headers: { Accept: 'application/json' }, credentials: 'same-origin' };
    if (body !== undefined) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    let response;
    try { response = await fetch(path, options); }
    catch { throw new Error('No se puede contactar con el servidor. Comprueba que está en marcha.'); }
    const raw = await response.text();
    let data = null;
    if (raw) {
      try { data = JSON.parse(raw); }
      catch { if (response.ok) throw new Error('El servidor devolvió una respuesta no válida.'); }
    }
    if (!response.ok) {
      const detail = data && (data.detail || data.error || data.message);
      const message = typeof detail === 'string' ? detail : detail && typeof detail === 'object'
        ? [detail.message, detail.hint].filter(Boolean).join(' — ') : `Error ${response.status} al comunicarse con el servidor.`;
      throw new Error(message);
    }
    return data;
  }

  function toast(message, error = false) {
    const stack = $('#toast-stack');
    const item = el('div', `toast${error ? ' error' : ''}`);
    item.setAttribute('role', error ? 'alert' : 'status');
    item.append(el('span', '', message));
    const close = el('button', '', '×');
    close.type = 'button'; close.setAttribute('aria-label', 'Cerrar aviso');
    close.addEventListener('click', () => item.remove());
    item.append(close); stack.append(item);
    window.setTimeout(() => item.remove(), error ? 8000 : 5000);
  }
  function showError(error) { toast(error instanceof Error ? error.message : String(error), true); }
  async function busy(button, task) {
    if (button?.disabled) return;
    if (button) button.disabled = true;
    try { await task(); }
    catch (error) { showError(error); }
    finally { if (button) button.disabled = false; }
  }
  function duration(value) {
    const total = Math.max(0, Math.floor(safeNumber(value) || 0));
    const hours = Math.floor(total / 3600);
    const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, '0');
    const seconds = String(total % 60).padStart(2, '0');
    return hours ? `${hours}:${minutes}:${seconds}` : `${minutes}:${seconds}`;
  }
  function displayUsage(value) {
    if (value == null) return '—';
    if (typeof value === 'number' || typeof value === 'string') return String(value);
    if (typeof value === 'object') {
      const parts = Object.entries(value).filter(([, v]) => typeof v === 'number' || typeof v === 'string');
      return parts.length ? parts.map(([key, v]) => `${key}: ${v}`).join(' · ') : '—';
    }
    return '—';
  }

  function renderStatus(data) {
    if (!data || typeof data !== 'object') return;
    state.status = data;
    if (data.scene_revision !== undefined && data.scene_revision !== state.scenesRevision) {
      state.scenesRevision = data.scene_revision;
      refreshScenes().catch(showError);
    }
    const connected = !!data.obs_connected;
    const simulated = !!data.simulated;
    const live = ['running', 'active', 'started'].includes(String(data.state || '').toLowerCase());
    const paused = String(data.state || '').toLowerCase() === 'paused';
    const statusText = connected ? (simulated ? 'Simulación activa' : 'OBS conectado') : 'OBS desconectado';
    setText('#connection-label', statusText);
    setText('#sidebar-connection', statusText);
    $('#connection-pill').className = `connection-pill ${connected && simulated ? 'simulated' : connected ? 'online' : ''}`;
    $('#sidebar-led').className = `tiny-led ${connected && simulated ? 'simulated' : connected ? 'online' : ''}`;
    $('.session-tag-dot').classList.toggle('online', live);
    setText('#session-label', live ? 'Sesión en directo' : paused ? 'Sesión en pausa' : 'Sesión en espera');
    setText('#current-scene', data.current_scene || 'Sin señal');
    setText('#program-caption', live ? 'En programa ahora mismo' : connected ? 'Señal disponible' : 'Conecta OBS para comenzar.');
    setText('#signal-label', connected && simulated ? 'SEÑAL SIMULADA' : connected ? 'SEÑAL CONECTADA' : 'SEÑAL SIN CONECTAR');
    setText('#program-state', label(data.state).toUpperCase());
    $('#program-state').className = `status-tag ${paused ? 'paused' : live ? '' : 'stopped'}`;
    $('.hero-card').classList.toggle('is-running', live);
    const next = safeNumber(data.next_cut_in);
    setText('#countdown', next == null ? '—' : Math.max(0, Math.ceil(next)));
    // The unit belongs to the countdown element and is rebuilt after updating the number.
    $('#countdown').append(el('span', 'countdown-unit', 's'));
    setText('#countdown-caption', live ? 'Hasta el siguiente cambio de plano' : paused ? 'Temporizador en pausa' : 'El director está en espera');
    setText('#mode-indicator', label(data.mode).toUpperCase());
    setText('#session-time', duration(data.session_seconds));
    setText('#total-changes', safeNumber(data.total_changes) ?? 0);
    const latency = safeNumber(data.ai_latency);
    setText('#ai-latency', latency == null ? '—' : `${Math.round(latency * 1000)} ms`);
    setText('#ai-usage', displayUsage(data.ai_usage));
    setText('#last-decision', data.last_decision || 'Sin decisiones todavía.');
    setText('#decision-reason', data.reason || 'El razonamiento aparecerá aquí cuando el director entre en acción.');
    const errorBox = $('#global-error');
    errorBox.hidden = !data.error;
    if (data.error) errorBox.textContent = String(data.error);
    $('#start-btn').disabled = live || paused || !connected;
    $('#pause-btn').disabled = !live;
    $('#resume-btn').disabled = !paused;
    $('#next-btn').disabled = !live;
    $('#stop-btn').disabled = !live && !paused;
    for (const button of document.querySelectorAll('[data-mode]')) {
      const current = String(data.mode || '').toLowerCase();
      button.classList.toggle('active', button.dataset.mode === current);
      button.setAttribute('aria-pressed', String(button.classList.contains('active')));
    }
    const unknown = $('#mode-unknown');
    unknown.hidden = !data.mode || ['automatic', 'ai'].includes(String(data.mode).toLowerCase());
    if (!unknown.hidden) unknown.textContent = `Modo actual: ${data.mode}`;
    if (Array.isArray(data.history)) renderHistory(data.history);
    if (state.scenes.length) updateSceneCurrent();
  }

  function updateSceneCurrent() {
    const current = state.status?.current_scene;
    for (const card of document.querySelectorAll('.scene-card')) {
      const scene = state.scenes.find(item => String(item.id) === card.dataset.sceneId);
      const active = !!scene && (String(scene.id) === String(current) || String(scene.name) === String(current));
      card.classList.toggle('current', active);
      const badge = $('.scene-badge', card);
      if (badge && !scene?.missing) badge.textContent = active ? 'EN PROGRAMA' : scene?.enabled === false ? 'DESACTIVADA' : 'DISPONIBLE';
    }
  }

  function updateSceneCard(scene) {
    const card = [...document.querySelectorAll('.scene-card')].find(node => node.dataset.sceneId === String(scene.id));
    if (card) {
      const fields = card.querySelectorAll('.scene-meta span');
      if (fields[0]) fields[0].textContent = categories[scene.category] || scene.category || 'Sin categoría';
      if (fields[1]) fields[1].textContent = `Peso ${scene.weight}`;
      card.classList.toggle('missing', !!scene.missing);
    }
    const enabled = state.scenes.filter(item => item.enabled && !item.missing).length;
    setText('#scene-summary', `${state.scenes.length} escenas · ${enabled} disponibles`);
    updateSceneCurrent();
  }

  function renderScenes(scenes) {
    state.scenes = Array.isArray(scenes) ? scenes : [];
    const grid = $('#scene-grid'); grid.replaceChildren();
    const enabled = state.scenes.filter(scene => scene.enabled && !scene.missing).length;
    setText('#scene-summary', `${state.scenes.length} escenas · ${enabled} disponibles`);
    if (!state.scenes.length) { grid.append(el('p', 'empty-state', 'No hay escenas disponibles. Conecta OBS y sincroniza para cargarlas.')); return; }
    state.scenes.forEach((scene, index) => {
      const card = el('article', `scene-card${scene.missing ? ' missing' : ''}`);
      card.dataset.sceneId = String(scene.id);
      const top = el('div', 'scene-card-top');
      top.append(el('span', 'scene-number', `PLANO ${String(index + 1).padStart(2, '0')}`));
      top.append(el('span', `scene-badge${scene.missing ? ' warning' : ''}`, scene.missing ? 'NO ENCONTRADA' : scene.enabled === false ? 'DESACTIVADA' : 'DISPONIBLE'));
      card.append(top, el('h3', '', scene.name || String(scene.id)));
      const meta = el('div', 'scene-meta');
      meta.append(el('span', '', categories[scene.category] || scene.category || 'Sin categoría'), el('span', '', `Peso ${scene.weight ?? '—'}`));
      card.append(meta);
      const actions = el('div', 'scene-card-actions');
      const take = el('button', 'button button-small button-secondary', '↗  Cortar a escena');
      take.type = 'button'; take.disabled = !!scene.missing; take.dataset.takeScene = String(scene.id);
      actions.append(take); card.append(actions);
      const details = el('div', 'scene-details');
      details.append(el('h4', 'scene-settings-title', 'Ajustes de escena'));
      const form = el('form', 'scene-form'); form.dataset.sceneForm = String(scene.id);
      const toggle = el('label', 'toggle-line');
      const toggleText = el('span'); toggleText.append(el('strong', '', 'Escena habilitada'));
      const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.name = 'enabled'; checkbox.checked = !!scene.enabled; checkbox.setAttribute('role', 'switch');
      toggle.append(toggleText, checkbox); form.append(toggle);
      form.append(numberField('Peso', 'weight', scene.weight, 0, 'any'));
      form.append(categoryField(scene.category));
      form.append(numberField('Mínimo (s)', 'min_seconds', scene.min_seconds, 1, 'any'));
      form.append(numberField('Máximo (s)', 'max_seconds', scene.max_seconds, 1, 'any'));
      const save = el('button', 'button button-small button-primary', 'Guardar ajustes'); save.type = 'submit'; form.append(save);
      details.append(form); card.append(details); grid.append(card);
    });
    updateSceneCurrent();
  }
  function textField(title, name, value) {
    const field = el('label', 'field'); field.append(el('span', '', title));
    const input = document.createElement('input'); input.name = name; input.type = 'text'; input.value = value ?? '';
    field.append(input); return field;
  }
  function numberField(title, name, value, min, step) {
    const field = textField(title, name, value);
    const input = $('input', field); input.type = 'number'; input.min = String(min); input.step = step;
    return field;
  }
  function categoryField(value) {
    const field = el('label', 'field'); field.append(el('span', '', 'Categoría'));
    const select = document.createElement('select'); select.name = 'category';
    for (const category of ['general', 'voice', 'guitar', 'bass', 'drums', 'zoom', 'multi', 'other']) {
      select.add(new Option(categories[category], category));
    }
    select.value = value || 'other'; field.append(select); return field;
  }

  function renderSimulation(changes) {
    const box = $('#simulation-results'); box.replaceChildren(); box.hidden = false;
    box.append(el('h3', '', `Próximos ${changes.length} cambios (solo simulación)`));
    const list = el('ol', 'simulation-list');
    changes.forEach(change => {
      const row = el('li', 'simulation-row');
      row.append(el('strong', '', change.scene || '—'), el('span', '', `${safeNumber(change.hold_seconds)?.toFixed(1) ?? '—'} s`));
      list.append(row);
    });
    if (!changes.length) box.append(el('p', 'empty-state', 'No hay cortes posibles con la selección actual.'));
    else box.append(list);
  }

  function renderHistory(entries) {
    if (!Array.isArray(entries)) return;
    state.history = entries;
    const list = $('#history-list'); list.replaceChildren();
    if (!entries.length) { list.append(el('p', 'empty-state', 'Todavía no hay actividad.')); return; }
    entries.slice(0, 50).forEach((entry, index) => {
      const row = el('div', 'history-row');
      const title = el('div');
      const scene = typeof entry === 'string' ? entry : entry.scene || entry.scene_name || entry.to_scene || entry.name || entry.action || entry.event || 'Cambio de escena';
      title.append(el('strong', '', scene));
      title.append(el('small', '', entry.mode ? label(entry.mode) : entry.type || 'Transición'));
      const reason = el('span', '', entry.reason || entry.decision || entry.description || (typeof entry === 'string' ? 'Cambio de plano' : '—'));
      const time = el('time');
      const stamp = entry.timestamp || entry.time || entry.created_at;
      if (stamp) {
        const date = new Date(stamp);
        if (!Number.isNaN(date.getTime())) { time.dateTime = date.toISOString(); time.textContent = date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
        else time.textContent = String(stamp);
      } else time.textContent = typeof entry === 'string' ? `#${String(index + 1).padStart(2, '0')}` : '—';
      row.append(title, reason, time); list.append(row);
    });
  }

  function setField(form, name, value) {
    const field = form.elements.namedItem(name);
    if (!field) return;
    if (field.type === 'checkbox') field.checked = !!value;
    else if (field.tagName === 'SELECT' && value != null && !Array.from(field.options).some(option => option.value === String(value))) {
      field.add(new Option(String(value), String(value)));
      field.value = String(value);
    } else field.value = value ?? '';
  }
  function renderConfig(config) {
    if (!config || typeof config !== 'object') return;
    state.config = config;
    for (const [formId, group, keys] of [
      ['#obs-form', 'obs', ['host', 'port']],
      ['#timing-form', 'timing', ['min_seconds', 'max_seconds', 'preferred_seconds', 'memory', 'intensity']],
      ['#manual-form', 'manual', ['policy', 'pause_seconds']],
      ['#ai-form', 'ai', ['provider', 'plan', 'model', 'instructions', 'frequency_seconds', 'timeout_seconds', 'fallback', 'recommend_only']]
    ]) for (const key of keys) setField($(formId), key, config[group]?.[key]);
    const chosen = $('#ai-form').elements.provider.value;
    setText('#ai-key-status', config.ai?.key_status?.[chosen] ? `Clave ${chosen} configurada` : `Sin clave ${chosen}`);
    if (!state.status && config.mode) {
      setText('#mode-indicator', label(config.mode).toUpperCase());
      for (const button of document.querySelectorAll('[data-mode]')) button.classList.toggle('active', button.dataset.mode === config.mode);
    }
  }
  function chosenAISettings() {
    const form = $('#ai-form');
    const model = form.elements.model.value;
    const selectedBase = form.elements.model.selectedOptions[0]?.dataset.baseUrl || null;
    const prior = state.config?.ai;
    return { provider: form.elements.provider.value, plan: form.elements.plan?.value || 'auto', model,
      model_base_url: selectedBase || (prior?.provider === form.elements.provider.value && prior?.model === model ? prior.model_base_url : null),
      instructions: form.elements.instructions.value,
      frequency_seconds: formNumber(form, 'frequency_seconds'), timeout_seconds: formNumber(form, 'timeout_seconds'),
      fallback: form.elements.fallback.value, recommend_only: form.elements.recommend_only.checked };
  }

  function showModelInfo() {
    const option = $('#ai-model').selectedOptions[0];
    const item = state.aiModels.find(model => model.id === option?.value && model.group === option?.dataset.group);
    if (!item) return;
    const price = item.input_price == null ? 'precio no publicado' : `$${item.input_price}/M entrada · $${item.output_price ?? '—'}/M salida`;
    setText('#ai-models-note', `${state.aiCatalogWarning ? state.aiCatalogWarning + ' ' : ''}${item.id} · ${price} · entrada: ${(item.input_modalities || ['text']).join(', ')}. Solo se envían metadatos en esta versión.`);
  }

  async function loadModels() {
    const provider = $('#ai-form').elements.provider.value;
    const current = $('#ai-model').value;
    const data = await request(`/api/ai/models?provider=${encodeURIComponent(provider)}`);
    if ($('#ai-form').elements.provider.value !== provider) return;
    state.aiModels = Array.isArray(data.models) ? data.models : [];
    const select = $('#ai-model'); select.replaceChildren();
    if (!state.aiModels.length) select.add(new Option('No se encontraron modelos compatibles', ''));
    for (const item of state.aiModels) {
      const cost = item.input_price == null ? '' : ` · $${item.input_price}/M entrada`;
      const option = new Option(`${item.name} (${item.id})${cost}`, item.id);
      option.dataset.baseUrl = item.model_base_url || '';
      option.dataset.group = item.group || '';
      select.add(option);
    }
    if (state.aiModels.some(item => item.id === current)) select.value = current;
    else if (state.aiModels.some(item => item.id === (state.config?.ai?.model))) select.value = state.config.ai.model;
    else if (state.aiModels.length) select.value = state.aiModels[0].id;
    state.aiCatalogWarning = data.warning || '';
    setText('#ai-models-note', data.warning || `${state.aiModels.length} modelos compatibles · ${data.source === 'account' ? 'catálogo de tu cuenta' : 'catálogo público'}. Los precios son USD por millón de tokens.`);
    showModelInfo();
  }

  function renderProfiles(data) {
    state.profiles = Array.isArray(data) ? data : Array.isArray(data?.profiles) ? data.profiles : data?.profiles && typeof data.profiles === 'object' ? Object.keys(data.profiles) : [];
    const select = $('#profile-select'); const previous = select.value;
    select.replaceChildren(new Option('Selecciona un perfil…', ''));
    for (const item of state.profiles) {
      const name = typeof item === 'string' ? item : item?.name;
      if (name) select.add(new Option(String(name), String(name)));
    }
    if (previous && Array.from(select.options).some(option => option.value === previous)) select.value = previous;
    else if (data?.active && Array.from(select.options).some(option => option.value === data.active)) select.value = data.active;
  }
  async function refreshStatus() { renderStatus(await request('/api/status')); }
  async function refreshScenes() { const data = await request('/api/scenes'); renderScenes(data?.scenes || data); }
  async function refreshConfig() { renderConfig(await request('/api/config')); }
  async function refreshProfiles() { renderProfiles(await request('/api/profiles')); }
  async function refreshHistory() { const data = await request('/api/history'); renderHistory(Array.isArray(data) ? data : data?.history || data?.scenes || []); }
  async function refreshAll() {
    const results = await Promise.allSettled([refreshStatus(), refreshScenes(), refreshConfig(), refreshProfiles(), refreshHistory()]);
    const errors = results.filter(result => result.status === 'rejected');
    if (errors.length) showError(errors[0].reason);
    if (state.config?.ai?.provider === 'opencode' || state.config?.ai?.has_key) loadModels().catch(showError);
  }

  function connectWebSocket() {
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) return;
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${scheme}//${location.host}/ws/status`);
    state.ws = ws;
    ws.addEventListener('message', event => {
      try { renderStatus(JSON.parse(event.data)); }
      catch { /* A malformed frame must not disrupt the console. */ }
    });
    ws.addEventListener('close', () => {
      if (state.ws !== ws) return;
      state.ws = null;
      clearTimeout(state.retry);
      state.retry = setTimeout(connectWebSocket, 4000);
    });
    ws.addEventListener('error', () => ws.close());
  }

  function formNumber(form, name) {
    const value = Number(form.elements.namedItem(name).value);
    if (!Number.isFinite(value)) throw new Error(`Valor no válido: ${name}.`);
    return value;
  }
  function optionalNumber(form, name) {
    return form.elements.namedItem(name).value.trim() === '' ? null : formNumber(form, name);
  }
  async function submitConfig(group, payload, message) {
    await request('/api/config', { method: 'PUT', body: { [group]: payload } });
    await refreshConfig(); toast(message);
  }
  function selectedProfile() {
    const name = $('#profile-select').value;
    if (!name) throw new Error('Selecciona primero un perfil.');
    return name;
  }

  async function handleAction(action, button) {
    const directorActions = ['start', 'pause', 'resume', 'stop', 'next'];
    if (directorActions.includes(action)) {
      if (action === 'stop' && !confirm('¿Detener la sesión actual?')) return;
      await request(`/api/director/${action}`, { method: 'POST' });
      await refreshStatus(); toast(action === 'next' ? 'Corte solicitado.' : `Director: ${label(action)}.`);
      return;
    }
    switch (action) {
      case 'refresh-scenes': await refreshScenes(); toast('Escenas sincronizadas.'); break;
      case 'refresh-history': await refreshHistory(); toast('Registro actualizado.'); break;
      case 'refresh-obs': await request('/api/obs/refresh', { method: 'POST' }); await Promise.all([refreshStatus(), refreshScenes()]); toast('OBS sincronizado.'); break;
      case 'disconnect': await request('/api/obs/disconnect', { method: 'POST' }); await refreshStatus(); toast('OBS desconectado.'); break;
      case 'simulate-obs': await request('/api/obs/connect', { method: 'POST', body: { simulated: true } }); await Promise.all([refreshStatus(), refreshScenes()]); toast('Simulación OBS activada.'); break;
      case 'refresh-models': await loadModels(); toast('Catálogo de modelos actualizado.'); break;
      case 'test-ai': {
        const target = $('#ai-test-result');
        try {
          await submitConfig('ai', chosenAISettings(), 'Configuración de IA guardada.');
          const result = await request('/api/ai/test', { method: 'POST' });
          target.hidden = false;
          target.replaceChildren(el('strong', '', `Recomendación: ${result.scene || '—'}`),
            el('p', '', result.decision?.reason || 'Sin motivo'),
            el('small', '', `Duración ${safeNumber(result.decision?.hold_seconds)?.toFixed(1) ?? '—'} s · Confianza ${safeNumber(result.decision?.confidence) ?? '—'} · Latencia ${safeNumber(result.latency) ?? '—'} s · ${result.base_url ? new URL(result.base_url).hostname : 'proveedor'} · No aplicada`));
          toast('Prueba de IA completada: OBS no se ha modificado.');
        } catch (error) {
          target.hidden = false;
          target.replaceChildren(el('strong', '', 'Error de conexión IA'), el('p', '', error.message));
          throw error;
        }
        break;
      }
      case 'simulation': {
        const result = await request('/api/simulation', { method: 'POST', body: { count: 20 } });
        renderSimulation(Array.isArray(result?.changes) ? result.changes : []);
        toast(`Ensayo completado: ${Array.isArray(result?.changes) ? result.changes.length : 0} decisiones simuladas; OBS no se modifica.`); break;
      }
      case 'save-profile': {
        const name = $('#profile-name').value.trim() || $('#profile-select').value;
        if (!name) throw new Error('Escribe un nombre para el perfil.');
        await request('/api/profiles', { method: 'POST', body: { action: 'save', name } });
        await refreshProfiles(); $('#profile-select').value = name; $('#profile-name').value = ''; toast('Perfil guardado.'); break;
      }
      case 'duplicate-profile': {
        const source = selectedProfile();
        const name = $('#profile-name').value.trim();
        if (!name) throw new Error('Escribe el nombre de la copia.');
        await request('/api/profiles', { method: 'POST', body: { action: 'duplicate', source, name } });
        await refreshProfiles(); $('#profile-select').value = name; $('#profile-name').value = '';
        toast('Perfil duplicado.'); break;
      }
      case 'load-profile': {
        const name = selectedProfile();
        if (!confirm(`¿Cargar el perfil «${name}»? Se reemplazará la configuración activa.`)) return;
        await request('/api/profiles', { method: 'POST', body: { action: 'load', name } });
        await Promise.all([refreshConfig(), refreshScenes(), refreshStatus()]); toast('Perfil cargado.'); break;
      }
      case 'delete-profile': {
        const name = selectedProfile();
        if (!confirm(`¿Eliminar el perfil «${name}»?`)) return;
        await request('/api/profiles', { method: 'POST', body: { action: 'delete', name } });
        await refreshProfiles(); toast('Perfil eliminado.'); break;
      }
      default: throw new Error(`Acción no reconocida: ${action}`);
    }
  }

  document.addEventListener('click', event => {
    const modeButton = event.target.closest('[data-mode]');
    if (modeButton) {
      busy(modeButton, async () => {
        await request('/api/director/mode', { method: 'POST', body: { mode: modeButton.dataset.mode } });
        await refreshStatus(); toast(`Modo: ${modeButton.textContent.trim()}.`);
      });
      return;
    }
    const take = event.target.closest('[data-take-scene]');
    if (take) {
      busy(take, async () => {
        await request('/api/director/manual', { method: 'POST', body: { scene_id: take.dataset.takeScene } });
        await refreshStatus(); toast('Corte manual realizado.');
      });
      return;
    }
    const button = event.target.closest('[data-action]');
    if (button) busy(button, () => handleAction(button.dataset.action, button));
  });

  document.addEventListener('change', event => {
    if (event.target.matches('#ai-form select[name="provider"]')) {
      const provider = event.target.value;
      const fallback = provider === 'opencode' ? 'deepseek-v4.1-flash' : 'deepseek-flash';
      state.aiModels = [];
      $('#ai-model').replaceChildren(new Option(fallback, fallback));
      setText('#ai-key-status', state.config?.ai?.key_status?.[provider] ? `Clave ${provider} configurada` : `Sin clave ${provider}`);
      setText('#ai-models-note', 'Selecciona un modelo de este proveedor; guarda los ajustes antes de probar.');
      if (provider === 'opencode' || state.config?.ai?.key_status?.[provider]) loadModels().catch(showError);
    }
    if (event.target.matches('#ai-model')) showModelInfo();
    if (event.target.matches('[data-scene-form] input[name="enabled"]')) {
      const checkbox = event.target;
      const sceneId = checkbox.closest('[data-scene-form]').dataset.sceneForm;
      const scene = state.scenes.find(item => String(item.id) === sceneId);
      if (!scene) return;
      const previous = scene.enabled;
      checkbox.disabled = true;
      request(`/api/scenes/${encodeURIComponent(sceneId)}`, { method: 'PUT', body: { enabled: checkbox.checked } })
        .then(saved => { Object.assign(scene, saved); updateSceneCard(scene); toast(`Escena ${saved.enabled ? 'habilitada' : 'deshabilitada'} y guardada.`); })
        .catch(error => { checkbox.checked = previous; showError(error); })
        .finally(() => { checkbox.disabled = false; });
    }
  });

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!form.matches('#ai-form, #key-form, #obs-form, #timing-form, #manual-form, [data-scene-form]')) return;
    event.preventDefault();
    busy(form.querySelector('[type="submit"]'), async () => {
      if (form.id === 'ai-form') {
        await submitConfig('ai', chosenAISettings(), 'Configuración de IA guardada.');
      } else if (form.id === 'key-form') {
        const key = form.elements.key.value.trim();
        if (!key) throw new Error('Introduce una clave de IA.');
        const provider = $('#ai-form').elements.provider.value;
        await submitConfig('ai', chosenAISettings(), 'Proveedor de IA guardado.');
        await request('/api/ai/key', { method: 'POST', body: { key, provider } });
        form.reset(); await refreshConfig(); toast(`Clave ${provider} guardada.`);
        await loadModels();
      } else if (form.id === 'obs-form') {
        const host = form.elements.host.value.trim(); const port = formNumber(form, 'port');
        if (!host || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Host o puerto de OBS no válido.');
        await request('/api/config', { method: 'PUT', body: { obs: { host, port } } });
        const password = form.elements.password.value;
        await request('/api/obs/connect', { method: 'POST', body: { host, port, ...(password ? { password } : {}) } });
        form.elements.password.value = '';
        await Promise.all([refreshConfig(), refreshStatus(), refreshScenes()]); toast('OBS conectado.');
      } else if (form.id === 'timing-form') {
        const min_seconds = formNumber(form, 'min_seconds');
        const max_seconds = formNumber(form, 'max_seconds');
        const preferred_seconds = formNumber(form, 'preferred_seconds');
        if (min_seconds > max_seconds || preferred_seconds < min_seconds || preferred_seconds > max_seconds) throw new Error('El tiempo preferido debe estar entre el mínimo y el máximo.');
        await submitConfig('timing', { min_seconds, max_seconds, preferred_seconds, memory: formNumber(form, 'memory'), intensity: formNumber(form, 'intensity') }, 'Ritmo actualizado.');
      } else if (form.id === 'manual-form') {
        await submitConfig('manual', { policy: form.elements.policy.value.trim(), pause_seconds: formNumber(form, 'pause_seconds') }, 'Política manual guardada.');
      } else if (form.dataset.sceneForm !== undefined) {
        const sceneId = form.dataset.sceneForm;
        const min_seconds = optionalNumber(form, 'min_seconds'); const max_seconds = optionalNumber(form, 'max_seconds');
        if (min_seconds != null && max_seconds != null && min_seconds > max_seconds) throw new Error('El mínimo de escena no puede superar el máximo.');
        const saved = await request(`/api/scenes/${encodeURIComponent(sceneId)}`, { method: 'PUT', body: {
          enabled: form.elements.enabled.checked, weight: formNumber(form, 'weight'),
          category: form.elements.category.value.trim(), min_seconds, max_seconds
        } });
        const existing = state.scenes.find(item => String(item.id) === sceneId);
        if (existing) { Object.assign(existing, saved); updateSceneCard(existing); }
        toast('Ajustes de escena guardados.');
      }
    });
  });

  const navObserver = new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) {
      document.querySelectorAll('.nav-link').forEach(link => link.classList.toggle('active', link.hash === `#${entry.target.id}`));
    }
  }, { rootMargin: '-20% 0px -65% 0px' });
  document.querySelectorAll('main[id], section[id]').forEach(section => navObserver.observe(section));
  const updateClock = () => setText('#clock', new Date().toLocaleTimeString('es-ES', { hour12: false }));
  updateClock(); setInterval(updateClock, 1000);
  refreshAll(); connectWebSocket();
  state.statusTimer = setInterval(() => {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) refreshStatus().catch(showError);
  }, 5000);
  setInterval(() => refreshHistory().catch(() => {}), 30000);
})();
