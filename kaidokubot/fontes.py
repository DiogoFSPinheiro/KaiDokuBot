"""Anúncios do Mercari (Japão), da Vinted (Europa) e preços novos do KuantoKusta (Portugal), pesquisados pelo bot.

O Claude, sozinho, não chega lá: o Mercari é uma app JavaScript, a Vinted não aparece na pesquisa web e as
lojas (ex.: Amazon) bloqueiam acessos automáticos. São APIs/páginas internas e podem mudar sem aviso.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

# item_condition_id do Mercari (新品、未使用 … 全体的に状態が悪い).
_ESTADO_MERCARI = {1: "novo", 2: "quase novo", 3: "sem marcas", 4: "marcas ligeiras", 5: "marcas", 6: "mau estado"}

VINTED_DOMINIO = "www.vinted.pt"
VINTED_POR_PAGINA = 30
KUANTOKUSTA_URL = "https://www.kuantokusta.pt/search"
_RE_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class FonteError(Exception):
    pass


@dataclass(frozen=True)
class Anuncio:
    titulo: str
    preco: float  # ¥ no Mercari, € na Vinted e no KuantoKusta
    estado: str
    url: str = ""


def anuncio_mercari(item) -> Anuncio:
    # Os anúncios das lojas (Mercari Shops) têm outro endereço.
    if getattr(item, "item_type", "") == "ITEM_TYPE_BEYOND":
        url = f"https://jp.mercari.com/shops/product/{item.id_}"
    else:
        url = f"https://jp.mercari.com/item/{item.id_}"
    return Anuncio(item.name, float(item.price), _ESTADO_MERCARI.get(item.item_condition_id, "?"), url)


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
    return Anuncio(raw.get("title") or "", preco, estado or "?", raw.get("url") or "")


def anuncio_kuantokusta(raw: dict) -> Anuncio | None:
    try:
        preco = float(raw["priceMin"])
    except (KeyError, TypeError, ValueError):
        return None
    lojas = int(raw.get("totalOffers") or 0)
    detalhe = f"novo · {lojas} {'loja' if lojas == 1 else 'lojas'}"
    if raw.get("category"):
        detalhe += f" · {raw['category']}"
    caminho = raw.get("url") or ""
    url = f"https://www.kuantokusta.pt{caminho}" if caminho.startswith("/") else caminho
    return Anuncio(raw.get("name") or "", preco, detalhe, url)


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


class KuantoKusta:
    """Comparador português: preço novo mais baixo em lojas que vendem para Portugal (inclui a Amazon.es)."""

    def __init__(self, session=None) -> None:
        if session is None:
            from curl_cffi.requests import AsyncSession

            session = AsyncSession(impersonate="chrome", timeout=20)
        self._session = session

    async def procurar(self, termo: str) -> list[Anuncio]:
        try:
            response = await self._session.get(KUANTOKUSTA_URL, params={"q": termo})
            if response.status_code == 404:  # é assim que responde quando não há resultados
                return []
            if response.status_code != 200:
                raise FonteError(f"KuantoKusta: HTTP {response.status_code}")
            # A página é Next.js: os resultados vêm em JSON no __NEXT_DATA__.
            match = _RE_NEXT_DATA.search(response.text)
            if match is None:
                raise FonteError("KuantoKusta: página sem dados")
            items = json.loads(match.group(1))["props"]["pageProps"]["basePage"]["data"]
        except FonteError:
            raise
        except Exception as exc:
            raise FonteError(f"KuantoKusta: {exc}") from exc
        return [anuncio for anuncio in map(anuncio_kuantokusta, items) if anuncio is not None]

    async def close(self) -> None:
        await self._session.close()


async def _smoke(termo_jp: str, termo_en: str) -> None:
    mercari, vinted, kuantokusta = Mercari(), Vinted(), KuantoKusta()
    try:
        vendidos, a_venda = await mercari.procurar(termo_jp)
        print(f"Mercari: {len(vendidos)} vendidos, {len(a_venda)} à venda")
        for a in vendidos[:3]:
            print(f"  ¥{a.preco:.0f} {a.estado} | {a.titulo}")
        anuncios = await vinted.procurar(termo_en)
        print(f"Vinted: {len(anuncios)} anúncios")
        for a in anuncios[:3]:
            print(f"  €{a.preco:.2f} {a.estado} | {a.titulo}")
        novos = await kuantokusta.procurar(termo_en)
        print(f"KuantoKusta: {len(novos)} produtos")
        for a in novos[:3]:
            print(f"  €{a.preco:.2f} {a.estado} | {a.titulo}")
    finally:
        await mercari.close()
        await vinted.close()
        await kuantokusta.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_smoke(sys.argv[1], sys.argv[2]))
