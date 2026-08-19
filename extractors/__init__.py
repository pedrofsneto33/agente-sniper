# -*- coding: utf-8 -*-
"""
Motor Genérico de Extração e Recuperação de Informação Espacial — Fase 6E
"""

from extractors.models import (
    BoundingBox,
    SpatialToken,
    ExclusionZone,
    RawSpatialDocument,
    CandidateAnchor,
    EvidenceRegion,
    SpatialCluster,
    EvidenceItem,
    ExtractedEntity,
    ExtractionResult,
)
from extractors.spatial_normalizer import normalizar_documento_espacial
from extractors.fusion import fundir_tokens_fragmentados
from extractors.candidates import (
    CandidateRule,
    StrictCurrencyRule,
    MeasurementContextRule,
    LegalProcessRule,
    PercentageRule,
    SalaryRule,
    TaxIdRule,
    DateRule,
    CandidateDetector,
)
from extractors.clustering import clusterizar_espacialmente
from extractors.entity_resolver import EntityResolver, GenericEntityResolver
from extractors.evaluation import (
    GroundTruthItem,
    GoldDataset,
    EvaluationMetrics,
    avaliar_extracao,
)
from extractors.adapters.flyer_product_adapter import FlyerProductAdapter, FlyerProductResolver
from extractors.bridge import (
    obter_engine_ativo,
    carregar_ocr_bruto,
    converter_entidades_para_price_items,
    converter_para_schema_legacy_cards,
    executar_pipeline_extracao,
)
from extractors.canary import (
    CanaryItemComparison,
    CanaryDocumentReport,
    comparar_documento_canary,
    percentil,
)
from extractors.canary_history import (
    CanaryHistoryRecord,
    CanaryHistoryTracker,
    calcular_hash_conteudo_ou_arquivo,
    CANARY_HISTORY_PATH,
)
from extractors.promotion_gate import (
    PromotionGate,
    PromotionGateResult,
    SQLITE_CANONICAL_HASH,
    calcular_sha256_arquivo,
)

__all__ = [
    "BoundingBox",
    "SpatialToken",
    "ExclusionZone",
    "RawSpatialDocument",
    "CandidateAnchor",
    "EvidenceRegion",
    "SpatialCluster",
    "EvidenceItem",
    "ExtractedEntity",
    "ExtractionResult",
    "normalizar_documento_espacial",
    "fundir_tokens_fragmentados",
    "CandidateRule",
    "StrictCurrencyRule",
    "MeasurementContextRule",
    "LegalProcessRule",
    "PercentageRule",
    "SalaryRule",
    "TaxIdRule",
    "DateRule",
    "CandidateDetector",
    "clusterizar_espacialmente",
    "EntityResolver",
    "GenericEntityResolver",
    "GroundTruthItem",
    "GoldDataset",
    "EvaluationMetrics",
    "avaliar_extracao",
    "FlyerProductAdapter",
    "FlyerProductResolver",
    "obter_engine_ativo",
    "carregar_ocr_bruto",
    "converter_entidades_para_price_items",
    "converter_para_schema_legacy_cards",
    "executar_pipeline_extracao",
    "CanaryItemComparison",
    "CanaryDocumentReport",
    "comparar_documento_canary",
    "percentil",
    "CanaryHistoryRecord",
    "CanaryHistoryTracker",
    "calcular_hash_conteudo_ou_arquivo",
    "CANARY_HISTORY_PATH",
    "PromotionGate",
    "PromotionGateResult",
    "SQLITE_CANONICAL_HASH",
    "calcular_sha256_arquivo",
]
