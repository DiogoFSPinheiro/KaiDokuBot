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
