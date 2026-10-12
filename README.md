# SoulsBPM

**Use agora: https://soulsbpm.onrender.com**

Curadoria musical por **vibe**, com **transições harmoniosas**. Você descreve o clima da música em linguagem natural
(“música calma para estudar à noite”) ou digita um artista (“tipo Calvin Harris”), e o SoulsBPM monta uma sequência em que
uma faixa leva à outra de forma natural, como um DJ faria, e aprende com o que você pula e curte.

> O app não toca áudio. Ele monta a ordem das faixas e o botão **Ouvir** abre a música no Spotify ou no YouTube.

## O que ele faz

- **Busca por vibe ou artista.** Escreva a frase do jeito que quiser; o app entende o clima, a energia e os gêneros e encontra músicas reais.
- **Modo DJ.** A partir de uma faixa, sugere a próxima com base em BPM (±5%, também em meio tempo e dobro), tom na roda de Camelot e energia, e mostra a **% de compatibilidade** e os motivos da sugestão.
- **Controle de BPM.** Os botões − 5 / + 5 definem um BPM alvo e a IA sugere faixas que levam o set até ele, em passos que soam naturais.
- **Aprende com você.** Curtir, aceitar, salvar e pular (antes ou depois da metade da faixa) ajustam as próximas sugestões. Vários pulos seguidos oferecem atalhos “mais calma” / “mais animada”.
- **Playlists.** Com uma conta, salve a sequência, abra depois, continue de onde parou e compartilhe por link.
- **Visão simples ou técnica.** O interruptor “Técnico” mostra BPM, tom e energia, além do gráfico da trajetória do set.
- **Privacidade.** Dá para ver o que o app aprendeu sobre você, zerar o perfil e apagar o histórico.

## Como usar

1. Abra o link e, se quiser salvar playlists, crie uma conta em *Entrar / Criar conta* (ou escolha *Continuar sem conta*).
2. Descreva uma vibe ou digite um artista e toque em **Buscar**.
3. Em uma faixa, toque em **Criar sequência** para entrar no Modo DJ.
4. **Aceitar**, **Pular**, **Curtir** ou **Voltar** conforme a sugestão. Quando gostar do set, **Salvar sequência**.

## Como a próxima faixa é escolhida

A nota de cada candidata é `0,35·vibe + 0,25·BPM + 0,25·tom + 0,15·energia`, ajustada pelo perfil aprendido. Com BPM alvo,
entra o termo de **rumo** (o quanto a faixa aproxima o set do alvo) e os pesos passam a
`0,08 vibe + 0,24 BPM + 0,15 tom + 0,08 energia + 0,45 rumo`. É um recomendador por regras e pontuação, explicável,
e não uma “caixa-preta”. A IA de linguagem, quando ligada, só ajuda a interpretar a frase da busca.

Feedback e peso no perfil: curtir +1,0 · salvar +1,5 · aceitar +0,5 · pular depois da metade −0,3 · pular antes −1,0.
Os pesos perdem força com o tempo (meia-vida de 30 dias) e quem é novo começa neutro.

## Privacidade

- O app guarda só **metadados** (artista, título, BPM, tom). Nenhum áudio.
- A senha é guardada apenas como hash scrypt com sal; a sessão é um cookie `HttpOnly`.
- O texto da busca é enviado ao provedor de IA de linguagem, quando ligado. Não vai nome, conta nem histórico.
- Não há recuperação de senha: quem esquecer cria outra conta.

## Créditos

