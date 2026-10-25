from __future__ import annotations

import sqlite3
import time
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from kaidokubot.parsing import Pedido

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    preco_yen INTEGER NOT NULL,
    estado TEXT NOT NULL,
    criado_em REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS avaliacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    pedido_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    preco_yen INTEGER NOT NULL,
    estado TEXT NOT NULL,
    chave TEXT NOT NULL,
    mercado_json TEXT NOT NULL,
    veredicto TEXT NOT NULL,
    da_cache INTEGER NOT NULL,
    criado_em REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS avaliacoes_chave ON avaliacoes (chave, criado_em);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

TOKYO = ZoneInfo("Asia/Tokyo")


def chave_cache(nome: str, estado: str) -> str:
    """Mesmo artigo e estado, independentemente de maiúsculas, acentos, largura e espaços."""
    texto = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", nome).lower())
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return f"{' '.join(texto.split())}|{estado}"


def inicio_do_dia_tokyo(agora: float) -> float:
    """Meia-noite de hoje em Tóquio (o limite diário de avaliações vira a essa hora)."""
    dia = datetime.fromtimestamp(agora, TOKYO).replace(hour=0, minute=0, second=0, microsecond=0)
    return dia.timestamp()


class Storage:
    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def add_pedido(self, chat_id: int, pedido: Pedido, now: float | None = None) -> int:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO pedidos (chat_id, nome, preco_yen, estado, criado_em) VALUES (?, ?, ?, ?, ?)",
                (chat_id, pedido.nome, pedido.preco_yen, pedido.estado, time.time() if now is None else now),
            )
        return cur.lastrowid

    def get_pedido(self, pedido_id: int) -> Pedido | None:
        row = self._db.execute("SELECT nome, preco_yen, estado FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        return Pedido(row["nome"], row["preco_yen"], row["estado"]) if row else None

    def update_pedido(self, pedido_id: int, pedido: Pedido) -> None:
        with self._db:
            self._db.execute(
                "UPDATE pedidos SET nome = ?, preco_yen = ?, estado = ? WHERE id = ?",
                (pedido.nome, pedido.preco_yen, pedido.estado, pedido_id),
            )

    def add_avaliacao(
        self, chat_id: int, pedido_id: int, pedido: Pedido, chave: str, mercado_json: str, veredicto: str,
        da_cache: bool, now: float | None = None,
    ) -> int:  # fmt: skip
        with self._db:
            cur = self._db.execute(
                "INSERT INTO avaliacoes (chat_id, pedido_id, nome, preco_yen, estado, chave, mercado_json, veredicto, "
                "da_cache, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (chat_id, pedido_id, pedido.nome, pedido.preco_yen, pedido.estado, chave, mercado_json, veredicto,
                 int(da_cache), time.time() if now is None else now),
            )  # fmt: skip
        return cur.lastrowid

    def cache(self, chave: str, desde: float) -> tuple[str, float] | None:
        """Dados de mercado da avaliação mais recente (feita de raiz) desde `desde`: (json, criado_em)."""
        row = self._db.execute(
            "SELECT mercado_json, criado_em FROM avaliacoes WHERE chave = ? AND da_cache = 0 AND criado_em >= ? "
            "ORDER BY criado_em DESC LIMIT 1",
            (chave, desde),
        ).fetchone()
        return (row["mercado_json"], row["criado_em"]) if row else None

    def contar_avaliacoes(self, desde: float) -> int:
        """Avaliações feitas pelo Claude (as da cache não contam) desde `desde`."""
        row = self._db.execute(
            "SELECT COUNT(*) FROM avaliacoes WHERE da_cache = 0 AND criado_em >= ?", (desde,)
        ).fetchone()
        return row[0]

    def ultimas_avaliacoes(self, n: int) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT nome, preco_yen, estado, veredicto, da_cache, criado_em FROM avaliacoes "
            "ORDER BY criado_em DESC, id DESC LIMIT ?",
            (n,),
        ).fetchall()

    def get_kv(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_kv(self, key: str, value: str | None) -> None:
        with self._db:
            if value is None:
                self._db.execute("DELETE FROM kv WHERE key = ?", (key,))
            else:
                self._db.execute(
                    "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
