from __future__ import annotations

import sqlite3
import time
import unicodedata
from dataclasses import dataclass
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
    criado_em REAL NOT NULL,
    dados_de REAL,  -- quando os dados de mercado foram recolhidos (≠ criado_em nas respostas da cache)
    chave_produto TEXT  -- chave da cache pelo produto identificado
);
CREATE INDEX IF NOT EXISTS avaliacoes_chave ON avaliacoes (chave, criado_em);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

TOKYO = ZoneInfo("Asia/Tokyo")


# Sobe quando a forma de avaliar muda: as avaliações antigas deixam de servir de cache.
CACHE_VERSAO = 3


def chave_cache(nome: str, estado: str) -> str:
    """Mesmo artigo e estado, independentemente de maiúsculas, acentos, largura e espaços."""
    texto = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", nome).lower())
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return f"v{CACHE_VERSAO}|{' '.join(texto.split())}|{estado}"


def inicio_do_dia_tokyo(agora: float) -> float:
    """Meia-noite de hoje em Tóquio (o limite diário de avaliações vira a essa hora)."""
    dia = datetime.fromtimestamp(agora, TOKYO).replace(hour=0, minute=0, second=0, microsecond=0)
    return dia.timestamp()


@dataclass(frozen=True)
class Avaliacao:
    pedido_id: int
    pedido: Pedido  # como estava quando foi avaliado
    mercado_json: str
    da_cache: bool
    dados_de: float
    criado_em: float


class Storage:
    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._migrar()

    def _migrar(self) -> None:
        colunas = {row["name"] for row in self._db.execute("PRAGMA table_info(avaliacoes)")}
        for coluna, tipo in (("dados_de", "REAL"), ("chave_produto", "TEXT")):
            if coluna not in colunas:
                with self._db:
                    self._db.execute(f"ALTER TABLE avaliacoes ADD COLUMN {coluna} {tipo}")

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
        da_cache: bool, dados_de: float | None = None, chave_produto: str | None = None, now: float | None = None,
    ) -> int:  # fmt: skip
        now = time.time() if now is None else now
        with self._db:
            cur = self._db.execute(
                "INSERT INTO avaliacoes (chat_id, pedido_id, nome, preco_yen, estado, chave, mercado_json, veredicto, "
                "da_cache, criado_em, dados_de, chave_produto) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (chat_id, pedido_id, pedido.nome, pedido.preco_yen, pedido.estado, chave, mercado_json, veredicto,
                 int(da_cache), now, now if dados_de is None else dados_de, chave_produto),
            )  # fmt: skip
        return cur.lastrowid

    def get_avaliacao(self, avaliacao_id: int) -> Avaliacao | None:
        row = self._db.execute("SELECT * FROM avaliacoes WHERE id = ?", (avaliacao_id,)).fetchone()
        if row is None:
            return None
        return Avaliacao(
            pedido_id=row["pedido_id"],
            pedido=Pedido(row["nome"], row["preco_yen"], row["estado"]),
            mercado_json=row["mercado_json"],
            da_cache=bool(row["da_cache"]),
            dados_de=row["dados_de"] if row["dados_de"] is not None else row["criado_em"],
            criado_em=row["criado_em"],
        )

    def _cache(self, coluna: str, chave: str, desde: float) -> tuple[str, float] | None:
        row = self._db.execute(
            f"SELECT mercado_json, COALESCE(dados_de, criado_em) AS de FROM avaliacoes "
            f"WHERE {coluna} = ? AND COALESCE(dados_de, criado_em) >= ? ORDER BY de DESC, id DESC LIMIT 1",
            (chave, desde),
        ).fetchone()
        return (row["mercado_json"], row["de"]) if row else None

    def cache(self, chave: str, desde: float) -> tuple[str, float] | None:
        """Dados de mercado mais recentes para o texto escrito, recolhidos desde `desde`: (json, quando)."""
        return self._cache("chave", chave, desde)

    def cache_produto(self, chave_produto: str, desde: float) -> tuple[str, float] | None:
        """Igual, mas pelo produto identificado (o mesmo produto escrito de outra forma)."""
        return self._cache("chave_produto", chave_produto, desde)

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
