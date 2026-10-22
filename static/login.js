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

/* telas da mesma página: entrar, criar conta, esqueci a senha e nova senha (link do e-mail) */
const TELAS = {
  entrar: { titulo: "Entrar", sub: "Entre para ver suas playlists e seu gosto musical em qualquer aparelho.", ok: "Entrar",
            campos: ["nome", "senha"], abas: true, visitante: true },
  criar: { titulo: "Criar conta", sub: "Suas playlists e o que o app aprende sobre o seu gosto ficam guardados na conta.", ok: "Criar conta",
           campos: ["nome", "email", "senha"], abas: true, visitante: true },
  esqueci: { titulo: "Esqueci minha senha", sub: "Digite o e-mail da sua conta e enviaremos um link para escolher uma nova senha.", ok: "Enviar link",
             campos: ["email"], voltar: true },
  redefinir: { titulo: "Nova senha", sub: "Escolha uma nova senha para a sua conta.", ok: "Salvar nova senha", campos: ["senha"] },
};
let recuperacao = false, tokenReset = null;

function aplicaModo(m, manterMensagem = false) {
  modo = m;
  const t = TELAS[m], novo = m === "criar";
  document.querySelectorAll(".lg-abas button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.m === m)));
  $("#lg-titulo").textContent = t.titulo;
  $("#lg-sub").textContent = t.sub;
  $("#lg-ok").textContent = t.ok;
  $("#lg-abas").hidden = !t.abas;
  $("#lg-voltar").hidden = !t.voltar;
  $("#lg-ou").hidden = $("#lg-visitante").hidden = !t.visitante || exigir;
  $("#g-nome").hidden = !t.campos.includes("nome");
  $("#g-email").hidden = !t.campos.includes("email");
  $("#g-senha").hidden = !t.campos.includes("senha");
  $("#f-login").hidden = false;
  $("#l-nome").textContent = novo ? "Nome" : "Usuário ou e-mail";
  $("#lg-nome").autocomplete = novo ? "name" : "username";
  $("#lg-nome").maxLength = novo ? 30 : 254;
  $("#d-nome").hidden = !novo;
  $("#d-email").hidden = !novo;
  $("#l-senha").textContent = m === "redefinir" ? "Nova senha" : "Senha";
  $("#lg-senha").autocomplete = (novo || m === "redefinir") ? "new-password" : "current-password";
  $("#lg-dica").hidden = !(novo || m === "redefinir");
  $("#lg-forca").hidden = !(novo || m === "redefinir");
  $("#lg-esqueci").hidden = !(m === "entrar" && recuperacao);
  $("#lg-erro").replaceChildren();
  if (!manterMensagem) $("#lg-ok-msg").replaceChildren();
  const temAnonimo = guarda.get(K.consent) === "sim" && guarda.get(K.uid);
  $("#lg-nota").textContent = novo && temAnonimo
    ? "O que você já fez neste navegador vai junto para a conta nova."
    : (novo ? "Guardamos o seu nome, o e-mail, uma versão embaralhada da senha e o que você curte." : "");
  pintaForca();
}
document.querySelectorAll(".lg-abas button").forEach(b => b.onclick = () => aplicaModo(b.dataset.m));
$("#lg-esqueci").onclick = () => { aplicaModo("esqueci"); $("#lg-email").value ||= $("#lg-nome").value.includes("@") ? $("#lg-nome").value : ""; $("#lg-email").focus(); };
$("#lg-voltar").onclick = () => aplicaModo("entrar");

/* força da senha: só orienta, quem manda é o mínimo de 8 caracteres */
function forca(s) {
  if (s.length < 8) return { n: 0, t: s ? "Muito curta" : "" };
  const pts = (s.length >= 12) + (/[a-z]/.test(s) && /[A-Z]/.test(s)) + (/\d/.test(s) || /[^\w\s]/.test(s));
  return pts >= 3 ? { n: 3, t: "Forte" } : pts === 2 ? { n: 2, t: "Boa" } : { n: 1, t: "Razoável" };
}
function pintaForca() {
  const f = forca($("#lg-senha").value);
  $("#lg-forca").dataset.n = f.n;
  $("#lg-forca-t").textContent = f.t;
}
$("#lg-senha").addEventListener("input", pintaForca);

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
function sucesso(texto) {
  const d = document.createElement("div");
  d.className = "aviso ok"; d.textContent = texto;
  $("#lg-ok-msg").replaceChildren(d);
}
/* no celular, o teclado cobre parte da tela: leva o campo focado para a área visível */
document.querySelectorAll("#f-login input").forEach(i =>
  i.addEventListener("focus", () => setTimeout(() => i.scrollIntoView({ block: "center", behavior: "smooth" }), 250)));
$("#lg-nome").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); ($("#g-email").hidden ? $("#lg-senha") : $("#lg-email")).focus(); } });
$("#lg-email").addEventListener("keydown", e => { if (e.key === "Enter" && modo === "criar") { e.preventDefault(); $("#lg-senha").focus(); } });

