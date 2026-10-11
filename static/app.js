/* SoulsBPM – console de DJ (interface). Cada tela corresponde a um estado do documento 4. */
const $ = (s, r = document) => r.querySelector(s);
const app = $("#app");
const K = { uid: "souls_uid", consent: "souls_consent", tec: "souls_tec", tema: "souls_tema", menu: "souls_menu" };
const guarda = {
  get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
};
const S = { clicado: null, ocupado: false, sid: null, dj: null, busca: "", tocando: null, res: null, origem: null, salvo: false, redesenha: null };

/* botão clicado (captura antes dos handlers) e indicador de carregamento: o spinner só aparece se a resposta
   demorar (>150 ms), para não piscar; cliques repetidos são ignorados enquanto a ação roda */
app.addEventListener("click", e => { S.clicado = e.target.closest("button"); }, true);
async function comSpinner(fn) {
  if (S.ocupado) return;
  S.ocupado = true;
  const b = S.clicado && app.contains(S.clicado) && S.clicado.classList.contains("btn") ? S.clicado : null;
  const t = setTimeout(() => b?.setAttribute("aria-busy", "true"), 150);
  try { return await fn(); }
  finally { clearTimeout(t); S.ocupado = false; if (b?.isConnected) b.removeAttribute("aria-busy"); }
}

