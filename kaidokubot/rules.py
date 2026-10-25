from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field

# --- premissas — confirmar antes da viagem -------------------------------------------------
# Desde 1/11/2026 o tax-free é por reembolso: paga-se o preço de montra (com 10% de imposto)
# e o imposto é devolvido depois da verificação na alfândega à saída do Japão (até 90 dias).
# Assumo que tudo é reembolsável.
IMPOSTO = 0.10
# Mínimo por loja e por dia, sem imposto (as compras do dia na mesma loja somam-se).
MINIMO_SEM_IMPOSTO = 5000
# Comissão cobrada no reembolso: depende da loja / empresa de reembolso (ex.: PPIH só cobra em dinheiro).
COMISSAO_REEMBOLSO = 0.0
# Mandar vir de uma loja online japonesa (ex.: AmiAmi) para Portugal: a loja vende sem o imposto japonês,
# e cá paga-se IVA sobre o artigo + portes, mais a taxa de desalfandegamento dos CTT.
IVA_PT = 0.23
PORTES_IMPORTACAO_EUR = 15.0  # envio de uma figura / jogo (SAL / EMS), estimativa
TAXA_CTT_EUR = 2.65  # ~€2,15 + IVA
# Portes de um artigo comprado na Vinted (envio nacional / ponto de recolha), estimativa.
PORTES_VINTED_EUR = 4.0
# --------------------------------------------------------------------------------------------

MIN_COMPARAVEIS_JP = 3
MIN_COMPARAVEIS_VINTED = 2


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


def importar_total_eur(preco_yen: float, taxa: float) -> float:
    """Custo total de mandar vir do Japão (preço da loja online com imposto japonês incluído)."""
    sem_imposto = preco_yen / (1 + IMPOSTO) * taxa
    return (sem_imposto + PORTES_IMPORTACAO_EUR) * (1 + IVA_PT) + TAXA_CTT_EUR


@dataclass(frozen=True)
class Mercado:
    """Dados de mercado de uma avaliação (guardados na cache; não dependem do preço da loja)."""

    termo_jp: str
    termo_en: str
    novo_eu_eur: float | None
    novo_eu_loja: str | None
    vinted_min_eur: float | None  # intervalo típico no mesmo estado
    vinted_max_eur: float | None
    vinted_n: int
    importar_yen: float | None  # preço numa loja online japonesa que envie para a Europa
    importar_loja: str | None
    jp_min_yen: float | None  # Mercari, mesmo estado
    jp_max_yen: float | None
    jp_n: int
    jp_so_pedidos: bool  # True se não houve vendas concluídas comparáveis
    cenarios: list[dict] = field(default_factory=list)  # estado desconhecido: {estado, eu_min, eu_max, jp_min, jp_max}
    razao: str = ""
    fontes: list[dict] = field(default_factory=list)  # {nome, url}
    avisos: list[str] = field(default_factory=list)
    vinted_tipico_eur: float | None = None  # mediana dos comparáveis (o mínimo costuma ser um outlier)
    produto: str = ""  # produto exato identificado (fabricante, linha, tamanho)
    # Links para confirmar com um toque: produto de referência, loja do preço novo, importar, pesquisas.
    produto_url: str = ""
    novo_eu_url: str = ""
    importar_url: str = ""
    vinted_url: str = ""
    mercari_url: str = ""

    @property
    def vinted_eur(self) -> float | None:
        """Preço típico na Vinted, sem portes."""
        if self.vinted_tipico_eur:
            return self.vinted_tipico_eur
        if self.vinted_min_eur and self.vinted_max_eur:
            return (self.vinted_min_eur + self.vinted_max_eur) / 2
        return self.vinted_min_eur or self.vinted_max_eur

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Mercado:
        return cls(**data)


@dataclass(frozen=True)
class Veredicto:
    codigo: str  # compensa | pouca | nao | incerto
    melhor: tuple[str, float] | None  # alternativa europeia mais barata (rótulo, €)
    poupanca_eur: float | None
    poupanca_pct: float | None
    max_montra_yen: int | None  # preço de montra a partir do qual deixa de compensar
    caro_no_japao: bool
    motivo: str | None = None  # só para "incerto"


def loja_curta(nome: str | None) -> str | None:
    """Só o nome da loja: o Claude às vezes junta notas («Amazon (promoção…; PVP…)»)."""
    if not nome:
        return None
    curto = re.split(r"\s*[(;,–—]|\s-\s", nome, maxsplit=1)[0].strip()
    return (curto[:24] + "…" if len(curto) > 25 else curto) or None


def alternativas(m: Mercado, taxa: float) -> list[tuple[str, float]]:
    opcoes = []
    if m.novo_eu_eur:
        loja = loja_curta(m.novo_eu_loja)
        opcoes.append((f"novo ({loja})" if loja else "novo", m.novo_eu_eur))
    if m.vinted_eur and m.vinted_n >= MIN_COMPARAVEIS_VINTED:
        opcoes.append(("Vinted", m.vinted_eur + PORTES_VINTED_EUR))
    if m.importar_yen:
        loja = loja_curta(m.importar_loja)
        rotulo = f"importar ({loja})" if loja else "importar"
        opcoes.append((rotulo, importar_total_eur(m.importar_yen, taxa)))
    return opcoes


def calcular_veredicto(m: Mercado, c: Contas, taxa: float | None, margem_pct: int) -> Veredicto:
    # Com poucos vendidos comparáveis o intervalo do Mercari não é fiável.
    caro = m.jp_max_yen is not None and m.jp_n >= MIN_COMPARAVEIS_JP and c.montra_yen > m.jp_max_yen
    if taxa is None or c.liquido_eur is None:
        return Veredicto("incerto", None, None, None, None, caro, "câmbio indisponível")
    opcoes = alternativas(m, taxa)
    if not opcoes:
        return Veredicto("incerto", None, None, None, None, caro, "sem preços europeus fiáveis")
    melhor = min(opcoes, key=lambda opcao: opcao[1])
    poupanca = melhor[1] - c.liquido_eur
    pct = poupanca / melhor[1] * 100
    margem = margem_pct / 100
    # Montra cujo líquido em € deixa exatamente a margem mínima face à melhor alternativa.
    liquido_max_yen = melhor[1] * (1 - margem) / taxa
    max_montra = math.floor(liquido_max_yen * (1 + IMPOSTO) / (1 - COMISSAO_REEMBOLSO) / 100) * 100
    codigo = "compensa" if pct >= margem_pct else "pouca" if poupanca >= 0 else "nao"
    return Veredicto(codigo, melhor, poupanca, pct, max_montra, caro)
