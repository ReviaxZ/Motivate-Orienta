/* Orienta – cliente web del orientador vocacional (LiveKit + API del servidor) */
(() => {
  const LK = window.LivekitClient;
  const $ = (id) => document.getElementById(id);
  const API = "/api/orientador";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const COLOR = { publica: "#1b9b67", beca: "#2a7bd6", accesible: "#c7811a", alto: "#8a5cc2", distancia: "#d0457a" };
  const CHIP_LABEL = { publica: "Públicas", beca: "Con beca", accesible: "Privadas accesibles", alto: "Privadas", distancia: "A distancia" };
  const NOMBRE = { eleccion: "Lucía", permanencia: "Fabiola" };
  const stateLabel = (st) => ({ initializing: `${NOMBRE[modo]} se está preparando…`, listening: "Te escucho…", thinking: "Pensando…", speaking: `${NOMBRE[modo]} está hablando` }[st]);
  const PASOS_F = [
    ["carrera", "Tu carrera"], ["motivos", "Qué te hace dudar"], ["satisfaccion", "Qué tanto te gusta"],
    ["basico", "Etapa básica"], ["intermedio", "Etapa intermedia"], ["avanzado", "Etapa avanzada"], ["dictamen", "Dictamen"],
  ];
  const NIVEL_TXT = { basico: "Básico", intermedio: "Intermedio", avanzado: "Avanzado" };
  const CARITAS = [[1, "😣", "Muy mal"], [2, "😕", "Mal"], [3, "😐", "Regular"], [4, "🙂", "Bien"], [5, "😄", "Muy bien"]];
  const DIC_COLOR = { continuar: "#1b9b67", continuar_apoyo: "#2a7bd6", reevaluar: "#c7811a", explorar_cambio: "#c2416f" };
  const PASOS = [
    ["disfruta", "Lo que más disfrutas", "intereses"],
    ["clase", "Tu clase favorita", "materias"],
    ["descripcion", "Cómo te describes", "rasgos"],
    ["ambiente", "Dónde te gustaría trabajar", "ambientes"],
    ["economia", "Tu situación económica", null],
    ["ubicacion", "Dónde vives", null],
    ["extra", "Algo más sobre ti", null],
  ];

  let room = null, agent = null, raf = 0, tick = 0, poll = 0, startedAt = 0, agentTimeout = 0;
  let sid = null, estado = null, catalogo = null, version = -1;
  let filtros = null, nivelFiltros = null, tabTemario = 0, videoCarrera = null;
  let map = null, capa = null, autoplayPara = null, micPausado = false;
  let modo = "eleccion";
  const guardar = (k, v) => { try { localStorage.setItem(k, v); } catch {} };
  const leer = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
  const segments = new Map();

  // ------------------------------------------------------------------ util
  async function api(path, opts = {}) {
    const res = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!res.ok) {
      let msg = `Error ${res.status}`;
      try { msg = (await res.json()).detail || msg; } catch {}
      throw new Error(msg);
    }
    return res.json();
  }
  const setMode = (m) => {
    document.body.classList.remove("idle", "connecting", "live");
    document.body.classList.add(m);
    $("micBtn").disabled = m !== "idle";
    $("pillText").textContent = { idle: "Sin conectar", connecting: "Conectando…", live: "En conversación" }[m];
  };
  const setStatus = (t) => ($("status").textContent = t);

  // ------------------------------------------------------------------ conversación
  async function start() {
    $("error").textContent = "";
    $("transcript").innerHTML = ""; segments.clear();
    setMode("connecting"); setStatus("Conectando…");
    try {
      const { serverUrl, token, sesion } = await api("/token", { method: "POST", body: JSON.stringify({ idioma: $("idioma").value || "es", modo }) });
      sid = sesion; version = -1; estado = null; filtros = null;
      history.replaceState(null, "", `#${sid}`);
      room = new LK.Room({ adaptiveStream: true, dynacast: true });
      wire(room);
      await room.connect(serverUrl, token);
      await room.startAudio();
      await room.localParticipant.setMicrophoneEnabled(true, { echoCancellation: true, noiseSuppression: true, autoGainControl: true });
      setStatus(`Esperando a ${NOMBRE[modo]}…`);
      findAgent();
      agentTimeout = setTimeout(() => { if (!agent) fail(`${NOMBRE[modo]} no se unió. Revisa que el contenedor del orientador esté corriendo.`); }, 20000);
      poll = setInterval(refresh, 5000);
      refresh();
    } catch (e) { fail(e.message || String(e)); }
  }

  function wire(r) {
    const E = LK.RoomEvent;
    r.on(E.TrackSubscribed, (t) => { if (t.kind === LK.Track.Kind.Audio) $("audio").appendChild(t.attach()); });
    r.on(E.TrackUnsubscribed, (t) => t.detach().forEach((el) => el.remove()));
    r.on(E.ParticipantConnected, findAgent);
    r.on(E.ParticipantDisconnected, (p) => { if (agent && p.identity === agent.identity) { agent = null; stop("La conversación terminó"); } });
    r.on(E.ParticipantAttributesChanged, (_c, p) => { if (agent && p.identity === agent.identity) showAgentState(); });
    r.on(E.Disconnected, () => { if (room === r) cleanup("Conversación finalizada"); });
    r.registerRpcMethod("ui.actualizar", async () => { refresh(); return "ok"; });
    r.registerTextStreamHandler("lk.transcription", async (reader, info) => {
      const attrs = reader.info.attributes || {};
      const id = attrs["lk.segment_id"] || reader.info.id;
      const isAgent = info.identity !== r.localParticipant.identity;
      const el = lineFor(id, isAgent);
      let text = "";
      for await (const chunk of reader) { text += chunk; el.textContent = text; $("transcript").scrollTop = 1e9; }
    });
  }
  function lineFor(id, isAgent) {
    if (segments.has(id)) return segments.get(id);
    const p = document.createElement("p");
    p.className = "line " + (isAgent ? "agent" : "user");
    p.innerHTML = `<span class="w">${isAgent ? NOMBRE[modo] : "Tú"}</span>`;
    const s = document.createElement("span"); p.appendChild(s);
    $("transcript").appendChild(p); segments.set(id, s);
    return s;
  }
  function findAgent() {
    if (!room || agent) return;
    for (const p of room.remoteParticipants.values()) {
      if (p.kind === LK.ParticipantKind.AGENT || p.identity.startsWith("agent-")) {
        agent = p; clearTimeout(agentTimeout); setMode("live");
        startedAt = Date.now(); tick = setInterval(timer, 500); timer(); showAgentState(); loop();
        return;
      }
    }
  }
  function showAgentState() {
    const st = agent?.attributes?.["lk.agent.state"];
    setStatus(stateLabel(st) || `Conectada con ${NOMBRE[modo]}`);
    // Si Lucía va a hablar y el video está sonando, se pausa para no encimar audios
    try { if (st === "speaking" && ytPlayer && ytPlayer.getPlayerState && ytPlayer.getPlayerState() === 1) ytPlayer.pauseVideo(); } catch {}
  }
  // Micrófono en pausa mientras suena el video (evita que Lucía "escuche" el video)
  async function pausarMic(on) {
    if (micPausado === on) return;
    micPausado = on;
    $("micNota").hidden = !on || !room;
    if (room) { try { await room.localParticipant.setMicrophoneEnabled(!on); } catch {} }
  }
  function timer() { const s = Math.floor((Date.now() - startedAt) / 1000); $("timer").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }
  function loop() {
    const a = agent ? agent.audioLevel || 0 : 0;
    const u = room ? room.localParticipant.audioLevel || 0 : 0;
    $("ringAgent").style.setProperty("--s", (0.72 + Math.min(a * 2.2, 0.28)).toFixed(3));
    $("ringUser").style.setProperty("--s2", (0.82 + Math.min(u * 2.2, 0.18)).toFixed(3));
    raf = requestAnimationFrame(loop);
  }
  async function stop(msg) { const r = room; room = null; if (r) await r.disconnect(); cleanup(msg); }
  function cleanup(msg) {
    cancelAnimationFrame(raf); clearInterval(tick); clearInterval(poll); clearTimeout(agentTimeout);
    agent = null; room = null; $("audio").innerHTML = ""; $("timer").textContent = ""; micPausado = false; $("micNota").hidden = true;
    setMode("idle"); setStatus(msg || "Toca el micrófono para empezar");
    if (sid) refresh();
  }
  function fail(msg) { $("error").textContent = msg; stop("Toca el micrófono para intentar de nuevo"); }

  async function avisarAgente(payload) {
    if (!room || !agent) return;
    try { await room.localParticipant.performRpc({ destinationIdentity: agent.identity, method: "orientador.evento", payload: JSON.stringify(payload), responseTimeout: 8000 }); }
    catch (e) { console.warn("RPC al agente falló", e); }
  }

  // ------------------------------------------------------------------ estado
  async function refresh() {
    if (!sid) return;
    try {
      const s = await api(`/sesiones/${sid}`);
      if (s.version === version) return;
      version = s.version; estado = s; render();
    } catch (e) { console.warn(e); }
  }
  const label = (dim, t) => catalogo?.vocabulario?.[dim]?.[t] || t;
  const carreraById = (id) => [...(estado?.resultado?.carreras || []), ...(estado?.resultado?.extras || [])].find((c) => c.id === id);

  function render() {
    if (estado.idioma && $("idioma").value !== estado.idioma && !room) { $("idioma").value = estado.idioma; notaIdioma(); }
    if (estado.modo && estado.modo !== modo) { modo = estado.modo; aplicarModo(); }
    if (modo === "permanencia") { renderFabiola(); renderAgendaVisible(); return; }
    renderFicha();
    const res = estado.resultado;
    const primeraVez = !!res && $("resultados").hidden;
    $("hero").hidden = !!res;
    $("resultados").hidden = !res;
    renderBotonResultados();
    if (!res) return;
    if (primeraVez && window.innerWidth < 1080 && room) setTimeout(() => $("resultados").scrollIntoView({ behavior: "smooth", block: "start" }), 300);
    if (nivelFiltros !== res.nivel_economico || !filtros) { filtros = new Set(res.filtros_sugeridos); nivelFiltros = res.nivel_economico; }
    $("pesoEco").textContent = `${Math.round(res.peso_economico * 100)}%`;
    renderCareers(); renderFocus(); renderChips(); renderMapa(); renderPlan(); renderExtras(); renderAgendaVisible();
  }

  function renderAgendaVisible() {
    const listo = modo === "permanencia" ? !!estado?.dictamen : !!estado?.resultado;
    $("agenda").hidden = !(listo || estado?.ui?.mostrar_agenda || estado?.cita);
    if (!$("agenda").hidden) renderAgenda();
  }

  // ------------------------------------------------------------------ modo (barra lateral)
  function aplicarModo() {
    document.body.classList.toggle("modo-permanencia", modo === "permanencia");
    document.body.classList.toggle("modo-eleccion", modo === "eleccion");
    $("navLucia").classList.toggle("on", modo === "eleccion");
    $("navFabiola").classList.toggle("on", modo === "permanencia");
    $("navLucia").setAttribute("aria-current", modo === "eleccion" ? "page" : "false");
    $("navFabiola").setAttribute("aria-current", modo === "permanencia" ? "page" : "false");
    $("vistaL").hidden = modo !== "eleccion";
    $("vistaF").hidden = modo !== "permanencia";
    $("quien").textContent = modo === "permanencia" ? "Fabiola · orientadora universitaria" : "Lucía · orientadora vocacional";
    $("idiomaLbl").textContent = `Idioma de ${NOMBRE[modo]}`;
    $("fichaTitulo").textContent = modo === "permanencia" ? "Tu caso" : "Tu ficha";
    $("micBtn").setAttribute("aria-label", `Iniciar conversación con ${NOMBRE[modo]}`);
    $("micNota").textContent = `Micrófono en pausa mientras ves el video. Pausa el video para hablar con ${NOMBRE[modo]}.`;
    document.title = modo === "permanencia" ? "Orienta · ¿Sigo en mi carrera?" : "Orienta · Orientación vocacional";
    if (!room) setStatus("Toca el micrófono para empezar");
  }
  async function setModo(m) {
    if (m === modo) return;
    if (room && !confirm(`¿Terminar la conversación actual y pasar con ${NOMBRE[m]}?`)) return;
    await nuevaSesion(true);
    modo = m; guardar("orienta.modo", m);
    aplicarModo(); renderFichaVacia();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ------------------------------------------------------------------ Fabiola: ¿sigo en mi carrera?
  function renderFabiola() {
    renderFichaF();
    const caso = estado.caso, t = estado.test, dic = estado.dictamen;
    $("heroF").hidden = !!caso;
    $("casoF").hidden = !caso;
    if (caso) {
      $("casoCarrera").textContent = caso.carrera_nombre || "—";
      $("casoUni").textContent = caso.universidad || "—";
      $("casoAnio").textContent = caso.anio ? `${caso.anio}.º año` : "";
      $("casoAnio").hidden = !caso.anio;
      $("casoSatis").innerHTML = [1, 2, 3, 4, 5].map((n) => `<i class="${n <= (caso.satisfaccion || 0) ? "on" : ""}"></i>`).join("") + (caso.satisfaccion ? ` <small class="muted">${caso.satisfaccion} de 5</small>` : "");
      $("casoMotivos").innerHTML = (caso.motivos || []).map((m) => `<span class="tag">${esc(catalogo?.motivos?.[m] || m)}</span>`).join("");
    }
    $("testF").hidden = !t;
    if (t) renderTest(t, caso);
    $("dictamenF").hidden = !dic;
    if (dic) renderDictamen(dic);
  }

  function renderFichaF() {
    const caso = estado.caso || {}, t = estado.test, dic = estado.dictamen;
    const omit = new Set(caso.omitidas || []);
    const pend = estado.pendiente;
    let hechos = 0, actual = false;
    $("steps").innerHTML = PASOS_F.map(([k, titulo]) => {
      let done = false, v = "";
      if ((k === "motivos" || k === "satisfaccion") && omit.has(k)) { done = true; v = OMITIDA; }
      if (k === "carrera" && caso.carrera_nombre) { done = true; v = esc([caso.carrera_nombre, caso.universidad, caso.anio ? `${caso.anio}.º año` : ""].filter(Boolean).join(" · ")); }
      if (k === "motivos" && (caso.motivos?.length || caso.texto)) { done = true; v = `<div class="tags">${(caso.motivos || []).map((m) => `<span class="tag">${esc(catalogo?.motivos?.[m] || m)}</span>`).join("")}</div>`; }
      if (k === "satisfaccion" && caso.satisfaccion) { done = true; v = `${caso.satisfaccion} de 5`; }
      if (NIVEL_TXT[k] && t) {
        const ps = t.preguntas.filter((p) => p.nivel === k);
        const resp = ps.filter((p) => t.respuestas[p.numero]);
        const ok = resp.filter((p) => t.respuestas[p.numero].correcta).length;
        const sen = t.sentimientos[k];
        if (resp.length === ps.length && sen) done = true;
        if (resp.length) v = `${ok} de ${ps.length} correctas${sen ? (sen.valor ? ` · se sintió ${sen.valor} de 5` : " · sentimiento omitido") : ""}`;
      }
      if (k === "dictamen" && dic) { done = true; v = esc(dic.titulo); }
      if (done) hechos++;
      let cls = done ? "done" : "";
      let extra = "";
      if (!done && !actual && room) {
        cls = "current"; actual = true;
        const pc = estado.por_confirmar;
        if (pc && pc.tipo === "caso") extra = cajaConfirmar(pc);
        else if (pc && NIVEL_TXT[k]) extra = `<div class="preg-actual"><p>Confirma tu respuesta en el test.</p></div>`;
        else if (pend && (pend.clave === k || pend.nivel === k)) extra = pregActual(pend);
      }
      return `<li class="step ${cls}"><span class="ic">✓</span><div><div class="t">${titulo}</div><div class="v">${v || '<span class="muted">Pendiente</span>'}</div>${extra}</div></li>`;
    }).join("");
    $("progressLabel").textContent = `${hechos} de 7`;
    $("progressBar").style.width = `${(hechos / 7) * 100}%`;
    $("verResultados").hidden = true;
    conectarSaltos($("steps"));
    conectarConfirmar($("steps"));
  }

  function renderTest(t, caso) {
    const total = t.preguntas.length, resp = Object.keys(t.respuestas).length;
    $("testTitulo").textContent = `Test de ${caso?.carrera_nombre || "tu carrera"}`;
    $("testProg").textContent = `${resp} de ${total} respondidas`;
    const paso = t.paso || {};
    const nivelActual = paso.tipo === "pregunta" ? paso.pregunta.nivel : paso.tipo === "sentimiento" ? paso.nivel : null;
    $("etapas").innerHTML = ["basico", "intermedio", "avanzado"].map((n) => {
      const ps = t.preguntas.filter((p) => p.nivel === n);
      const ok = ps.filter((p) => t.respuestas[p.numero]?.correcta).length;
      const r = ps.filter((p) => t.respuestas[p.numero]).length;
      const hecha = r === ps.length && t.sentimientos[n];
      return `<li class="etapa ${n === nivelActual ? "actual" : ""} ${hecha ? "hecha" : ""}"><b>${NIVEL_TXT[n]}</b><span>${r ? `${ok} de ${ps.length} correctas` : "Pendiente"}${t.sentimientos[n] ? (t.sentimientos[n].valor ? ` · ${CARITAS[t.sentimientos[n].valor - 1][1]}` : " · omitido") : ""}</span></li>`;
    }).join("");
    // Retroalimentación de la última respuesta
    const nums = Object.keys(t.respuestas).map(Number).sort((a, b) => a - b);
    const ult = nums.length ? t.respuestas[nums[nums.length - 1]] : null;
    const fb = ult?.omitida ? `<p class="feedback mal">⏭ Pregunta ${ult.numero} omitida. La correcta era la ${esc(ult.letra_correcta)}, ${esc(ult.texto_correcta)}.</p>` : ult ? (ult.correcta ? `<p class="feedback ok">✓ Pregunta ${ult.numero}: ¡correcta!</p>` : `<p class="feedback mal">✗ Pregunta ${ult.numero}: la correcta era la ${esc(ult.letra_correcta)}, ${esc(ult.texto_correcta)}.</p>`) : "";
    const pc = estado.por_confirmar;
    if (paso.tipo === "pregunta") {
      const q = paso.pregunta;
      const elegida = pc && pc.tipo === "test" && pc.numero === q.numero ? pc.opcion : null;
      $("qBox").innerHTML = `${fb}<p class="q-meta">Pregunta ${q.numero} de ${total} · ${NIVEL_TXT[q.nivel]}</p><h3>${esc(q.pregunta)}</h3>
        <div class="opciones">${q.opciones.map((o, i) => `<button class="opcion ${elegida === "ABCD"[i] ? "elegida" : ""}" data-n="${q.numero}" data-o="${"ABCD"[i]}" aria-pressed="${elegida === "ABCD"[i]}"><span class="l">${"ABCD"[i]}</span><span>${esc(o)}</span></button>`).join("")}</div>
        ${elegida ? cajaConfirmar(pc) : ""}
        ${botonSaltar(`test:${q.numero}`, "Saltar esta pregunta")}`;
      $("qBox").querySelectorAll(".opcion").forEach((b) => b.onclick = () => proponer("test", { numero: +b.dataset.n, opcion: b.dataset.o }));
      conectarSaltos($("qBox")); conectarConfirmar($("qBox"));
    } else if (paso.tipo === "sentimiento") {
      $("qBox").innerHTML = `${fb}<p class="q-meta">Terminaste la etapa ${{ basico: "básica", intermedio: "intermedia", avanzado: "avanzada" }[paso.nivel]}</p><h3>¿Cómo te sentiste en esta etapa?</h3>
        <p class="muted small">Puedes decírselo a ${NOMBRE[modo]} o tocar una opción.</p>
        <div class="caritas">${CARITAS.map(([v, e, t2]) => `<button class="carita ${pc?.tipo === "sentimiento" && pc.valor === v ? "elegida" : ""}" data-v="${v}"><span>${e}</span><small>${t2}</small></button>`).join("")}</div>
        ${pc?.tipo === "sentimiento" ? cajaConfirmar(pc) : ""}
        ${botonSaltar(`sentimiento:${paso.nivel}`, "Prefiero no responder")}`;
      $("qBox").querySelectorAll(".carita").forEach((b) => b.onclick = () => proponer("sentimiento", { valor: +b.dataset.v }));
      conectarSaltos($("qBox")); conectarConfirmar($("qBox"));
    } else {
      $("qBox").innerHTML = `${fb}<p class="muted">Test completo. Mira tu dictamen abajo.</p>`;
    }
  }

  function renderDictamen(dic) {
    const color = DIC_COLOR[dic.decision] || "var(--primary)";
    $("dictamenF").style.setProperty("--dic-color", color);
    $("gaugeVal").textContent = dic.indice;
    $("gaugeArc").style.strokeDashoffset = String(314.16 * (1 - dic.indice / 100));
    $("dicDecision").textContent = dic.titulo;
    $("dicTexto").textContent = dic.texto;
    $("dicTest").textContent = `Test: ${dic.puntaje_test} de 100 (lo esperado para tu año es alrededor de ${dic.esperado_por_anio}).`;
    const c = dic.componentes || {};
    $("dicComp").innerHTML = [["Bienestar", c.bienestar], ["Satisfacción", c.satisfaccion], ["Conocimiento", c.conocimiento], ["Señal vocacional", c.vocacional]]
      .map(([k, v]) => `<div><span>${k}</span><b>${v ?? "—"}</b><div class="track"><i class="fill" style="width:${v || 0}%"></i></div></div>`).join("");
    $("dicEtapas").innerHTML = `<tr><th>Etapa</th><th>Aciertos</th><th>Cómo te sentiste</th></tr>` +
      Object.entries(dic.por_nivel).map(([n, v]) => {
        const s2 = dic.sentimientos?.[n];
        return `<tr><td>${NIVEL_TXT[n]}</td><td>${v.aciertos} de ${v.total}</td><td>${s2?.valor ? `${CARITAS[s2.valor - 1][1]} ${s2.valor} de 5${s2.texto ? ` · ${esc(s2.texto)}` : ""}` : s2 ? "Omitido" : "—"}</td></tr>`;
      }).join("");
    const enlace = (r) => r.url ? ` <a href="${esc(r.url)}" target="_blank" rel="noopener">Abrir</a>` : "";
    $("dicRecs").innerHTML = (dic.recomendaciones || []).map((r) => `<li>${esc(r.texto)}${enlace(r)}</li>`).join("");
    $("irLucia").hidden = !(dic.decision === "explorar_cambio" || dic.decision === "reevaluar");
  }

  // Botón de respaldo: si ya hay respuestas suficientes pero aún no hay resultados
  function renderBotonResultados() {
    const r = estado.respuestas || {};
    const n = ["disfruta", "clase", "descripcion", "ambiente", "economia"].filter((k) => r[k]).length;
    $("verResultados").hidden = !!estado.resultado || n < 4 || !estado.ubicacion;
  }
  async function verResultados() {
    $("verResultados").disabled = true;
    try { estado = await api(`/sesiones/${sid}/recomendar`, { method: "POST" }); version = estado.version; render(); }
    catch (e) { $("error").textContent = e.message; }
    $("verResultados").disabled = false;
  }

  function renderFicha() {
    const r = estado.respuestas || {};
    let hechos = 0, actualMarcado = false;
    $("steps").innerHTML = PASOS.map(([k, titulo, dim]) => {
      let done = false, v = "";
      if (k === "ubicacion") {
        const u = estado.ubicacion;
        if (u?.omitida) { done = true; v = OMITIDA; }
        else if (u) { done = true; v = [u.colonia, u.municipio, u.departamento, u.pais].filter(Boolean).map(esc).join(", ") + (u.zona === "rural" ? " · zona rural" : ""); }
      } else if (r[k]?.omitida) {
        done = true; v = OMITIDA;
      } else if (r[k]) {
        done = true; v = esc(r[k].texto);
        if (k === "economia") {
          const n = { baja: "Necesito opciones gratuitas o beca", media: "Puedo costear una pública", alta: "Puedo costear una privada" }[r[k].nivel] || "";
          v = `<div class="tags"><span class="tag">${esc(n)}</span>${r[k].internet === false ? '<span class="tag">Sin internet en casa</span>' : ""}${r[k].necesita_trabajar ? '<span class="tag">Necesito trabajar</span>' : ""}</div>`;
        } else if (dim && r[k].etiquetas?.length) {
          v += `<div class="tags">${r[k].etiquetas.map((t) => `<span class="tag">${esc(label(dim, t).split(",")[0])}</span>`).join("")}</div>`;
        }
      }
      if (done) hechos++;
      let cls = done ? "done" : "";
      let extra = "";
      if (!done && !actualMarcado && room) {
        cls = "current"; actualMarcado = true;
        if (estado.por_confirmar && estado.pendiente?.clave === k) extra = cajaConfirmar(estado.por_confirmar);
        else if (estado.pendiente?.clave === k) extra = pregActual(estado.pendiente);
      }
      return `<li class="step ${cls}"><span class="ic">✓</span><div><div class="t">${titulo}</div><div class="v">${v || '<span class="muted">Pendiente</span>'}</div>${extra}</div></li>`;
    }).join("");
    $("progressLabel").textContent = `${hechos} de 7`;
    $("progressBar").style.width = `${(hechos / 7) * 100}%`;
    conectarSaltos($("steps"));
    conectarConfirmar($("steps"));
  }

  // ------------------------------------------------------------------ confirmaciones
  // Cada respuesta de selección se confirma antes de pasar a la siguiente pregunta
  function cajaConfirmar(pc) {
    const ctl = room ? `<div class="conf-botones"><button class="conf-si primary" type="button">Sí, es correcto</button><button class="conf-no" type="button">Corregir</button></div>` : "";
    return `<div class="confirmar" role="group" aria-label="Confirma tu respuesta"><p>${esc(pc.texto)}</p>${ctl}</div>`;
  }
  function conectarConfirmar(raiz) {
    raiz.querySelectorAll(".conf-si").forEach((b) => b.onclick = () => confirmarRespuesta(true));
    raiz.querySelectorAll(".conf-no").forEach((b) => b.onclick = () => confirmarRespuesta(false));
  }
  let confirmando = false;
  async function confirmarRespuesta(si) {
    if (confirmando || !sid) return;
    confirmando = true;
    document.querySelectorAll(".conf-si, .conf-no").forEach((b) => (b.disabled = true));
    try {
      const r = await api(`/sesiones/${sid}/confirmar`, { method: "POST", body: JSON.stringify({ si }) });
      estado = r.vista; version = estado.version; render();
      const { vista, ...data } = r;
      avisarAgente({ tipo: "confirmacion", data });
      if (estado.dictamen) $("dictamenF").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      $("error").textContent = e.message; refresh();
    }
    confirmando = false;
  }
  async function proponer(tipo, datos) {
    try {
      const r = await api(`/sesiones/${sid}/proponer`, { method: "POST", body: JSON.stringify({ tipo, datos }) });
      estado = r.vista; version = estado.version; render();
      const { vista, ...data } = r;
      avisarAgente({ tipo: "propuesta", data });
    } catch (e) { $("error").textContent = e.message; refresh(); }
  }

  // ------------------------------------------------------------------ saltar pregunta
  const OMITIDA = '<span class="omitida">⏭ Omitida</span>';
  function botonSaltar(clave, texto = "Saltar pregunta") {
    if (!room || !estado?.pendiente || estado.pendiente.clave !== clave || !estado.pendiente.saltable) return "";
    return `<button class="skip" type="button" data-clave="${esc(clave)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5l9 7-9 7zM16 5h3v14h-3z" fill="currentColor"/></svg>${esc(texto)}</button>`;
  }
  function pregActual(p) {
    const nota = p.saltable ? botonSaltar(p.clave) : `<span class="muted small">${esc(p.motivo_no_saltable || "")}</span>`;
    return `<div class="preg-actual"><p>${esc(p.texto)}</p>${nota}</div>`;
  }
  function conectarSaltos(raiz) {
    raiz.querySelectorAll(".skip").forEach((b) => b.onclick = () => saltarPregunta(b.dataset.clave, b));
  }
  let saltando = false;
  async function saltarPregunta(clave, boton) {
    if (saltando || !sid) return;
    saltando = true;
    document.querySelectorAll(".skip").forEach((b) => (b.disabled = true));
    if (boton) boton.textContent = "Saltando…";
    try {
      const r = await api(`/sesiones/${sid}/saltar`, { method: "POST", body: JSON.stringify({ clave }) });
      estado = r.vista; version = estado.version; render();
      if (r.ok) {
        const { vista, ...data } = r;
        avisarAgente({ tipo: "saltar", data });
        if (estado.dictamen) $("dictamenF").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (e) {
      $("error").textContent = e.message;
      document.querySelectorAll(".skip").forEach((b) => (b.disabled = false));
    }
    saltando = false;
  }

  function renderCareers() {
    const res = estado.resultado;
    $("careers").innerHTML = res.carreras.map((c, i) => {
      const s = c.sede_accesible_cercana || c.sede_publica_cercana;
      const donde = s ? `${esc(s.siglas)} · ${esc(s.ciudad)}${s.distancia_km != null ? ` · ${s.distancia_km} km` : ""}` : "Opciones a distancia y becas";
      return `<button class="career ${c.id === estado.enfoque ? "on" : ""}" data-id="${c.id}">
        <span class="rank">Opción ${i + 1}${estado.carrera_elegida === c.id ? " · tu elección" : ""}</span>
        <span class="name">${esc(c.nombre)}</span>
        <span class="score">${Math.round(c.puntaje)}<small> / 100</small></span>
        <span class="bar"><span>Afinidad</span><span class="track"><span class="fill" style="width:${c.afinidad}%"></span></span><span>${Math.round(c.afinidad)}</span></span>
        <span class="bar v"><span>Viabilidad</span><span class="track"><span class="fill" style="width:${c.viabilidad}%"></span></span><span>${c.viabilidad}</span></span>
        <span class="where">${donde}</span>
      </button>`;
    }).join("");
    $("careers").querySelectorAll(".career").forEach((b) => b.onclick = () => enfocar(b.dataset.id));
  }

  async function enfocar(id) {
    const c = carreraById(id);
    autoplayPara = id;
    try { estado = await api(`/sesiones/${sid}/enfoque`, { method: "POST", body: JSON.stringify({ carrera: id }) }); version = estado.version; render(); } catch {}
    avisarAgente({ tipo: "enfoque", carrera: id, nombre: c?.nombre });
    $("focus").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderFocus() {
    const c = carreraById(estado.enfoque) || estado.resultado.carreras[0];
    if (!c) return;
    $("fArea").textContent = c.area;
    $("fNombre").textContent = c.nombre;
    $("fDesc").textContent = c.descripcion;
    $("fDur").textContent = c.duracion;
    $("fElegida").hidden = estado.carrera_elegida !== c.id;
    $("fRazones").innerHTML = (c.razones.length ? c.razones : ["Coincide con tu perfil general"]).map((r) => `<li>${esc(r)}</li>`).join("");
    $("fCampo").innerHTML = c.campo_laboral.map((r) => `<li>${esc(r)}</li>`).join("");
    $("fAlt").innerHTML = c.alternativas_cortas.map((r) => `<li>${esc(r)}</li>`).join("");
    $("fPlanes").innerHTML = planesHtml(c);
    renderStars(c);
    renderVideo(c);
    renderTemario(c);
  }

  // Enlaces al plan de estudios / contacto de las universidades que ofrecen la carrera (primero las que puede costear)
  function enlacesSede(s) {
    const out = [];
    if (s.plan_url) out.push(`<a href="${esc(s.plan_url)}" target="_blank" rel="noopener">Plan de estudios</a>`);
    else if (s.contacto_url) out.push(`<a href="${esc(s.contacto_url)}" target="_blank" rel="noopener">Oferta académica</a>`);
    if (s.telefono) out.push(`<a href="tel:+504${esc(s.telefono.replace(/[^0-9]/g, "").slice(0, 8))}">Tel. ${esc(s.telefono)}</a>`);
    if (s.correo) out.push(`<a href="mailto:${esc(s.correo)}">${esc(s.correo)}</a>`);
    return out.join('<span class="sep">·</span>');
  }
  function planesHtml(c) {
    const vistas = new Set(), filas = [];
    for (const s of c.sedes) {
      if (vistas.has(s.universidad_id)) continue;
      vistas.add(s.universidad_id);
      filas.push(`<li><b>${esc(s.siglas)}</b>${s.accesible ? "" : ' <span class="muted">(fuera de tu presupuesto)</span>'}<div class="uni-links">${enlacesSede(s)}</div></li>`);
      if (filas.length >= 4) break;
    }
    return filas.join("") || '<li class="muted">Revisa las opciones a distancia en el mapa.</li>';
  }

  function renderStars(c) {
    const val = (estado.calificaciones || {})[c.id] || 0;
    const star = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.8l2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.2l-5.7 3.1 1.2-6.4L2.8 9.5l6.4-.8z"/></svg>';
    $("stars").innerHTML = [1, 2, 3, 4, 5].map((n) => `<button class="star ${n <= val ? "on" : ""}" data-n="${n}" role="radio" aria-checked="${n === val}" aria-label="${n} de 5">${star}</button>`).join("");
    $("stars").querySelectorAll(".star").forEach((b) => b.onclick = () => calificar(c, +b.dataset.n));
  }
  async function calificar(c, n) {
    try { estado = await api(`/sesiones/${sid}/calificacion`, { method: "POST", body: JSON.stringify({ carrera: c.id, puntaje: n }) }); version = estado.version; render(); } catch (e) { console.warn(e); }
    avisarAgente({ tipo: "calificacion", carrera: c.id, nombre: c.nombre, puntaje: n });
  }

  // Video: reproductor de YouTube con varios candidatos; si uno no se puede ver, pasa al siguiente
  let ytListo = null, ytPlayer = null;
  function cargarYT() {
    if (ytListo) return ytListo;
    ytListo = new Promise((resolve) => {
      if (window.YT && window.YT.Player) return resolve();
      window.onYouTubeIframeAPIReady = () => resolve();
      const s = document.createElement("script"); s.src = "https://www.youtube.com/iframe_api"; s.onerror = () => resolve();
      document.head.appendChild(s);
      setTimeout(resolve, 6000);
    });
    return ytListo;
  }
  async function renderVideo(c) {
    const auto = autoplayPara === c.id;
    autoplayPara = null;
    if (videoCarrera === c.id) {
      if (auto && ytPlayer && ytPlayer.playVideo) { try { ytPlayer.playVideo(); } catch {} }
      else if (auto) { const f = $("video").querySelector("iframe"); if (f && !/autoplay=1/.test(f.src)) f.src += "&autoplay=1"; }
      return;
    }
    videoCarrera = c.id;
    try { ytPlayer && ytPlayer.destroy && ytPlayer.destroy(); } catch {}
    ytPlayer = null; pausarMic(false);
    $("video").innerHTML = '<div class="fallback"><div>Cargando video…</div></div>';
    let v;
    try { v = await api(`/video/${c.id}`); } catch { v = { ids: [], buscar_url: `https://www.youtube.com/results?search_query=${encodeURIComponent(c.nombre)}` }; }
    if (videoCarrera !== c.id) return;
    $("videoMas").href = v.buscar_url; $("videoMas").hidden = false;
    const ids = v.ids || [];
    const sinVideo = () => { $("video").innerHTML = `<div class="fallback"><div><b>Conoce ${esc(c.nombre)} en video</b><br><a href="${esc(v.buscar_url)}" target="_blank" rel="noopener">Ver videos en YouTube</a></div></div>`; };
    if (!ids.length) return sinVideo();
    await cargarYT();
    if (videoCarrera !== c.id) return;
    if (!(window.YT && window.YT.Player)) {
      $("video").innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(ids[0])}?rel=0${auto ? "&autoplay=1" : ""}" title="Video sobre ${esc(c.nombre)}" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>`;
      return;
    }
    let i = 0;
    $("video").innerHTML = '<div id="ytPlayer"></div>';
    ytPlayer = new YT.Player("ytPlayer", {
      host: "https://www.youtube-nocookie.com", videoId: ids[0],
      playerVars: { rel: 0, modestbranding: 1, playsinline: 1, hl: "es", autoplay: auto ? 1 : 0 },
      events: {
        onReady: (e) => {
          if (!auto) return;
          try { e.target.playVideo(); } catch {}
          // Si el navegador bloquea el audio, arranca en silencio (YouTube muestra el botón para activar sonido)
          setTimeout(() => { try { if (e.target.getPlayerState() !== 1) { e.target.mute(); e.target.playVideo(); } } catch {} }, 1500);
        },
        onStateChange: (e) => {
          if (videoCarrera !== c.id) return;
          if (e.data === 1) pausarMic(true);
          else if (e.data === 2 || e.data === 0) pausarMic(false);
          if (e.data === 0) avisarAgente({ tipo: "video_fin", carrera: c.id, nombre: c.nombre });
        },
        onError: () => {
          i += 1;
          if (videoCarrera !== c.id) return;
          if (i < ids.length) (auto ? ytPlayer.loadVideoById(ids[i]) : ytPlayer.cueVideoById(ids[i]));
          else { try { ytPlayer.destroy(); } catch {} ytPlayer = null; sinVideo(); }
        },
      },
    });
  }

  function renderTemario(c) {
    if (renderTemario.last !== c.id) { tabTemario = 0; renderTemario.last = c.id; }
    $("tTabs").innerHTML = c.temario.map((t, i) => `<button class="tab ${i === tabTemario ? "on" : ""}" role="tab" data-i="${i}">${esc(t.nivel)}</button>`).join("");
    $("tTabs").querySelectorAll(".tab").forEach((b) => b.onclick = () => { tabTemario = +b.dataset.i; renderTemario(c); });
    $("tList").innerHTML = c.temario[tabTemario].materias.map((m) => `<li>${esc(m)}</li>`).join("");
    const po = $("planOficial");
    const sp = c.sedes.find((s) => s.accesible && s.plan_url) || c.sedes.find((s) => s.plan_url);
    const url = sp ? sp.plan_url : c.plan_oficial_url;
    po.hidden = !url;
    if (url) { po.href = url; po.textContent = sp ? `Plan oficial de ${sp.siglas}` : "Plan oficial"; }
  }

  // ------------------------------------------------------------------ mapa y universidades
  function renderChips() {
    $("chips").innerHTML = Object.keys(CHIP_LABEL).map((k) => `<button class="chip ${filtros.has(k) ? "on" : ""}" data-k="${k}"><i style="background:${COLOR[k]}"></i>${CHIP_LABEL[k]}</button>`).join("");
    $("chips").querySelectorAll(".chip").forEach((b) => b.onclick = () => { const k = b.dataset.k; filtros.has(k) ? filtros.delete(k) : filtros.add(k); renderChips(); renderMapa(); });
  }

  function renderMapa() {
    const c = carreraById(estado.enfoque) || estado.resultado.carreras[0];
    const u = estado.ubicacion;
    if (!map) {
      map = L.map("map", { scrollWheelZoom: false }).setView([14.75, -86.75], 7);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "&copy; OpenStreetMap" }).addTo(map);
      capa = L.layerGroup().addTo(map);
    }
    capa.clearLayers();
    const pts = [];
    if (u && u.lat != null) {
      L.circleMarker([u.lat, u.lng], { radius: 9, color: "#fff", weight: 3, fillColor: "#e23b3b", fillOpacity: 1 })
        .bindPopup(`<b>Tú</b><br>${esc([u.municipio, u.departamento].filter(Boolean).join(", "))}<br><small>Ubicación ${esc(u.precision)}</small>`).addTo(capa);
      pts.push([u.lat, u.lng]);
    }
    const sedes = c.sedes.filter((s) => filtros.has(s.costo));
    const vistos = {};
    sedes.forEach((s) => {
      const k = `${s.lat},${s.lng}`; const n = (vistos[k] = (vistos[k] || 0) + 1) - 1;
      const lat = s.lat + (n ? Math.sin(n * 2.1) * 0.012 : 0), lng = s.lng + (n ? Math.cos(n * 2.1) * 0.012 : 0);
      L.circleMarker([lat, lng], { radius: 8, color: "#fff", weight: 2, fillColor: COLOR[s.costo], fillOpacity: 0.95 })
        .bindPopup(`<b>${esc(s.siglas)} – ${esc(s.sede)}</b><br>${esc(s.ciudad)}, ${esc(s.departamento)}<br>${esc(s.costo_texto)}${s.distancia_km != null ? `<br>≈ ${s.distancia_km} km de ti` : ""}<div class="uni-links">${enlacesSede(s)}</div>`)
        .addTo(capa);
      pts.push([lat, lng]);
    });
    setTimeout(() => {
      map.invalidateSize();
      if (pts.length > 1) map.fitBounds(pts, { padding: [30, 30], maxZoom: 10 }); else if (pts.length === 1) map.setView(pts[0], 9);
    }, 50);

    const items = sedes.map((s) => `<li class="uni"><span class="dot" style="background:${COLOR[s.costo]}"></span>
        <div><b>${esc(s.siglas)} · ${esc(s.sede)}</b><span>${esc(s.ciudad)}, ${esc(s.departamento)} · ${esc(s.costo_texto)}${s.modalidad === "telecentro" ? " · telecentro" : ""}</span><div class="uni-links">${enlacesSede(s)}</div></div>
        <div class="km">${s.distancia_km != null ? `${s.distancia_km} km<small>en línea recta</small>` : ""}</div></li>`);
    if (filtros.has("distancia")) {
      (c.oportunidades || []).map((id) => catalogo?.oportunidades?.[id]).filter((o) => o && o.tipo === "distancia").forEach((o) => {
        items.push(`<li class="uni"><span class="dot" style="background:${COLOR.distancia}"></span>
          <div><b>${esc(o.nombre)}</b><span>${esc(o.resumen)}</span></div>
          <div class="km"><a href="${esc(o.url)}" target="_blank" rel="noopener">Ver</a></div></li>`);
      });
    }
    $("unis").innerHTML = items.join("") || '<li class="empty">No hay sedes con estos filtros. Activa otros tipos arriba.</li>';
  }

  // ------------------------------------------------------------------ plan, extras, agenda
  function renderPlan() {
    const res = estado.resultado;
    $("plan").hidden = !res.plan_directo?.length;
    if (!res.plan_directo?.length) return;
    $("planMotivo").textContent = res.alejado ? res.motivo_alejado : "Por tu situación económica, este es el camino más directo con opciones gratuitas y becas.";
    const enlace = (p) => p.url ? ` <a href="${esc(p.url)}" target="_blank" rel="noopener">Abrir</a>` : "";
    $("phases").innerHTML = res.plan_directo.map((f) => `<li class="phase"><h3>${esc(f.fase)}</h3><ul>${f.pasos.map((p) => `<li>${esc(p.texto)}${enlace(p)}</li>`).join("")}</ul></li>`).join("");
  }

  function renderExtras() {
    $("extras").innerHTML = estado.resultado.extras.map((e) => {
      const s = e.sede_publica_cercana;
      const dist = (e.oportunidades || []).map((id) => catalogo?.oportunidades?.[id]).find((o) => o && o.tipo === "distancia" && o.gratuita);
      const u = s ? `Gratis o muy bajo costo: ${esc(s.siglas)} ${esc(s.ciudad)}${s.distancia_km != null ? ` · ${s.distancia_km} km` : ""}` : dist ? `A distancia: ${esc(dist.nombre)}` : "Sin sede pública: revisa becas";
      return `<li><button class="extra" data-id="${e.id}"><span class="s">${Math.round(e.puntaje)} / 100</span><b>${esc(e.nombre)}</b><span class="u">${u}</span></button></li>`;
    }).join("");
    $("extras").querySelectorAll(".extra").forEach((b) => b.onclick = () => enfocar(b.dataset.id));
  }

  let horarios = null, slotSel = null;
  function renderAgenda() {
    const cita = estado.cita;
    if (cita?.estado === "agendada") {
      $("agendaBody").innerHTML = `<div class="ok-box"><b>¡Reunión agendada!</b><br>${esc(fmt(cita.inicio))}<br>${cita.enlace ? `<a href="${esc(cita.enlace)}" target="_blank" rel="noopener">Unirme por Teams</a>` : "Recibirás la invitación por correo."}</div>`;
      return;
    }
    if (cita?.estado === "pendiente") {
      $("agendaBody").innerHTML = `<div class="ok-box"><b>Solicitud registrada</b><br>Pediste: ${esc(fmt(cita.inicio))}<br>El equipo de psicología te contactará para confirmar.</div>`;
      return;
    }
    if (estado.ui?.mostrar_agenda && !$("agendaForm")) abrirAgenda();
  }
  function fmt(iso) { try { return new Date(iso).toLocaleString("es-HN", { weekday: "long", day: "numeric", month: "long", hour: "numeric", minute: "2-digit" }); } catch { return iso; } }

  async function abrirAgenda() {
    $("agendaBody").innerHTML = '<p class="muted">Cargando horarios…</p>';
    try { horarios = await api("/horarios"); } catch { horarios = { horarios: [], teams: false }; }
    const est = estado.estudiante || {};
    $("agendaBody").innerHTML = `<form class="form" id="agendaForm">
      <label>Tu nombre<input name="nombre" required minlength="2" maxlength="80" value="${esc(est.nombre || "")}" autocomplete="name"></label>
      <label>Tu correo (opcional)<input name="correo" type="email" maxlength="120" value="${esc(est.correo || "")}" autocomplete="email"></label>
      <div class="slots" id="slots">${horarios.horarios.map((h) => `<button type="button" class="slot" data-v="${esc(h.inicio)}" data-l="${esc(h.etiqueta)}">${esc(h.etiqueta)}</button>`).join("") || '<span class="muted">No hay horarios disponibles ahora.</span>'}</div>
      <div class="actions"><button class="primary" type="submit" id="agendaBtn" disabled>Agendar reunión</button>
      <span class="muted small">${horarios.teams ? `Reunión de ${horarios.duracion_min} minutos por Microsoft Teams.` : "Registraremos tu solicitud y el equipo te contactará."}</span></div>
    </form>`;
    $("slots").querySelectorAll(".slot").forEach((b) => b.onclick = () => {
      $("slots").querySelectorAll(".slot").forEach((x) => x.classList.remove("on"));
      b.classList.add("on"); slotSel = { v: b.dataset.v, l: b.dataset.l }; $("agendaBtn").disabled = false;
    });
    $("agendaForm").onsubmit = async (ev) => {
      ev.preventDefault();
      const f = new FormData(ev.target);
      $("agendaBtn").disabled = true; $("agendaBtn").textContent = "Agendando…";
      try {
        estado = await api(`/sesiones/${sid}/cita`, { method: "POST", body: JSON.stringify({ nombre: f.get("nombre"), correo: f.get("correo") || null, inicio: slotSel.v }) });
        version = estado.version; render();
        avisarAgente({ tipo: "cita", estado: estado.cita?.estado, etiqueta: slotSel.l });
      } catch (e) { $("agendaBtn").disabled = false; $("agendaBtn").textContent = "Agendar reunión"; alertaInline(e.message); }
    };
    $("agenda").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function alertaInline(msg) { const p = document.createElement("p"); p.className = "error"; p.textContent = msg; $("agendaForm").appendChild(p); }

  // ------------------------------------------------------------------ idioma
  function llenarIdiomas() {
    const idi = catalogo?.idiomas || { es: { nombre: "Español", region: "Principal" } };
    const grupos = {};
    Object.entries(idi).forEach(([k, v]) => { (grupos[v.region] = grupos[v.region] || []).push([k, v]); });
    $("idioma").innerHTML = Object.entries(grupos).map(([g, arr]) =>
      `<optgroup label="${esc(g === "Principal" ? "Principal" : "Indígenas · " + g)}">${arr.map(([k, v]) => `<option value="${k}">${esc(v.nombre)}${v.nivel === "experimental" ? " (experimental)" : ""}</option>`).join("")}</optgroup>`).join("");
    const pref = leer("orienta.idioma");
    $("idioma").value = pref && idi[pref] ? pref : "es";
    notaIdioma();
  }
  function notaIdioma() {
    const v = catalogo?.idiomas?.[$("idioma").value];
    $("idiomaNota").textContent = v?.nota || "";
    $("idiomaNota").hidden = !v?.nota || v.nivel !== "experimental";
  }
  async function cambiarIdioma() {
    guardar("orienta.idioma", $("idioma").value);
    notaIdioma();
    if (sid && room) {
      try { estado = await api(`/sesiones/${sid}/idioma`, { method: "POST", body: JSON.stringify({ idioma: $("idioma").value }) }); version = estado.version; } catch {}
      avisarAgente({ tipo: "idioma", idioma: $("idioma").value });
    }
  }

  // ------------------------------------------------------------------ nueva sesión
  async function nuevaSesion(sinConfirmar) {
    if (room && sinConfirmar !== true && !confirm("¿Terminar la conversación actual y empezar una sesión nueva?")) return;
    if (room) await stop();
    try { ytPlayer && ytPlayer.destroy && ytPlayer.destroy(); } catch {}
    ytPlayer = null; videoCarrera = null; autoplayPara = null;
    sid = null; estado = null; version = -1; filtros = null; nivelFiltros = null;
    history.replaceState(null, "", location.pathname);
    $("transcript").innerHTML = ""; segments.clear();
    $("error").textContent = "";
    $("hero").hidden = false; $("resultados").hidden = true; $("verResultados").hidden = true;
    $("heroF").hidden = false; ["casoF", "testF", "dictamenF", "agenda"].forEach((id) => ($(id).hidden = true));
    $("agendaBody").innerHTML = '<p class="muted">Agenda una reunión por Teams para seguir conversando sobre tu futuro.</p><button class="primary" id="agendaOpen" type="button">Quiero agendar</button>';
    $("agendaOpen").onclick = abrirAgenda;
    $("gpsBtn").textContent = "Usar mi ubicación exacta";
    if (capa) capa.clearLayers();
    renderFichaVacia();
    setMode("idle"); setStatus("Toca el micrófono para empezar");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ------------------------------------------------------------------ eventos
  $("micBtn").onclick = start;
  $("hangBtn").onclick = () => stop();
  $("agendaOpen").onclick = abrirAgenda;
  $("verResultados").onclick = verResultados;
  $("nuevaSesion").onclick = () => nuevaSesion();
  $("navLucia").onclick = () => setModo("eleccion");
  $("navFabiola").onclick = () => setModo("permanencia");
  $("irLucia").onclick = () => setModo("eleccion");
  $("idioma").onchange = cambiarIdioma;
  $("gpsBtn").onclick = () => {
    if (!sid || !navigator.geolocation) return;
    $("gpsBtn").textContent = "Ubicando…";
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try { estado = await api(`/sesiones/${sid}/gps`, { method: "POST", body: JSON.stringify({ lat: pos.coords.latitude, lng: pos.coords.longitude }) }); version = estado.version; render(); } catch {}
      $("gpsBtn").textContent = "Ubicación actualizada";
    }, () => { $("gpsBtn").textContent = "No se pudo ubicar"; }, { enableHighAccuracy: false, timeout: 10000 });
  };
  window.addEventListener("beforeunload", () => { if (room) room.disconnect(); });

  // Inicio: catálogo y, si el enlace trae una sesión, mostrar sus resultados
  (async () => {
    setMode("idle");
    try { catalogo = await api("/catalogo"); } catch {}
    modo = leer("orienta.modo") === "permanencia" ? "permanencia" : "eleccion";
    if (location.hash === "#fabiola") { modo = "permanencia"; history.replaceState(null, "", location.pathname); }
    aplicarModo();
    llenarIdiomas();
    const h = location.hash.replace("#", "");
    if (/^orienta-[0-9a-f]{24}$/.test(h)) { sid = h; await refresh(); }
    else renderFichaVacia();
  })();
  function renderFichaVacia() {
    estado = { respuestas: {}, ubicacion: null, caso: null, test: null, dictamen: null };
    modo === "permanencia" ? renderFichaF() : renderFicha();
    estado = null;
  }
})();