/* ---------- ícones (traço, estilo Lucide) ---------- */
const P = {
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  list: '<path d="M21 15V6"/><circle cx="18.5" cy="18" r="2.5"/><path d="M12 12H3M16 6H3M12 18H3"/>',
  skip: '<polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/>',
  heart: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  copy: '<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  warn: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  note: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  plus: '<path d="M5 12h14M12 5v14"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  chev: '<path d="m9 18 6-6-6-6"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
  swap: '<path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/>',
  save: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
  sparkle: '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5a2 2 0 0 0 1.44 1.44l6.14 1.58a.5.5 0 0 1 0 .96l-6.14 1.58a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"/><path d="M20 3v4M22 5h-4"/>',
  disc: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="2"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  chart: '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="m19 9-5 5-4-4-3 3"/>',
};
const ic = (n, cls = "ic") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[n]}</svg>`;
const LOGO = `<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#7a66ff"/>
  <g stroke="#0e0d1c" stroke-width="2.6" stroke-linecap="round"><path d="M8 14v4M12 10v12M16 7v18M20 11v10M24 14v4"/></g></svg>`;
document.querySelectorAll("[data-i]").forEach(e => { e.innerHTML = ic(e.dataset.i); });
$("#side-logo").innerHTML = LOGO + '<span class="tab-t"> SoulsBPM</span>';

/* ---------- utilidades ---------- */
function userId() {
  if (guarda.get(K.consent) !== "sim") return null;           // sem consentimento nada é guardado
  let u = guarda.get(K.uid);
  if (!u) { u = "u_" + Math.random().toString(36).slice(2, 12); guarda.set(K.uid, u); }
  return u;
}
async function api(method, url, body) {
  const sem = method === "GET" || method === "DELETE";
  const q = sem ? (url.includes("?") ? "&" : "?") + "user_id=" + encodeURIComponent(userId() || "") : "";
  const r = await fetch(url + q, { method, headers: { "Content-Type": "application/json" },
    body: sem ? undefined : JSON.stringify({ user_id: userId(), ...(body || {}) }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.erro || "Algo deu errado. Tente de novo.");
  return j;
}
const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const mmss = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const pct = (a, b) => { const d = (b - a) / a * 100; return (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(1).replace(".", ",") + "%"; };
const paraTop = () => window.scrollTo({ top: 0 });
function pararReproducao() { if (S.tocando) { clearInterval(S.tocando.t); S.tocando = null; } }
function setTecnico(on, salvar = true) {
  document.body.classList.toggle("tecnico", on);
  if (salvar) guarda.set(K.tec, on ? "1" : "0");
}
/* ativa = aba em destaque; foco = Modo DJ / salvar (o menu lateral continua visível) */
function abas(ativa, foco = false) {
  S.redesenha = null; app.classList.remove("sem-anim");
  $("#shell").classList.toggle("foco", foco);
  ["buscar", "playlists"].forEach(t => $("#tab-" + t).classList.toggle("ativa", t === ativa));
}
function toast(msg) {
  document.querySelector(".toast")?.remove();
  const t = document.createElement("div");
  t.className = "toast"; t.setAttribute("role", "status"); t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.classList.add("sai"); setTimeout(() => t.remove(), 220); }, 3000);
}
/* ---------- tema claro / escuro ---------- */
const temaAtual = () => document.documentElement.dataset.tema === "claro" ? "claro" : "escuro";
const temaInner = t => `${ic(t === "claro" ? "moon" : "sun")}<span class="tema-l">${t === "claro" ? "Modo escuro" : "Modo claro"}</span>`;
const temaBtn = (cls = "") => { const t = temaAtual(); return `<button class="tema-btn ${cls}" type="button" aria-label="Mudar para o modo ${t === "claro" ? "escuro" : "claro"}" title="Mudar para o modo ${t === "claro" ? "escuro" : "claro"}">${temaInner(t)}</button>`; };
function aplicarTema(t, salvar = false) {
  document.documentElement.dataset.tema = t;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", t === "claro" ? "#f4f3fa" : "#0e0d1c");
  if (salvar) guarda.set(K.tema, t);
  const outro = t === "claro" ? "escuro" : "claro";
  document.querySelectorAll(".tema-btn").forEach(b => {
    b.setAttribute("aria-label", `Mudar para o modo ${outro}`); b.title = `Mudar para o modo ${outro}`; b.innerHTML = temaInner(t);
  });
}
document.addEventListener("click", e => { if (e.target.closest(".tema-btn")) aplicarTema(temaAtual() === "claro" ? "escuro" : "claro", true); });
/* sem escolha salva, o app acompanha o tema do sistema */
matchMedia("(prefers-color-scheme: light)").addEventListener?.("change", e => { if (!guarda.get(K.tema)) aplicarTema(e.matches ? "claro" : "escuro"); });
aplicarTema(temaAtual());

const topbar = (rotulo = "Voltar", meio = "", dir = "") =>
  `<div class="topbar"><button class="back" id="b-voltar" type="button">${ic("back")}<span>${esc(rotulo)}</span></button>
   <span class="sp"></span>${meio}${dir}</div>`;
const ligaVoltar = fn => { $("#b-voltar").onclick = fn; };
const erroHtml = m => `<div class="aviso erro">${esc(m)}</div>`;

/* caixa de confirmação do próprio app (no lugar do confirm() do navegador) */
/* fecha um <dialog> com animação de saída (sem animação se o usuário prefere menos movimento) */
function fechaDlg(dlg) {
  if (!dlg.open) return;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) { dlg.close(); return; }
  dlg.classList.add("fechando");
  setTimeout(() => { dlg.classList.remove("fechando"); dlg.close(); }, 180);
}
function confirma(titulo, texto, rotuloOk, rotuloNao) {
  return new Promise(res => {
    const dlg = $("#dlg-conf");
    $("#conf-tit").textContent = titulo; $("#conf-txt").textContent = texto;
    $("#conf-ok").textContent = rotuloOk; $("#conf-no").textContent = rotuloNao;
    const fim = v => { fechaDlg(dlg); res(v); };
    $("#conf-ok").onclick = () => fim(true);
    $("#conf-no").onclick = () => fim(false);
    dlg.oncancel = e => { e.preventDefault(); fim(false); };      // tecla Esc = ficar
    dlg.showModal();
  });
}
/* antes de largar uma sequência montada e ainda não salva */
async function saidaOk() {
  const d = S.dj;
  if (!(d && d.sequencia.length >= 2 && !S.salvo)) return true;
  return confirma("Sair do Modo DJ?", "A sequência que você montou ainda não foi salva e vai se perder.",
                  "Sair sem salvar", "Continuar no Modo DJ");
}

/* ---------- peças visuais ---------- */
const parseTom = t => { const m = /^(\d+)([AB])$/.exec(t || ""); return m ? { n: +m[1], l: m[2] } : null; };
function corChave(tom) {                                   // cores da roda de Camelot: vizinhas têm tons vizinhos
  const k = parseTom(tom); if (!k) return "#888";
  const h = ((k.n - 1) * 30 + 175) % 360;
  return k.l === "A" ? `hsl(${h} 62% 58%)` : `hsl(${h} 80% 66%)`;
}
const chave = (tom, grande = false) => `<span class="k${grande ? " g" : ""}" style="--k:${corChave(tom)}" title="Chave Camelot ${esc(tom)}">${esc(tom)}</span>`;
const energia = e => `<span class="en" role="img" aria-label="energia ${Math.round(e * 10)} de 10">${[1, 2, 3, 4, 5].map(i => `<i class="${i <= Math.round(e * 5) ? "on" : ""}"></i>`).join("")}</span>`;
const semente = id => { let h = 2166136261; for (const c of String(id)) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return h >>> 0; };
const prng = s => () => { s |= 0; s = s + 0x6D2B79F5 | 0; let t = Math.imul(s ^ s >>> 15, 1 | s); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const capa = (f, cls = "", tocando = false) =>
  `<div class="capa ${cls}" style="--k:${corChave(f.tom)};--a:${90 + semente(f.id) % 180}deg">${ic("note")}${tocando ? '<span class="eq"><i></i><i></i><i></i><i></i></span>' : ""}</div>`;

function ondaSvg(f) {                                      // forma de onda de enfeite, sempre igual para a mesma faixa
  const r = prng(semente(f.id)), N = 100, base = 0.3 + f.energia * 0.45, voltas = 2 + semente(f.id) % 3;
  let d = "";
  for (let i = 0; i < N; i++) {
    const env = 0.55 + 0.45 * Math.sin(i / N * Math.PI * voltas);
    const h = Math.max(0.12, Math.min(1, base * env + r() * 0.35)) * 56;
    d += `<rect x="${(i * 2).toFixed(1)}" y="${((60 - h) / 2).toFixed(1)}" width="1.4" height="${h.toFixed(1)}" rx=".5"/>`;
  }
  return d;
}
const onda = (f, p) => `<div class="onda"><svg class="base" viewBox="0 0 200 60" preserveAspectRatio="none" aria-hidden="true">${ondaSvg(f)}</svg>
  <svg class="on" id="barra" viewBox="0 0 200 60" preserveAspectRatio="none" aria-hidden="true" style="clip-path:inset(0 ${100 - p}% 0 0)">${ondaSvg(f)}</svg></div>`;

function roda(a, b) {                                      // roda de Camelot: mostra o salto de chave da troca
  const ponto = k => { const ang = ((k.n - 1) * 30 - 90) * Math.PI / 180, r = k.l === "B" ? 38 : 25; return [48 + r * Math.cos(ang), 48 + r * Math.sin(ang)]; };
  const ka = parseTom(a), kb = parseTom(b);
  let s = "";
  for (let n = 1; n <= 12; n++) for (const l of ["A", "B"]) {
    const [x, y] = ponto({ n, l });
    s += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${corChave(n + l)}" opacity=".4"/>`;
  }
  if (ka && kb) {
    const [xa, ya] = ponto(ka), [xb, yb] = ponto(kb);
    if (a !== b) s += `<line x1="${xa}" y1="${ya}" x2="${xb}" y2="${yb}" style="stroke:var(--ambar)" stroke-width="1.5" stroke-dasharray="3 3"/>`;
    s += `<circle cx="${xa}" cy="${ya}" r="6" fill="${corChave(a)}" style="stroke:var(--contorno)" stroke-width="2"/>`;
    if (a !== b) s += `<circle cx="${xb}" cy="${yb}" r="6" fill="${corChave(b)}" style="stroke:var(--ambar)" stroke-width="2"/>`;
  }
  return `<svg class="roda" viewBox="0 0 96 96" role="img" aria-label="Roda de Camelot: ${esc(a)} para ${esc(b)}">${s}</svg>`;
}
function anel(p) {                                         // % de compatibilidade técnica
  const c = { combina_bem: "var(--ok)", ok: "var(--indigo-claro)", arriscada: "var(--risco)" }[p.classe], L = 2 * Math.PI * 26;
  return `<div class="anel so-tec" style="--cor:${c}" role="img" aria-label="Compatibilidade ${p.compatibilidade}%"><svg viewBox="0 0 68 68">
    <circle class="f" cx="34" cy="34" r="26"/><circle class="v" cx="34" cy="34" r="26" stroke-dasharray="${(L * p.compatibilidade / 100).toFixed(1)} ${L.toFixed(1)}"/></svg><b>${p.compatibilidade}%</b></div>`;
}

