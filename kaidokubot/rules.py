from __future__ import annotations

from dataclasses import dataclass

# --- premissas — confirmar antes da viagem -------------------------------------------------
# Desde 1/11/2026 o tax-free é por reembolso: paga-se o preço de montra (com 10% de imposto)
# e o imposto é devolvido depois da verificação na alfândega à saída do Japão (até 90 dias).
# Assumo que tudo é reembolsável.
IMPOSTO = 0.10
# Mínimo por loja e por dia, sem imposto (as compras do dia na mesma loja somam-se).
MINIMO_SEM_IMPOSTO = 5000
# Comissão cobrada no reembolso: depende da loja / empresa de reembolso (ex.: PPIH só cobra em dinheiro).
COMISSAO_REEMBOLSO = 0.0
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Contas:
    montra_yen: int
    liquido_yen: float
    montra_eur: float | None  # None sem câmbio
    liquido_eur: float | None

    @property
    def reembolso_eur(self) -> float | None:
        if self.montra_eur is None or self.liquido_eur is None:
            return None
        return self.montra_eur - self.liquido_eur


def contas(montra_yen: int, taxa: float | None) -> Contas:
    liquido = montra_yen / (1 + IMPOSTO) * (1 - COMISSAO_REEMBOLSO)
    return Contas(
        montra_yen=montra_yen,
        liquido_yen=liquido,
        montra_eur=None if taxa is None else montra_yen * taxa,
        liquido_eur=None if taxa is None else liquido * taxa,
    )


def abaixo_do_minimo(montra_yen: int) -> bool:
    """Sozinho, o artigo não chega ao mínimo do tax-free."""
    return montra_yen / (1 + IMPOSTO) < MINIMO_SEM_IMPOSTO
