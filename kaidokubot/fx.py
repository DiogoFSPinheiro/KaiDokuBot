from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx

from kaidokubot.storage import Storage

log = logging.getLogger(__name__)

URL_BCE = "https://api.frankfurter.dev/v1/latest?base=JPY&symbols=EUR"
URL_ALTERNATIVA = "https://open.er-api.com/v6/latest/JPY"
# O BCE publica 1× por dia útil: não vale a pena perguntar mais vezes.
INTERVALO_S = 20 * 3600


@dataclass(frozen=True)
class EstadoCambio:
    taxa: float | None  # euros por iene
    data: str | None  # AAAA-MM-DD da cotação
    fonte: str | None
    manual: bool


def parse_taxa(texto: str) -> float | None:
    try:
        taxa = float(texto.strip().replace(",", "."))
    except ValueError:
        return None
    return taxa if math.isfinite(taxa) and 0 < taxa < 1 else None


def _do_bce(data: dict) -> tuple[float, str]:
    return float(data["rates"]["EUR"]), str(data["date"])


def _da_alternativa(data: dict) -> tuple[float, str]:
    if data.get("result") != "success":
        raise ValueError(f"resultado {data.get('result')!r}")
    dia = parsedate_to_datetime(data["time_last_update_utc"]).date().isoformat()
    return float(data["rates"]["EUR"]), dia


_FONTES = [("BCE", URL_BCE, _do_bce), ("open.er-api", URL_ALTERNATIVA, _da_alternativa)]


class HttpJson:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=10, follow_redirects=True)

    async def get_json(self, url: str) -> dict:
        response = await self._client.get(url)
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()


class Cambio:
    """Câmbio ¥→€ guardado no SQLite: automático (1× por dia) ou um valor manual."""

    def __init__(self, storage: Storage, http, now: Callable[[], float] = time.time) -> None:
        self._storage = storage
        self._http = http
        self._now = now

    def estado(self) -> EstadoCambio:
        manual = self._storage.get_kv("fx_manual")
        if manual is not None:
            return EstadoCambio(float(manual), None, "manual", True)
        taxa = self._storage.get_kv("fx_taxa")
        return EstadoCambio(
            float(taxa) if taxa is not None else None,
            self._storage.get_kv("fx_data"),
            self._storage.get_kv("fx_fonte"),
            False,
        )

    def taxa(self) -> float | None:
        return self.estado().taxa

    async def atualizar(self, force: bool = False) -> EstadoCambio:
        if self._storage.get_kv("fx_manual") is not None:
            return self.estado()
        ultimo = self._storage.get_kv("fx_atualizado_em")
        if not force and ultimo is not None and self._now() - float(ultimo) < INTERVALO_S:
            return self.estado()
        for fonte, url, ler in _FONTES:
            try:
                taxa, dia = ler(await self._http.get_json(url))
                if parse_taxa(str(taxa)) is None:
                    raise ValueError(f"taxa inválida {taxa}")
            except Exception as exc:  # rede, HTTP ou JSON inesperado: tenta a fonte seguinte
                log.warning("Câmbio: %s falhou (%s)", fonte, exc)
                continue
            self._storage.set_kv("fx_taxa", repr(taxa))
            self._storage.set_kv("fx_data", dia)
            self._storage.set_kv("fx_fonte", fonte)
            self._storage.set_kv("fx_atualizado_em", repr(self._now()))
            log.info("Câmbio atualizado: 1 JPY = %s EUR (%s, %s)", taxa, fonte, dia)
            break
        else:
            log.warning("Câmbio: sem fontes disponíveis; mantenho o último guardado")
        return self.estado()

    def definir_manual(self, taxa: float) -> None:
        self._storage.set_kv("fx_manual", repr(taxa))

    async def voltar_auto(self) -> EstadoCambio:
        self._storage.set_kv("fx_manual", None)
        return await self.atualizar(force=True)