/* trajetória do set: BPM faixa a faixa, alvo, faixa de ±5% e o ponto sugerido pela IA */
function trajetoria(w, h, seq, prox, alvo) {
  const pl = 42, pr = alvo != null ? 66 : 22, pt = 14, pb = 28;
  const pts = seq.slice(-10), ia = pts.length - 1, cur = pts[ia], n0 = seq.length - pts.length + 1;
  const todos = prox ? [...pts, prox] : pts;
  const slots = Math.max(todos.length + 1, 6);
  const vals = todos.map(f => f.bpm); if (alvo != null) vals.push(alvo);
  let lo = Math.min(...vals, cur.bpm * 0.95), hi = Math.max(...vals, cur.bpm * 1.05);
  const pad = Math.max(5, (hi - lo) * 0.12);
  lo = Math.floor((lo - pad) / 10) * 10; hi = Math.ceil((hi + pad) / 10) * 10;
  if (hi - lo < 30) hi = lo + 30;
  const X = i => pl + i * (w - pl - pr) / (slots - 1), Y = v => pt + (hi - v) * (h - pt - pb) / (hi - lo);
  const passo = hi - lo > 80 ? 20 : 10;
  const tip = f => `<title>${esc(f.titulo)}, ${f.bpm} BPM</title>`;
  let s = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Trajetória do BPM ao longo do set">`;
  for (let v = Math.ceil(lo / passo) * passo; v <= hi; v += passo)
    s += `<line class="g-grid" x1="${pl}" x2="${w - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="g-lbl" x="${pl - 8}" y="${Y(v) + 4}" text-anchor="end">${v}</text>`;
  s += `<rect class="g-faixa" x="${X(ia)}" y="${Y(cur.bpm * 1.05)}" width="${X(ia + 1) - X(ia)}" height="${Y(cur.bpm * 0.95) - Y(cur.bpm * 1.05)}" rx="3"><title>Faixa de ±5% de BPM onde a próxima troca soa natural</title></rect>`;
  if (alvo != null) s += `<line class="g-alvo" x1="${pl}" x2="${w - pr}" y1="${Y(alvo)}" y2="${Y(alvo)}"/><text class="g-alvo-l" x="${w - pr + 8}" y="${Y(alvo) + 4}">alvo ${alvo}</text>`;
  if (pts.length > 1) s += `<polyline class="g-linha" points="${pts.map((f, i) => `${X(i)},${Y(f.bpm)}`).join(" ")}"/>`;
  if (prox) s += `<line class="g-prox-l" x1="${X(ia)}" y1="${Y(cur.bpm)}" x2="${X(ia + 1)}" y2="${Y(prox.bpm)}"/>`;
  pts.forEach((f, i) => {
    if (i === ia) s += `<circle class="g-halo" cx="${X(i)}" cy="${Y(f.bpm)}" r="12"/><circle class="g-agora" cx="${X(i)}" cy="${Y(f.bpm)}" r="6">${tip(f)}</circle>`;
    else s += `<circle class="g-pt" cx="${X(i)}" cy="${Y(f.bpm)}" r="4.5">${tip(f)}</circle>`;
    s += `<text class="g-lbl" x="${X(i)}" y="${h - 8}" text-anchor="middle">${n0 + i}</text>`;
  });
  if (prox) s += `<circle class="g-prox g-prox-n" cx="${X(ia + 1)}" cy="${Y(prox.bpm)}" r="6">${tip(prox)}</circle><text class="g-lbl" x="${X(ia + 1)}" y="${h - 8}" text-anchor="middle">IA</text>`;
  return s + "</svg>";
}
/* o gráfico acompanha a largura do contêiner (celular, tablet, PC, rotação da tela, janela redimensionada) */
let _roTraj, _roEl, _roW = 0;
function desenhaTraj(seq, prox, alvo) {
  const el = $("#traj"); if (!el) return;
  const cs = getComputedStyle(el);
  const largura = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const w = Math.max(240, Math.floor(largura));
  _roW = w;
  el.innerHTML = trajetoria(w, w < 480 ? 190 : 230, seq, prox, alvo);
  if (window.ResizeObserver && _roEl !== el) {
    _roTraj?.disconnect(); _roEl = el;
    _roTraj = new ResizeObserver(() => {
      const c = getComputedStyle(el), l = Math.floor(el.clientWidth - parseFloat(c.paddingLeft) - parseFloat(c.paddingRight));
      if (el.isConnected && Math.abs(Math.max(240, l) - _roW) > 1) S.redesenha?.();
    });
    _roTraj.observe(el);
  }
}
const legenda = alvo => `<div class="legenda"><span><i></i>Tocadas</span><span><i class="agora"></i>Agora</span><span><i class="ia"></i>Sugerida pela IA</span>
  ${alvo ? '<span><i class="alvo"></i>BPM alvo</span>' : ""}<span><i class="faixa"></i>Faixa de ±5%</span></div>`;
