"""Envio de e-mail (recuperação de senha). Sem biblioteca extra: o Brevo é chamado por HTTPS.

Por que API e não SMTP: o plano gratuito do Render bloqueia as portas de SMTP, então o envio precisa ir por HTTPS.
Configuração (variáveis de ambiente):
  BREVO_API_KEY         chave da API do Brevo
  EMAIL_REMETENTE       e-mail remetente já validado no Brevo
  EMAIL_REMETENTE_NOME  nome que aparece como remetente (padrão: SoulsBPM)
  EMAIL_MODO=console    só para testar no seu computador: escreve o link no terminal em vez de enviar
"""
import html
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger("soulsbpm.emails")


class EmailErro(RuntimeError):
    pass


def _post_json(url, cabecalhos, corpo, timeout):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), headers=cabecalhos, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        try:                                              # o Brevo explica o motivo no corpo (ex.: remetente não validado)
            detalhe = json.loads(e.read().decode("utf-8", "replace")).get("message", "")
        except Exception:
            detalhe = ""
        raise EmailErro(f"o Brevo respondeu HTTP {e.code}" + (f": {str(detalhe)[:200]}" if detalhe else ""))
    except (urllib.error.URLError, TimeoutError) as e:
        raise EmailErro(f"falha de rede: {type(e).__name__}")


class Brevo:
    URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, chave, remetente, nome="SoulsBPM", http=_post_json, timeout=15):
        self.chave, self.remetente, self.nome, self.http, self.timeout = chave, remetente, nome, http, timeout

    def enviar(self, para, nome_para, assunto, html_corpo, texto):
        status = self.http(self.URL, {"api-key": self.chave, "Content-Type": "application/json", "Accept": "application/json"},
                           {"sender": {"name": self.nome, "email": self.remetente},
                            "to": [{"email": para, "name": nome_para}],
                            "subject": assunto, "htmlContent": html_corpo, "textContent": texto}, self.timeout)
        if status not in (200, 201, 202):
            raise EmailErro(f"o Brevo respondeu HTTP {status}")


class Console:
    """Só para desenvolvimento: mostra o e-mail no terminal. Não use em produção (o link vai para o log)."""

    def enviar(self, para, nome_para, assunto, html_corpo, texto):
        log.warning("E-MAIL (modo console) para %s | %s\n%s", para, assunto, texto)


def do_ambiente(env):
    """Brevo se as variáveis estiverem preenchidas; console se EMAIL_MODO=console; senão None (recuperação desligada)."""
    if (env.get("EMAIL_MODO") or "").lower() == "console":
        return Console()
    chave, remetente = (env.get("BREVO_API_KEY") or "").strip(), (env.get("EMAIL_REMETENTE") or "").strip()
    if chave and remetente:
        return Brevo(chave, remetente, (env.get("EMAIL_REMETENTE_NOME") or "SoulsBPM").strip() or "SoulsBPM")
    return None


def recuperacao(nome, link):
    """(assunto, html, texto) do e-mail de redefinição de senha."""
    n, l = html.escape(nome), html.escape(link, quote=True)
    assunto = "Redefinir sua senha do SoulsBPM"
    corpo = (f'<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:auto;color:#1b1a33">'
             f'<h2 style="margin:0 0 12px">Olá, {n}</h2>'
             f"<p>Recebemos um pedido para redefinir a senha da sua conta no SoulsBPM.</p>"
             f'<p><a href="{l}" style="display:inline-block;background:#7a66ff;color:#fff;text-decoration:none;'
             f'padding:12px 20px;border-radius:10px;font-weight:bold">Escolher nova senha</a></p>'
             f"<p>O link vale por 1 hora e só funciona uma vez. Se o botão não abrir, copie este endereço no navegador:<br>{l}</p>"
             f'<p style="color:#6b6a85">Se não foi você, ignore este e-mail: sua senha continua a mesma.</p></div>')
    texto = (f"Olá, {nome}.\n\nRecebemos um pedido para redefinir a senha da sua conta no SoulsBPM.\n"
             f"Abra o link para escolher uma nova senha (vale por 1 hora e só funciona uma vez):\n{link}\n\n"
             "Se não foi você, ignore este e-mail: sua senha continua a mesma.\n")
    return assunto, corpo, texto
