# -*- coding: utf-8 -*-
"""
Catálogo e Resolução de Perfis de Nicho — Agente Sniper
Camada de domínio para taxonomias, vocabulários e estratégias de inteligência competitiva por segmento.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

NICHE_PROFILES: Dict[str, Dict[str, Any]] = {
    "supermercado": {
        "label": "Varejo alimentar",
        "queries": [
            "preço oferta promoção cesta concorrente",
            "reclamação atendimento fila produto entrega",
            "inauguração loja expansão app delivery fidelidade",
            "Procon fiscalização vigilância sanitária",
            "emprego contratação nova unidade",
        ],
        "signals": ["preço", "oferta", "promoção", "fila", "produto", "entrega", "loja", "app", "delivery", "inauguração"],
        "commercial_sources": [
            {
                "name": "Assaí Atacadista",
                "role": "competitor",
                "url": "https://www.assai.com.br/ofertas",
                "channel_type": "flyer_ocr",
                "location_note": "nacional",
            },
            {
                "name": "Pão de Açúcar",
                "role": "competitor",
                "url": "https://www.paodeacucar.com",
                "channel_type": "interactive_catalog",
                "location_note": "nacional",
            },
        ],
        "relevance_weights": {
            "PREÇO": 1.00, "EXPANSÃO": 0.90, "PRODUTO/SERVIÇO": 0.85,
            "DIGITAL": 0.80, "REPUTAÇÃO": 0.80, "ATENDIMENTO": 0.75,
            "PESSOAS": 0.70, "REGULAÇÃO": 0.70, "MARKETING": 0.65, "PARCERIA": 0.50
        },
    },
    "restaurante": {
        "label": "Alimentação e hospitalidade",
        "queries": [
            "preço cardápio promoção delivery concorrente",
            "avaliação reclamação atendimento qualidade",
            "nova unidade expansão franquia",
            "iFood delivery aplicativo marketing",
            "fiscalização vigilância sanitária",
        ],
        "signals": ["cardápio", "preço", "delivery", "avaliação", "atendimento", "franquia", "unidade"],
        "commercial_sources": [],
        "relevance_weights": {
            "PRODUTO/SERVIÇO": 1.00, "REPUTAÇÃO": 0.95, "ATENDIMENTO": 0.90,
            "DIGITAL": 0.90, "PREÇO": 0.80, "EXPANSÃO": 0.75,
            "MARKETING": 0.70, "PESSOAS": 0.65, "REGULAÇÃO": 0.65, "PARCERIA": 0.50
        },
    },
    "clinica": {
        "label": "Saúde e serviços clínicos",
        "queries": [
            "serviços especialidades preço convênio",
            "avaliação reclamação atendimento",
            "nova unidade médicos contratação",
            "marketing tecnologia agendamento aplicativo",
            "licença fiscalização regulação",
        ],
        "signals": ["especialidade", "convênio", "consulta", "avaliação", "atendimento", "agendamento", "unidade"],
        "commercial_sources": [],
        "relevance_weights": {
            "REGULAÇÃO": 1.00, "PESSOAS": 0.95, "REPUTAÇÃO": 0.95,
            "PRODUTO/SERVIÇO": 0.90, "ATENDIMENTO": 0.85, "DIGITAL": 0.80,
            "EXPANSÃO": 0.75, "PARCERIA": 0.70, "PREÇO": 0.50, "MARKETING": 0.50
        },
    },
    "hotel": {
        "label": "Hotelaria",
        "queries": [
            "diária preço promoção concorrente",
            "avaliação reclamação atendimento",
            "ocupação expansão nova unidade",
            "booking hoteis.com turismo eventos",
            "serviços experiência hóspede",
        ],
        "signals": ["diária", "hotel", "reserva", "ocupação", "avaliação", "hóspede", "serviço"],
        "commercial_sources": [],
        "relevance_weights": {
            "PRODUTO/SERVIÇO": 1.00, "REPUTAÇÃO": 0.95, "ATENDIMENTO": 0.90,
            "DIGITAL": 0.85, "PREÇO": 0.85, "EXPANSÃO": 0.80,
            "MARKETING": 0.75, "PARCERIA": 0.70, "PESSOAS": 0.65, "REGULAÇÃO": 0.60
        },
    },
    "farmacia": {
        "label": "Varejo farmacêutico",
        "queries": [
            "preço promoção medicamento concorrente",
            "avaliação atendimento entrega",
            "nova loja expansão",
            "app delivery fidelidade",
            "Anvisa Procon fiscalização",
        ],
        "signals": ["preço", "promoção", "medicamento", "delivery", "farmácia", "loja", "Anvisa"],
        "commercial_sources": [],
        "relevance_weights": {
            "PRODUTO/SERVIÇO": 1.00, "REGULAÇÃO": 0.95, "PREÇO": 0.90,
            "DIGITAL": 0.85, "REPUTAÇÃO": 0.80, "ATENDIMENTO": 0.75,
            "EXPANSÃO": 0.75, "PESSOAS": 0.70, "MARKETING": 0.60, "PARCERIA": 0.55
        },
    },
    "imobiliaria": {
        "label": "Mercado imobiliário",
        "queries": [
            "lançamento preço imóvel concorrente",
            "avaliação atendimento corretores",
            "novos empreendimentos expansão",
            "marketing leads digital",
            "mercado vendas aluguel",
        ],
        "signals": ["imóvel", "lançamento", "preço", "aluguel", "vendas", "leads", "empreendimento"],
        "commercial_sources": [],
        "relevance_weights": {
            "PRODUTO/SERVIÇO": 1.00, "PREÇO": 0.95, "EXPANSÃO": 0.90,
            "DIGITAL": 0.85, "MARKETING": 0.80, "PARCERIA": 0.75,
            "REPUTAÇÃO": 0.70, "PESSOAS": 0.70, "REGULAÇÃO": 0.65, "ATENDIMENTO": 0.60
        },
    },
    "tecnologia": {
        "label": "Tecnologia e SaaS",
        "queries": [
            "produto lançamento preço concorrente",
            "avaliação cliente churn reclamação",
            "parceria investimento aquisição",
            "feature roadmap tecnologia",
            "contratação engenharia vendas",
        ],
        "signals": ["produto", "SaaS", "preço", "feature", "API", "parceria", "investimento"],
        "commercial_sources": [],
        "relevance_weights": {
            "PRODUTO/SERVIÇO": 1.00, "DIGITAL": 0.95, "PARCERIA": 0.90,
            "PESSOAS": 0.85, "EXPANSÃO": 0.80, "MARKETING": 0.75,
            "REPUTAÇÃO": 0.70, "PREÇO": 0.65, "REGULAÇÃO": 0.60, "ATENDIMENTO": 0.60
        },
    },
    "educacao": {
        "label": "Educação",
        "queries": [
            "curso preço matrícula promoção concorrente",
            "avaliação aluno atendimento",
            "nova unidade expansão",
            "plataforma aplicativo tecnologia",
            "vagas contratação professores",
        ],
        "signals": ["curso", "mensalidade", "matrícula", "aluno", "professor", "plataforma", "unidade"],
        "commercial_sources": [],
        "relevance_weights": {
            "PRODUTO/SERVIÇO": 1.00, "PESSOAS": 0.95, "REPUTAÇÃO": 0.90,
            "PREÇO": 0.85, "DIGITAL": 0.85, "EXPANSÃO": 0.80,
            "REGULAÇÃO": 0.75, "ATENDIMENTO": 0.70, "MARKETING": 0.70, "PARCERIA": 0.60
        },
    },
    "varejo": {
        "label": "Varejo geral",
        "queries": [
            "preço promoção produto concorrente",
            "avaliação atendimento entrega",
            "nova loja expansão",
            "e-commerce aplicativo fidelidade",
            "campanha marketing lançamento",
        ],
        "signals": ["preço", "promoção", "produto", "loja", "e-commerce", "app", "campanha"],
        "commercial_sources": [],
        "relevance_weights": {
            "PREÇO": 1.00, "PRODUTO/SERVIÇO": 0.90, "DIGITAL": 0.85,
            "EXPANSÃO": 0.85, "REPUTAÇÃO": 0.80, "MARKETING": 0.75,
            "ATENDIMENTO": 0.75, "PESSOAS": 0.70, "REGULAÇÃO": 0.65, "PARCERIA": 0.55
        },
    },
    "servicos": {
        "label": "Serviços",
        "queries": [
            "preço serviço concorrente",
            "avaliação reclamação atendimento",
            "expansão nova unidade contratação",
            "digital aplicativo agendamento",
            "marketing parceria campanha",
        ],
        "signals": ["preço", "serviço", "avaliação", "atendimento", "agendamento", "parceria"],
        "commercial_sources": [],
        "relevance_weights": {
            "PRODUTO/SERVIÇO": 1.00, "REPUTAÇÃO": 0.95, "ATENDIMENTO": 0.90,
            "PESSOAS": 0.85, "DIGITAL": 0.80, "PREÇO": 0.75,
            "PARCERIA": 0.75, "EXPANSÃO": 0.70, "MARKETING": 0.65, "REGULAÇÃO": 0.60
        },
    },
    "generico": {
        "label": "Empresa genérica",
        "queries": [
            "preço produto serviço concorrente",
            "avaliação reclamação atendimento",
            "expansão nova unidade contratação",
            "produto tecnologia marketing",
            "regulação fiscalização parceria",
        ],
        "signals": ["preço", "produto", "serviço", "avaliação", "expansão", "tecnologia", "marketing"],
        "commercial_sources": [],
        "relevance_weights": {
            "PREÇO": 0.85, "EXPANSÃO": 0.85, "REGULAÇÃO": 0.85,
            "REPUTAÇÃO": 0.80, "DIGITAL": 0.75, "PRODUTO/SERVIÇO": 0.75,
            "PESSOAS": 0.70, "ATENDIMENTO": 0.70, "MARKETING": 0.65, "PARCERIA": 0.55
        },
    },
}


def obter_perfil_nicho(nicho: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna o perfil de nicho configurado ou o perfil genérico como fallback.
    Trata case-insensitivity e remoção de espaços em branco.
    """
    if not nicho or not isinstance(nicho, str):
        return NICHE_PROFILES["generico"]
    nicho_norm = nicho.strip().lower()
    return NICHE_PROFILES.get(nicho_norm, NICHE_PROFILES["generico"])


def listar_nichos_disponiveis() -> List[str]:
    """Retorna a lista ordenada dos identificadores de nichos suportados pelo Agente Sniper."""
    return list(NICHE_PROFILES.keys())
