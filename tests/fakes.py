class FakeHttp:
    """Resposta por URL: dict devolvido como JSON ou Exception lançada. URLs sem resposta falham."""

    def __init__(self, respostas=None):
        self.respostas = dict(respostas or {})
        self.chamadas = []

    async def get_json(self, url):
        self.chamadas.append(url)
        resposta = self.respostas.get(url, RuntimeError(f"sem resposta para {url}"))
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    async def close(self):
        pass


class FakeClock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeRunner:
    """Simula o ClaudeCli: devolve a resposta registada para cada esquema (pelo título) e regista os prompts."""

    def __init__(self, respostas, pesquisas=(), bloquear=None):
        self.respostas = respostas  # {"termos": dict | Exception, "mercado": dict | Exception}
        self.pesquisas = list(pesquisas)
        self.bloquear = bloquear  # asyncio.Event: a chamada "mercado" espera por ele
        self.chamadas = []  # (tipo, prompt, tools)

    async def run(self, prompt, schema, *, system, tools="", on_search=None):
        tipo = schema["title"]
        self.chamadas.append((tipo, prompt, tools))
        if on_search is not None:
            for query in self.pesquisas:
                on_search(query)
        if tipo == "mercado" and self.bloquear is not None:
            await self.bloquear.wait()
        resposta = self.respostas[tipo]
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class FakeMercari:
    def __init__(self, vendidos=(), a_venda=(), erro=None):
        self.vendidos, self.a_venda, self.erro = list(vendidos), list(a_venda), erro
        self.termos = []

    async def procurar(self, termo, n=40):
        self.termos.append(termo)
        if self.erro:
            raise self.erro
        return self.vendidos, self.a_venda


class FakeVinted:
    def __init__(self, anuncios=(), erro=None):
        self.anuncios, self.erro = list(anuncios), erro
        self.termos = []

    async def procurar(self, termo):
        self.termos.append(termo)
        if self.erro:
            raise self.erro
        return self.anuncios
