"""Contas de usuário: cadastro, login e sessões (cookie), tudo em SQLite.

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
NOME_VALIDO = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
SENHA_MIN, SENHA_MAX = 8, 128
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
    def criar(self, nome, senha, id_existente=None):
        nome = (nome or "").strip() if isinstance(nome, str) else ""
        if not NOME_VALIDO.match(nome):
            raise Erro("O usuário precisa ter de 3 a 30 caracteres: letras, números, ponto, hífen ou _.")
        if not isinstance(senha, str) or not (SENHA_MIN <= len(senha) <= SENHA_MAX):
            raise Erro(f"A senha precisa ter de {SENHA_MIN} a {SENHA_MAX} caracteres.")
        uid = id_existente if id_existente and not self.eh_conta(id_existente) else "u_" + secrets.token_hex(16)
        sal = secrets.token_bytes(16)
        valor = f"scrypt${sal.hex()}${_hash(senha, sal).hex()}"
        try:
            self.store._run("INSERT INTO users(id,nome,hash,created_at) VALUES(?,?,?,?)", (uid, nome, valor, self.agora()))
        except Exception as e:                         # UNIQUE(nome) já existe
            if "UNIQUE" in str(e).upper():
                raise Erro("Esse usuário já existe. Escolha outro ou entre na sua conta.", 409)
            raise
        return {"id": uid, "nome": nome}

    def entrar(self, nome, senha):
        nome = nome.strip() if isinstance(nome, str) else ""
        rows = self.store._run("SELECT id,nome,hash FROM users WHERE nome=?", (nome,), fetch=True) if nome else []
        if not isinstance(senha, str) or len(senha) > SENHA_MAX:
            senha = ""
        if rows:
            _, sal_hex, h_hex = rows[0][2].split("$")
            ok = hmac.compare_digest(_hash(senha, bytes.fromhex(sal_hex)), bytes.fromhex(h_hex))
        else:
            _hash(senha, self._sal_falso)
            ok = False
        if not ok:
            raise Erro("Usuário ou senha incorretos.", 401)
        return {"id": rows[0][0], "nome": rows[0][1]}

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