let _rz; window.addEventListener("resize", () => { clearTimeout(_rz); _rz = setTimeout(() => S.redesenha?.(), 120); });

/* ---------- Tela 1: Início ---------- */
async function telaInicio(msg, exemplos) {
  pararReproducao(); abas("buscar"); S.sid = null; S.dj = null; S.res = null; S.salvo = false;
  let recentes = [];
  try { recentes = (await api("GET", "/api/recent")).buscas; } catch {}
  const sugestoes = exemplos?.length ? exemplos : (recentes.length ? recentes : ["estudar à noite", "treino", "festa", "jantar romântico"]);
  app.innerHTML = `
    <div class="hero"><h1>Qual é a <span class="vibe">vibe</span> do seu momento?</h1>
      <p>Descreva o clima. A IA escolhe por onde começar e conduz o BPM de uma faixa à outra.</p></div>
    <form id="f-busca">
      <textarea id="vibe" placeholder="Ex.: música calma para estudar à noite" aria-label="Descreva a vibe">${esc(S.busca)}</textarea>
      <button class="btn btn-pri">${ic("search")} Buscar faixas</button>
    </form>
    ${msg ? `<div class="aviso">${esc(msg)}</div>` : ""}
    <div class="exemplos"><div class="mudo">${exemplos?.length ? "Experimente:" : recentes.length ? "Buscas recentes:" : "Ideias para começar:"}</div>
      <div class="chips">${sugestoes.map(c => `<button class="chip" data-v="${esc(c)}">${esc(c)}</button>`).join("")}</div></div>
    <section class="painel demo"><div class="ph">${ic("chart")} Como a IA conduz o set</div>
      <div id="traj"></div><div style="padding:0 16px 8px">${legenda(true)}</div>
      <p class="mudo pb" style="padding-top:4px">Defina um BPM alvo e ela monta a subida faixa a faixa, mantendo BPM dentro de ±5% e chaves compatíveis a cada troca.</p></section>
    <div class="rodape-nota">MVP acadêmico: faixas fictícias e reprodução simulada, sem áudio.</div>`;
  const demo = [88, 93, 96, 99, 102, 110, 114].map((b, i) => ({ bpm: b, titulo: "Faixa " + (i + 1) }));
  S.redesenha = () => desenhaTraj(demo, { bpm: 117, titulo: "Sugestão da IA" }, 128);
  S.redesenha();
  $("#f-busca").onsubmit = e => { e.preventDefault(); buscar($("#vibe").value); };
  $("#vibe").onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); buscar($("#vibe").value); } };
  app.querySelectorAll(".chip").forEach(b => b.onclick = () => buscar(b.dataset.v));
}

async function buscar(texto) {
  if (!texto.trim()) { $("#vibe")?.focus(); return; }
  S.busca = texto;
  abas(null);                                                       // estado Buscando
  app.innerHTML = `<div class="centro-tela"><div class="logo">${LOGO} SoulsBPM</div>
    <div class="indet"><i></i></div><div class="mudo">Interpretando a vibe…</div></div>`;
  try {
    const [r] = await Promise.all([api("POST", "/api/search", { text: texto }), new Promise(ok => setTimeout(ok, 450))]);
    if (r.interpretacao?.tecnico) { setTecnico(true, false); }
    S.sid = r.session_id;
    if (r.estado === "inicio") return telaInicio(r.mensagem, r.exemplos);       // D1: vibe pouco clara
    if (r.estado === "sem_resultados") return telaSemResultados(r);             // D4
    telaResultados(r);
  } catch (e) {
    abas("buscar"); app.innerHTML = erroHtml(e.message) + `<button class="btn btn-pri" id="erro-v" style="align-self:flex-start">Voltar</button>`;
    $("#erro-v").onclick = () => telaInicio();
  }
}

/* ---------- Sem resultados ---------- */
function telaSemResultados() {
  abas("buscar");
  app.innerHTML = topbar("Início") + `<div class="centro-tela"><div class="circ">${ic("search")}</div>
    <h2 class="titulo-p" style="font-size:34px">Nenhuma faixa para essa vibe</h2>
    <div class="mudo" style="max-width:34ch">Descreva de outro jeito: o clima, a energia ou o gênero que você quer no set.</div>
    <button class="btn btn-pri" id="nova" style="margin-top:8px">Nova busca</button></div>`;
  ligaVoltar(() => telaInicio());
  $("#nova").onclick = () => telaInicio();
}

/* ---------- Resultados: biblioteca ---------- */
function telaResultados(r) {
  abas("buscar"); S.res = r;
  app.innerHTML = topbar("Nova busca") + `
    <div><h2 class="titulo-p">Resultados</h2><p class="mudo" style="margin-top:6px">${esc(r.interpretacao.resumo)}</p></div>
    <section class="painel tabela">
      <div class="th"><span></span><span>Faixa</span><span class="so-tec">BPM</span><span class="so-tec">Chave</span><span class="so-tec">Energia</span><span></span></div>
      ${r.resultados.map((f, i) => `
      <div class="tr"><span class="n">${i + 1}</span>
        <div class="tx">${capa(f, "p")}<div style="min-width:0"><div class="tit">${esc(f.titulo)}</div><div class="art">${esc(f.artista)}</div></div></div>
        <div class="meta so-tec"><span class="bpm-v">${f.bpm}</span>${chave(f.tom)}${energia(f.energia)}</div>
        <div class="acao"><button class="btn btn-pri pequeno" data-id="${f.id}">${ic("disc")} Tocar</button></div>
      </div>`).join("")}
    </section>`;
  ligaVoltar(() => telaInicio());
  app.querySelectorAll("[data-id]").forEach(b => b.onclick = () => entrarDJ(b.dataset.id));
  paraTop();
}
const entrarDJ = id => comSpinner(async () => {
  try {
    const d = await api("POST", `/api/session/${S.sid}/play`, { track_id: id });
    S.origem = { rotulo: "Resultados", fn: () => telaResultados(S.res) }; S.salvo = false;
    telaDJ(d);
  } catch (e) { toast(e.message); }
});

