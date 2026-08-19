# -*- coding: utf-8 -*-
"""
Canary Controlado e Observabilidade — Fase 6C
Compara determinística e semanticamente os resultados de LEGACY vs GENERIC item a item.
Classifica cada entidade em: MATCH_EXACT, MATCH_SEMANTIC, NAME_IMPROVEMENT, FP_LEGACY,
FN_LEGACY, FP_GENERIC, FN_GENERIC, PRICE_DIVERGENCE, UNIT_DIVERGENCE, DUPLICATE, UNRESOLVED.
"""

from dataclasses import dataclass, field
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from domain.models import PriceItem
from domain.normalizer import normalizar, nome_produto_normalizado, tokens_produto


@dataclass
class CanaryItemComparison:
    """Classificação item-a-item da comparação entre Legacy e Generic."""
    classificacao: str  # MATCH_EXACT, MATCH_SEMANTIC, NAME_IMPROVEMENT, FP_LEGACY, FN_LEGACY, etc.
    legacy_item: Optional[PriceItem] = None
    generic_item: Optional[PriceItem] = None
    motivo: str = ""
    score_similaridade_nome: float = 0.0
    detalhes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classificacao": self.classificacao,
            "motivo": self.motivo,
            "score_similaridade_nome": round(self.score_similaridade_nome, 4),
            "legacy": {
                "nome": self.legacy_item.name,
                "preco": self.legacy_item.price,
                "unidade": self.legacy_item.unit,
                "product_key": self.legacy_item.key() if self.legacy_item else ""
            } if self.legacy_item else None,
            "generic": {
                "nome": self.generic_item.name,
                "preco": self.generic_item.price,
                "unidade": self.generic_item.unit,
                "product_key": self.generic_item.key() if self.generic_item else ""
            } if self.generic_item else None,
            "detalhes": self.detalhes
        }


@dataclass
class CanaryDocumentReport:
    """Relatório Canary de um documento OCR."""
    documento_id: str
    total_legacy: int = 0
    total_generic: int = 0
    matches_exatos: int = 0
    matches_semanticos: int = 0
    melhorias_nome: int = 0
    fp_legacy: int = 0
    fn_legacy: int = 0
    fp_generic: int = 0
    fn_generic: int = 0
    divergencias_preco: int = 0
    divergencias_unidade: int = 0
    duplicatas: int = 0
    unresolved: int = 0
    tempo_legacy_ms: float = 0.0
    tempo_generic_ms: float = 0.0
    comparacoes: List[CanaryItemComparison] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "documento_id": self.documento_id,
            "total_legacy": self.total_legacy,
            "total_generic": self.total_generic,
            "contagem_classificacoes": {
                "MATCH_EXACT": self.matches_exatos,
                "MATCH_SEMANTIC": self.matches_semanticos,
                "NAME_IMPROVEMENT": self.melhorias_nome,
                "FP_LEGACY": self.fp_legacy,
                "FN_LEGACY": self.fn_legacy,
                "FP_GENERIC": self.fp_generic,
                "FN_GENERIC": self.fn_generic,
                "PRICE_DIVERGENCE": self.divergencias_preco,
                "UNIT_DIVERGENCE": self.divergencias_unidade,
                "DUPLICATE": self.duplicatas,
                "UNRESOLVED": self.unresolved
            },
            "performance_ms": {
                "legacy": round(self.tempo_legacy_ms, 2),
                "generic": round(self.tempo_generic_ms, 2)
            },
            "comparacoes": [c.to_dict() for c in self.comparacoes]
        }


def calcular_similaridade_tokens(nome_a: str, nome_b: str) -> float:
    """Calcula similaridade Jaccard/overlap de tokens normalizados."""
    ta = tokens_produto(nome_a)
    tb = tokens_produto(nome_b)
    if not ta and not tb:
        return 1.0 if normalizar(nome_a) == normalizar(nome_b) else 0.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union > 0 else 0.0


_RE_DISCLAIMER_CANARY = re.compile(
    r'\b(pre[cç]os?\s+v[aá]lidos?|imagens?\s+(?:meramente\s+)?ilustrativas?|ofertas?\s+v[aá]lidas?|enquanto\s+durarem|condi[cç][oõ]es?\s+gerais|v[aá]lido\s+(?:de\s+\d+|para\s+todas))\b',
    re.IGNORECASE
)
_RE_PALAVRA_SEMANTICA = re.compile(r'[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{3,}')


