# -*- coding: utf-8 -*-
"""
Adapter de Extração de Produtos e Preços de Encartes / Folhetos Digitais — Fase 2
Especializa o motor genérico espacial sem hardcode na camada central.
"""

import re
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
from extractors.candidates import StrictCurrencyRule, MeasurementContextRule, CandidateDetector
from extractors.clustering import clusterizar_espacialmente
from extractors.entity_resolver import EntityResolver


class FlyerProductResolver(EntityResolver):
    """Resolvedor especializado para produtos de varejo em encartes."""

    def __init__(self):
        self.tipo_entidade = "produto"
        self._re_medida = re.compile(
            r'(\b\d+(?:[.,]\d+)?\s*(?:kg|g|mg|ml|l|litros?|sach[eê]s?|c[aá]psulas?|unidades?|un|cm|mm|m)\b|\b\d+x\d+(?:[.,]\d+)?\s*(?:g|ml|cm|mm)?\b)',
            re.IGNORECASE
        )
        self._re_embalagem = re.compile(
            r'\b(caixeta|pacote|frasco|cartela|sach[eê]|lata|garrafa|pote|bandeja|caixa|pack|v[aá]cuo)\b',
            re.IGNORECASE
        )
        self._re_ruido_comercial = re.compile(
            r'^(r\$|cada|un|kg|de|por|unidade|compre|leve)$',
            re.IGNORECASE
        )
        self._re_disclaimer = re.compile(
            r'\b(pre[cç]os?\s+v[aá]lidos?|imagens?\s+(?:meramente\s+)?ilustrativas?|ofertas?\s+v[aá]lidas?|enquanto\s+durarem\s+os?\s+estoques?|condi[cç][oõ]es?\s+gerais|v[aá]lido\s+(?:de\s+\d+|para\s+todas))\b',
            re.IGNORECASE
        )
        self._re_condicao_comercial = re.compile(
            r'^(?:a\s+partir\s+de(?:\s+\d+\s*(?:unidades?|un\.?|kg|g|cx|pct|pe[cç]as?|itens|l|litros?))?|'
            r'leve\s+\d+\s+pague\s+\d+|'
            r'na\s+compra\s+de\s+\d+.*|'
            r'acima\s+de\s+\d+.*|'
            r'm[ií]nimo\s+de\s+\d+.*|'
            r'desconto\s+de\s+\d+.*|'
            r'compre\s+mais\s+pague\s+menos|'
            r'\d+\s*(?:unidades?|un\.?))$',
            re.IGNORECASE
        )

    def resolve_region(self, region: EvidenceRegion) -> Optional[ExtractedEntity]:
        ancora = region.ancora
        if not ancora:
            return None

        tokens = region.tokens_incluidos
        if not tokens:
            # Âncora isolada sem tokens de contexto: preserva a entidade sem fabricar nome artificial
            return ExtractedEntity(
                entidade="produto",
                origem_tipo="ancora_isolada",
                atributos={
                    "nome": ancora.texto_bruto,
                    "peso_volume": None,
                    "condicao_comercial": None,
                    "textos_detectados": [],
                    "regiao_card": region.bbox_delimitada.to_dict() if region.bbox_delimitada else None
                },
                valor=ancora.valor_normalizado,
                unidade=ancora.unidade or "BRL",
                ancoras=[ancora],
                confianca=ancora.confianca,
                evidencias=[EvidenceItem(
                    tipo="preco_anuncio",
                    texto_bruto=ancora.texto_bruto,
                    confianca=ancora.confianca,
                    bbox=ancora.bbox,
                    token_id=ancora.token_ref.id_token
                )]
            )

        # 1. Coleta e categorização de textos
        textos_filtrados: List[str] = []
        medidas_encontradas: List[str] = []
        embalagens_encontradas: List[str] = []
        condicoes_encontradas: List[str] = []
        evidencias: List[EvidenceItem] = []

        # Evidência da âncora de preço
        evidencias.append(EvidenceItem(
            tipo="preco_anuncio",
            texto_bruto=ancora.texto_bruto,
            confianca=ancora.confianca,
            bbox=ancora.bbox,
            token_id=ancora.token_ref.id_token
        ))

        # Classifica os tokens de contexto
        for t in tokens:
            t_str = normalizar_espacos(t.texto)
            if not t_str or self._re_ruido_comercial.match(t_str) or self._re_disclaimer.search(t_str):
                continue

            # Detecta condições comerciais (não podem ser nome de produto)
            if self._re_condicao_comercial.match(t_str):
                condicoes_encontradas.append(t_str)
                continue

            # Detecta medidas
            match_med = self._re_medida.search(t_str)
            if match_med:
                medidas_encontradas.append(match_med.group(1))

            # Detecta termos de embalagem
            match_emb = self._re_embalagem.search(t_str)
            if match_emb:
                embalagens_encontradas.append(t_str)

            textos_filtrados.append(t_str)
            evidencias.append(EvidenceItem(
                tipo="texto_produto",
                texto_bruto=t_str,
                confianca=t.confianca,
                bbox=t.bbox,
                token_id=t.id_token
            ))

        # 2. Heurística determinística de nome de produto:
        # Ordena por proximidade vertical em relação à âncora de preço
        if ancora.bbox:
            tokens_proximos = sorted(
                [
                    t for t in tokens
                    if not self._re_ruido_comercial.match(normalizar_espacos(t.texto))
                    and not self._re_disclaimer.search(normalizar_espacos(t.texto))
                    and not self._re_condicao_comercial.match(normalizar_espacos(t.texto))
                    and t.bbox
                ],
                key=lambda t: abs(t.bbox.centro_y - ancora.bbox.centro_y) if t.bbox else 0
            )
        else:
            tokens_proximos = [
                t for t in tokens
                if not self._re_ruido_comercial.match(normalizar_espacos(t.texto))
                and not self._re_disclaimer.search(normalizar_espacos(t.texto))
                and not self._re_condicao_comercial.match(normalizar_espacos(t.texto))
            ]

        linhas_candidatas = [t.texto.strip() for t in tokens_proximos if len(t.texto.strip()) >= 5]
        nome_candidato = " ".join(linhas_candidatas[:2]) if linhas_candidatas else " ".join(textos_filtrados[:2])
        nome_limpo = normalizar_espacos(nome_candidato) if (linhas_candidatas or textos_filtrados) else ancora.texto_bruto

        # 3. Identificação de marca e peso/volume
        peso_volume = medidas_encontradas[-1] if medidas_encontradas else None
        if embalagens_encontradas and peso_volume:
            if peso_volume not in embalagens_encontradas[-1]:
                peso_volume = f"{embalagens_encontradas[-1]} {peso_volume}"
            else:
                peso_volume = embalagens_encontradas[-1]

        # 4. Cálculo de confiança consolidada
        conf_preco = ancora.confianca
        conf_textos = sum(t.confianca for t in tokens) / max(1, len(tokens))
        conf_final = round(min(1.0, 0.60 * conf_preco + 0.40 * conf_textos), 4)

        return ExtractedEntity(
            entidade="produto",
            origem_tipo="ancora_unica",
            atributos={
                "nome": nome_limpo,
                "peso_volume": peso_volume,
                "condicao_comercial": " ".join(condicoes_encontradas) if condicoes_encontradas else None,
                "textos_detectados": textos_filtrados,
                "regiao_card": region.bbox_delimitada.to_dict() if region.bbox_delimitada else None
            },
            valor=ancora.valor_normalizado,
            unidade=ancora.unidade or "BRL",
            ancoras=[ancora],
            confianca=conf_final,
            evidencias=evidencias
        )


