"""DJ Intelligent: compatibilidade técnica entre faixas (documento 5, seção 4.2).

nota = 0,35·vibe + 0,25·BPM + 0,25·tom + 0,15·energia, ajustada pelo perfil.
"""
import math
import re

W_VIBE, W_BPM, W_KEY, W_ENERGY = 0.35, 0.25, 0.25, 0.15
BPM_TOLERANCE = 0.05          # ±5%
# Com BPM alvo definido pelo DJ, o "rumo" entra na nota e os demais pesos encolhem (soma continua 1,0).
# Valores escolhidos numa varredura em 6 vibes (subindo e descendo): 0 passos na direção errada, compatibilidade média ~71%.
W_RUMO = 0.45
W_ALVO = {"vibe": 0.08, "bpm": 0.24, "tom": 0.15, "energia": 0.08}
PERFIL_COM_ALVO = 0.3         # com alvo, o gosto aprendido pesa menos que a direção pedida pelo DJ
RUMO_ESCALA = 1.0             # quão forte o progresso (ou recuo) em direção ao alvo muda a nota
RUMO_TOL = 0.03               # a menos de 3% do alvo já "chegou": a IA passa a manter o ritmo
PROFILE_RANGE = 0.25          # o perfil move a nota no máximo ±0,25 (calibrado nos testes)
RISKY_BELOW = 55              # % técnica abaixo da qual a transição é "arriscada"
GOOD_FROM = 80                # % técnica a partir da qual "combina bem"

_CAMELOT = re.compile(r"^(1[0-2]|[1-9])([AB])$")


def bpm_score(a: float, b: float, meio_dobro: bool = True) -> float:
    """1 com BPM igual, cai linearmente até 0 em 5% de diferença.
    Considera também meio tempo e dobro (70 ↔ 140), a menos que `meio_dobro=False`."""
    d = (min(abs(b - a), abs(2 * b - a), abs(b / 2 - a)) if meio_dobro else abs(b - a)) / a
    return max(0.0, 1.0 - d / BPM_TOLERANCE)


def parse_key(key: str):
    m = _CAMELOT.match(key.strip().upper())
    if not m:
        raise ValueError(f"Tom fora da escala de Camelot: {key!r}")
    return int(m.group(1)), m.group(2)


def key_score(a: str, b: str) -> float:
    """1,0 mesma chave; 0,9 vizinha (±1, circular) ou relativa (mesmo número, A↔B); 0,3 demais."""
    na, la = parse_key(a)
    nb, lb = parse_key(b)
    if (na, la) == (nb, lb):
        return 1.0
    circular = min((na - nb) % 12, (nb - na) % 12)
    if la == lb and circular == 1:
        return 0.9
    if na == nb and la != lb:
        return 0.9
    return 0.3


def energy_score(a: float, b: float) -> float:
    return max(0.0, 1.0 - abs(a - b))


def rumo_score(prev_bpm: float, cand_bpm: float, alvo: float) -> float:
    """Quanto a candidata aproxima o set do BPM alvo (1 = chega no alvo, 0,5 = não muda, 0 = afasta muito).
    Se a faixa atual já está no alvo, vale ficar perto dele."""
    d_prev, d_cand = abs(prev_bpm - alvo), abs(cand_bpm - alvo)
    if d_prev <= RUMO_TOL * alvo:
        return max(0.0, 1.0 - d_cand / (BPM_TOLERANCE * alvo))
    progresso = (d_prev - d_cand) / d_prev
    return max(0.0, min(1.0, 0.5 + RUMO_ESCALA * progresso))


def technical(prev: dict, cand: dict, meio_dobro: bool = True) -> dict:
    """Compatibilidade técnica de prev → cand (sem a vibe)."""
    bs = bpm_score(prev["bpm"], cand["bpm"], meio_dobro)
    ks = key_score(prev["tom"], cand["tom"])
    es = energy_score(prev["energia"], cand["energia"])
    pct = round(100 * (W_BPM * bs + W_KEY * ks + W_ENERGY * es) / (W_BPM + W_KEY + W_ENERGY))
    return {"bpm": round(bs, 3), "tom": round(ks, 3), "energia": round(es, 3), "percentual": pct}


def nota(prev: dict, cand: dict, vibe: float) -> float:
    t = technical(prev, cand)
    return W_VIBE * vibe + W_BPM * t["bpm"] + W_KEY * t["tom"] + W_ENERGY * t["energia"]


