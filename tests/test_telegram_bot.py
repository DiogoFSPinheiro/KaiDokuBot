from kaidokubot.commands import Resposta
from kaidokubot.telegram_bot import markup


def test_markup_converte_botoes():
    m = markup(Resposta("x", [[("Nome", "fixf:1:nome"), ("Preço", "fixf:1:preco")], [("Cancelar", "fixx")]]))
    linhas = [[(b.text, b.callback_data) for b in linha] for linha in m.inline_keyboard]
    assert linhas == [[("Nome", "fixf:1:nome"), ("Preço", "fixf:1:preco")], [("Cancelar", "fixx")]]


def test_markup_sem_botoes_e_none():
    assert markup(Resposta("x")) is None
