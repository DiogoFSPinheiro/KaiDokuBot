from __future__ import annotations

import asyncio
import base64
import json
import logging
import subprocess
import threading
from collections.abc import Callable, Iterable

log = logging.getLogger(__name__)

TIMEOUT_S = 300


class ClaudeError(Exception):
    pass


def ler_stream(linhas: Iterable[str], on_search: Callable[[str], None] | None) -> dict:
    """Lê os eventos do `claude -p --output-format stream-json`; devolve o structured_output do resultado."""
    resultado = None
    for linha in linhas:
        if not linha.strip():
            continue
        try:
            evento = json.loads(linha)
        except ValueError:
            log.debug("Linha inesperada do claude: %s", linha[:200])
            continue
        if evento.get("type") == "assistant" and on_search is not None:
            for bloco in (evento.get("message") or {}).get("content") or []:
                if bloco.get("type") == "tool_use" and bloco.get("name") == "WebSearch":
                    query = (bloco.get("input") or {}).get("query")
                    if query:
                        on_search(query)
        elif evento.get("type") == "result":
            resultado = evento
    if resultado is None:
        raise ClaudeError("sem resposta do Claude")
    if resultado.get("is_error") or not isinstance(resultado.get("structured_output"), dict):
        motivo = resultado.get("result") or resultado.get("subtype")
        raise ClaudeError(f"o Claude falhou: {str(motivo)[:200]}")
    return resultado["structured_output"]


def mensagem_com_imagem(prompt: str, imagem: bytes, media_type: str) -> str:
    """Mensagem do utilizador (uma linha JSON) com a imagem e o texto, para `--input-format stream-json`."""
    conteudo = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                     "data": base64.b64encode(imagem).decode()}},
        {"type": "text", "text": prompt},
    ]  # fmt: skip
    return json.dumps({"type": "user", "message": {"role": "user", "content": conteudo}}) + "\n"


class ClaudeCli:
    """Corre o Claude CLI em modo não interativo, com a subscrição de quem tem sessão iniciada."""

    def __init__(self, binary: str, model: str, timeout_s: int = TIMEOUT_S) -> None:
        self._binary = binary
        self._model = model
        self._timeout_s = timeout_s

    def _cmd(self, schema: dict, system: str, tools: str, com_imagem: bool = False) -> list[str]:
        # `--bare` não serve (exige ANTHROPIC_API_KEY); estas opções tornam a chamada leve.
        cmd = [
            self._binary, "-p",
            "--model", self._model,
            "--output-format", "stream-json", "--verbose",
            "--tools", tools,
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--setting-sources", "",
            "--system-prompt", system,
            "--json-schema", json.dumps(schema, ensure_ascii=False),
        ]  # fmt: skip
        if tools:
            cmd[cmd.index("--strict-mcp-config") : cmd.index("--strict-mcp-config")] = ["--allowedTools", tools]
        if com_imagem:
            # A imagem vai no stdin, como mensagem JSON (sem ficheiros nem a ferramenta Read).
            cmd += ["--input-format", "stream-json"]
        return cmd

    def _correr(self, cmd: list[str], prompt: str, on_search: Callable[[str], None] | None) -> dict:
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8",
            )  # fmt: skip
        except FileNotFoundError as exc:
            raise ClaudeError("não encontrei o comando claude") from exc
        expirou = threading.Event()

        def matar() -> None:
            expirou.set()
            proc.kill()

        timer = threading.Timer(self._timeout_s, matar)
        timer.start()
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            try:
                return ler_stream(proc.stdout, on_search)
            except ClaudeError:
                if expirou.is_set():
                    raise ClaudeError("o Claude demorou demasiado") from None
                proc.wait(timeout=5)
                log.warning("claude terminou com código %s: %s", proc.returncode, proc.stderr.read()[:500])
                raise
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
            proc.wait()

    async def run(
        self, prompt: str, schema: dict, *, system: str, tools: str = "",
        on_search: Callable[[str], None] | None = None, imagem: bytes | None = None, media_type: str = "image/jpeg",
    ) -> dict:  # fmt: skip
        loop = asyncio.get_running_loop()
        avisar = None
        if on_search is not None:

            def avisar(query: str) -> None:
                loop.call_soon_threadsafe(on_search, query)

        # Numa thread: o event loop Selector do Windows não suporta subprocessos asyncio.
        if imagem is not None:
            prompt = mensagem_com_imagem(prompt, imagem, media_type)
        cmd = self._cmd(schema, system, tools, com_imagem=imagem is not None)
        return await asyncio.to_thread(self._correr, cmd, prompt, avisar)
