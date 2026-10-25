import asyncio

from kaidokubot.commands import Resposta
from kaidokubot.telegram_bot import Progresso, markup


def test_markup_converte_botoes():
    m = markup(Resposta("x", [[("Nome", "fixf:1:nome"), ("Preço", "fixf:1:preco")], [("Cancelar", "fixx")]]))
    linhas = [[(b.text, b.callback_data) for b in linha] for linha in m.inline_keyboard]
    assert linhas == [[("Nome", "fixf:1:nome"), ("Preço", "fixf:1:preco")], [("Cancelar", "fixx")]]


def test_markup_sem_botoes_e_none():
    assert markup(Resposta("x")) is None


class FakeMensagem:
    def __init__(self):
        self.edicoes = []

    async def edit_text(self, texto, **kwargs):
        self.edicoes.append(texto)


async def test_progresso_limita_edicoes_e_mostra_sempre_o_ultimo():
    mensagem = FakeMensagem()
    progresso = Progresso(mensagem, intervalo_s=0.05)
    progresso("a")
    await asyncio.sleep(0.01)
    assert mensagem.edicoes == ["a"]
    progresso("b")
    progresso("c")
    await asyncio.sleep(0.01)
    assert mensagem.edicoes == ["a"]  # ainda dentro do intervalo
    await asyncio.sleep(0.1)
    assert mensagem.edicoes == ["a", "c"]
    await progresso.fechar()
    progresso("d")  # depois de fechar já não edita
    await asyncio.sleep(0.06)
    assert mensagem.edicoes == ["a", "c"]
