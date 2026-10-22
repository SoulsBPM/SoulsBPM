"""Contas de usuário: cadastro (nome, e-mail e senha), login, recuperação de senha e sessões (cookie).

Senhas nunca são guardadas: só um hash scrypt com sal aleatório. O cookie de sessão é um token aleatório;
no banco fica apenas o hash SHA-256 dele (se o banco vazar, os tokens não servem para entrar).
"""
import hashlib
import hmac
import re
import secrets
import time

from .engine import Erro

COOKIE = "souls_sess"
SESSAO_DIAS = 30
NOME_VALIDO = re.compile(r"^(?! )[\w .'-]{3,30}(?<! )$")           # letras (com acento), números, espaço, . _ - '
EMAIL_VALIDO = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
EMAIL_MAX = 254
SENHA_MIN, SENHA_MAX = 8, 128
RESET_VALIDADE = 3600           # o link de redefinição vale 1 hora e só funciona uma vez
RESET_MAX_POR_HORA = 3          # pedidos por conta (contra quem enche a caixa de e-mail de alguém)
_N, _R, _P = 2 ** 14, 8, 1


def _hash(senha, sal):
    return hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=32)


def _sha(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Contas:
    def __init__(self, store, agora=time.time):
        self.store, self.agora = store, agora
        self._sal_falso = secrets.token_bytes(16)       # para gastar o mesmo tempo quando o usuário não existe

    # -- cadastro e login --------------------------------------------------
    @staticmethod
    def normaliza_email(email):
        e = email.strip().lower() if isinstance(email, str) else ""
        if len(e) > EMAIL_MAX or not EMAIL_VALIDO.match(e):
            raise Erro("Digite um e-mail válido, por exemplo nome@email.com.")
        return e

    @staticmethod
    def _valida_senha(senha):
        if not isinstance(senha, str) or not (SENHA_MIN <= len(senha) <= SENHA_MAX):
            raise Erro(f"A senha precisa ter de {SENHA_MIN} a {SENHA_MAX} caracteres.")

    @staticmethod
    def _novo_hash(senha):
        sal = secrets.token_bytes(16)
        return f"scrypt${sal.hex()}${_hash(senha, sal).hex()}"

    def criar(self, nome, senha, id_existente=None, email=None, email_obrigatorio=False):
        nome = " ".join(nome.split()) if isinstance(nome, str) else ""
        if not NOME_VALIDO.match(nome):
            raise Erro("O nome precisa ter de 3 a 30 caracteres: letras, números, espaço, ponto, hífen ou _.")
        if email is None and not email_obrigatorio:
            email = None
        else:
            email = self.normaliza_email(email)
        self._valida_senha(senha)
        uid = id_existente if id_existente and not self.eh_conta(id_existente) else "u_" + secrets.token_hex(16)
        if email and self.store._run("SELECT 1 FROM users WHERE email=?", (email,), fetch=True):
            raise Erro("Esse e-mail já tem cadastro. Entre na sua conta ou recupere a senha.", 409)
        if self.store._run("SELECT 1 FROM users WHERE lower(nome)=lower(?)", (nome,), fetch=True):     # "João" e "JOÃO" são o mesmo nome
            raise Erro("Esse nome já está em uso. Escolha outro ou entre na sua conta.", 409)
        try:
            self.store._run("INSERT INTO users(id,nome,hash,created_at,email) VALUES(?,?,?,?,?)",
                            (uid, nome, self._novo_hash(senha), self.agora(), email))
        except Exception as e:                         # UNIQUE(nome) ou UNIQUE(email) já existe
            if "UNIQUE" in str(e).upper() or "DUPLICATE" in str(e).upper():
                if email and ("users.email" in str(e).lower() or "users_email" in str(e).lower()):
                    raise Erro("Esse e-mail já tem cadastro. Entre na sua conta ou recupere a senha.", 409)
                raise Erro("Esse nome já está em uso. Escolha outro ou entre na sua conta.", 409)
            raise
        return {"id": uid, "nome": nome}

    def entrar(self, login, senha):
        """`login` pode ser o nome de usuário ou o e-mail."""
        login = login.strip() if isinstance(login, str) else ""
        if not login:
            rows = []
        elif "@" in login:
            rows = self.store._run("SELECT id,nome,hash FROM users WHERE email=?", (login.lower(),), fetch=True)
        else:
            rows = self.store._run("SELECT id,nome,hash FROM users WHERE lower(nome)=lower(?)", (login,), fetch=True)
        if not isinstance(senha, str) or len(senha) > SENHA_MAX:
            senha = ""
        if rows:
            _, sal_hex, h_hex = rows[0][2].split("$")
            ok = hmac.compare_digest(_hash(senha, bytes.fromhex(sal_hex)), bytes.fromhex(h_hex))
        else:
            _hash(senha, self._sal_falso)
            ok = False
        if not ok:
            raise Erro("Usuário, e-mail ou senha incorretos.", 401)
        return {"id": rows[0][0], "nome": rows[0][1]}

    def email_da_conta(self, uid):
        rows = self.store._run("SELECT email FROM users WHERE id=?", (uid,), fetch=True)
        return rows[0][0] if rows else None

    @staticmethod
    def mascara_email(email):
        """maria.silva@gmail.com -> m***@gmail.com (a tela mostra sem expor o endereço inteiro)."""
        if not email or "@" not in email:
            return None
        local, dominio = email.split("@", 1)
        return f"{local[:1]}***@{dominio}"

    def definir_email(self, uid, email, senha):
        """Para contas antigas, criadas quando o e-mail não era pedido. Exige a senha atual."""
        email = self.normaliza_email(email)
        rows = self.store._run("SELECT hash FROM users WHERE id=?", (uid,), fetch=True)
        if not rows:
            raise Erro("Conta não encontrada.", 404)
        _, sal_hex, h_hex = rows[0][0].split("$")
        if not isinstance(senha, str) or len(senha) > SENHA_MAX or \
                not hmac.compare_digest(_hash(senha, bytes.fromhex(sal_hex)), bytes.fromhex(h_hex)):
            raise Erro("Senha incorreta.", 401)
        dono = self.store._run("SELECT id FROM users WHERE email=?", (email,), fetch=True)
        if dono and dono[0][0] != uid:
            raise Erro("Esse e-mail já está em uso em outra conta.", 409)
        self.store._run("UPDATE users SET email=? WHERE id=?", (email, uid))
        return email

    # -- recuperação de senha ----------------------------------------------
    def pedir_recuperacao(self, email):
        """Gera o link de redefinição. Devolve {nome, email, token} ou None se o e-mail não tem conta (ou se
        a conta já pediu demais): quem chama responde igual nos dois casos, para não revelar quem tem conta."""
        email = self.normaliza_email(email)
        rows = self.store._run("SELECT id,nome FROM users WHERE email=?", (email,), fetch=True)
        if not rows:
            return None
        uid, nome = rows[0]
        agora = self.agora()
        recentes = self.store._run("SELECT COUNT(*) FROM reset WHERE user_id=? AND created_at>?",
                                   (uid, agora - 3600), fetch=True)[0][0]
        if recentes >= RESET_MAX_POR_HORA:
            return None
        self.store._run("UPDATE reset SET expires=0 WHERE user_id=?", (uid,))          # o pedido novo invalida os antigos
        self.store._run("DELETE FROM reset WHERE created_at<?", (agora - 86400,))
        token = secrets.token_urlsafe(32)
        self.store._run("INSERT INTO reset(token,user_id,expires,created_at) VALUES(?,?,?,?)",
                        (_sha(token), uid, agora + RESET_VALIDADE, agora))
        return {"nome": nome, "email": email, "token": token}

    def redefinir(self, token, senha):
        """Troca a senha pelo link recebido. O link vale uma vez; todas as sessões abertas da conta são encerradas."""
        self._valida_senha(senha)
        rows = self.store._run("SELECT user_id,expires FROM reset WHERE token=?",
                               (_sha(token),), fetch=True) if isinstance(token, str) and 0 < len(token) <= 200 else []
        if not rows or rows[0][1] <= self.agora():
            raise Erro("Esse link não vale mais. Peça um novo em “Esqueci minha senha”.", 400)
        uid = rows[0][0]
        self.store._run("UPDATE users SET hash=? WHERE id=?", (self._novo_hash(senha), uid))
        self.store._run("UPDATE reset SET expires=0 WHERE user_id=?", (uid,))
        self.store._run("DELETE FROM auth WHERE user_id=?", (uid,))
        return {"id": uid}

    def eh_conta(self, uid):
        return bool(self.store._run("SELECT 1 FROM users WHERE id=?", (uid,), fetch=True))

    # -- sessões -----------------------------------------------------------
    def abrir_sessao(self, uid):
        token = secrets.token_urlsafe(32)
        agora = self.agora()
        self.store._run("DELETE FROM auth WHERE expires<?", (agora,))
        self.store._run("INSERT INTO auth(token,user_id,expires) VALUES(?,?,?)",
                        (_sha(token), uid, agora + SESSAO_DIAS * 86400))
        return token

    def por_token(self, token):
        if not token or not isinstance(token, str) or len(token) > 200:
            return None
        rows = self.store._run("SELECT u.id,u.nome FROM auth a JOIN users u ON u.id=a.user_id "
                               "WHERE a.token=? AND a.expires>?", (_sha(token), self.agora()), fetch=True)
        return {"id": rows[0][0], "nome": rows[0][1]} if rows else None

    def fechar_sessao(self, token):
        if token:
            self.store._run("DELETE FROM auth WHERE token=?", (_sha(token),))
