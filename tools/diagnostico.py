"""Diagnóstico do modo ao vivo: testa Last.fm e GetSongBPM e mostra o que cada uma respondeu.

Uso (PowerShell):
    $env:LASTFM_API_KEY="sua_chave"
    $env:GETSONGBPM_API_KEY="sua_chave"
    python tools/diagnostico.py
As chaves nunca são impressas.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def pegar(url, chaves):
    req = urllib.request.Request(url, headers={"User-Agent": "SoulsBPM/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")
        return e.code, corpo
    except Exception as e:  # rede, DNS, firewall…
        return None, f"{type(e).__name__}: {e}"


def limpa(txt, chaves):
    for c in chaves:
        if c:
            txt = txt.replace(c, "***")
    return txt


def main():
    lf, gb = os.environ.get("LASTFM_API_KEY", ""), os.environ.get("GETSONGBPM_API_KEY", "")
    print("Chave Last.fm:", f"definida ({len(lf)} caracteres)" if lf else "NÃO definida")
    print("Chave GetSongBPM:", f"definida ({len(gb)} caracteres)" if gb else "NÃO definida")

    print("\n1) Last.fm — músicas da tag 'chill'")
    if lf:
        u = "https://ws.audioscrobbler.com/2.0/?" + urllib.parse.urlencode(
            {"method": "tag.gettoptracks", "tag": "chill", "limit": 5, "api_key": lf, "format": "json"})
        st, corpo = pegar(u, [lf])
        print("   HTTP:", st)
        try:
            d = json.loads(corpo)
            if d.get("error"):
                print("   ERRO do Last.fm:", d.get("error"), d.get("message"))
            else:
                bloco = d.get("tracks") or d.get("toptracks") or {}
                faixas = bloco.get("track") or []
                print(f"   OK: {len(faixas)} faixas, por exemplo:",
                      [f"{t['artist']['name']} - {t['name']}" for t in faixas[:3]])
        except Exception:
            print("   Resposta inesperada:", limpa(corpo[:300], [lf]))

    print("\n2) GetSongBPM — busca 'Strobe' de deadmau5")
    if gb:
        u = "https://api.getsong.co/search/?" + urllib.parse.urlencode(
            {"api_key": gb, "type": "both", "lookup": "song:Strobe artist:deadmau5", "limit": 3})
        st, corpo = pegar(u, [gb])
        print("   HTTP:", st)
        try:
            d = json.loads(corpo)
            itens = d.get("search") if isinstance(d, dict) else None
            if isinstance(itens, list) and itens:
                i = itens[0]
                print("   busca OK:", {k: i.get(k) for k in ("id", "title", "tempo", "key_of")})
                if i.get("id"):
                    st2, corpo2 = pegar("https://api.getsong.co/song/?" + urllib.parse.urlencode(
                        {"api_key": gb, "id": i["id"]}), [gb])
                    try:
                        s = (json.loads(corpo2) or {}).get("song") or {}
                        print("   /song/ HTTP", st2, "->", {k: s.get(k) for k in ("tempo", "key_of", "open_key", "camelot")})
                    except Exception:
                        print("   /song/ resposta inesperada:", limpa(corpo2[:300], [gb]))
            else:
                print("   Sem resultados ou erro. Resposta:", limpa(corpo[:300], [gb]))
        except Exception:
            print("   Resposta inesperada:", limpa(corpo[:300], [gb]))
    print("\nCopie tudo isto e mande para quem está te ajudando.")


if __name__ == "__main__":
    main()
