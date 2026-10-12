"""Testa a IA do MusicFinder e mostra o erro exato, se houver (a chave nunca é impressa).

Uso (PowerShell):
    $env:GEMINI_API_KEY="sua_chave"      # ou GROQ_API_KEY / OPENROUTER_API_KEY / ANTHROPIC_API_KEY
    python tools/diagnostico_ia.py "música pra chorar no ônibus"
"""
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from soulsbpm import llm  # noqa: E402


def main():
    ia = llm.do_ambiente()
    if ia is None:
        print("Nenhuma chave de IA encontrada. Defina GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY ou ANTHROPIC_API_KEY.")
        return 1
    texto = " ".join(sys.argv[1:]) or "música pra chorar no ônibus voltando da faculdade"
    print(f"Provedor: {ia.provedor} | modelo: {ia.modelo}\nFrase: {texto}")
    try:
        resp = ia._http(ia._corpo(texto), ia._chave, ia.timeout)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")[:600].replace(ia._chave, "***")
        print(f"ERRO HTTP {e.code}: {corpo}")
        if e.code in (400, 404):
            print("Dica: o nome do modelo pode estar errado. Defina SOULSBPM_MODELO_IA com um modelo válido do provedor.")
        if e.code in (401, 403):
            print("Dica: chave inválida ou sem permissão.")
        if e.code == 429:
            print("Dica: limite gratuito atingido; espere um pouco.")
        return 2
    except Exception as e:
        print(f"ERRO: {type(e).__name__}: {e}".replace(ia._chave, "***"))
        return 2
    bruto = llm._texto_da_resposta(resp)
    print("Resposta do modelo:", bruto[:300].replace("\n", " "))
    r = llm.validar(llm._json_da_resposta(bruto))
    print("Validado:", r if r else "INVÁLIDO (o app usaria o léxico)")
    return 0 if r else 3


if __name__ == "__main__":
    sys.exit(main())
