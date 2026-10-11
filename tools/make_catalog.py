"""Gera data/catalog.json: catálogo de AMOSTRA com faixas e artistas FICTÍCIOS.

Só metadados (BPM, tom em Camelot, energia, gêneros e tags de clima); nunca áudio.
No produto real estes campos viriam das integrações (Spotify/Last.fm/fonte de BPM).
Execução: python tools/make_catalog.py
"""
import json, random, pathlib

rng = random.Random(42)

# cada grupo: faixas (títulos), faixa de BPM, faixa de energia, tons Camelot, gêneros e tags
GRUPOS = [
 dict(titulos=["Névoa de Domingo","Café Frio","Papel de Parede","Luz de Abajur","Fita Cassete","Janela Aberta"],
      bpm=(70,88), energia=(.18,.34), tons=["8A","9A","7A","8B"], generos=["lofi","chillhop"],
      tags=["calma","foco","noite","relaxar"], artistas=["Lumo Verde","Sala 12","Maré Baixa"]),
 dict(titulos=["Respirar Fundo","Lago Parado","Hora Azul","Quarto Escuro","Sono Leve","Dunas"],
      bpm=(58,74), energia=(.08,.2), tons=["6A","7A","5A","6B"], generos=["ambient","instrumental"],
      tags=["calma","dormir","noite","relaxar","meditar"], artistas=["Aurora Seca","Neblina","Ninho de Vento"]),
 dict(titulos=["Carta Sem Resposta","Chuva no Vidro","Cadeira Vazia","Saudade de Ontem","Voz Rouca","Último Ônibus"],
      bpm=(72,98), energia=(.26,.45), tons=["5A","6A","4A","5B"], generos=["mpb","indie","acustico"],
      tags=["triste","melancolia","chuva","saudade","romantico"], artistas=["Clara Vento","Joaquim Brasa","Dora Lume"]),
 dict(titulos=["Sol na Estrada","Janela Baixa","Vento a Favor","Bom Dia, Cidade","Horizonte Aberto","Praia Cheia"],
      bpm=(100,118), energia=(.58,.72), tons=["8B","9B","10B","7B"], generos=["pop","indie"],
      tags=["feliz","animada","manha","dirigir","viagem"], artistas=["Tiê Solar","Bruna Alto","Os Girassóis"]),
 dict(titulos=["Ferro e Suor","Última Série","Sem Freio","Corrida Contra o Relógio","Adrenalina 04","Levanta e Vai"],
      bpm=(126,150), energia=(.84,.96), tons=["4A","5A","3A","4B"], generos=["eletronica","hiphop","rock"],
      tags=["treino","energia","motivacao","correr","animada"], artistas=["Voltagem","Peso Morto","Zé Cardio"]),
 dict(titulos=["Pista Cheia","Neon 128","Corpo e Som","Madrugada Dourada","Batida Quente","Luzes na Pista"],
      bpm=(120,128), energia=(.78,.9), tons=["8A","9A","7A","8B"], generos=["house","eletronica"],
      tags=["festa","danca","balada","animada","noite"], artistas=["DJ Cobalto","Kiara Beat","Dois Mil e Vinte"]),
 dict(titulos=["Domingo de Churrasco","Roda de Samba","Mesa Posta","Cerveja Gelada","Quintal em Festa","Gargalhada"],
      bpm=(88,104), energia=(.55,.72), tons=["10B","9B","11B","8B"], generos=["pagode","samba","forro"],
      tags=["festa","churrasco","amigos","feliz","danca"], artistas=["Grupo Quintal","Nenê da Viola","Samba de Esquina"]),
 dict(titulos=["Jantar às Oito","Xícara de Prata","Noite em Ipanema Velha","Piano e Chuva Fina","Mesa de Canto","Tarde Dourada"],
      bpm=(80,110), energia=(.28,.5), tons=["8B","9B","7B","8A"], generos=["jazz","bossa"],
      tags=["calma","jantar","cafe","romantico","relaxar","tarde"], artistas=["Trio Lírio","Marina Sax","Duo Veludo"]),
 dict(titulos=["Estrada de Fogo","Amplificador","Velha Garagem","Riff de Verão","Pedal Torto","Motor Ligado"],
      bpm=(110,140), energia=(.7,.88), tons=["4A","5A","6A","3A"], generos=["rock"],
      tags=["energia","dirigir","raiva","nostalgia","animada"], artistas=["Os Parafusos","Garagem 77","Fusível"]),
 dict(titulos=["Linha de Código","Pulso Contínuo","Mesa Limpa","Zona Cinza","Tela Dupla","Prazo Final"],
      bpm=(118,126), energia=(.5,.62), tons=["8A","9A","7A","10A"], generos=["techno","eletronica","instrumental"],
      tags=["foco","trabalhar","concentracao","calma"], artistas=["Eixo","Matriz 9","Pixel Norte"]),
]

faixas = []
n = 1
for g in GRUPOS:
    for t in g["titulos"]:
        faixas.append(dict(
            id=f"t{n:03d}", titulo=t, artista=rng.choice(g["artistas"]),
            bpm=rng.randint(*g["bpm"]), tom=rng.choice(g["tons"]),
            energia=round(rng.uniform(*g["energia"]), 2),
            generos=g["generos"], tags=g["tags"],
            duracao=rng.randint(150, 260)))
        n += 1

out = pathlib.Path(__file__).resolve().parent.parent / "data" / "catalog.json"
out.write_text(json.dumps(faixas, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(faixas), "faixas ->", out)