/* ---------- Modo DJ ---------- */
function iniciarReproducao(faixa) {
  pararReproducao();
  const VEL = 15;                        // simulação acelerada (sem áudio)
  S.tocando = { id: faixa.id, dur: faixa.duracao, pos: 0, t: null };
  S.tocando.t = setInterval(() => {
    const t = S.tocando; if (!t) return;
    t.pos = Math.min(t.dur, t.pos + VEL * 0.25);
    const b = $("#barra"), c = $("#tempo-atual");
    if (b) b.style.clipPath = `inset(0 ${100 - 100 * t.pos / t.dur}% 0 0)`;
    if (c) c.textContent = mmss(t.pos);
    if (t.pos >= t.dur) { clearInterval(t.t); $(".eq")?.classList.add("parado"); }
  }, 250);
}
const fracao = () => (S.tocando ? S.tocando.pos / S.tocando.dur : 0);
async function sairDoDJ() {
  if (!(await saidaOk())) return;
  pararReproducao();
  (S.origem ? S.origem.fn : telaInicio)();
}

/* controle de BPM do DJ: a IA conduz o set na direção do BPM alvo */
function painelBpm(d) {
  const a = d.atual, alvo = d.bpm_alvo, dif = alvo == null ? 0 : alvo - a.bpm;
  const nota = alvo == null
    ? "Automático: a IA segue a vibe e o ritmo da faixa atual. Use + e − para conduzir o set."
    : Math.abs(dif) <= 0.03 * alvo
      ? `O set está no alvo. A IA mantém o ritmo perto de ${alvo} BPM.`
      : `A IA conduz o set ${dif > 0 ? "subindo" : "descendo"}: tocando ${a.bpm} BPM, alvo ${alvo} BPM (${dif > 0 ? "+" : "−"}${Math.abs(dif)}).`;
  return `<div class="ctl">
    <div class="ctl-n" aria-live="polite">${alvo ?? a.bpm}</div>
    <div class="ctl-l">${alvo != null ? "BPM alvo" : "BPM atual (automático)"}</div>
    <div class="ctl-btns">
      <button class="btn btn-sec" id="b-bpm-menos" type="button" aria-label="Baixar o BPM alvo em 5" ${alvo != null && alvo <= 50 ? "disabled" : ""}>− 5</button>
      <button class="btn btn-pri" id="b-bpm-mais" type="button" aria-label="Subir o BPM alvo em 5" ${alvo != null && alvo >= 200 ? "disabled" : ""}>+ 5</button>
    </div>
    <p class="ctl-nota">${esc(nota)}</p>
    ${alvo != null ? `<button class="link-sub" id="b-bpm-auto" type="button">Voltar ao automático</button>` : ""}
  </div>`;
}

