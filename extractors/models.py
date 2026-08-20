# -*- coding: utf-8 -*-
"""
Contratos e Modelos de Dados Genéricos do Motor de Extração Espacial — Fase 2
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Sequence
import math


@dataclass(frozen=True)
class BoundingBox:
    """Caixa delimitadora espacial 2D imutável (x_min, y_min, x_max, y_max)."""
    x_min: float = 0.0
    y_min: float = 0.0
    x_max: float = 0.0
    y_max: float = 0.0

    def __post_init__(self):
        if self.x_min > self.x_max:
            x_min, x_max = self.x_max, self.x_min
            object.__setattr__(self, "x_min", x_min)
            object.__setattr__(self, "x_max", x_max)
        if self.y_min > self.y_max:
            y_min, y_max = self.y_max, self.y_min
            object.__setattr__(self, "y_min", y_min)
            object.__setattr__(self, "y_max", y_max)

    @property
    def largura(self) -> float:
        return max(0.0, self.x_max - self.x_min)

    @property
    def altura(self) -> float:
        return max(0.0, self.y_max - self.y_min)

    @property
    def centro_x(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def centro_y(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    @property
    def area(self) -> float:
        return self.largura * self.altura

    @property
    def is_valid(self) -> bool:
        return self.largura > 0.0 or self.altura > 0.0

    def contains_point(self, x: float, y: float) -> bool:
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max

    def intersects(self, other: Optional["BoundingBox"]) -> bool:
        if other is None or not self.is_valid or not other.is_valid:
            return False
        return not (
            self.x_max < other.x_min
            or self.x_min > other.x_max
            or self.y_max < other.y_min
            or self.y_min > other.y_max
        )

    def intersection_area(self, other: Optional["BoundingBox"]) -> float:
        if other is None:
            return 0.0
        x_overlap = max(0.0, min(self.x_max, other.x_max) - max(self.x_min, other.x_min))
        y_overlap = max(0.0, min(self.y_max, other.y_max) - max(self.y_min, other.y_min))
        return x_overlap * y_overlap

    def iou(self, other: Optional["BoundingBox"]) -> float:
        if other is None:
            return 0.0
        inter = self.intersection_area(other)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0

    def distance_to(self, other: Optional["BoundingBox"]) -> float:
        """Distância euclidiana entre os centros das duas caixas."""
        if other is None:
            return float("inf")
        dx = (self.x_min + self.x_max - other.x_min - other.x_max) * 0.5
        dy = (self.y_min + self.y_max - other.y_min - other.y_max) * 0.5
        return math.hypot(dx, dy)

    def expand(self, other: Optional["BoundingBox"]) -> "BoundingBox":
        """Retorna uma nova caixa que envolve ambas as caixas."""
        if other is None or not other.is_valid:
            return self
        if not self.is_valid:
            return other
        return BoundingBox(
            x_min=min(self.x_min, other.x_min),
            y_min=min(self.y_min, other.y_min),
            x_max=max(self.x_max, other.x_max),
            y_max=max(self.y_max, other.y_max),
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "x_min": round(self.x_min, 2),
            "y_min": round(self.y_min, 2),
            "x_max": round(self.x_max, 2),
            "y_max": round(self.y_max, 2),
            "largura": round(self.largura, 2),
            "altura": round(self.altura, 2),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["BoundingBox"]:
        if not data or not isinstance(data, dict):
            return None
        try:
            return cls(
                x_min=float(data.get("x_min", 0.0)),
                y_min=float(data.get("y_min", 0.0)),
                x_max=float(data.get("x_max", 0.0)),
                y_max=float(data.get("y_max", 0.0)),
            )
        except (ValueError, TypeError):
            return None


@dataclass(frozen=True)
class SpatialToken:
    """
    Token de texto associado ou não a uma posição espacial.
    Suporta documentos sem BBox (HTML, texto puro, PDFs simples).
    """
    texto: str
    bbox: Optional[BoundingBox] = None
    confianca: float = 1.0
    id_token: Optional[int] = None
    metadados: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_geometry(self) -> bool:
        b = self.bbox
        return b is not None and ((b.x_max > b.x_min) or (b.y_max > b.y_min))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id_token": self.id_token,
            "texto": self.texto,
            "confianca": round(self.confianca, 4),
            "bbox": self.bbox.to_dict() if self.bbox is not None else None,
            "tem_geometria": self.has_geometry,
            "metadados": self.metadados,
        }


@dataclass(frozen=True)
class ExclusionZone:
    """Zona de exclusão espacial (ex: cabeçalhos de logos ou rodapés jurídicos)."""
    nome: str
    relative_bbox: BoundingBox  # Coordenadas relativas 0.0 a 1.0


@dataclass
class RawSpatialDocument:
    """Documento espacial bruto recebido de OCR, PDF, HTML ou Layout Parser."""
    identificador: str
    origem: str
    dimensoes: Tuple[float, float] = (1.0, 1.0)  # (largura, altura)
    tokens: List[SpatialToken] = field(default_factory=list)
    metadados: Dict[str, Any] = field(default_factory=dict)


class AnchorEvidenceKind(str, Enum):
    """Taxonomia abstrata para classificação da força e natureza de âncoras numéricas multi-nicho."""
    EXPLICIT_CURRENCY = "explicit_currency"  # Moeda explícita: R$ 20,79, $ 99.00, € 15,00
    CADENCE_PRICE     = "cadence_price"      # Preço com cadência/recorrência: 99,90/mês, 20,79 CADA, 180,00/sessão
    BARE_DECIMAL      = "bare_decimal"       # Decimal isolado sem indicador de moeda: 23,90, 59,90, 162,49
    SPECIFICATION     = "specification"      # Valor atrelado a quantidade/medida: 162,4g, 10 sessões, 2 diárias
    TEMPORAL_OR_CODE  = "temporal_code"      # Identificador temporal ou código: 2026, 0812345-67...


class AnchorRole(str, Enum):
    """Papel relacional da âncora dentro de uma oferta ou contexto estruturado."""
    STANDALONE    = "standalone"     # Preço padrão/isolado vigente
    OLD_PRICE     = "old_price"      # Preço anterior/regular em oferta ("De", "Antes", "Era", etc.)
    CURRENT_PRICE = "current_price"  # Preço promocional/vigente em oferta ("Por", "Agora", "Promoção", etc.)


@dataclass(frozen=True)
class CandidateAnchor:
    """Âncora candidata identificada (Preço, Salário, Processo, Data, CNPJ, etc.)."""
    tipo: str
    texto_bruto: str
    valor_normalizado: Any
    unidade: Optional[str]
    confianca: float
    token_ref: SpatialToken
    bbox: Optional[BoundingBox] = None
    evidence_kind: AnchorEvidenceKind = AnchorEvidenceKind.BARE_DECIMAL
    cadencia: Optional[str] = None
    role: AnchorRole = AnchorRole.STANDALONE
    metadados: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_strong_monetary_evidence(self) -> bool:
        """Indica se a âncora possui evidência monetária explícita ou cadência de oferta."""
        return self.evidence_kind in (AnchorEvidenceKind.EXPLICIT_CURRENCY, AnchorEvidenceKind.CADENCE_PRICE)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tipo": self.tipo,
            "texto_bruto": self.texto_bruto,
            "valor_normalizado": self.valor_normalizado,
            "unidade": self.unidade,
            "confianca": round(self.confianca, 4),
            "evidence_kind": self.evidence_kind.value if hasattr(self.evidence_kind, "value") else str(self.evidence_kind),
            "cadencia": self.cadencia,
            "role": self.role.value if hasattr(self.role, "value") else str(self.role),
            "bbox": self.bbox.to_dict() if self.bbox is not None else None,
            "token_id": self.token_ref.id_token,
        }


@dataclass
class EvidenceRegion:
    """
    Região de Evidência Auditável.
    Evolução de SpatialCluster com suporte a âncora única, múltiplas âncoras ou sem âncora.
    Registra decisões, tokens incluídos, tokens rejeitados e scores.
    """
    identificador: str = ""
    ancoras: List[CandidateAnchor] = field(default_factory=list)
    tokens_incluidos: List[SpatialToken] = field(default_factory=list)
    tokens_rejeitados: List[Dict[str, Any]] = field(default_factory=list)
    bbox_delimitada: Optional[BoundingBox] = None
    scores: Dict[str, float] = field(default_factory=dict)
    motivos_decisao: List[str] = field(default_factory=list)

    # Retrocompatibilidade com SpatialCluster
    @property
    def ancora(self) -> Optional[CandidateAnchor]:
        return self.ancoras[0] if self.ancoras else None

    @ancora.setter
    def ancora(self, val: Optional[CandidateAnchor]):
        if val is not None:
            self.ancoras = [val]
        else:
            self.ancoras = []

    @property
    def tokens_contexto(self) -> List[SpatialToken]:
        return self.tokens_incluidos

    @tokens_contexto.setter
    def tokens_contexto(self, val: List[SpatialToken]):
        self.tokens_incluidos = val

    def calcular_bbox_envolvente(self) -> Optional[BoundingBox]:
        box: Optional[BoundingBox] = None
        for a in self.ancoras:
            if a.bbox is not None and a.bbox.is_valid:
                box = a.bbox if box is None else box.expand(a.bbox)

        for t in self.tokens_incluidos:
            if t.bbox is not None and t.bbox.is_valid:
                box = t.bbox if box is None else box.expand(t.bbox)

        self.bbox_delimitada = box
        return box

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identificador": self.identificador,
            "total_ancoras": len(self.ancoras),
            "ancoras": [a.to_dict() for a in self.ancoras],
            "total_tokens_incluidos": len(self.tokens_incluidos),
            "total_tokens_rejeitados": len(self.tokens_rejeitados),
            "tokens_rejeitados": self.tokens_rejeitados,
            "bbox_delimitada": self.bbox_delimitada.to_dict() if self.bbox_delimitada else None,
            "scores": self.scores,
            "motivos_decisao": self.motivos_decisao,
        }


# Alias de retrocompatibilidade
SpatialCluster = EvidenceRegion


@dataclass(frozen=True)
class EvidenceItem:
    """Item de evidência forense rastreável com coordenadas e confiança."""
    tipo: str
    texto_bruto: str
    confianca: float
    bbox: Optional[BoundingBox] = None
    token_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tipo": self.tipo,
            "texto_bruto": self.texto_bruto,
            "confianca": round(self.confianca, 4),
            "bbox": self.bbox.to_dict() if self.bbox is not None else None,
            "token_id": self.token_id,
        }


@dataclass
class ExtractedEntity:
    """Entidade genérica extraída com atributos, valores e evidências auditáveis."""
    entidade: str
    atributos: Dict[str, Any]
    valor: Optional[Any] = None
    old_price: Optional[float] = None
    unidade: Optional[str] = None
    confianca: float = 0.0
    origem_tipo: str = "ancora_unica"  # "ancora_unica", "multiplas_ancoras", "apenas_contexto"
    ancoras: List[CandidateAnchor] = field(default_factory=list)
    valores: List[Dict[str, Any]] = field(default_factory=list)
    evidencias: List[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "entidade": self.entidade,
            "origem_tipo": self.origem_tipo,
            "atributos": self.atributos,
            "valor": self.valor,
            "unidade": self.unidade,
            "valores": self.valores if self.valores else None,
            "confianca": round(self.confianca, 4),
            "evidencias": [e.to_dict() for e in self.evidencias],
        }
        if self.old_price is not None:
            d["old_price"] = self.old_price
        elif "old_price" in self.atributos and self.atributos["old_price"] is not None:
            d["old_price"] = self.atributos["old_price"]
        return d


@dataclass
class ExtractionResult:
    """Resultado estruturado e auditável de uma extração espacial."""
    documento_id: str
    tipo_extracao: str
    total_entidades: int
    entidades: List[ExtractedEntity]
    regioes_evidencia: List[EvidenceRegion] = field(default_factory=list)
    metricas: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "documento_id": self.documento_id,
            "tipo_extracao": self.tipo_extracao,
            "total_entidades": self.total_entidades,
            "entidades": [e.to_dict() for e in self.entidades],
            "metricas": self.metricas,
        }
