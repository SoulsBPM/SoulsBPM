"""Motor de Feedback: pulos, likes e salvamentos viram ajustes no perfil e no grafo.

Pesos (documento 5, seção 4.2): curtir +1,0 · salvar +1,5 · aceitar +0,5 ·
pular depois da metade −0,3 · pular antes da metade −1,0.
Pesos antigos perdem força com o tempo (meia-vida) e usuário novo começa neutro.
"""
import math
import time

DELTAS = {"like": 1.0, "save": 1.5, "accept": 0.5, "skip_late": -0.3, "skip_early": -1.0}
HALF_LIFE_DAYS = 30.0
CLAMP = 5.0
LOW_TECH = 60   # % técnica abaixo da qual o pulo é atribuído à transição


def efetivo(valor: float, atualizado_em: float, agora: float) -> float:
    dias = max(0.0, (agora - atualizado_em) / 86400.0)
    return valor * math.pow(0.5, dias / HALF_LIFE_DAYS)


def tipo_pulo(fracao_tocada: float) -> str:
    return "skip_late" if fracao_tocada >= 0.5 else "skip_early"


def bucket_bpm(bpm: int) -> int:
    return int(round(bpm / 10.0)) * 10


def bucket_energia(e: float) -> int:
    return int(round(e * 5))


class Perfil:
    """Pesos de um usuário. `store` precisa de get_weights(uid) e set_weight(uid, key, value, ts)."""

    def __init__(self, store, user_id, agora=None):
        self.store, self.uid = store, user_id
        self._agora = agora or time.time
        self._cache = None

    def _pesos(self):
        if self._cache is None:
            self._cache = self.store.get_weights(self.uid) if self.uid else {}
        return self._cache

    def peso(self, chave: str) -> float:
        v = self._pesos().get(chave)
        return efetivo(v[0], v[1], self._agora()) if v else 0.0

    def somar(self, chave: str, delta: float):
        if not self.uid:
            return
        agora = self._agora()
        novo = max(-CLAMP, min(CLAMP, self.peso(chave) + delta))
        self._pesos()[chave] = (novo, agora)
        self.store.set_weight(self.uid, chave, novo, agora)

    def bonus(self, prev, faixa, tags_vibe) -> float:
        """Bônus acumulado do perfil para `faixa` (entra em dj.ajuste_perfil)."""
        gens = faixa["generos"]
        b = sum(self.peso(f"genre:{g}") for g in gens) / max(1, len(gens))
        b += 0.5 * self.peso(f"bpm:{bucket_bpm(faixa['bpm'])}")
        b += 0.5 * self.peso(f"energy:{bucket_energia(faixa['energia'])}")
        for t in tags_vibe:
            b += self.peso(f"assoc:{t}|{faixa['id']}")
        if prev:
            b += self.peso(f"pair:{prev['id']}>{faixa['id']}")
        return b


def registrar_positivo(perfil: Perfil, acao: str, faixa: dict, prev: dict | None, sinal: int = 1):
    """`sinal=-1` desfaz o efeito (ex.: tirar a curtida)."""
    d = DELTAS[acao] * sinal
    gens = faixa["generos"]
    for g in gens:
        perfil.somar(f"genre:{g}", d / len(gens))
    perfil.somar(f"bpm:{bucket_bpm(faixa['bpm'])}", d)
    perfil.somar(f"energy:{bucket_energia(faixa['energia'])}", d)
    if prev:
        perfil.somar(f"pair:{prev['id']}>{faixa['id']}", d)


def registrar_pulo(perfil: Perfil, faixa: dict, prev: dict | None, tags_vibe, fracao: float,
                   tecnica_pct: int | None) -> dict:
    """Pulo: descobre se a culpa é da transição ou da vibe (documento 5, 4.2)."""
    tipo = tipo_pulo(fracao)
    d = DELTAS[tipo]
    if prev is not None and tecnica_pct is not None and tecnica_pct < LOW_TECH:
        perfil.somar(f"pair:{prev['id']}>{faixa['id']}", d)
        causa = "transicao"
    else:
        for t in tags_vibe:
            perfil.somar(f"assoc:{t}|{faixa['id']}", d)
        causa = "vibe"
    return {"tipo": tipo, "delta": d, "causa": causa}


def desfazer_pulo(perfil: Perfil, faixa: dict, prev: dict | None, tags_vibe, info: dict):
    """Reverte o ajuste que `registrar_pulo` fez (ao voltar para uma faixa pulada sem querer)."""
    d = -info["delta"]
    if info["causa"] == "transicao" and prev is not None:
        perfil.somar(f"pair:{prev['id']}>{faixa['id']}", d)
    else:
        for t in tags_vibe:
            perfil.somar(f"assoc:{t}|{faixa['id']}", d)


def resumo(perfil: Perfil, limite: int = 5) -> dict:
    """Visão transparente do que o sistema aprendeu (para o usuário ver e apagar)."""
    ag = perfil._agora()
    itens = [(k, efetivo(v, ts, ag)) for k, (v, ts) in perfil._pesos().items()]
    gen = sorted([(k[6:], round(v, 2)) for k, v in itens if k.startswith("genre:") and abs(v) > 0.05],
                 key=lambda x: -x[1])
    return {"generos_preferidos": [g for g in gen if g[1] > 0][:limite],
            "generos_evitados": [g for g in reversed(gen) if g[1] < 0][:limite],
            "total_pesos": len(itens)}