def ajuste_perfil(bonus: float) -> float:
    """Converte o bônus acumulado do perfil em um ajuste limitado de nota."""
    return PROFILE_RANGE * math.tanh(bonus / 2.0)


def existe_compativel(prev: dict, candidatos: list, meio_dobro: bool = True) -> bool:
    """Ponto de decisão D2: há faixa com BPM dentro de ±5% e chave compatível?"""
    return any(bpm_score(prev["bpm"], c["bpm"], meio_dobro) > 0 and key_score(prev["tom"], c["tom"]) >= 0.9
               for c in candidatos)


def classificar(percentual: int, d2_ok: bool = True) -> str:
    if not d2_ok or percentual < RISKY_BELOW:
        return "arriscada"
    if percentual >= GOOD_FROM:
        return "combina_bem"
    return "ok"


def _pct(a: float, b: float) -> str:
    d = (b - a) / a * 100
    return ("+" if d >= 0 else "−") + f"{abs(d):.1f}".replace(".", ",") + "%"


def explicar(prev: dict, cand: dict, t: dict, vibe: float, alvo=None) -> list:
    """Frases curtas que dizem ao DJ por que a IA escolheu esta faixa."""
    a, b = prev["bpm"], cand["bpm"]
    m = []
    if t["bpm"] == 0:
        m.append(f"BPM distante ({a} → {b})")
    elif alvo is not None or (abs(b - a) <= abs(2 * b - a) and abs(b - a) <= abs(b / 2 - a)):
        m.append(f"BPM {a} → {b} ({_pct(a, b)})")
    else:
        m.append(f"BPM em {'dobro' if b > a else 'meio tempo'} ({a} → {b})")
    if t["tom"] == 1.0:
        m.append(f"mesma chave ({cand['tom']})")
    elif t["tom"] >= 0.9:
        m.append(f"chave compatível ({prev['tom']} → {cand['tom']})")
    else:
        m.append(f"chave distante ({prev['tom']} → {cand['tom']})")
    if alvo is not None:
        if abs(a - alvo) <= RUMO_TOL * alvo:
            m.append(f"mantém o ritmo perto do alvo de {alvo} BPM")
        elif abs(b - alvo) < abs(a - alvo):
            m.append(f"{'sobe' if alvo > a else 'desce'} em direção ao alvo de {alvo} BPM")
        else:
            m.append(f"não avança para o alvo de {alvo} BPM")
    if t["energia"] < 0.7:
        m.append("energia " + ("sobe" if cand["energia"] > prev["energia"] else "cai") + " bastante")
    if vibe >= 0.6:
        m.append("combina com a vibe")
    return m


def rank_next(prev: dict, candidatos: list, vibe_fn, bonus_fn=None, alvo=None) -> list:
    """Ordena candidatos por nota (maior primeiro). Cada item traz a explicação da nota.
    `alvo` = BPM que o DJ quer atingir; sem ele vale a fórmula original."""
    md = alvo is None      # com BPM alvo, meio tempo/dobro não aproxima o set do alvo
    d2 = existe_compativel(prev, candidatos, md)
    saida = []
    for c in candidatos:
        v = vibe_fn(c)
        t = technical(prev, c, md)
        if alvo is None:
            rumo = None
            base = W_VIBE * v + W_BPM * t["bpm"] + W_KEY * t["tom"] + W_ENERGY * t["energia"]
        else:
            rumo = rumo_score(prev["bpm"], c["bpm"], alvo)
            base = (W_ALVO["vibe"] * v + W_ALVO["bpm"] * t["bpm"] + W_ALVO["tom"] * t["tom"]
                    + W_ALVO["energia"] * t["energia"] + W_RUMO * rumo)
        adj = ajuste_perfil(bonus_fn(prev, c)) if bonus_fn else 0.0
        if alvo is not None:
            adj *= PERFIL_COM_ALVO
        final = min(1.0, max(0.0, base + adj))
        saida.append({"faixa": c, "nota": round(final, 4), "nota_base": round(base, 4),
                      "vibe": round(v, 3), "tecnica": t, "rumo": None if rumo is None else round(rumo, 3),
                      "motivos": explicar(prev, c, t, v, alvo),
                      "classe": classificar(t["percentual"], d2)})
    saida.sort(key=lambda x: (-x["nota"], x["faixa"]["id"]))
    return saida
