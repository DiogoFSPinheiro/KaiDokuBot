from __future__ import annotations

import sqlite3
import time

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
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


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