function telaDJ(d, aviso) {
  abas("buscar", true); S.dj = d;
  const quieto = !!app.querySelector(".dj");           // já estava no Modo DJ: só atualiza, sem reanimar nem rolar
  app.classList.toggle("sem-anim", quieto);
  const a = d.atual, p = d.sugerida, alvo = d.bpm_alvo;
  if (!S.tocando || S.tocando.id !== a.id) iniciarReproducao(a);
  const pos = S.tocando ? S.tocando.pos : 0;
  const rotulo = { combina_bem: "Combina bem", ok: "Compatível", arriscada: "Transição arriscada" };
  const e10 = e => `energia ${Math.round(e * 10)}/10`;
  app.innerHTML = `
    ${topbar(S.origem ? S.origem.rotulo : "Início", "", `<label class="chave" title="Mostra BPM, chave Camelot, energia e % de compatibilidade">
      <input type="checkbox" id="modo-tecnico" ${document.body.classList.contains("tecnico") ? "checked" : ""}><span class="sw"></span>Visão técnica</label>`)}
    ${aviso ? `<div class="aviso">${esc(aviso)}</div>` : ""}
    <div class="dj">
      <section class="painel traj">
        <div class="ph">${ic("chart")} Trajetória do set <span class="fim-ph">${d.sequencia.length} ${d.sequencia.length === 1 ? "faixa" : "faixas"}</span></div>
        <div class="traj-corpo">
          <div><div id="traj"></div><div style="padding:0 16px 14px">${legenda(alvo != null)}</div></div>
          ${painelBpm(d)}
        </div>
      </section>
      <section class="painel deck-now">
        <div class="ph">${ic("disc")} Tocando agora${d.pode_desfazer ? `<button class="desfazer" id="b-desfazer" type="button">${ic("undo")} Desfazer aceite</button>` : ""}</div>
        <div class="pb">
          <div class="deck-id">${capa(a, "", true)}<div class="tx"><div class="tit">${esc(a.titulo)}</div><div class="art">${esc(a.artista)}</div></div></div>
          <div class="stats so-tec"><div class="stat"><span class="bpm-v">${a.bpm}</span><span class="u">BPM</span></div>${chave(a.tom, true)}
            <span class="en-l">${energia(a.energia)} ${e10(a.energia)}</span></div>
          ${onda(a, 100 * pos / a.duracao)}
          <div class="tempos"><span id="tempo-atual">${mmss(pos)}</span><span>${mmss(a.duracao)}</span></div>
        </div>
      </section>
      <section class="painel deck-ia">
        <div class="ph">${ic("sparkle")} Próxima sugerida pela IA</div>
        <div class="pb">${p ? `
          <div class="ia-topo">${capa(p)}<div class="tx" style="flex:1;min-width:0"><div class="tit" style="font-size:22px;font-weight:700">${esc(p.titulo)}</div><div class="art">${esc(p.artista)}</div></div>${anel(p)}</div>
          <span class="selo ${p.classe}">${rotulo[p.classe]}</span>
          <div class="stats so-tec"><div class="stat"><span class="bpm-v">${p.bpm}</span><span class="u">BPM</span></div><span class="delta">${pct(a.bpm, p.bpm)}</span>${chave(p.tom, true)}
            <span class="en-l">${energia(p.energia)} ${e10(p.energia)}</span></div>
          ${p.motivos?.length ? `<div class="motivos so-tec"><div><div class="t">Por que a IA sugeriu</div><ul>${p.motivos.map(m => `<li>${esc(m)}</li>`).join("")}</ul></div>${roda(a.tom, p.tom)}</div>` : ""}
          ${p.arriscada ? `<p class="nota-risco">Não achei faixa com BPM e chave bem próximos; esta é a mais perto disso.</p>` : ""}
          <button class="btn btn-sec troca" id="b-trocar" type="button">${ic("swap")} Trocar sugestão</button>`
          : `<div class="aviso">Acabaram as sugestões para esta vibe. Salve a sequência ou faça uma nova busca.</div>`}
        </div>
      </section>
    </div>
    ${d.dica === "ajustar_vibe" ? `<section class="dica"><strong>Quer ajustar a vibe?</strong>
      <p>Você pulou algumas seguidas. Escolha um atalho:</p>
      <div class="chips"><button class="chip" data-aj="calma">Mais calma</button><button class="chip" data-aj="animada">Mais animada</button>
      <button class="chip" id="b-vibe">Mudar a vibe</button></div></section>` : ""}
    <details class="dev"><summary>Estados e eventos</summary><div>${d.caminho_estados.join(" → ")} · ${d.eventos.join(", ")}</div></details>
    <div class="transporte">
      <button class="btn btn-sec" id="b-pular" type="button">${ic("skip")} Pular</button>
      <button class="btn ${d.curtida ? "btn-pri" : "btn-sec"}" id="b-curtir" type="button" aria-pressed="${!!d.curtida}">${ic("heart")} ${d.curtida ? "Curtida" : "Curtir"}</button>
      <button class="btn btn-sec" id="b-salvar" type="button" aria-label="Salvar sequência" ${d.sequencia.length < 2 ? "disabled title='Aceite uma sugestão primeiro'" : ""}>${ic("save")}<span class="rot-s">Salvar sequência</span></button>
      <button class="btn btn-pri" id="b-aceitar" type="button" ${p ? "" : "disabled"}>${ic("check")} Aceitar</button>
    </div>`;
  S.redesenha = () => desenhaTraj(d.sequencia, p, alvo);
  S.redesenha();
  const chama = (url, body, av) => comSpinner(async () => {
    try { telaDJ(await api("POST", `/api/session/${S.sid}/${url}`, body), av); } catch (e) { toast(e.message); }
  });
  ligaVoltar(sairDoDJ);
  $("#modo-tecnico").onchange = e => setTecnico(e.target.checked);
  $("#b-aceitar").onclick = () => chama("accept");
  $("#b-desfazer")?.addEventListener("click", () => chama("undo-accept"));
  $("#b-bpm-mais").onclick = () => chama("bpm", { delta: 5 });
  $("#b-bpm-menos").onclick = () => chama("bpm", { delta: -5 });
  $("#b-bpm-auto")?.addEventListener("click", () => chama("bpm", { auto: true }));
  $("#b-trocar")?.addEventListener("click", () => chama("skip", { target: "sugestao" }));
  $("#b-pular").onclick = () => chama("skip", { target: "atual", elapsed_fraction: fracao() });
  $("#b-curtir").onclick = async () => {
    try {
      const on = (await api("POST", `/api/session/${S.sid}/like`)).curtida, b = $("#b-curtir");
      b.innerHTML = `${ic("heart")} ${on ? "Curtida" : "Curtir"}`;
      b.classList.toggle("btn-pri", on); b.classList.toggle("btn-sec", !on); b.setAttribute("aria-pressed", String(on));
    } catch (e) { toast(e.message); }
  };
  $("#b-salvar").onclick = () => telaSalvar(d);
  app.querySelectorAll("[data-aj]").forEach(b => b.onclick = () => chama("adjust", { direction: b.dataset.aj }));
  $("#b-vibe")?.addEventListener("click", () => { pararReproducao(); telaInicio(); });
  if (!quieto) paraTop();
}