def comparar_documento_canary(
    itens_legacy: Sequence[PriceItem],
    itens_generic: Sequence[PriceItem],
    documento_id: str = "",
    tempo_legacy_ms: float = 0.0,
    tempo_generic_ms: float = 0.0
) -> CanaryDocumentReport:
    """
    Executa a auditoria Canary item a item de forma determinística e detalhada.
    """
    doc_rep = CanaryDocumentReport(
        documento_id=documento_id,
        total_legacy=len(itens_legacy),
        total_generic=len(itens_generic),
        tempo_legacy_ms=tempo_legacy_ms,
        tempo_generic_ms=tempo_generic_ms
    )

    legacy_pool = list(itens_legacy)
    generic_pool = list(itens_generic)
    comparacoes: List[CanaryItemComparison] = []

    # 1. PASSO 1: Itens com Preço Idêntico (|p_L - p_G| <= 0.02)
    for g_item in list(generic_pool):
        match_idx = None
        melhor_sim = -1.0
        for idx, l_item in enumerate(legacy_pool):
            if g_item.price is not None and l_item.price is not None:
                if abs(g_item.price - l_item.price) <= 0.02:
                    sim = calcular_similaridade_tokens(g_item.name, l_item.name)
                    if sim > melhor_sim:
                        melhor_sim = sim
                        match_idx = idx

        if match_idx is not None:
            l_match = legacy_pool.pop(match_idx)
            generic_pool.remove(g_item)
            sim = max(0.0, melhor_sim)

            # Classificação refinada de nomes
            if sim >= 0.80 or normalizar(g_item.name) == normalizar(l_match.name):
                # Checagem de unidade
                if l_match.unit and g_item.unit and normalizar(l_match.unit) != normalizar(g_item.unit):
                    classif = "UNIT_DIVERGENCE"
                    doc_rep.divergencias_unidade += 1
                    motivo = f"Preço e nome idênticos, mas unidades diferem (Legacy: '{l_match.unit}' vs Generic: '{g_item.unit}')"
                else:
                    classif = "MATCH_EXACT"
                    doc_rep.matches_exatos += 1
                    motivo = "Preço, nome e unidade estritamente idênticos ou equivalentes"
            elif sim >= 0.50:
                classif = "MATCH_SEMANTIC"
                doc_rep.matches_semanticos += 1
                motivo = f"Preço R$ {g_item.price:.2f} coincide com alta similaridade de tokens ({sim:.2f})"
            else:
                # O Generic reconstruiu morfemas quebrados pelo OCR
                classif = "NAME_IMPROVEMENT"
                doc_rep.melhorias_nome += 1
                motivo = f"Preço R$ {g_item.price:.2f} coincide; Generic reconstruiu nome OCR fragmentado (Legacy: '{l_match.name}' -> Generic: '{g_item.name}')"

            comparacoes.append(CanaryItemComparison(
                classificacao=classif,
                legacy_item=l_match,
                generic_item=g_item,
                score_similaridade_nome=sim,
                motivo=motivo
            ))

    # 2. PASSO 2: Itens com Nome Similar, mas Preço Divergente
    for g_item in list(generic_pool):
        match_idx = None
        for idx, l_item in enumerate(legacy_pool):
            sim = calcular_similaridade_tokens(g_item.name, l_item.name)
            if sim >= 0.65:
                match_idx = idx
                break

        if match_idx is not None:
            l_match = legacy_pool.pop(match_idx)
            generic_pool.remove(g_item)
            sim = calcular_similaridade_tokens(g_item.name, l_match.name)
            doc_rep.divergencias_preco += 1
            comparacoes.append(CanaryItemComparison(
                classificacao="PRICE_DIVERGENCE",
                legacy_item=l_match,
                generic_item=g_item,
                score_similaridade_nome=sim,
                motivo=f"Mesmo produto com preços divergentes: Legacy R$ {l_match.price} vs Generic R$ {g_item.price}"
            ))

    # 3. PASSO 3: Itens Restantes do LEGACY
    for l_item in legacy_pool:
        nome_lower = l_item.name.lower()
        has_noise_chars = bool(re.search(r'[\[\]|{}]', l_item.name))
        is_disclaimer = bool(_RE_DISCLAIMER_CANARY.search(nome_lower))
        is_gramatura_pattern = bool(re.search(r'\b\d+([.,]\d+)?\s*(g|kg|ml|l|sach[eê]s?)\b', nome_lower))
        not_semantic = not bool(_RE_PALAVRA_SEMANTICA.search(nome_lower))

        if is_disclaimer or has_noise_chars or not_semantic:
            doc_rep.fp_legacy += 1
            classif = "FP_LEGACY"
            motivo = "Falso positivo Legacy: disclaimer jurídico de rodapé ou ruído semântico"
        elif is_gramatura_pattern and l_item.price and l_item.price > 50.0:
            # Padrão genérico: gramatura/especificação em nome com preço espúrio
            doc_rep.fp_legacy += 1
            classif = "FP_LEGACY"
            motivo = f"Falso positivo Legacy: especificação de gramatura/código confundida com preço R$ {l_item.price}"
        else:
            doc_rep.fn_generic += 1
            classif = "FN_GENERIC"
            motivo = f"Item presente apenas no Legacy (Preço R$ {l_item.price})"

        comparacoes.append(CanaryItemComparison(
            classificacao=classif,
            legacy_item=l_item,
            generic_item=None,
            motivo=motivo
        ))

    # 4. PASSO 4: Itens Restantes do GENERIC
    for g_item in generic_pool:
        # Em auditoria diferencial sem evidência documental independente externa,
        # qualquer entidade presente exclusivamente no Generic é classificada como falso positivo do Generic (FP_GENERIC).
        doc_rep.fp_generic += 1
        classif = "FP_GENERIC"
        motivo = f"Item presente apenas no Generic sem corroboração pelo baseline de produção (Preço R$ {g_item.price})"

        comparacoes.append(CanaryItemComparison(
            classificacao=classif,
            legacy_item=None,
            generic_item=g_item,
            motivo=motivo
        ))

    doc_rep.comparacoes = comparacoes
    return doc_rep


def percentil(dados: List[float], p: float) -> float:
    """Calcula percentil exato de uma lista de valores float."""
    if not dados:
        return 0.0
    s = sorted(dados)
    idx = (len(s) - 1) * (p / 100.0)
    floor_idx = int(idx)
    ceil_idx = min(floor_idx + 1, len(s) - 1)
    weight = idx - floor_idx
    return round(s[floor_idx] * (1.0 - weight) + s[ceil_idx] * weight, 2)