class FlyerProductAdapter:
    """
    Fachada especializada do adaptador de encartes de supermercado/varejo.
    Conecta as fases de normalização, detecção de candidatos, clustering e montagem de entidades.
    """

    def __init__(
        self,
        topo_exclusao_rel: float = 0.12,
        rodape_exclusao_rel: float = 0.88,
        min_preco: float = 0.10,
        max_preco: float = 999999.0,
        fundir_fragmentos_ocr: bool = False
    ):
        self.fundir_fragmentos_ocr = fundir_fragmentos_ocr
        # Zonas de exclusão canônicas para tablóides e folhetos
        self.zonas_exclusao = [
            ExclusionZone(
                nome="banner_topo_cabecalho",
                relative_bbox=BoundingBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=topo_exclusao_rel)
            ),
            ExclusionZone(
                nome="rodape_disclaimer_juridico",
                relative_bbox=BoundingBox(x_min=0.0, y_min=rodape_exclusao_rel, x_max=1.0, y_max=1.0)
            )
        ]
        self.detector = CandidateDetector(rules=[
            StrictCurrencyRule(default_currency="BRL", min_val=min_preco, max_val=max_preco)
        ])
        self.resolver = FlyerProductResolver()

    def processar_documento(self, documento_bruto: RawSpatialDocument) -> ExtractionResult:
        """Executa a esteira completa sobre o documento espacial."""
        # 1. Normalização e filtragem espacial de zonas de exclusão
        doc_normalizado = normalizar_documento_espacial(
            documento_bruto,
            zonas_exclusao=self.zonas_exclusao,
            confianca_minima=0.25,
            fundir_fragmentos=self.fundir_fragmentos_ocr
        )

        # 2. Detecção estrita de âncoras de preço
        ancoras = self.detector.detect_anchors(doc_normalizado)

        # 3. Agrupamento espacial delimitado (sem regiões infinitas)
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