/* ---------- Salvar sequência ---------- */
function telaSalvar(d) {
  pararReproducao(); abas("buscar", true);
  let tags = d.interpretacao.tags.slice(0, 4);
  const titulo0 = S.busca ? S.busca.charAt(0).toUpperCase() + S.busca.slice(1) : "Minha sequência";
  const desenha = () => {
    $("#tags-box").innerHTML = tags.map((t, i) => `<button type="button" class="chip" data-rm="${i}" title="Remover">${esc(t)}<span class="x">×</span></button>`).join("")
      + `<button type="button" class="chip add" id="add-tag">+ tag</button>`;
    app.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { tags.splice(+b.dataset.rm, 1); desenha(); });
    $("#add-tag").onclick = () => {
      const inp = document.createElement("input");
      inp.type = "text"; inp.className = "tag-in"; inp.placeholder = "nova tag"; inp.maxLength = 20;
      $("#add-tag").replaceWith(inp); inp.focus();
      let feito = false;
      const fim = ok => {
        if (feito) return; feito = true;
        const v = inp.value.trim().toLowerCase();
        if (ok && v && tags.length < 8 && !tags.includes(v)) tags.push(v);
        desenha();
      };
      inp.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); fim(true); } else if (e.key === "Escape") fim(false); };
      inp.onblur = () => fim(true);
    };
  };
  app.innerHTML = topbar("Modo DJ") + `
    <h2 class="titulo-p">Salvar sequência</h2>
    <form id="f-salvar">
      <div class="campo-l">Título da playlist</div>
      <input type="text" id="titulo" value="${esc(titulo0)}" maxlength="80" required>
      <div class="campo-l">Tags de clima</div>
      <div class="chips" id="tags-box"></div>
      <section class="painel lista" style="margin-top:6px">${d.sequencia.map((f, i) => `
        <div class="item"><span class="n" style="width:22px;text-align:center;color:var(--apagado);font:600 18px var(--num)">${i + 1}</span>${capa(f, "m")}
          <div class="tx"><div class="tit">${esc(f.titulo)}</div><div class="art">${esc(f.artista)}</div></div>
          <span class="so-tec" style="display:flex;gap:10px;align-items:center"><span class="bpm-v">${f.bpm}</span>${chave(f.tom)}</span></div>`).join("")}</section>
      <div class="fim"><button class="btn btn-pri cheio">${ic("save")} Salvar</button>
        <button type="button" class="btn btn-sec cheio" id="voltar">Cancelar</button></div>
    </form>`;
  desenha();
  ligaVoltar(() => telaDJ(d));
  $("#voltar").onclick = () => telaDJ(d);
  $("#f-salvar").onsubmit = async e => {
    e.preventDefault();
    try { telaSalva(await api("POST", `/api/session/${S.sid}/save`, { title: $("#titulo").value, tags })); }
    catch (er) { toast(er.message); }
  };
  paraTop();
}

/* ---------- Sequência guardada ---------- */
function telaSalva(r) {
  abas("playlists", true); S.salvo = true;
  const url = location.host + r.link;
  app.innerHTML = `
    <div class="circ ok">${ic("check")}</div><h2 class="titulo-p">Sequência guardada</h2>
    <div class="card-pl" style="max-width:460px"><div class="tit">${esc(r.titulo)}</div>
      <div class="art">${r.faixas ?? S.dj.sequencia.length} faixas · ${r.tags.map(esc).join(", ")}</div></div>
    <div class="link-box" id="url" style="max-width:460px">${esc(url)}</div>
    <button class="btn btn-pri" id="copiar" style="max-width:460px">${ic("copy")} Copiar link</button>
    <div class="fim"><button class="btn btn-sec cheio" id="dj">Voltar ao Modo DJ</button>
      <button class="btn btn-sec cheio" id="abrir">Abrir playlists</button>
      <button class="btn btn-sec cheio" id="nova">Nova busca</button></div>`;
  $("#copiar").onclick = async () => {
    const full = location.origin + r.link;
    try { await navigator.clipboard.writeText(full); } catch { const t = document.createElement("textarea"); t.value = full; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); }
    $("#copiar").innerHTML = `${ic("check")} Link copiado`;
  };
  $("#dj").onclick = () => telaDJ(S.dj);
  $("#abrir").onclick = telaPlaylists;
  $("#nova").onclick = () => { S.busca = ""; telaInicio(); };
  paraTop();
}

/* ---------- Playlists ---------- */
async function telaPlaylists() {
  pararReproducao(); abas("playlists");
  app.innerHTML = `<h1 class="titulo-p">Playlists</h1><p class="mudo">Carregando…</p>`;
  try {
    const { playlists } = await api("GET", "/api/playlists");
    app.innerHTML = `<h1 class="titulo-p">Playlists</h1>` + (playlists.length
      ? `<section class="painel lista">${playlists.map(p => `<button class="item clic" data-pl="${p.id}"><div class="capa p" style="--k:#7a66ff;--a:${90 + semente(p.id) % 180}deg">${ic("list")}</div><div class="tx">
          <div class="tit">${esc(p.title)}</div><div class="art">${p.faixas} faixas</div><div class="tags-i">${p.tags.map(esc).join(", ")}</div></div>${ic("chev", "ic seta")}</button>`).join("")}</section>`
      : `<div class="vazio">${userId() ? "Nenhuma playlist ainda. Faça uma busca e salve uma sequência." : "Você não permitiu que eu lembre, então nada é guardado."}</div>`)
      + `<div class="fim"><button class="btn btn-pri cheio" id="nova">${ic("plus")} Nova busca</button></div>`;
    app.querySelectorAll("[data-pl]").forEach(b => b.onclick = () => telaPlaylist(b.dataset.pl, true));
    $("#nova").onclick = () => { S.busca = ""; telaInicio(); };
  } catch (e) { app.innerHTML = erroHtml(e.message); }
}
async function telaPlaylist(pid, minha) {
  pararReproducao(); abas("playlists");
  try {
    const p = await api("GET", "/api/playlists/" + pid);
    const url = location.origin + "/p/" + pid;
    app.innerHTML = (minha ? topbar("Playlists") : topbar("Início")) + `<h2 class="titulo-p">${esc(p.title)}</h2>
      <div class="chips">${p.tags.map(t => `<span class="chip mini">${esc(t)}</span>`).join("")}</div>
      <section class="painel tabela">
        <div class="th"><span></span><span>Faixa</span><span class="so-tec">BPM</span><span class="so-tec">Chave</span><span class="so-tec">Energia</span><span></span></div>
        ${p.faixas.map((f, i) => `<div class="tr"><span class="n">${i + 1}</span>
          <div class="tx">${capa(f, "p")}<div style="min-width:0"><div class="tit">${esc(f.titulo)}</div><div class="art">${esc(f.artista)}</div></div></div>
          <div class="meta so-tec"><span class="bpm-v">${f.bpm}</span>${chave(f.tom)}${energia(f.energia)}</div><div class="acao"></div></div>`).join("")}
      </section>
      <div class="fim">
        ${minha ? `<button class="btn btn-pri cheio" id="cont">Continuar no Modo DJ</button>` : `<button class="btn btn-pri cheio" id="montar">Montar a minha</button>`}
        <button class="btn btn-sec cheio" id="copiar">${ic("copy")} Copiar link</button></div>`;
    ligaVoltar(minha ? telaPlaylists : irInicio);
    $("#montar")?.addEventListener("click", irInicio);
    $("#copiar").onclick = async () => { try { await navigator.clipboard.writeText(url); } catch {} $("#copiar").innerHTML = `${ic("check")} Link copiado`; };
    $("#cont")?.addEventListener("click", async () => {
      try {
        const d = await api("POST", `/api/playlists/${pid}/continue`);
        S.sid = d.session_id; S.busca = p.title; S.salvo = true;
        S.origem = { rotulo: "Playlist", fn: () => telaPlaylist(pid, true) };
        telaDJ(d);
      } catch (e) { toast(e.message); }
    });
    paraTop();
  } catch (e) { app.innerHTML = topbar("Início") + erroHtml(e.message); ligaVoltar(irInicio); }
}
/* link compartilhado (/p/...): sai dele e volta à página inicial */
function irInicio() { if (location.pathname !== "/") history.pushState(null, "", "/"); telaInicio(); }

