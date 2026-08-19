# -*- coding: utf-8 -*-
"""
Adapter Genérico de Extração Espacial Multi-Nicho — Fase 14.1
Fornece uma esteira espacial desacoplada de premissas ou zonas de exclusão de encarte/tablóide.
"""

from typing import Any, Dict, List, Optional, Sequence

from extractors.models import (
    BoundingBox,
    SpatialToken,
    ExclusionZone,
    RawSpatialDocument,
    EvidenceRegion,
    ExtractedEntity,
    EvidenceItem,
    ExtractionResult,
)
from extractors.spatial_normalizer import normalizar_documento_espacial, normalizar_espacos
from extractors.candidates import StrictCurrencyRule, CandidateDetector
from extractors.clustering import clusterizar_espacialmente
from extractors.entity_resolver import EntityResolver


class GeneralSpatialAdapter:
    """
    Fachada genérica do motor espacial multi-nicho.
    Agnóstica a formato físico ou encarte — NÃO impõe zonas de exclusão fixas.
    Apropriada para páginas web, tabelas de SaaS, cartazes de academia, hotelaria e serviços gerais.
    """

    def __init__(
        self,
        zonas_exclusao: Optional[Sequence[ExclusionZone]] = None,
        min_preco: float = 0.10,
        max_preco: float = 999999.0,
        fundir_fragmentos_ocr: bool = False,
        resolver: Optional[EntityResolver] = None
    ):
        from extractors.adapters.flyer_product_adapter import FlyerProductResolver

        self.zonas_exclusao = list(zonas_exclusao) if zonas_exclusao is not None else []
        self.fundir_fragmentos_ocr = fundir_fragmentos_ocr
        self.detector = CandidateDetector(rules=[
            StrictCurrencyRule(default_currency="BRL", min_val=min_preco, max_val=max_preco)
        ])
        self.resolver = resolver or FlyerProductResolver()

    def processar_documento(self, documento_bruto: RawSpatialDocument) -> ExtractionResult:
        """Executa a esteira espacial agnóstica sobre o documento espacial."""
        # 1. Normalização espacial (sem exclusão fixa se zonas_exclusao estiver vazio)
        doc_normalizado = normalizar_documento_espacial(
            documento_bruto,
            zonas_exclusao=self.zonas_exclusao,
            confianca_minima=0.25,
            fundir_fragmentos=self.fundir_fragmentos_ocr
        )

        # 2. Detecção estrita de âncoras de preço
        ancoras = self.detector.detect_anchors(doc_normalizado)

        # 3. Agrupamento espacial delimitado
        regioes = clusterizar_espacialmente(
            documento=doc_normalizado,
            ancoras=ancoras,
            max_distancia_horizontal_rel=0.22,
            max_distancia_vertical_rel=0.40
        )

        # 4. Resolução de entidades estruturadas
        resultado = self.resolver.resolve_all(
            regioes,
            documento_id=documento_bruto.identificador,
            dimensoes_pagina=doc_normalizado.dimensoes
        )
        resultado.metricas.update({
            "tokens_originais": len(documento_bruto.tokens),
            "tokens_apos_filtro": len(doc_normalizado.tokens),
            "ancoras_detectadas": len(ancoras),
            "clusters_formados": len(regioes),
        })

        return resultado
