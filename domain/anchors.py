# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Classificação Genérica de Âncoras e Sinais Competitivos.
Camada pura de domínio para classificação determinística, multi-nicho e extensível
de evidências, sinais temáticos e pontos de ancoragem sem dependência de infraestrutura.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from domain.normalizer import normalizar


@dataclass(frozen=True)
class AnchorClassification:
    """
    Classificação determinística e imutável de uma âncora, sinal ou evidência temática.
    """
    category: str
    confidence: float
    matched_term: str
    source_type: str = "text_signal"
    secondary_categories: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_known(self) -> bool:
        """Indica se a âncora foi reconhecida em uma categoria canônica."""
        return self.category != "UNKNOWN" and self.confidence > 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "confidence": round(self.confidence, 4),
            "matched_term": self.matched_term,
            "source_type": self.source_type,
            "secondary_categories": list(self.secondary_categories),
            "is_known": self.is_known,
            "metadata": self.metadata,
        }


# Precedência Canônica Determinística entre Categorias
ANCHOR_PRECEDENCE: Tuple[str, ...] = (
    "REGULAÇÃO",
    "PESSOAS",
    "EXPANSÃO",
    "REPUTAÇÃO",
    "ATENDIMENTO",
    "PREÇO",
    "DIGITAL",
    "MARKETING",
    "PRODUTO/SERVIÇO",
    "PARCERIA",
)

# Regras Declarativas Padrão de Classificação de Âncoras
DEFAULT_ANCHOR_RULES: Dict[str, Dict[str, Any]] = {
    "REGULAÇÃO": {
        "keys": (
            "procon", "multa", "fiscalizacao", "anvisa", "vigilancia sanitaria",
        ),
        "base_confidence": 0.90,
        "priority": 1,
    },
    "PESSOAS": {
        "keys": (
            "vaga", "vagas", "emprego", "contratacao", "recrutamento", "processo seletivo",
        ),
        "base_confidence": 0.85,
        "priority": 2,
    },
    "EXPANSÃO": {
        "keys": (
            "inaugur", "nova unidade", "nova loja", "expansao", "filial",
            "abre as portas", "instalacao de", "vai abrir", "planeja abrir",
        ),
        "base_confidence": 0.85,
        "priority": 3,
    },
    "REPUTAÇÃO": {
        "keys": (
            "reclamacao", "reclame aqui", "queixa", "avaliacao", "nota",
        ),
        "base_confidence": 0.80,
        "priority": 4,
    },
    "ATENDIMENTO": {
        "keys": (
            "fila", "demora no atendimento", "mau atendimento", "suporte",
        ),
        "base_confidence": 0.75,
        "priority": 5,
    },
    "PREÇO": {
        "keys": (
            "preco", "oferta", "promocao", "desconto",
        ),
        "base_confidence": 0.80,
        "priority": 6,
    },
    "DIGITAL": {
        "keys": (
            "app", "aplicativo", "delivery", "e-commerce", "ecommerce",
            "plataforma", "supershop",
        ),
        "base_confidence": 0.75,
        "priority": 7,
    },
    "MARKETING": {
        "keys": (
            "campanha", "publicidade", "patrocin", "marketing", "evento promocional",
        ),
        "base_confidence": 0.70,
        "priority": 8,
    },
    "PRODUTO/SERVIÇO": {
        "keys": (
            "lancamento", "produto novo", "novo produto", "cardapio",
            "catalogo", "servico",
        ),
        "base_confidence": 0.75,
        "priority": 9,
    },
    "PARCERIA": {
        "keys": (
            "parceria", "acordo", "joint venture", "fornecedor",
        ),
        "base_confidence": 0.70,
        "priority": 10,
    },
}

# Aliases Semânticos para Unificação de Termos
ANCHOR_ALIASES: Dict[str, str] = {
    "promo": "promocao",
    "descontos": "desconto",
    "ofertas": "oferta",
    "precos": "preco",
    "vagas": "vaga",
    "contrata": "contratacao",
    "reclama": "reclamacao",
    "queixas": "queixa",
    "inauguracao": "inaugur",
    "inaugura": "inaugur",
    "loja nova": "nova loja",
    "novo restaurante": "nova unidade",
    "nova clinica": "nova unidade",
    "novo hotel": "nova unidade",
    "sanitaria": "vigilancia sanitaria",
}


