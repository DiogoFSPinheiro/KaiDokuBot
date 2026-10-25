# KaiDokuBot — Fase 3 (fotos) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Uma foto da etiqueta ou da caixa vira um pedido (nome, preço, estado, produto identificado) que o utilizador confirma com «💡 Avaliar» ou corrige.

**Architecture:** `claude.py` aceita uma imagem (bloco `image` em base64 via `--input-format stream-json`, testado na fase 0). `vision.py` tem o prompt, o esquema e a conversão pura da resposta + legenda numa `Leitura`. O pedido guarda os termos de identificação (`termos_json`) para a avaliação saltar a identificação. `commands.py` cria o pedido a partir da leitura; `telegram_bot.py` descarrega a foto e mostra o progresso.

**Spec:** `docs/superpowers/specs/2026-10-25-kaidokubot-design.md` §6.

## Global Constraints
- Iguais às fases anteriores; sem `git push`.
- Fotos **não** avaliam sozinhas; depois de uma correção, sim.
- A legenda tem prioridade sobre o que foi lido (preço e estado).

## Review Focus
1. Foto sem preço legível e sem legenda → pergunta o preço; a resposta seguinte (só um número) completa o pedido e avalia.
2. Preço lido < ¥100 ou absurdo → tratado como não lido.
3. Corrigir o nome de um pedido vindo de foto apaga a identificação guardada (senão avaliava o produto errado).
4. Falha do Claude a ler a foto → mensagem curta, sem pedido criado.
5. Imagem como ficheiro (documento) também funciona.

---

### Task 1: Claude com imagem
- `claude.mensagem_com_imagem(prompt: str, imagem: bytes, media_type: str) -> str` (linha JSON para o stdin); `ClaudeCli.run(..., imagem: bytes | None = None, media_type: str = "image/jpeg")` usa `--input-format stream-json` quando há imagem.
- Teste da linha JSON (bloco image base64 + bloco text) e do comando.

### Task 2: Leitura da foto (puro)
- `vision.py`: `SCHEMA_FOTO` (nome, fabricante, linha, personagem, referencia, termo_jp, termo_en, preco_yen, estado ∈ ESTADOS, confianca alta|media|baixa), `SYSTEM_FOTO`, `PROMPT_FOTO`; `Leitura(nome, preco_yen | None, estado, confianca, termos: dict)`; `leitura_de(dados: dict, legenda: str | None) -> Leitura` (legenda ganha; preço fora de ¥100–10M → None; estado inválido → desconhecido); `async ler_foto(runner, imagem, media_type, legenda) -> Leitura`.

### Task 3: Pedido com termos guardados
- `Storage.add_pedido(..., termos: dict | None = None)`, `get_termos(pedido_id) -> dict | None`, `set_termos(pedido_id, termos | None)` (coluna `termos_json`, com migração).
- `Commands.foto(chat_id, leitura) -> Resposta`: "📷 Percebi:" + resposta imediata + aviso se confiança baixa; botões «💡 Avaliar» / «✏️ Corrigir»; `pedido_id=None` (não avalia sozinho). Sem preço: pergunta-o e fica à espera (a resposta seguinte completa-o e devolve `pedido_id` → avalia).
- Corrigir o nome → `set_termos(pid, None)`.
- `Avaliador`: usa `get_termos` em vez de identificar, quando existem.

### Task 4: Telegram
- `MessageHandler(filters.PHOTO | filters.Document.IMAGE)`: "📷 A ler a foto…", descarrega a maior resolução, `ler_foto`, edita com o resultado; erro → "❌ Não consegui ler a foto: …".
- Teste real no PC com uma foto.
