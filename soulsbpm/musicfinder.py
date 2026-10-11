"""MusicFinder: transforma a vibe em parâmetros (sentimento, energia, gênero).

MVP: interpretador por léxico em português (sem chamada externa), isolado atrás de
`interpretar()` para ser trocado depois por uma API de linguagem natural.
"""
import re
import unicodedata

EXEMPLOS = [
    "música calma para estudar à noite",
    "treino pesado de academia",
    "festa animada para dançar",
    "jantar romântico com jazz",
    "tristeza em dia de chuva",
]

# (termos, efeito). Termo terminado em * casa por prefixo; sem * casa exato.
LEXICO = [
    (["estud*", "concentr*", "foco", "focar", "ler", "leitura", "trabalh*", "programar"],
     dict(tags=["foco", "calma"], energia=0.3)),
    (["noite", "noites", "noturn*", "madrugad*"], dict(tags=["noite"], delta=-0.1)),
    (["calm*", "tranquil*", "relax*", "suave", "paz", "sereno", "descansar"],
     dict(tags=["calma", "relaxar"], energia=0.22)),
    (["dormir", "sono", "sonolent*", "meditar", "meditacao"],
     dict(tags=["dormir", "calma", "meditar"], energia=0.12)),
    (["trein*", "academia", "malhar", "malhacao", "correr", "corrida", "corrend*", "musculacao"],
     dict(tags=["treino", "energia", "correr"], energia=0.92)),
    (["festa", "balada", "danc*", "pista", "rave"], dict(tags=["festa", "danca", "balada"], energia=0.85)),
    (["animad*", "agitad*", "energetic*", "intens*", "pesad*", "forte", "empolg*"],
     dict(tags=["animada", "energia"], energia=0.85)),
    (["triste*", "tristeza", "chorar", "saudade*", "melancoli*", "nostalg*", "sofrer"],
     dict(tags=["triste", "melancolia", "saudade"], energia=0.32)),
    (["chuva", "chuvos*", "garoa", "nublad*"], dict(tags=["chuva"], delta=-0.05)),
    (["feliz", "alegr*", "sol", "ensolarad*", "manha", "verao", "praia", "bom"],
     dict(tags=["feliz", "animada"], energia=0.65)),
    (["viag*", "estrada", "dirigir", "dirigindo", "carro"], dict(tags=["viagem", "dirigir"], energia=0.62)),
    (["romanti*", "amor", "namor*", "jantar", "date", "casal", "apaixonad*"],
     dict(tags=["romantico"], energia=0.38)),
    (["churrasco", "amigos", "reuniao", "quintal"], dict(tags=["churrasco", "amigos", "festa"], energia=0.65)),
    (["cafe", "tarde", "domingo"], dict(tags=["cafe", "tarde", "calma"], energia=0.35)),
    (["raiva", "ira", "furia", "nervos*"], dict(tags=["raiva", "energia"], energia=0.88)),
    (["lento", "devagar", "devagarinho"], dict(delta=-0.15)),
    (["rapido", "acelerad*"], dict(delta=0.15)),
]
GENEROS = {
    "lofi": ["lofi", "lo-fi", "chillhop"], "ambient": ["ambient", "ambiente"],
    "jazz": ["jazz"], "bossa": ["bossa"], "mpb": ["mpb"], "indie": ["indie"],
    "acustico": ["acustic*", "violao"], "pop": ["pop"], "rock": ["rock"],
    "eletronica": ["eletronic*", "edm"], "house": ["house"], "techno": ["techno"],
    "hiphop": ["rap", "hiphop", "hip-hop", "trap"], "pagode": ["pagode"], "samba": ["samba"],
    "forro": ["forro"], "instrumental": ["instrumental"],
}
TECNICOS = {"bpm", "camelot", "tom", "harmonic*", "harmonica", "tonalidade"}

_ANTI_NEGACAO = {"sem", "nao"}


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _casa(token: str, termo: str) -> bool:
    return token.startswith(termo[:-1]) if termo.endswith("*") else token == termo


def rotulo_energia(e):
    if e is None:
        return None
    return "baixa" if e < 0.35 else ("média" if e < 0.65 else "alta")


def interpretar(texto: str) -> dict:
    """Devolve {clara, tags(dict tag→peso), energia, generos, tecnico, resumo, termos}."""
    tokens = re.findall(r"[a-z0-9-]+", normalizar(texto or ""))
    tags, alvos, deltas, generos, termos = {}, [], 0.0, [], []
    tecnico = any(_casa(t, x) for t in tokens for x in TECNICOS)
    for tok in tokens:
        for termos_lex, ef in LEXICO:
            if any(_casa(tok, x) for x in termos_lex):
                termos.append(tok)
                for tg in ef.get("tags", []):
                    tags[tg] = tags.get(tg, 0) + 1
                if "energia" in ef:
                    alvos.append(ef["energia"])
                deltas += ef.get("delta", 0.0)
        for gen, formas in GENEROS.items():
            if any(_casa(tok, x) for x in formas) and gen not in generos:
                generos.append(gen)
                termos.append(tok)
    energia = None
    if alvos:
        energia = sum(alvos) / len(alvos) + deltas
    elif deltas:
        energia = 0.5 + deltas
    if energia is not None:
        energia = round(min(0.95, max(0.05, energia)), 2)
    clara = bool(tags or generos or energia is not None)
    partes = []
    if tags:
        partes.append("clima " + ", ".join(sorted(tags, key=lambda k: -tags[k])[:4]))
    if energia is not None:
        partes.append(f"energia {rotulo_energia(energia)}")
    if generos:
        partes.append("gênero " + ", ".join(generos))
    return {"clara": clara, "tags": tags, "energia": energia, "generos": generos,
            "tecnico": tecnico, "termos": sorted(set(termos)),
            "resumo": ("Entendi: " + " · ".join(partes)) if partes else "Não consegui identificar o clima.",
            "exemplos": [] if clara else EXEMPLOS}


def vibe_score(faixa: dict, interp: dict) -> float:
    """Quanto a faixa combina com a vibe interpretada (0 a 1)."""
    tags, alvo, gens = interp["tags"], interp["energia"], interp["generos"]
    total = sum(tags.values())
    s_tag = sum(w for t, w in tags.items() if t in faixa["tags"]) / total if total else None
    s_en = (1.0 - abs(faixa["energia"] - alvo)) if alvo is not None else None
    s_gen = (1.0 if set(gens) & set(faixa["generos"]) else 0.0) if gens else None
    pesos = [(s_tag, 0.5), (s_en, 0.3), (s_gen, 0.2)]
    usados = [(s, w) for s, w in pesos if s is not None]
    if not usados:
        return 0.0
    return sum(s * w for s, w in usados) / sum(w for _, w in usados)


def buscar(catalogo: list, interp: dict, limite: int = 10, minimo: float = 0.4) -> list:
    """Faixas do catálogo alinhadas à vibe, da mais para a menos aderente."""
    pontuadas = [(vibe_score(f, interp), f) for f in catalogo]
    pontuadas = [(s, f) for s, f in pontuadas if s >= minimo]
    pontuadas.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [dict(f, vibe=round(s, 3)) for s, f in pontuadas[:limite]]
