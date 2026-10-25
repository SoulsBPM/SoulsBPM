"""GetSongBPM simulada (sem rede): responde /search/, /tempo/ e /artist/ a partir de uma tabela."""
import re
import unicodedata
import urllib.parse

from soulsbpm.fontes import Cache, GetSongBPM


def _s(t):
    t = unicodedata.normalize("NFKD", t.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def gsb_falso(tabela, similares=None, impostor=None, sem_tom=(), sem_tempo=False, sem_listagem=False):
    """tabela: {(artista, título): (bpm, tom)}. similares: {artista: [nomes]}.
    impostor: nome devolvido para um artista que não existe (a busca de artista sempre acha algo)."""
    similares = similares or {}
    artistas = {}
    for a, _ in tabela:
        artistas.setdefault(a, len(artistas) + 1)

    def item(a, t, bpm, tom, i=1):
        d = {"id": str(i), "title": t, "artist": {"name": a, "id": str(artistas[a])}}
        if (a, t) not in sem_tom:
            d.update(tempo=str(bpm), key_of=tom)
        return d

    def http(url):
        u = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        lim = int(q.get("limit", 10))
        if u.path == "/search/":
            tipo, look = q["type"], q["lookup"]
            if tipo == "artist":
                for a, i in artistas.items():
                    if _s(a) == _s(look):
                        return {"search": [{"id": str(i), "name": a}]}
                return {"search": [{"id": "99", "name": impostor}]} if impostor else {"search": []}
            m = re.fullmatch(r"song:(.*) artist:(.*)", look)
            if m:
                t, a = m.groups()
                return {"search": [item(x, y, *v) for (x, y), v in tabela.items() if _s(y) == _s(t) and _s(x) == _s(a)][:lim]}
            if look.startswith("artist:") and sem_listagem:
                return {"search": []}
            if look.startswith("artist:"):
                a = look[7:]
                return {"search": [item(x, y, *v) for (x, y), v in tabela.items() if _s(x) == _s(a)][:lim]}
            tok = set(_s(look).split())
            return {"search": [item(x, y, *v) for (x, y), v in tabela.items() if tok and tok <= set(_s(y).split())][:lim]}
        if u.path == "/tempo/" and sem_tempo:
            return {"tempo": []}
        if u.path == "/tempo/":
            bpm = int(q["bpm"])
            return {"tempo": [{"song_id": "1", "song_title": y, "tempo": str(v[0]), "artist": {"name": x}}
                              for (x, y), v in tabela.items() if abs(v[0] - bpm) <= 12][:lim]}
        if u.path == "/artist/":
            nome = next((a for a, i in artistas.items() if str(i) == q["id"]), None)
            return {"artist": {"name": nome, "similar": [{"name": n} for n in similares.get(nome, [])]}}
        return {}
    return GetSongBPM("k", Cache(), http, pausa=0)
