/* Exportar playlist: gera CSV e lista em texto no navegador (sem login nas plataformas, nada é enviado ao servidor).
   O CSV leva links de busca no Spotify e no YouTube; a lista "Artista - Título" serve para colar em conversores de playlist. */
(function (raiz) {
  const q = f => encodeURIComponent(`${f.artista} ${f.titulo}`.trim());
  const linkSpotify = f => "https://open.spotify.com/search/" + q(f);
  const linkYoutube = f => "https://www.youtube.com/results?search_query=" + q(f);

  /* célula de CSV: aspas quando preciso e, contra "injeção de fórmula" no Excel, texto que começa com = + - @ ganha um ' */
  function celula(v) {
    let s = String(v ?? "");
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return /[",;\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function csvDaPlaylist(p) {
    const cab = ["posicao", "artista", "titulo", "bpm", "tom", "link_spotify", "link_youtube"];
    const linhas = p.faixas.map((f, i) => [i + 1, f.artista, f.titulo, f.bpm, f.tom, linkSpotify(f), linkYoutube(f)].map(celula).join(","));
    return "﻿" + [cab.join(","), ...linhas].join("\r\n") + "\r\n";      // BOM: o Excel abre os acentos certos
  }

  function textoDaPlaylist(p) {
    return p.faixas.map(f => `${f.artista} - ${f.titulo}`).join("\n");
  }

  function nomeDoArquivo(p) {
    const base = String(p.title || "playlist").normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
    return (base || "playlist") + ".csv";
  }

  const api = { csvDaPlaylist, textoDaPlaylist, nomeDoArquivo, linkSpotify, linkYoutube };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else raiz.Exportar = api;
})(typeof window !== "undefined" ? window : globalThis);