Dados de BPM e tom: [GetSongBPM](https://getsongbpm.com) (link exigido pela licença da API). Descoberta de músicas: Last.fm.
Fontes Barlow e Barlow Condensed (licença SIL OFL).

Projeto da disciplina Tópicos Especiais · Professor: Érico Borgonove Cruz
Equipe: Kawan Silva do Nascimento, Rafael Mateus Viana, Raimundo de Souza

---

# Parte técnica

## Rodar localmente

Requer Python 3.10+ e as chaves gratuitas do [Last.fm](https://www.last.fm/api/account/create) e da [GetSongBPM](https://getsongbpm.com/api).

```bash
git clone https://github.com/SoulsBPM/SoulsBPM.git
cd SoulsBPM
pip install -r requirements.txt
# crie um arquivo .env ao lado do app.py com:
#   LASTFM_API_KEY=sua_chave
#   GETSONGBPM_API_KEY=sua_chave
python app.py               # http://localhost:5000
python -m unittest discover -s tests -t .   # 176 testes
```

No Windows use `python -m pip` se o `pip` não for reconhecido; no Mac, `pip3` e `python3`.
`/api/health` mostra `"ao_vivo": true` quando as chaves estão certas; `python tools/diagnostico.py` testa cada chave.

## Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `LASTFM_API_KEY`, `GETSONGBPM_API_KEY` | **Obrigatórias.** Sem elas o app não abre. |
| `GEMINI_API_KEY` / `GROQ_API_KEY` / `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` | Opcional: liga a IA de linguagem na busca (vale a primeira da lista; `SOULSBPM_IA_PROVEDOR` e `SOULSBPM_MODELO_IA` ajustam). |
| `DATABASE_URL` | PostgreSQL (ex.: Neon). Sem ela, usa SQLite em `data/soulsbpm.db`. |
| `SOULSBPM_DATA` | Pasta do SQLite e do cache, para disco persistente. |
| `SOULSBPM_EXIGIR_LOGIN=1` | Exige conta para tudo (links de playlist continuam abertos). |
| `SOULSBPM_PROXY=1` | Nº de proxies na frente (HTTPS da hospedagem). |
| `SOULSBPM_BUSCAS_POR_MIN`, `SOULSBPM_LOGINS_POR_MIN` | Limites por IP (padrão 20 buscas e 10 logins por minuto). |
| `PORT`, `HOST` | Porta (padrão 5000) e interface (padrão `127.0.0.1`). |

Nunca suba o `.env` para o Git (o `.gitignore` já o ignora).

## Publicação

Comando de início: `python app.py` (servidor waitress, a hospedagem define `PORT`). **Rode uma instância só**: as sessões do
Modo DJ ficam em memória. Use `DATABASE_URL` para contas e playlists não sumirem quando a hospedagem reinicia.
Cadastre o endereço público no painel da GetSongBPM (o link de retorno é obrigatório). A cota dela (3000 consultas/h) é de
todos os visitantes juntos; o app para em 2500/h e passa a usar só o cache.

## Estrutura

```
app.py               servidor Flask (rotas, login, limites)
soulsbpm/            engine (estados), dj (ranking), feedback, musicfinder, llm,
                     aovivo/fontes (Last.fm e GetSongBPM), contas, store (SQLite/Postgres), limite
static/              interface (index, login, app.js, CSS, fontes)
tests/               testes automatizados (unittest)
tools/               diagnósticos das APIs e importador de catálogo
```

## API

| Método e rota | Função |
|---|---|
| `POST /api/search` `{text}` | Interpreta a vibe e devolve resultados |
| `POST /api/session/<id>/play` `{track_id}` | Entra no Modo DJ e sugere a próxima |
| `POST /api/session/<id>/accept` · `/undo-accept` · `/back` | Aceitar, desfazer aceite, voltar à faixa anterior |
| `POST /api/session/<id>/skip` `{target, elapsed_fraction}` | Pular e trocar na hora |
| `POST /api/session/<id>/bpm` `{delta}` ou `{target}` ou `{auto: true}` | BPM alvo (50–200) ou volta ao automático |
| `POST /api/session/<id>/like` · `/adjust` `{direction}` · `/save` `{title, tags}` | Curtir (de novo descurte), ajustar a vibe, salvar |
| `GET /api/playlists` · `/api/playlists/<id>` · `POST /api/playlists/<id>/continue` | Playlists |
| `GET/DELETE /api/profile` · `GET/DELETE /api/history` | Privacidade |
| `GET /api/health` | Estado do app (chaves, IA) |

## Limitações

- O BPM e o tom vêm da GetSongBPM (o Spotify não libera mais audio features para apps novos). Faixas sem BPM/tom lá são descartadas.
- Energia é **estimada** (BPM, gênero e, quando existe, danceability/acousticness) e a duração fica em 200 s.
- A primeira busca de uma vibe nova é a mais lenta (até ~10 s); depois o cache deixa rápido.
- Não busca por nome de música, só por vibe ou artista.
- Sem recuperação de senha, confirmação de e-mail ou exclusão de conta pela tela.
- Sessões do Modo DJ em memória (expiram após 3 h paradas); reiniciar o servidor encerra as abertas.