const EMAIL_OK = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;
async function chamar(url, corpo) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.erro || "Não deu certo. Tente de novo.");
  return j;
}

$("#f-login").onsubmit = async e => {
  e.preventDefault();
  const nome = $("#lg-nome").value.trim(), email = $("#lg-email").value.trim(), senha = $("#lg-senha").value, ok = $("#lg-ok");
  if (modo === "entrar" && (!nome || !senha)) return erro("Preencha o usuário (ou e-mail) e a senha.");
  if (modo === "criar" && (!nome || !email || !senha)) return erro("Preencha o nome, o e-mail e a senha.");
  if ((modo === "criar" || modo === "esqueci") && !EMAIL_OK.test(email)) return erro("Digite um e-mail válido, por exemplo nome@email.com.");
  if (modo === "redefinir" && !senha) return erro("Digite a nova senha.");
  ok.disabled = true; ok.setAttribute("aria-busy", "true");
  try {
    if (modo === "esqueci") {
      const j = await chamar("/api/auth/forgot", { email });
      $("#f-login").hidden = true; $("#lg-voltar").hidden = false; $("#lg-sub").textContent = "";
      sucesso(j.mensagem);
      return;
    }
    if (modo === "redefinir") {
      await chamar("/api/auth/reset", { token: tokenReset, senha });
      tokenReset = null; $("#lg-senha").value = "";
      history.replaceState(null, "", "/login");
      aplicaModo("entrar", true);
      sucesso("Senha alterada. Entre com a nova senha.");
      $("#lg-nome").focus();
      return;
    }
    const novo = modo === "criar";
    const corpo = novo ? { nome, email, senha } : { nome, senha };
    if (novo && guarda.get(K.consent) === "sim" && guarda.get(K.uid)) corpo.user_id = guarda.get(K.uid);   // leva o histórico anônimo
    await chamar(novo ? "/api/auth/register" : "/api/auth/login", corpo);
    guarda.del(K.uid); guarda.del(K.visitante); guarda.set(K.consent, "sim");
    location.replace(destino);
  } catch (err) {
    erro(err instanceof TypeError ? "Sem conexão com o servidor. Tente de novo." : err.message);
  } finally {
    ok.disabled = false; ok.removeAttribute("aria-busy");
  }
};

$("#lg-visitante").onclick = () => { guarda.set(K.visitante, "1"); location.replace(destino); };

/* se já está logado, não mostra o login (menos no link de redefinição); se o login é obrigatório, esconde o "sem conta" */
(async () => {
  const noReset = location.pathname === "/redefinir";
  try {
    const me = await (await fetch("/api/auth/me")).json();
    if (me.logado && !noReset) return location.replace(destino);
    exigir = !!me.exigir_login;
    recuperacao = !!me.recuperacao;
  } catch {}
  if (noReset) {
    tokenReset = params.get("token");
    history.replaceState(null, "", "/redefinir");                       // tira o token do endereço
    if (!tokenReset) { aplicaModo("esqueci"); return erro("Esse link está incompleto. Peça um novo abaixo."); }
    aplicaModo("redefinir");
    $("#lg-senha").focus();
    return;
  }
  aplicaModo("entrar");
  if (params.get("expirou")) erro("Sua sessão acabou. Entre de novo.");
})();
aplicaModo("entrar");
if (matchMedia("(hover:hover)").matches && location.pathname !== "/redefinir") $("#lg-nome").focus();     // no celular não abre o teclado sozinho
