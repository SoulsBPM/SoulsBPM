# SoulsBPM

**Use agora: https://soulsbpm.onrender.com**

Curadoria musical por **vibe**, com **transições harmoniosas**. Você descreve o clima da música em linguagem natural
(“música calma para estudar à noite”), e o SoulsBPM monta uma sequência em que
uma faixa leva à outra de forma natural, como um DJ faria, e aprende com o que você pula e curte.

> O app não toca áudio. Ele monta a ordem das faixas e o botão **Ouvir** abre a música no Spotify ou no YouTube.

## O que ele faz

- **Busca por qualquer coisa.** Digite o nome da música (ou "Artista - Música"), a banda, um trecho da letra ou o clima. Música pelo nome: a GetSongBPM acha e o app traz as do mesmo artista e de artistas parecidos; trecho de letra: a IA palpita e a GetSongBPM confirma (nada inventado). Se a música não tiver BPM/tom na fonte, o app avisa e mostra parecidas.
- **Modo DJ.** A partir de uma faixa, sugere a próxima com base em BPM (±5%, também em meio tempo e dobro), tom na roda de Camelot e energia, e mostra a **% de compatibilidade** e os motivos da sugestão.
- **Controle de BPM.** Os botões − 5 / + 5 definem um BPM alvo e a IA sugere faixas que levam o set até ele, em passos que soam naturais.
- **Aprende com você.** Curtir, aceitar, salvar e pular (antes ou depois da metade da faixa) ajustam as próximas sugestões. Vários pulos seguidos oferecem atalhos “mais calma” / “mais animada”.
- **Playlists.** Com uma conta, salve a sequência, abra depois, continue de onde parou e compartilhe por link.
- **Visão simples ou técnica.** O interruptor “Técnico” mostra BPM, tom e energia, além do gráfico da trajetória do set.
- **Privacidade.** Dá para ver o que o app aprendeu sobre você, zerar o perfil e apagar o histórico.

## Dois modos de uso

Ao entrar pela primeira vez o app pergunta como você quer usá-lo (dá para trocar a qualquer momento em **Modo** no menu; a escolha fica guardada neste navegador):

- **Para DJs.** As telas técnicas: BPM, chave Camelot, energia, trajetória do set, BPM alvo e os motivos de cada troca.
- **Para ouvir sem complicação.** Telas próprias e mais leves: escolha pelo clima (relaxar, treinar, festa…), cartões de música, uma sugestão de cada vez ("Quero esta", "Outra sugestão", "Por que esta?"), sem números nem termos técnicos. A explicação "Por que esta?" também sai em linguagem simples.

Os dois modos usam a mesma conta, as mesmas playlists e o mesmo motor de sugestão.

## Como usar

1. Abra o link e, se quiser salvar playlists, crie uma conta em *Entrar / Criar conta* (ou escolha *Continuar sem conta*).
2. Digite uma música, banda, trecho de letra ou vibe e toque em **Buscar**.
3. Em uma faixa, toque em **Criar sequência** para entrar no Modo DJ.
4. No Modo DJ, **Aceitar** passa a música sugerida para a faixa atual; **Trocar sugestão** pede outra. Cada música tem **Salvar na playlist** (depois vira “Música já salva em…”) e a faixa atual tem **Curtir**. Com conta dá para escolher uma playlist de destino: tudo que for aceito entra nela, e **Desfazer aceite** e **Voltar** também tiram a faixa. No fim, **Salvar toda a sequência** cria uma playlist nova com o set.
5. **Playlists** (precisam de conta): em *Playlists* use **Nova playlist**; nos resultados da busca use **Salvar resultados como playlist** ou o **+** de uma faixa para colocá-la em uma playlist existente (ou criar uma na hora).
6. Dentro de uma playlist dá para **Renomear**, **subir/descer** e **remover** faixas, **Continuar no Modo DJ** e **Excluir playlist**. Só o dono edita; o link compartilhado (`/p/...`) é somente leitura.
7. **Baixar CSV** ou **Copiar lista** levam a playlist ao Spotify ou ao YouTube: o CSV traz os links de busca de cada faixa e a lista (`Artista - Título`) pode ser colada em um conversor de playlists, como TuneMyMusic ou Soundiiz. A exportação é feita no navegador, sem login nessas plataformas.

## Como a próxima faixa é escolhida

A nota de cada candidata é `0,35·vibe + 0,25·BPM + 0,25·tom + 0,15·energia`, ajustada pelo perfil aprendido. Com BPM alvo,
entra o termo de **rumo** (o quanto a faixa aproxima o set do alvo) e os pesos passam a
`0,08 vibe + 0,24 BPM + 0,15 tom + 0,08 energia + 0,45 rumo`. É um recomendador por regras e pontuação, explicável,
e não uma “caixa-preta”. Os pesos `0,35 / 0,25 / 0,25 / 0,15` são o ponto de partida: com dados suficientes o app os
recalibra com uma regressão logística (ver *Onde entra a IA*). A IA de linguagem ajuda a interpretar a busca, sugerir
artistas e explicar a transição, mas não escolhe a ordem.

