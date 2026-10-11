# SoulsBPM – MVP

Curadoria musical por **vibe** em linguagem natural, com **transições harmoniosas** (BPM ±5%, escala de
Camelot e energia) e **aprendizado** a partir de pulos, curtidas e playlists salvas.

> Disciplina: Tópicos Especiais · Professor: Érico Borgonove Cruz
> Equipe: Kawan Silva do Nascimento, Rafael Mateus Viana, Raimundo de Souza

> Dados de BPM e tom: [GetSongBPM](https://getsongbpm.com) (link exigido pela licença da API).

## Como rodar

PASSO A PASSO – RODAR O SOULSBPM

ANTES DE COMEÇAR
- Instale o Python (versão 3.10 ou mais nova) em python.org
- No Windows, marque a opção "Add Python to PATH" durante a instalação

1) DESCOMPACTAR
- Extraia o arquivo SoulsBPM-completo.zip numa pasta
  (ex.: Área de Trabalho). Vai surgir a pasta "SoulsBPM".

2) ABRIR O TERMINAL NA PASTA
- Windows: abra a pasta SoulsBPM, clique na barra de endereço,
  digite  cmd  e aperte Enter.
- Mac: clique com o botão direito na pasta SoulsBPM e escolha
  "Nova janela de Terminal na pasta".

3) INSTALAR (só na primeira vez)
   pip install -r requirements.txt
- Se der erro de "pip não reconhecido", use:
   python -m pip install -r requirements.txt
- No Mac, troque pip por pip3 e python por python3.

4) LIGAR O SERVIDOR
   python app.py
- Deixe essa janela aberta enquanto usa.

5) ABRIR NO NAVEGADOR
   http://localhost:5000

6) USAR O APP
- Clique em "Pode lembrar".
- Digite: música calma para estudar à noite  -> Buscar
- Clique em "Tocar" numa faixa (entra no Modo DJ).
- Aceitar = segue a sugestão (dá para Desfazer aceite logo em seguida)
- Trocar sugestão / Pular = rejeita (a IA aprende)
- Curtir = reforça o gosto (tocar de novo em Curtir descurte)
- Ligue o interruptor "Técnico" (topo) para ver BPM, tom e energia.
- Aceite ao menos 1 sugestão e clique em "Salvar sequência"
  para gerar o link da playlist.

7) DESLIGAR
- No terminal, aperte  Ctrl + C

8) RODAR OS TESTES (opcional)
   python -m unittest discover -s tests -t .
- Deve aparecer "OK" no final (107 testes).

Resumo:
```bash
pip install -r requirements.txt     # só o Flask
python app.py                       # http://localhost:5000
python -m unittest discover -s tests -t .   # 107 testes
```

Variáveis opcionais: `PORT` (padrão 5000) e `SOULSBPM_DB` (caminho do SQLite, padrão `data/soulsbpm.db`).

## O que o MVP faz

