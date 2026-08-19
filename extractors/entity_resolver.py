# -*- coding: utf-8 -*-
"""
Resolvedor Genérico de Entidades e Preservação de Evidências Forenses — Fase 2
Suporta entidades originadas por:
- Âncora única + contexto
- Múltiplas âncoras
- Apenas contexto sem âncora
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence, Tuple
from extractors.models import (
    EvidenceRegion,
    ExtractedEntity,
    EvidenceItem,
    ExtractionResult,
)


def _normalizar_espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip()


class EntityResolver(ABC):
    """Contrato abstrato para resolvedores de entidade a partir de regiões de evidência."""

    @abstractmethod
    def resolve_region(self, region: EvidenceRegion) -> Optional[ExtractedEntity]:
        pass

    # Retrocompatibilidade com nome antigo
    def resolve_cluster(self, cluster: EvidenceRegion) -> Optional[ExtractedEntity]:
        return self.resolve_region(cluster)

    def consolidar_concorrencia_entidades(
        self,
        entidades: Sequence[ExtractedEntity],
        dimensoes_pagina: Optional[Tuple[float, float]] = None
    ) -> List[ExtractedEntity]:
        """
        Consolida concorrência entre entidades da mesma oferta/coluna com base na hierarquia de evidência e relações promocionais.
        1. Preços bare-number únicos/isolados são 100% PRESERVADOS.
        2. Relações promocionais explícitas (De/Por) no mesmo card são unificadas em uma única entidade (price = current_price, old_price = old_price, promotion = True).
        3. Quando há concorrência espacial no mesmo card entre uma âncora forte (EXPLICIT_CURRENCY / CADENCE_PRICE)
           e uma âncora fraca (BARE_DECIMAL), a âncora forte domina a oferta e a âncora fraca é subordinada/absorvida.
        """
        if len(entidades) <= 1:
            return list(entidades)

        from extractors.models import BoundingBox, AnchorRole

        w_doc, h_doc = dimensoes_pagina if dimensoes_pagina else (2000.0, 3000.0)
        if w_doc <= 1.0:
            w_doc = 2000.0
        if h_doc <= 1.0:
            h_doc = 3000.0

        dist_max_px = 0.10 * w_doc
        dy_ancoras_max_px = 0.08 * h_doc

        subordinadas_indices = set()

        # PASSO 1: Consolidação Promocional De/Por (com marcadores semânticos explícitos)
        for i, ent_a in enumerate(entidades):
            if i in subordinadas_indices:
                continue
            ancora_a = ent_a.ancoras[0] if ent_a.ancoras else None
            if not ancora_a or not ancora_a.bbox:
                continue
            role_a = getattr(ancora_a, "role", AnchorRole.STANDALONE)
            box_a = ancora_a.bbox

            for j, ent_b in enumerate(entidades):
                if i == j or j in subordinadas_indices:
                    continue
                ancora_b = ent_b.ancoras[0] if ent_b.ancoras else None
                if not ancora_b or not ancora_b.bbox:
                    continue
                role_b = getattr(ancora_b, "role", AnchorRole.STANDALONE)
                box_b = ancora_b.bbox

                # Alinhamento e proximidade espacial de mesmo card
                x_overlap = max(0.0, min(box_a.x_max, box_b.x_max) - max(box_a.x_min, box_b.x_min))
                min_w = min(box_a.largura, box_b.largura)
                overlap_x_ratio = (x_overlap / min_w) if min_w > 0 else 0.0
                dy_ancoras = max(0.0, max(box_a.y_min, box_b.y_min) - min(box_a.y_max, box_b.y_max))
                is_same_card = (overlap_x_ratio >= 0.40 or box_a.distance_to(box_b) <= dist_max_px) and dy_ancoras <= dy_ancoras_max_px

                if not is_same_card:
                    continue

                # Caso 1.1: ent_a é OLD_PRICE e ent_b é CURRENT_PRICE (ou STANDALONE)
                if role_a == AnchorRole.OLD_PRICE and role_b in (AnchorRole.CURRENT_PRICE, AnchorRole.STANDALONE):
                    subordinadas_indices.add(i)
                    ent_b.old_price = float(ent_a.valor) if ent_a.valor is not None else None
                    ent_b.atributos["old_price"] = ent_b.old_price
                    ent_b.atributos["promocao"] = True
                    ent_b.atributos["tipo_oferta"] = "desconto_de_por"
                    ent_b.origem_tipo = "multiplas_ancoras"

                    nome_a = ent_a.atributos.get("nome", "")
                    nome_b = ent_b.atributos.get("nome", "")
                    if nome_a and not nome_b:
                        ent_b.atributos["nome"] = nome_a
                    elif nome_a and nome_b and nome_a not in nome_b:
                        ent_b.atributos["nome"] = f"{nome_a} {nome_b}".strip()

                    ent_b.evidencias.extend(ent_a.evidencias)
                    break

                # Caso 1.2: ent_b é OLD_PRICE e ent_a é CURRENT_PRICE (ou STANDALONE)
                elif role_b == AnchorRole.OLD_PRICE and role_a in (AnchorRole.CURRENT_PRICE, AnchorRole.STANDALONE):
                    subordinadas_indices.add(j)
                    ent_a.old_price = float(ent_b.valor) if ent_b.valor is not None else None
                    ent_a.atributos["old_price"] = ent_a.old_price
                    ent_a.atributos["promocao"] = True
                    ent_a.atributos["tipo_oferta"] = "desconto_de_por"
                    ent_a.origem_tipo = "multiplas_ancoras"

                    nome_a = ent_a.atributos.get("nome", "")
                    nome_b = ent_b.atributos.get("nome", "")
                    if nome_b and not nome_a:
                        ent_a.atributos["nome"] = nome_b
                    elif nome_a and nome_b and nome_b not in nome_a:
                        ent_a.atributos["nome"] = f"{nome_b} {nome_a}".strip()

                    ent_a.evidencias.extend(ent_b.evidencias)

        # PASSO 2: Subordinação Forte vs Bare (Fase 15)
        for i, ent_a in enumerate(entidades):
            if i in subordinadas_indices:
                continue

            ancora_a = ent_a.ancoras[0] if ent_a.ancoras else None
            if not ancora_a or not ancora_a.bbox:
                continue
            is_strong_a = getattr(ancora_a, "is_strong_monetary_evidence", False)
            box_a = ancora_a.bbox

            for j, ent_b in enumerate(entidades):
                if i == j or j in subordinadas_indices:
                    continue

                ancora_b = ent_b.ancoras[0] if ent_b.ancoras else None
                if not ancora_b or not ancora_b.bbox:
                    continue
                is_strong_b = getattr(ancora_b, "is_strong_monetary_evidence", False)
                box_b = ancora_b.bbox

                # Subordinação: ent_b tem moeda forte e ent_a é bare decimal no mesmo card/coluna
                if is_strong_b and not is_strong_a:
                    # 1. Alinhamento horizontal na mesma coluna
                    x_overlap = max(0.0, min(box_a.x_max, box_b.x_max) - max(box_a.x_min, box_b.x_min))
                    min_w = min(box_a.largura, box_b.largura)
                    overlap_x_ratio = (x_overlap / min_w) if min_w > 0 else 0.0

                    # 2. Distância vertical entre as ÂNCORAS
                    dy_ancoras = max(0.0, max(box_a.y_min, box_b.y_min) - min(box_a.y_max, box_b.y_max))

                    # 3. Deve estar dentro do mesmo card (dy <= dy_ancoras_max_px)
                    if (overlap_x_ratio >= 0.50 or box_a.distance_to(box_b) <= dist_max_px) and dy_ancoras <= dy_ancoras_max_px:
                        escala_subordinada = (box_a.altura / max(1.0, box_b.altura)) <= 0.50
                        textos_b_str = " ".join(ent_b.atributos.get("textos_detectados", [])).upper()

                        val_str_1 = f"{ancora_a.valor_normalizado:.2f}".replace('.', ',')
                        val_str_2 = f"{int(ancora_a.valor_normalizado * 10) / 10:.1f}".replace('.', ',')
                        tem_especificacao_correspondente = (val_str_2 in textos_b_str or val_str_1 in textos_b_str)

                        if escala_subordinada or tem_especificacao_correspondente:
                            subordinadas_indices.add(i)

                            nome_a = ent_a.atributos.get("nome", "")
                            nome_b = ent_b.atributos.get("nome", "")
                            if nome_a:
                                nome_a_limpo = re.sub(r'^\d+[\s\d]*\s+', '', nome_a).strip()
                                if nome_b and nome_a_limpo and nome_a_limpo not in nome_b:
                                    novo_nome = f"{nome_a_limpo} {nome_b}".strip()
                                else:
                                    novo_nome = nome_a_limpo or nome_b
                                ent_b.atributos["nome"] = novo_nome

                            ent_b.evidencias.extend(ent_a.evidencias)
                            break

        return [ent for idx, ent in enumerate(entidades) if idx not in subordinadas_indices]

    def resolve_all(
        self,
        regions: Sequence[EvidenceRegion],
        documento_id: str = "",
        dimensoes_pagina: Optional[Tuple[float, float]] = None
    ) -> ExtractionResult:
        entidades: List[ExtractedEntity] = []
        for r in regions:
            ent = self.resolve_region(r)
            if ent is not None:
                entidades.append(ent)

        entidades_consolidadas = self.consolidar_concorrencia_entidades(
            entidades,
            dimensoes_pagina=dimensoes_pagina
        )

        return ExtractionResult(
            documento_id=documento_id,
            tipo_extracao=getattr(self, "tipo_entidade", "entidade_generica"),
            total_entidades=len(entidades_consolidadas),
            entidades=entidades_consolidadas,
            regioes_evidencia=list(regions),
            metricas={
                "regioes_analisadas": len(regions),
                "entidades_produzidas": len(entidades_consolidadas),
            }
        )


class GenericEntityResolver(EntityResolver):
    """Resolvedor genérico padrão com rastreabilidade total e suporte a múltiplos modos de origem."""

    def __init__(self, tipo_entidade: str = "entidade_generica"):
        self.tipo_entidade = tipo_entidade

    def resolve_region(self, region: EvidenceRegion) -> Optional[ExtractedEntity]:
        evidencias: List[EvidenceItem] = []

        # 1. Determinação da modalidade de origem
        num_ancoras = len(region.ancoras)
        if num_ancoras == 1:
            origem_tipo = "ancora_unica"
        elif num_ancoras > 1:
            origem_tipo = "multiplas_ancoras"
        else:
            origem_tipo = "apenas_contexto"

        # 2. Evidências das âncoras
        soma_conf = 0.0
        for a in region.ancoras:
            evidencias.append(EvidenceItem(
                tipo="ancora_primaria",
                texto_bruto=a.texto_bruto,
                confianca=a.confianca,
                bbox=a.bbox,
                token_id=a.token_ref.id_token
            ))
            soma_conf += a.confianca

        # 3. Evidências dos tokens de contexto
        textos_brutos: List[str] = []
        for t in region.tokens_incluidos:
            t_limpo = _normalizar_espacos(t.texto)
            if t_limpo:
                textos_brutos.append(t_limpo)
                evidencias.append(EvidenceItem(
                    tipo="contexto_espacial" if t.has_geometry else "contexto_sequencial",
                    texto_bruto=t_limpo,
                    confianca=t.confianca,
                    bbox=t.bbox,
                    token_id=t.id_token
                ))
                soma_conf += t.confianca

        total_elementos = len(region.ancoras) + len(region.tokens_incluidos)
        if total_elementos == 0:
            return None

        # Confiança agregada balanceada
        media_conf = soma_conf / max(1, total_elementos)

        # Montagem dos valores principais
        valor_principal = region.ancoras[0].valor_normalizado if region.ancoras else None
        unidade_principal = region.ancoras[0].unidade if region.ancoras else None
        lista_valores = [
            {"tipo": a.tipo, "valor": a.valor_normalizado, "unidade": a.unidade, "texto": a.texto_bruto}
            for a in region.ancoras
        ] if len(region.ancoras) > 1 else []

        return ExtractedEntity(
            entidade=self.tipo_entidade,
            origem_tipo=origem_tipo,
            atributos={
                "textos_contexto": textos_brutos,
                "texto_completo": " ".join(textos_brutos),
                "total_tokens": len(region.tokens_incluidos),
                "bbox_regiao": region.bbox_delimitada.to_dict() if region.bbox_delimitada else None,
                "motivos_decisao": region.motivos_decisao
            },
            valor=valor_principal,
            unidade=unidade_principal,
            valores=lista_valores,
            ancoras=list(region.ancoras),
            confianca=round(min(1.0, media_conf), 4),
            evidencias=evidencias
        )