Feedback e peso no perfil: curtir +1,0 · salvar +1,5 · aceitar +0,5 · pular depois da metade −0,3 · pular antes −1,0.
Os pesos perdem força com o tempo (meia-vida de 30 dias) e quem é novo começa neutro.

## Onde entra a IA

Quatro recursos, todos **opcionais e com reserva**: sem chave, sem rede ou com qualquer erro, o app volta a funcionar como antes.

| Recurso | O que faz | Precisa de |
|---|---|---|
| **Interpretar a vibe** | Um modelo de linguagem traduz a frase em tags, energia e gêneros (resposta validada contra listas fixas). | uma chave de IA (Gemini, Groq, OpenRouter ou Anthropic) |
| **Sugerir artistas** | O modelo propõe até 6 artistas para a vibe. Cada nome é **confirmado na GetSongBPM** (nome quase igual, senão é descartado, o que barra artista inventado) e só entra música com BPM e tom na GetSongBPM. | a mesma chave de IA |
| **Embeddings de vibe** | Mede a proximidade de *significado* entre a frase e cada música (cosseno entre vetores) e entra com 35% na nota de vibe. Entende frases que não usam nenhuma palavra do léxico. | chave do Gemini ou do OpenRouter |
| **Explicar a transição** | O botão **Explicar com IA** pede ao modelo 1–2 frases sobre por que a próxima faixa combina. A IA só reescreve os fatos que as regras já calcularam; sem IA, a frase sai das regras. | a mesma chave de IA |
| **Aprender os pesos** | Cada aceite, curtida, salvamento e pulo vira um exemplo (vibe, BPM, tom, energia → gostou ou não). Uma **regressão logística** (Python puro, sem biblioteca) calibra o peso de cada critério. | nada (liga sozinha) |

O ranking continua sendo feito pelas regras e pela nota explicável. A IA propõe candidatos, mede significado e escreve o texto; quem escolhe a ordem é a fórmula.

**Como o aprendizado é protegido de dar errado:** só treina com pelo menos 40 exemplos e 10 de cada tipo (aceite e pulo); entra misturado com os pesos manuais, em proporção `n / (n + 150)`; peso negativo vira zero e a soma continua 1,0; com BPM alvo definido a fórmula é outra e esses gestos não contam. Os 4 pesos valem para todos (não há modelo por pessoa). `GET /api/modelo` mostra os pesos manuais, os aprendidos e quantos exemplos existem. Apagar o histórico ou zerar o perfil apaga também os exemplos da pessoa.

**Limites honestos:** os embeddings usam só "título + artista" (não ouvem o áudio nem leem a letra), então o sinal é fraco para faixas obscuras. O app só vê o que ele mesmo sugeriu, então o aprendizado tem viés de seleção; por isso é um ajuste fino sobre o prior manual, não uma troca da fórmula. A IA pode sugerir um artista que existe mas não combina; a checagem garante que ele existe, não que acertou o gosto.

## Contas e recuperação de senha

- O cadastro pede **nome**, **e-mail** e **senha** (8 a 128 caracteres). Dá para entrar com o nome ou com o e-mail.
- **Esqueci minha senha:** o app envia um link de uso único, válido por 1 hora (guardamos só o hash dele). Ao redefinir, todas as sessões abertas da conta são encerradas. A resposta é a mesma exista ou não conta com o e-mail, e há limite de 3 pedidos por hora por conta.
- **Contas criadas antes do e-mail** continuam funcionando; em *Privacidade* há **Cadastrar e-mail** (pede a senha atual).
- A senha é guardada só como hash scrypt. O banco antigo ganha a coluna `email` sozinho ao abrir.

## Privacidade

- O app guarda só **metadados** (artista, título, BPM, tom). Nenhum áudio.
- A senha é guardada apenas como hash scrypt com sal; a sessão é um cookie `HttpOnly`.
- O texto da busca é enviado ao provedor de IA de linguagem, quando ligado. Não vai nome, conta nem histórico.
  Com embeddings, também vão ao provedor o texto da busca e "título + artista" das faixas encontradas. Na explicação,
  vão título, artista, BPM, tom e energia das duas faixas.
- Para o aprendizado de pesos, o app guarda por gesto 4 números (0 a 1) e o resultado, ligados ao seu código de
  usuário só para poderem ser apagados com o histórico.
- O **e-mail** serve só para recuperar a senha. Ele só sai do app quando alguém pede a recuperação: aí vão o e-mail e o link ao serviço de envio (Brevo). Sem o serviço configurado, a recuperação fica desligada.

## Créditos