| Funcionalidade | Onde está | Documento |
|---|---|---|
| Busca por vibe em linguagem natural (“música calma para estudar à noite”) | `soulsbpm/musicfinder.py` | 3 (evento 1), 5 |
| Próxima faixa por BPM ±5% (com meio tempo e dobro), Camelot e energia, com **% de compatibilidade** | `soulsbpm/dj.py` | 3 (evento 2), 5 (4.2) |
| Nota `0,35·vibe + 0,25·BPM + 0,25·tom + 0,15·energia`, ajustada pelo perfil | `dj.rank_next` | 5 (4.2) |
| Feedback: curtir +1,0 · salvar +1,5 · aceitar +0,5 · pular depois da metade −0,3 · pular antes −1,0 | `soulsbpm/feedback.py` | 5 (4.2) |
| Pulo: transição ruim → peso do par A→B; transição boa → associação vibe↔faixa | `feedback.registrar_pulo` | 5 (4.2) |
| Pesos que perdem força com o tempo (meia-vida de 30 dias); usuário novo neutro | `feedback.efetivo` | 5 (4.2) |
| **Controle de BPM + IA do DJ**: botões − 5 / + 5 definem um BPM alvo; a IA passa a sugerir faixas que levam o set até ele, em passos que respeitam BPM ±5% e chave | `dj.rumo_score`, `engine.ajustar_bpm`, `static/app.js` | extensão do MVP |
| **“Por que a IA sugeriu”**: cada sugestão vem com os motivos (BPM, chave, rumo ao alvo, energia, vibe) | `dj.explicar` | extensão do MVP |
| Estados e eventos (Início → Buscando → Resultados → Tocando → Sugerindo → Reajustando → Salvando → Playlist salva) | `soulsbpm/engine.py` | 3, 4 |
| Decisões D1 (vibe pouco clara), D2 (transição arriscada), D3 (aceitar/pular), D4 (sem resultados), D5 (salvar) | `engine.py`, `dj.classificar` | 4 |
| Vários pulos seguidos → atalhos “mais calma” / “mais animada” | `engine.ajustar` | 4 (5), 6 (4) |
| Visão simples × técnica; aviso de “transição arriscada” | `static/` | 6 |
| Salvar sequência, link para exportar, reabrir e continuar playlist | `engine.salvar`, `/p/<id>` | 3 (evento 4), 6 |
| Grafo global só com **pares de faixas** | `store.py` (tabela `graph`) | 5 (5) |
| LGPD: consentimento, ver o que foi aprendido, zerar perfil, apagar histórico | `app.py`, `static/app.js` | 5 (5) |
| Só metadados, nenhum áudio | `data/catalog.json` | 2, 5 |

### API

| Método e rota | Função |
|---|---|
| `POST /api/search` `{text}` | Interpreta a vibe e devolve resultados (ou D1/D4) |
| `POST /api/session/<id>/play` `{track_id}` | Entra no Modo DJ e sugere a próxima |
| `POST /api/session/<id>/accept` | Aceita a sugestão |
| `POST /api/session/<id>/undo-accept` | Desfaz o último aceite (a faixa volta a ser a sugestão) |
| `POST /api/session/<id>/skip` `{target: atual\|sugestao, elapsed_fraction}` | Pula e troca na hora |
| `POST /api/session/<id>/bpm` `{delta}` ou `{target}` ou `{auto: true}` | Define/ajusta o BPM alvo (50–200) ou volta ao automático; devolve nova sugestão |
| `POST /api/session/<id>/like` (curtir; chamar de novo descurte) · `/adjust` `{direction}` · `/save` `{title, tags}` | Curtir, ajustar a vibe, salvar |
| `GET /api/playlists` · `/api/playlists/<id>` · `POST /api/playlists/<id>/continue` | Playlists |
| `GET/DELETE /api/profile` · `GET/DELETE /api/history` | Privacidade |

Cada resposta do Modo DJ traz `caminho_estados` e `eventos`, o que permite acompanhar o diagrama de estados
do documento 4 em funcionamento.

## Interface

**Visual de console de DJ** (modo escuro e modo claro: o botão de tema fica dentro do menu em painel, que abre pelo botão do topo e fecha ao tocar fora, com Esc ou ao escolher uma opção; sem escolha salva o app segue o tema do sistema): noite violeta, índigo da marca nas ações e âmbar só para BPM e alvo,
como o visor de um CDJ. A peça principal é a **trajetória do set**, um gráfico do BPM faixa a faixa com a linha do
alvo, a faixa de ±5% onde a próxima troca soa natural e o ponto que a IA sugere. As chaves aparecem como selos
coloridos da roda de Camelot, a energia como medidor e os resultados como uma tabela de biblioteca.

**Responsiva:** no celular é uma coluna única com abas embaixo (Buscar · Playlists · Privacidade) e os botões
Pular / Curtir / Aceitar fixos no rodapé do Modo DJ; no PC (a partir de 900 px) o
Modo DJ mostra “Tocando agora” e “Próxima sugerida” lado a lado. Todas as telas internas têm o botão **Voltar**
(Resultados → Início, Modo DJ → Resultados/Playlist, Salvar → Modo DJ, Playlist → Playlists); ao sair do Modo DJ
com uma sequência não salva o app pede confirmação.

