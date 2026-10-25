"""Anúncios do Mercari (Japão) e da Vinted (Europa), pesquisados pelo próprio bot.

O Claude, sozinho, não chega lá: o Mercari é uma app JavaScript e a Vinted não aparece na pesquisa web.
As duas APIs são internas (não oficiais) e podem mudar sem aviso.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

# item_condition_id do Mercari (新品、未使用 … 全体的に状態が悪い).
_ESTADO_MERCARI = {1: "novo", 2: "quase novo", 3: "sem marcas", 4: "marcas ligeiras", 5: "marcas", 6: "mau estado"}

VINTED_DOMINIO = "www.vinted.pt"
VINTED_POR_PAGINA = 30


class FonteError(Exception):
    pass


@dataclass(frozen=True)
class Anuncio:
    titulo: str
    preco: float  # ¥ no Mercari, € na Vinted
    estado: str


def anuncio_mercari(item) -> Anuncio:
    return Anuncio(item.name, float(item.price), _ESTADO_MERCARI.get(item.item_condition_id, "?"))


def anuncio_vinted(raw: dict) -> Anuncio | None:
    # O preço com a proteção do comprador é o que se paga de facto (sem portes).
    total = (raw.get("total_item_price") or {}).get("amount")
    base = (raw.get("price") or {}).get("amount")
    try:
        preco = float(total or base)
    except (TypeError, ValueError):
        return None
    # second_line: "<tamanho> · <estado>" (às vezes só o estado).
    second_line = (raw.get("item_box") or {}).get("second_line") or ""
    estado = second_line.rsplit("·", 1)[-1].strip() if second_line else "?"
    return Anuncio(raw.get("title") or "", preco, estado or "?")


class Mercari:
    def __init__(self) -> None:
        from mercapi import Mercapi

        self._http = httpx.AsyncClient(timeout=20)
        self._api = Mercapi(httpx_client=self._http)

    async def procurar(self, termo: str, n: int = 40) -> tuple[list[Anuncio], list[Anuncio]]:
        """(vendidos, à venda) para o termo (em japonês)."""
        from mercapi.requests import SearchRequestData

        status = SearchRequestData.Status
        try:
            vendidos, a_venda = await asyncio.gather(
                self._api.search(termo, status=[status.STATUS_SOLD_OUT]),
                self._api.search(termo, status=[status.STATUS_ON_SALE]),
            )
        except Exception as exc:
            raise FonteError(f"Mercari: {exc}") from exc
        return (
            [anuncio_mercari(item) for item in vendidos.items[:n]],
            [anuncio_mercari(item) for item in a_venda.items[:n]],
        )

    async def close(self) -> None:
        await self._http.aclose()


class Vinted:
    """Pesquisa na Vinted (adaptado do cliente do VintedBot)."""

    def __init__(self, session=None) -> None:
        if session is None:
            from curl_cffi.requests import AsyncSession

            session = AsyncSession(impersonate="chrome", timeout=20)
        self._session = session
        self._aquecido = False
        self._locale: str | None = None

    async def procurar(self, termo: str) -> list[Anuncio]:
        try:
            if not self._aquecido:
                await self._aquecer()
            response = await self._items(termo)
            if response.status_code in (401, 403):
                # Token expirado: recomeça do zero, como no arranque.
                self._session.cookies.clear()
                await self._aquecer()
                response = await self._items(termo)
            if response.status_code != 200:
                raise FonteError(f"Vinted: HTTP {response.status_code}")
            items = response.json().get("items", [])
        except FonteError:
            raise
        except Exception as exc:
            raise FonteError(f"Vinted: {exc}") from exc
        return [anuncio for anuncio in map(anuncio_vinted, items) if anuncio is not None]

    async def _aquecer(self) -> None:
        # A homepage dá os cookies (token anónimo) e a língua dos textos (estado em português).
        await self._session.get(f"https://{VINTED_DOMINIO}/")
        for cookie in self._session.cookies.jar:
            if cookie.name == "anonymous-iso-locale":
                self._locale = cookie.value
        self._aquecido = True

    async def _items(self, termo: str):
        api = "https://api." + VINTED_DOMINIO.removeprefix("www.") + "/svc-catalogue/items"
        params = {"search_text": termo, "order": "relevance", "page": "1", "per_page": str(VINTED_POR_PAGINA)}
        headers = {"Locale": self._locale} if self._locale else None
        return await self._session.get(api, params=params, headers=headers)

    async def close(self) -> None:
        await self._session.close()


async def _smoke(termo_jp: str, termo_en: str) -> None:
    mercari, vinted = Mercari(), Vinted()
    try:
        vendidos, a_venda = await mercari.procurar(termo_jp)
        print(f"Mercari: {len(vendidos)} vendidos, {len(a_venda)} à venda")
        for a in vendidos[:3]:
            print(f"  ¥{a.preco:.0f} {a.estado} | {a.titulo}")
        anuncios = await vinted.procurar(termo_en)
        print(f"Vinted: {len(anuncios)} anúncios")
        for a in anuncios[:3]:
            print(f"  €{a.preco:.2f} {a.estado} | {a.titulo}")
    finally:
        await mercari.close()
        await vinted.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_smoke(sys.argv[1], sys.argv[2]))
