# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Modelos de Dados e Entidades (Dataclasses).
Lógica pura de domínio sem I/O, rede, banco ou estado global.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from domain.normalizer import normalizar


@dataclass
class Fonte:
    """Entidade que representa uma fonte bruta coletada e classificada."""
    id: int
    titulo: str
    url: str
    origem: str
    categoria: str = "geral"
    conteudo: str = ""
    resumo_busca: str = ""
    data_publicacao: str = ""
    data_tipo: str = "desconhecida"
    atual: bool = False
    direta: bool = False
    score: float = 0.0
    confianca: float = 0.0
    alias_empresa: str = ""
    cidade_confirmada: bool = False
    estado_confirmado: bool = False
    escopo: str = "global"  # local | nacional | corporativo | global | incerto
    fingerprint: str = ""
    dominio: str = ""
    sinais: List[str] = field(default_factory=list)
    entidade: str = ""  # empresa monitorada | concorrente | mercado

    def texto(self) -> str:
        """Concatena os campos textuais para análise temática e de sinais."""
        return f"{self.titulo}\n{self.url}\n{self.resumo_busca}\n{self.conteudo}"


@dataclass
class PriceItem:
    """Entidade de produto e precificação para matching de catálogos."""
    source: str
    role: str
    name: str
    url: str
    price: Optional[float] = None
    old_price: Optional[float] = None
    promotion: bool = False
    brand: str = ""
    unit: str = ""
    sku: str = ""
    matched_name: str = ""
    competitor: str = ""
    similarity: float = 0.0
    availability: str = "unknown"
    location_note: str = ""
    evidence_url: str = ""
    page_type: str = ""
    price_confidence: float = 0.0

    def key(self) -> str:
        """Gera chave canônica do item para indexação."""
        return normalizar(f"{self.brand} {self.name} {self.unit} {self.sku}")