A interface segue os protótipos do Figma do documento 6: tema claro em formato de celular (no desktop aparece
como uma coluna centralizada), índigo `#3b2f9e`, cartão cinza “Tocando agora”, cartão azul “Próxima sugerida”,
selos verde (“combina bem”) e amarelo (“Transição arriscada”), botões Pular / Curtir / Aceitar, barra de abas
Buscar / Playlists e as telas Início, Interpretando, Sem resultados, Modo DJ (simples e técnico), Salvar
sequência, Sequência guardada e Playlists.

Pontos que **não** estão no Figma e foram acrescentados no mesmo estilo: a lista de **Resultados** (existe no
documento 6, mas não nos protótipos), o interruptor **Técnico** no topo do Modo DJ (no Figma a visão técnica
aparece como outra tela), o atalho **Trocar sugestão** (recusar a sugestão sem tocá-la, decisão D3), o cartão
“Quer ajustar a vibe?” e o diálogo de **Privacidade**.

As fontes são a Barlow e a Barlow Condensed (licença SIL OFL), incluídas em `static/fonts/` para funcionar sem internet.

## Músicas reais, sem lista pronta (modo ao vivo)

Com duas chaves gratuitas no ambiente, o app deixa de usar as 60 faixas fictícias: a pessoa descreve a vibe e ele
busca **músicas reais** sozinho. Cada busca faz isto: interpreta a vibe → traduz para tags do **Last.fm** →
pega as músicas populares dessas tags → consulta **BPM e tom na GetSongBPM** (com cache) → entra no Modo DJ.
As faixas descobertas ficam guardadas no banco (só metadados), então playlists salvas reabrem depois.

1. Chave do Last.fm: https://www.last.fm/api/account/create (gratuita).
2. Chave da GetSongBPM: https://getsongbpm.com/api (gratuita; exige link visível para getsongbpm.com, que o app
   mostra em *Privacidade* quando o modo ao vivo está ligado).
3. Rodar:
   ```bash
   export LASTFM_API_KEY=sua_chave_lastfm          # Windows (cmd): set LASTFM_API_KEY=...
   export GETSONGBPM_API_KEY=sua_chave_getsongbpm  # Windows (cmd): set GETSONGBPM_API_KEY=...
   python app.py
   ```
   Sem as duas chaves o app continua no catálogo de amostra. `/api/health` mostra `"ao_vivo": true/false`.

Como funciona na prática e limites:
- A **primeira busca de uma vibe nova é a mais lenta** (uma consulta de BPM por faixa, até ~10 s; o que não
  terminar continua em segundo plano e aparece na próxima busca). Depois o cache deixa rápido.
- O Modo DJ sugere a partir das faixas já descobertas: quanto mais buscas, mais rico o "repertório".
- Last.fm não traz BPM nem duração e a GetSongBPM não traz energia: a **energia é estimada** (BPM, gênero e, quando a API traz, danceability e acousticness), a
  duração fica em 200 s e faixas sem BPM/tom na GetSongBPM são descartadas. A reprodução continua simulada.
- A tradução vibe → tag do Last.fm está em `soulsbpm/aovivo.py` (`TAG_LASTFM`, `GENERO_LASTFM`) e pode ser ajustada.
- A GetSongBPM limita a 3000 consultas/hora (acima disso bloqueia a chave por 1 h); o app para em 2500/h e passa a usar só o cache.
- Ainda não busca por **nome de música ou artista** (só por vibe e gênero).
- Código testado só com respostas simuladas; o formato real das duas APIs deve ser conferido na primeira execução.

### Alternativa: catálogo próprio a partir de uma lista (opcional)

Se preferir controlar as músicas, `python tools/importar_catalogo.py --entrada data/minhas_faixas.csv` (modelo em
`data/minhas_faixas.exemplo.csv`) gera `data/catalog.real.json` só com a GetSongBPM (chave `GETSONGBPM_API_KEY`), e
`SOULSBPM_CATALOG=data/catalog.real.json python app.py` usa esse arquivo.

## Limitações do MVP (o que **não** foi feito)