/* ---------- Privacidade (LGPD) ---------- */
async function abrirPrivacidade() {
  const dlg = $("#dlg-priv");
  const ligado = guarda.get(K.consent) === "sim";
  $("#priv-estado").textContent = ligado ? "O SoulsBPM está lembrando das suas buscas e escolhas neste navegador." : "Você não permitiu que eu lembre. Nada é guardado.";
  let html = "Ainda não aprendi nada sobre você.";
  if (ligado) {
    try {
      const p = await api("GET", "/api/profile");
      const g = a => a.map(([n, v]) => `${esc(n)} (${v > 0 ? "+" : ""}${v})`).join(", ") || "—";
      if (p.total_pesos) html = `<div><strong>Gêneros que você curte:</strong> ${g(p.generos_preferidos || [])}</div>
        <div style="margin-top:6px"><strong>Gêneros que você evita:</strong> ${g(p.generos_evitados || [])}</div>`;
    } catch {}
  }
  $("#priv-perfil").innerHTML = html;
  dlg.showModal();
}
$("#priv-fechar").onclick = () => fechaDlg($("#dlg-priv"));
$("#dlg-priv").addEventListener("cancel", e => { e.preventDefault(); fechaDlg($("#dlg-priv")); });
$("#dlg-priv").addEventListener("click", e => { if (e.target === e.currentTarget) fechaDlg(e.currentTarget); });
$("#priv-zerar").onclick = async () => { await api("DELETE", "/api/profile"); abrirPrivacidade(); };
$("#priv-apagar").onclick = async () => { await api("DELETE", "/api/history"); abrirPrivacidade(); if (!S.sid) telaInicio(); };
$("#tab-buscar").onclick = async () => { if (!(await saidaOk())) return; pararReproducao(); irInicio(); };
$("#tab-playlists").onclick = async () => { if (!(await saidaOk())) return; if (location.pathname !== "/") history.pushState(null, "", "/"); telaPlaylists(); };
$("#tab-priv").onclick = abrirPrivacidade;
$("#consent-sim").onclick = () => { guarda.set(K.consent, "sim"); $("#consent").hidden = true; telaInicio(); };
$("#consent-nao").onclick = () => { guarda.set(K.consent, "nao"); $("#consent").hidden = true; };
window.addEventListener("popstate", iniciar);

function iniciar() {
  const m = location.pathname.match(/^\/p\/([\w-]+)/);
  if (guarda.get(K.consent) === null && !m) $("#consent").hidden = false;
  setTecnico(guarda.get(K.tec) !== "0", false);        // DJ: BPM, chave e energia visíveis por padrão
  m ? telaPlaylist(m[1], false) : telaInicio();
}
iniciar();

/* ---------- menu lateral ----------
   Fechado por padrão (só o botão ☰ no canto). Abre como painel sobre o conteúdo; fecha ao escolher uma opção, tocar fora ou Esc. */
(() => {
  const shell = $("#shell"), nav = $("#tabs"), btn = $("#menu-toggle"), abrir = $("#menu-abrir");
  const aberto = () => shell.classList.contains("menu-aberto");
  function aplicar() {
    const a = aberto();
    btn.setAttribute("aria-expanded", String(a)); abrir.setAttribute("aria-expanded", String(a));
    nav.toggleAttribute("inert", !a);          // fechado: fora do foco do teclado e de leitores de tela
  }
  function fechar(voltaFoco) { shell.classList.remove("menu-aberto"); aplicar(); if (voltaFoco) abrir.focus(); }
  abrir.onclick = () => { shell.classList.add("menu-aberto"); aplicar(); requestAnimationFrame(() => ($(".tab.ativa", nav) || $("#tab-buscar")).focus()); };
  btn.onclick = () => fechar(true);
  $("#menu-veu").onclick = () => fechar(false);
  nav.addEventListener("click", e => { if (e.target.closest(".tab")) fechar(false); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && aberto()) fechar(true); });
  aplicar();
})();