Dados de músicas, BPM e tom: [GetSongBPM](https://getsongbpm.com) (link exigido pela licença da API). Não usa Last.fm.
Fontes Barlow e Barlow Condensed (licença SIL OFL).

Projeto da disciplina Tópicos Especiais · Professor: Érico Borgonove Cruz
Equipe: Kawan Silva do Nascimento, Rafael Mateus Viana, Raimundo de Souza

---

# Parte técnica

## Rodar localmente

Requer Python 3.10+ e a chave gratuita da [GetSongBPM](https://getsongbpm.com/api).

```bash
git clone https://github.com/SoulsBPM/SoulsBPM.git
cd SoulsBPM
pip install -r requirements.txt
# crie um arquivo .env ao lado do app.py com:
#   GETSONGBPM_API_KEY=sua_chave
python app.py               # http://localhost:5000
python -m unittest discover -s tests -t .   # 382 testes
```

No Windows use `python -m pip` se o `pip` não for reconhecido; no Mac, `pip3` e `python3`.
`/api/health` mostra `"ao_vivo": true` quando as chaves estão certas; `python tools/diagnostico.py` testa cada chave.

## Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `GETSONGBPM_API_KEY` | **Obrigatória.** Sem ela o app não abre. |
| `GEMINI_API_KEY` / `GROQ_API_KEY` / `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` | Opcional: liga a IA de linguagem na busca (vale a primeira da lista; `SOULSBPM_IA_PROVEDOR` e `SOULSBPM_MODELO_IA` ajustam). |
| `DATABASE_URL` | PostgreSQL (ex.: Neon). Sem ela, usa SQLite em `data/soulsbpm.db`. |
| `SOULSBPM_IA_ARTISTAS` | Quantos artistas sugeridos pela IA entram por busca (padrão 3; `0` desliga). |
| `SOULSBPM_EMBEDDINGS=0`, `SOULSBPM_MODELO_EMB` | Desliga os embeddings / troca o modelo (padrão `gemini-embedding-001` ou `openai/text-embedding-3-small`). |
| `SOULSBPM_APRENDER=0` | Desliga o aprendizado dos pesos (volta aos pesos manuais). |
| `SOULSBPM_IA_POR_MIN` | Limite por IP de explicações por IA (padrão 30 por minuto). |
| `SOULSBPM_DATA` | Pasta do SQLite e do cache, para disco persistente. |
| `BREVO_API_KEY`, `EMAIL_REMETENTE`, `EMAIL_REMETENTE_NOME` | Opcional: liga a recuperação de senha por e-mail (Brevo, por API). O remetente precisa estar validado no Brevo. Sem elas, o link "Esqueci minha senha" não aparece. |
| `SOULSBPM_URL` | Endereço público do site (ex.: `https://seu-app.onrender.com`), usado no link do e-mail de redefinição. Sem ele, usa o endereço da requisição. |
| `EMAIL_MODO=console` | Só para testes locais: escreve o link de redefinição no terminal em vez de enviar o e-mail. |
| `SOULSBPM_EXIGIR_LOGIN=1` | Exige conta para tudo (links de playlist continuam abertos). |
| `SOULSBPM_PROXY=1` | Nº de proxies na frente (HTTPS da hospedagem). No Render já vale 1 sozinho; `0` desliga. Sem isso o limite de tentativas de login seria compartilhado por todos. |
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
soulsbpm/            engine (estados), dj (ranking), feedback, musicfinder, llm, sugestor, embeddings, narrador, aprendizado,
                     aovivo/fontes (GetSongBPM), contas, store (SQLite/Postgres), limite
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
| `POST /api/session/<id>/destination` | Define (ou tira, com `playlist_id: null`) a playlist onde o Modo DJ guarda as faixas aceitas |
| `POST /api/playlists` · `PATCH /api/playlists/<id>` · `DELETE /api/playlists/<id>` · `POST /api/playlists/<id>/tracks` | Criar, editar (nome, tags, ordem e faixas), excluir e adicionar faixa (só o dono, com login) |
| `GET/DELETE /api/profile` · `GET/DELETE /api/history` | Privacidade |
| `POST /api/session/<id>/explain` | Explica em linguagem natural por que a faixa sugerida combina (IA ou regras) |
| `GET /api/modelo` | Recursos de IA ligados e os pesos da nota (manuais x aprendidos) |
| `GET /api/health` | Estado do app (chaves, IA) |

## Limitações

- O BPM e o tom vêm da GetSongBPM (o Spotify não libera mais audio features para apps novos). Faixas sem BPM/tom lá são descartadas.
- Energia é **estimada** (BPM, gênero e, quando existe, danceability/acousticness) e a duração fica em 200 s.
- A primeira busca de uma vibe nova é a mais lenta (até ~10 s); depois o cache deixa rápido.
- Não busca por nome de música, só por vibe ou artista.
- Sem recuperação de senha, confirmação de e-mail ou exclusão de conta pela tela.
- Sessões do Modo DJ em memória (expiram após 3 h paradas); reiniciar o servidor encerra as abertas.

## Avaliar a qualidade das buscas

`python tools/avaliar_buscas.py` roda 15 buscas por fonte (músicas populares no BPM da vibe, artistas sugeridos pela IA e o combinado que o app mostra) e gera `avaliacao/avaliacao.csv`. Marque `s` ou `n` na coluna `boa` e rode `python tools/avaliar_buscas.py --resumo avaliacao/avaliacao.csv` para ver, por fonte, a porcentagem de músicas boas. Usa o cache da GetSongBPM, então repetir não gasta a cota.