- **Sem Spotify/Last.fm.** O documento 5 já aponta que o Spotify não libera mais audio features para apps
  novos e que o Last.fm não fornece BPM nem tom. O MVP usa um **catálogo local de amostra** (60 faixas e artistas
  **fictícios**, gerado por `tools/make_catalog.py`). Trocar por uma fonte real é implementar a camada de
  integrações com cache; o formato da faixa já é o necessário (`bpm`, `tom`, `energia`, `generos`, `tags`).
- **MusicFinder por léxico em português**, não por um modelo de linguagem. Entende um vocabulário limitado
  (estudar, treinar, festa, triste, jazz, noite…). Está isolado em `interpretar()` para ser trocado por uma API
  de linguagem natural sem mexer no resto.
- **Reprodução simulada** (sem áudio, por direitos autorais). A barra de progresso é acelerada só para
  demonstrar a diferença entre pular antes e depois da metade.
- **Sessões em memória** (o documento 5 sugere Redis) e **SQLite** no lugar do PostgreSQL. Reiniciar o
  servidor encerra as sessões abertas; perfis, histórico e playlists continuam salvos.
- O usuário é identificado por um código aleatório no navegador, só depois do consentimento. Não há login:
  quem tiver o código de outra pessoa lê o perfil e o histórico dela.
- Sessões em memória não expiram (acumulam com o uso) e `app.py` escuta em `0.0.0.0`, então qualquer pessoa na
  mesma rede acessa o app. Para produção, usar login, expiração de sessão e `127.0.0.1`/proxy.

## IA do DJ e BPM alvo

Sem BPM alvo a nota é a do documento 5 (`0,35·vibe + 0,25·BPM + 0,25·tom + 0,15·energia`, ajustada pelo perfil).
Quando o DJ aperta **+ 5 / − 5**, entra o termo de **rumo** (`dj.rumo_score`: o quanto a candidata aproxima o set do
alvo) e os pesos passam a `0,08 vibe + 0,24 BPM + 0,15 tom + 0,08 energia + 0,45 rumo`. Nesse modo:

- a vibe deixa de filtrar o catálogo (um set calmo pode subir até a pista), vira só um critério;
- meio tempo/dobro não conta como transição (130 → 65 não leva o set a 98 BPM);
- o perfil aprendido pesa 30% do normal, para o gosto passado não puxar o set de volta.

Os pesos foram escolhidos numa varredura em 6 vibes, subindo e descendo: com `W_RUMO = 0,45` nenhum passo foi na
direção errada, a compatibilidade média ficou em ~71% (a fórmula original dá ~72%) e as transições “arriscadas”
caíram de 18 para 9 em 60. É um recomendador por regras e pontuação, **não** um modelo de linguagem; a camada
`dj.rank_next` pode ser trocada por um modelo treinado ou uma API sem mexer no resto. Com só 60 faixas fictícias
há “buracos” de BPM, então a IA às vezes precisa de uma faixa de transição antes de subir mais.

## Calibração

Os pesos do documento 5 foram mantidos. O único valor definido durante o MVP foi o **teto do ajuste do perfil
sobre a nota** (`dj.PROFILE_RANGE = ±0,25`). Com ±0,15 um pulo forte não conseguia tirar do topo uma faixa com
compatibilidade técnica muito alta; o teste `test_aprendizado_muda_as_proximas_sugestoes` cobre esse caso.

## Roteiro de demonstração (3 minutos)

1. Aceitar o consentimento e buscar **“música calma para estudar à noite”**. Mostrar a frase interpretada.
2. Tocar a primeira faixa e ligar o **Modo técnico**: BPM, tom e a % de compatibilidade da próxima.
3. **Aceitar** duas vezes e **Curtir** uma faixa.
4. Clicar em **Trocar sugestão** três vezes: aparecem os atalhos “mais calma / mais animada”.
5. **Salvar sequência**, copiar o link e abri-lo em outra aba.
6. Em **Privacidade**, mostrar o que foi aprendido e apagar o histórico.
7. Buscar `asdf` para mostrar o caso de vibe pouco clara (D1).
