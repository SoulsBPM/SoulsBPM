/* SoulsBPM – página de login (/login). Fala com /api/auth/* e volta para o app ("/") ao terminar. */
const $ = s => document.querySelector(s);
const K = { uid: "souls_uid", consent: "souls_consent", tema: "souls_tema", visitante: "souls_visitante" };
const guarda = {
  get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
  del: k => { try { localStorage.removeItem(k); } catch {} },
};
const params = new URLSearchParams(location.search);
/* só volta para caminhos do próprio site (nada de //outro-site ou http://...) */
const destino = (n => (n && /^\/(?!\/)[\w\-\/]*$/.test(n) ? n : "/"))(params.get("next"));
let modo = "entrar", exigir = false;

/* tema claro/escuro */
const SUN = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>';
const MOON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>';
function pintaTema() {
  const claro = document.documentElement.dataset.tema === "claro";
  const b = $("#lg-tema");
  b.innerHTML = (claro ? MOON : SUN) + `<span class="tema-l">${claro ? "Modo escuro" : "Modo claro"}</span>`;
  b.setAttribute("aria-label", `Mudar para o modo ${claro ? "escuro" : "claro"}`);
}
$("#lg-tema").onclick = () => {
  const t = document.documentElement.dataset.tema === "claro" ? "escuro" : "claro";
  document.documentElement.dataset.tema = t; guarda.set(K.tema, t);
  document.querySelector('meta[name="theme-color"]').setAttribute("content", t === "claro" ? "#f4f3fa" : "#0e0d1c");
  pintaTema();
};
pintaTema();

/* entrar x criar conta (os campos digitados são mantidos) */
function aplicaModo(m) {
  modo = m;
  const novo = m === "criar";
  document.querySelectorAll(".lg-abas button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.m === m)));
  $("#lg-titulo").textContent = novo ? "Criar conta" : "Entrar";
  $("#lg-sub").textContent = novo
    ? "Suas playlists e o que o app aprende sobre o seu gosto ficam guardados na conta."
    : "Entre para ver suas playlists e seu gosto musical em qualquer aparelho.";
  $("#lg-ok").textContent = novo ? "Criar conta" : "Entrar";
  $("#lg-senha").autocomplete = novo ? "new-password" : "current-password";
  $("#lg-dica").hidden = !novo;
  $("#lg-erro").replaceChildren();
  const temAnonimo = guarda.get(K.consent) === "sim" && guarda.get(K.uid);
  $("#lg-nota").textContent = novo && temAnonimo
    ? "O que você já fez neste navegador vai junto para a conta nova."
    : "Não pedimos e-mail. Guardamos só o usuário, uma versão embaralhada da senha e o que você curte.";
}
document.querySelectorAll(".lg-abas button").forEach(b => b.onclick = () => aplicaModo(b.dataset.m));

/* mostrar / esconder a senha */
$("#lg-ver").onclick = () => {
  const i = $("#lg-senha"), ver = i.type === "password";
  i.type = ver ? "text" : "password";
  $("#lg-ver").textContent = ver ? "Esconder" : "Mostrar";
  $("#lg-ver").setAttribute("aria-pressed", String(ver));
  $("#lg-ver").setAttribute("aria-label", ver ? "Esconder a senha" : "Mostrar a senha");
};

function erro(texto) {
  const d = document.createElement("div");
  d.className = "aviso erro"; d.textContent = texto;
  $("#lg-erro").replaceChildren(d);
}
/* no celular, o teclado cobre parte da tela: leva o campo focado para a área visível */
document.querySelectorAll("#f-login input").forEach(i =>
  i.addEventListener("focus", () => setTimeout(() => i.scrollIntoView({ block: "center", behavior: "smooth" }), 250)));
$("#lg-nome").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); $("#lg-senha").focus(); } });

$("#f-login").onsubmit = async e => {
  e.preventDefault();
  const nome = $("#lg-nome").value.trim(), senha = $("#lg-senha").value;
  if (!nome || !senha) return erro("Preencha o usuário e a senha.");
  const novo = modo === "criar", ok = $("#lg-ok");
  ok.disabled = true; ok.setAttribute("aria-busy", "true");
  try {
    const corpo = { nome, senha };
    if (novo && guarda.get(K.consent) === "sim" && guarda.get(K.uid)) corpo.user_id = guarda.get(K.uid);   // leva o histórico anônimo
    const r = await fetch(novo ? "/api/auth/register" : "/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.erro || "Não deu certo. Tente de novo.");
    guarda.del(K.uid); guarda.del(K.visitante); guarda.set(K.consent, "sim");
    location.replace(destino);
  } catch (err) {
    erro(err instanceof TypeError ? "Sem conexão com o servidor. Tente de novo." : err.message);
    ok.disabled = false; ok.removeAttribute("aria-busy");
  }
};

$("#lg-visitante").onclick = () => { guarda.set(K.visitante, "1"); location.replace(destino); };

/* se já está logado, não mostra o login; se o login é obrigatório, esconde o "sem conta" */
(async () => {
  try {
    const me = await (await fetch("/api/auth/me")).json();
    if (me.logado) return location.replace(destino);
    exigir = !!me.exigir_login;
  } catch {}
  if (exigir) { $("#lg-visitante").hidden = true; $("#lg-ou").hidden = true; }
  if (params.get("expirou")) erro("Sua sessão acabou. Entre de novo.");
})();
aplicaModo("entrar");
if (matchMedia("(hover:hover)").matches) $("#lg-nome").focus();     // no celular não abre o teclado sozinho