class GenericAnchorClassifier:
    """
    Classificador determinístico e genérico de âncoras e sinais competitivos.
    Opera exclusivamente em memória sem dependências de infraestrutura.
    """

    def __init__(
        self,
        custom_rules: Optional[Dict[str, Dict[str, Any]]] = None,
        aliases: Optional[Dict[str, str]] = None,
        precedence: Optional[Sequence[str]] = None,
    ):
        self.rules = dict(custom_rules or DEFAULT_ANCHOR_RULES)
        self.aliases = dict(aliases or ANCHOR_ALIASES)
        self.precedence = tuple(precedence or ANCHOR_PRECEDENCE)

    def classify(
        self,
        text: str,
        profile: Optional[Dict[str, Any]] = None,
        is_price_candidate_fn: Optional[Callable[..., bool]] = None,
        url: str = "",
        title: str = "",
    ) -> AnchorClassification:
        """
        Classifica um texto em uma categoria canônica com determinismo estrito.
        """
        if not text or not text.strip():
            return AnchorClassification(
                category="UNKNOWN",
                confidence=0.0,
                matched_term="",
                source_type="empty",
                secondary_categories=(),
            )

        norm_text = normalizar(text)
        if not norm_text:
            return AnchorClassification(
                category="UNKNOWN",
                confidence=0.0,
                matched_term="",
                source_type="empty",
                secondary_categories=(),
            )

        # Expansão determinística de aliases
        expanded_terms: Set[str] = set()
        words = norm_text.split()
        for w in words:
            if w in self.aliases:
                expanded_terms.add(normalizar(self.aliases[w]))
        for alias_k, alias_target in self.aliases.items():
            if normalizar(alias_k) in norm_text:
                expanded_terms.add(normalizar(alias_target))

        # 1. Avaliação de correspondências diretas nas regras
        matches_by_cat: Dict[str, List[Tuple[str, float]]] = {}

        for cat, rule in self.rules.items():
            keys = rule.get("keys", ())
            base_conf = float(rule.get("base_confidence", 0.70))
            for k in keys:
                k_norm = normalizar(k)
                if k_norm in norm_text or k_norm in expanded_terms:
                    # Bônus leve para match de frase/palavra exata mais longa
                    conf = min(1.0, base_conf + min(0.10, len(k_norm) / 50.0))
                    matches_by_cat.setdefault(cat, []).append((k_norm, conf))

        # 2. Avaliação de sinais declarativos do perfil de nicho (se fornecido)
        if profile and isinstance(profile, dict):
            profile_signals = profile.get("signals") or []
            for sig in profile_signals:
                sig_norm = normalizar(str(sig))
                if sig_norm and sig_norm in norm_text:
                    # Encontra a melhor categoria associada a este sinal ou atribui a PRODUTO/SERVIÇO
                    cat_found = None
                    for cat, rule in self.rules.items():
                        if any(sig_norm in normalizar(k) or normalizar(k) in sig_norm for k in rule.get("keys", ())):
                            cat_found = cat
                            break
                    if not cat_found:
                        cat_found = "PRODUTO/SERVIÇO"
                    matches_by_cat.setdefault(cat_found, []).append((sig_norm, 0.75))

        # 3. Tratamento especial para validação de PREÇO com gate de candidato
        if "PREÇO" in matches_by_cat and is_price_candidate_fn is not None:
            if not is_price_candidate_fn(url, title, text):
                del matches_by_cat["PREÇO"]

        if not matches_by_cat:
            return AnchorClassification(
                category="UNKNOWN",
                confidence=0.0,
                matched_term="",
                source_type="unmatched",
                secondary_categories=(),
            )

        # 4. Resolução determinística por ordem de precedência estrita
        primary_category: Optional[str] = None
        best_term: str = ""
        best_confidence: float = 0.0

        for cat in self.precedence:
            if cat in matches_by_cat:
                primary_category = cat
                # Seleciona o termo de maior especificidade (mais longo) e maior confiança
                best_matches = sorted(
                    matches_by_cat[cat],
                    key=lambda m: (m[1], len(m[0])),
                    reverse=True
                )
                best_term, best_confidence = best_matches[0]
                break

        # Fallback caso a categoria encontrada não esteja na lista de precedência
        if not primary_category:
            sorted_cats = sorted(
                matches_by_cat.keys(),
                key=lambda c: max(m[1] for m in matches_by_cat[c]),
                reverse=True
            )
            primary_category = sorted_cats[0]
            best_term, best_confidence = matches_by_cat[primary_category][0]

        # 5. Identificação de categorias secundárias/correlatas
        secondary = []
        for cat in self.precedence:
            if cat != primary_category and cat in matches_by_cat:
                secondary.append(cat)

        # Regra de negócio canônica: Vagas (PESSOAS) com contexto de nova loja correlaciona com EXPANSÃO
        if primary_category == "PESSOAS":
            if any(k in norm_text for k in ["nova unidade", "nova loja", "inaugur", "filial"]):
                if "EXPANSÃO" not in secondary:
                    secondary.append("EXPANSÃO")

        return AnchorClassification(
            category=primary_category,
            confidence=round(best_confidence, 4),
            matched_term=best_term,
            source_type="text_signal",
            secondary_categories=tuple(secondary),
            metadata={"total_categories_matched": len(matches_by_cat)},
        )


# Instância canônica global do classificador de âncoras de domínio
_GLOBAL_CLASSIFIER = GenericAnchorClassifier()


def classificar_ancora(
    text: str,
    profile: Optional[Dict[str, Any]] = None,
    is_price_candidate_fn: Optional[Callable[..., bool]] = None,
    url: str = "",
    title: str = "",
) -> AnchorClassification:
    """
    Função pública canônica para classificação determinística de âncoras/sinais.
    """
    return _GLOBAL_CLASSIFIER.classify(
        text=text,
        profile=profile,
        is_price_candidate_fn=is_price_candidate_fn,
        url=url,
        title=title,
    )


def classificar_texto_ancora(text: str) -> str:
    """
    Retorna apenas a categoria canônica de uma âncora textual (ou 'UNKNOWN').
    """
    return classificar_ancora(text).category
