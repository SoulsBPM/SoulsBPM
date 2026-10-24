"""MusicFinder: transforma a vibe em parâmetros (sentimento, energia, gênero).

Interpretador por modelo de linguagem (Claude, soulsbpm/llm.py) quando há ANTHROPIC_API_KEY, com o
léxico em português como reserva. Tudo isolado atrás de `interpretar()`.
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
PESO_SEMANTICA = 0.35       # parte da nota de vibe que vem dos embeddings (o resto: tags, energia e gênero)

_ANTI_NEGACAO = {"sem", "nao"}


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _casa(token: str, termo: str) -> bool:
    return token.startswith(termo[:-1]) if termo.endswith("*") else token == termo


_ARTIGOS = {"a", "o", "as", "os", "de", "da", "do", "the", "and", "e"}


def _tokens(txt):
    return set(re.findall(r"[a-z0-9]+", normalizar(txt or "")))


def relevancia(consulta: str, titulo: str, artista: str = "") -> float:
    """Quanto o texto digitado parece ser o nome desta música (ou o artista dela): 0 a 1.
    Compara as palavras (sem acento, sem maiúsculas): vale o melhor entre título, artista e os dois juntos."""
    q = _tokens(consulta) - _ARTIGOS or _tokens(consulta)
    if not q:
        return 0.0
    melhor = 0.0
    for alvo in (_tokens(titulo), _tokens(artista), _tokens(titulo) | _tokens(artista)):
        alvo = (alvo - _ARTIGOS) or alvo
        if not alvo:
            continue
        comum = len(q & alvo)
        if comum:
            f, g = comum / len(q), comum / len(alvo)
            melhor = max(melhor, 2 * f * g / (f + g))
    return round(melhor, 3)


def destaques_no_catalogo(catalogo: list, texto: str, limite: int = 3, minimo: float = 0.7) -> dict:
    """{id: 1,0} das faixas do catálogo cujo título/artista combinam com o texto (catálogo de amostra, sem Last.fm)."""
    pontuadas = sorted(((relevancia(texto, f["titulo"], f["artista"]), f["id"]) for f in catalogo), key=lambda x: (-x[0], x[1]))
    return {i: 1.0 for s, i in pontuadas[:limite] if s >= minimo}


def rotulo_energia(e):
    if e is None:
        return None
    return "baixa" if e < 0.35 else ("média" if e < 0.65 else "alta")


_PREFIXOS_ARTISTA = [
    r"(?:no\s+)?estilo\s+(?:de|do|da)", r"parecid[oa]s?\s+com", r"similar(?:es)?\s+(?:a|ao|à)", r"(?:tipo|como)",
    r"(?:artista|banda|cantor|cantora|dj)\s*:?", r"(?:m[uú]sicas?|sons?|faixas?|hits?)\s+(?:de|do|da|dos|das)",
    r"(?:quero|gosto|curto|ou[cç]o|escuto|gostar)\s+(?:de\s+|do\s+|da\s+)?(?:ouvir\s+)?",
]
_RE_ARTISTA = re.compile(r"^(?:.*?\b)?(?:" + "|".join(_PREFIXOS_ARTISTA) + r")\s+(.{2,60})$", re.I)


def extrair_artista(texto: str):
    """Nome de artista citado de forma explícita ("tipo Calvin Harris", "músicas do Coldplay"). None se não houver.
    É só um candidato: o modo ao vivo confirma no Last.fm antes de usar."""
    t = re.sub(r"\s+", " ", (texto or "").strip().strip("\"'“”.!?"))
    m = _RE_ARTISTA.match(t)
    if not m:
        return None
    nome = m.group(1).strip(" .,!?")
    sem_acento = normalizar(nome)
    toks = re.findall(r"[a-z0-9-]+", sem_acento)
    if not toks or len(toks) > 5:
        return None
    if any(_casa(tk, x) for tk in toks for termos, _ in LEXICO for x in termos):   # "músicas de treino" é vibe, não artista
        return None
    return nome


def candidato_artista(texto: str, clara: bool):
    """Explícito ("tipo X") ou, quando a vibe não foi entendida, a frase curta inteira (confirmada depois no Last.fm)."""
    nome = extrair_artista(texto)
    if nome:
        return nome, True
    t = (texto or "").strip()
    if not clara and 0 < len(re.findall(r"\S+", t)) <= 5:
        return t, False
    return None, False


_ia = None          # interpretador por modelo de linguagem (soulsbpm.llm); None = só léxico


def configurar_ia(interpretador):
    """Liga (ou desliga, com None) o interpretador por IA. Chamado pelo app quando há ANTHROPIC_API_KEY."""
    global _ia
    _ia = interpretador


def ia_ativa() -> bool:
    return _ia is not None


def ia_atual():
    """O interpretador por IA em uso (ou None). Outros recursos de IA (artistas, narração) reaproveitam o mesmo."""
    return _ia


def ia_nome():
    """Provedor e modelo em uso (sem a chave), ou None."""
    return f"{_ia.provedor}/{_ia.modelo}" if _ia is not None and hasattr(_ia, "provedor") else None


def _resumo(tags, energia, generos):
    partes = []
    if tags:
        partes.append("clima " + ", ".join(sorted(tags, key=lambda k: -tags[k])[:4]))
    if energia is not None:
        partes.append(f"energia {rotulo_energia(energia)}")
    if generos:
        partes.append("gênero " + ", ".join(generos))
    return ("Entendi: " + " · ".join(partes)) if partes else "Não consegui identificar o clima."


def interpretar(texto: str) -> dict:
    """Devolve {clara, tags(dict tag→peso), energia, generos, tecnico, resumo, termos}.

    Com IA ligada, o modelo de linguagem interpreta a frase; se ele falhar ou não achar o clima,
    vale o léxico em português (abaixo), então a busca nunca fica sem resposta."""
    if _ia is not None:
        r = _ia(texto)
        if r and r["clara"]:
            lex = interpretar_lexico(texto)
            return {"clara": True, "tags": r["tags"], "energia": r["energia"], "generos": r["generos"],
                    "tecnico": r["tecnico"] or lex["tecnico"], "termos": lex["termos"],
                    "resumo": _resumo(r["tags"], r["energia"], r["generos"]), "exemplos": [], "origem": "ia"}
    return interpretar_lexico(texto)


def interpretar_lexico(texto: str) -> dict:
    """Interpretador por léxico em português (sem chamada externa)."""
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
    return {"clara": clara, "tags": tags, "energia": energia, "generos": generos,
            "tecnico": tecnico, "termos": sorted(set(termos)),
            "resumo": _resumo(tags, energia, generos),
            "exemplos": [] if clara else EXEMPLOS}


def vibe_score(faixa: dict, interp: dict) -> float:
    """Quanto a faixa combina com a vibe interpretada (0 a 1)."""
    if interp.get("pontos") is not None:                    # busca por artista: vale a lista montada na busca
        return interp["pontos"].get(faixa["id"], 0.0)
    tags, alvo, gens = interp["tags"], interp["energia"], interp["generos"]
    total = sum(tags.values())
    s_tag = sum(w for t, w in tags.items() if t in faixa["tags"]) / total if total else None
    s_en = (1.0 - abs(faixa["energia"] - alvo)) if alvo is not None else None
    s_gen = (1.0 if set(gens) & set(faixa["generos"]) else 0.0) if gens else None
    pesos = [(s_tag, 0.5), (s_en, 0.3), (s_gen, 0.2)]
    usados = [(s, w) for s, w in pesos if s is not None]
    if not usados:
        return 0.0
    base = sum(s * w for s, w in usados) / sum(w for _, w in usados)
    sem = interp.get("semantica")                           # embeddings da busca (soulsbpm.embeddings), se houver
    if sem is not None:                                     # faixa fora do grupo analisado fica neutra (0,5)
        base = (1 - PESO_SEMANTICA) * base + PESO_SEMANTICA * sem.get(faixa["id"], 0.5)
    return base


def buscar(catalogo: list, interp: dict, limite: int = 10, minimo: float = 0.4) -> list:
    """Faixas do catálogo alinhadas à vibe, da mais para a menos aderente."""
    pontuadas = [(vibe_score(f, interp), f) for f in catalogo]
    pontuadas = [(s, f) for s, f in pontuadas if s >= minimo]
    pontuadas.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [dict(f, vibe=round(s, 3)) for s, f in pontuadas[:limite]]


def diversificar(faixas: list, limite: int = 10, max_por_artista: int = 3) -> list:
    """Mantém a ordem, mas deixa no máximo `max_por_artista` músicas de cada artista entre as primeiras.
    Se não houver artistas suficientes, completa com as que sobraram (a lista nunca encolhe por causa disso)."""
    contagem, escolhidas, sobras = {}, [], []
    for f in faixas:
        a = f["artista"].strip().lower()
        if contagem.get(a, 0) < max_por_artista:
            contagem[a] = contagem.get(a, 0) + 1
            escolhidas.append(f)
        else:
            sobras.append(f)
    return (escolhidas + sobras)[:limite]
