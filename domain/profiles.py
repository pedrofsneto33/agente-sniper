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
