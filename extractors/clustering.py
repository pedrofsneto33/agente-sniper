# -*- coding: utf-8 -*-
"""
Agrupamento Espacial e Formação de Regiões de Evidência Auditáveis — Fase 5
Produz EvidenceRegion com registro forense de tokens incluídos e rejeitados.
"""

from typing import List, Optional, Sequence, Dict, Any
import math
from extractors.models import (
    BoundingBox,
    SpatialToken,
    CandidateAnchor,
    EvidenceRegion,
    RawSpatialDocument,
)


def clusterizar_espacialmente(
    documento: RawSpatialDocument,
    ancoras: Sequence[CandidateAnchor],
    max_distancia_horizontal_rel: float = 0.22,
    max_distancia_vertical_rel: float = 0.40,
    margem_seguranca_px: float = 40.0,
    permitir_regioes_sem_ancora: bool = False,
    max_tokens_por_regiao_sem_ancora: int = 15
) -> List[EvidenceRegion]:
    """
    Agrupa tokens em torno de âncoras (ou por blocos de texto) de forma auditável e delimitada.
    Retorna uma lista de EvidenceRegion ricas com motivos de decisão e rejeição.
    """
    largura_doc, altura_doc = documento.dimensoes
    if largura_doc <= 0 or altura_doc <= 0:
        largura_doc, altura_doc = 1.0, 1.0

    tem_geometria_doc = any(t.has_geometry for t in documento.tokens)

    # -------------------------------------------------------------
    # CASO A: Documento Puramente Sequencial / Sem Bounding Boxes
    # -------------------------------------------------------------
    if not tem_geometria_doc:
        if not ancoras:
            if permitir_regioes_sem_ancora and documento.tokens:
                reg = EvidenceRegion(
                    identificador="regiao_texto_1",
                    ancoras=[],
                    tokens_incluidos=list(documento.tokens),
                    motivos_decisao=["documento_sequencial_sem_ancoras"]
                )
                return [reg]
            return []

        # Agrupa sequencialmente em janela ao redor de cada âncora
        regioes: List[EvidenceRegion] = []
        ids_ancoras = {a.token_ref.id_token for a in ancoras if a.token_ref.id_token is not None}
        tokens_livres = [t for t in documento.tokens if t.id_token not in ids_ancoras]

        janela = max(1, len(tokens_livres) // max(1, len(ancoras)))
        for i, a in enumerate(ancoras):
            inicio = i * janela
            fim = (i + 1) * janela if i < len(ancoras) - 1 else len(tokens_livres)
            tokens_reg = tokens_livres[inicio:fim]
            reg = EvidenceRegion(
                identificador=f"regiao_seq_{i+1}",
                ancoras=[a],
                tokens_incluidos=tokens_reg,
                motivos_decisao=["agrupamento_sequencial_por_janela"]
            )
            regioes.append(reg)
        return regioes

    # -------------------------------------------------------------
    # CASO B: Documento Espacial 2D com Geometria
    # -------------------------------------------------------------
    max_dx_px = max_distancia_horizontal_rel * largura_doc
    max_dy_px = max_distancia_vertical_rel * altura_doc

    regioes: List[EvidenceRegion] = [
        EvidenceRegion(
            identificador=f"regiao_ancora_{i+1}",
            ancoras=[a],
            tokens_incluidos=[],
            tokens_rejeitados=[],
            motivos_decisao=["ancora_primaria_detectada"]
        )
        for i, a in enumerate(ancoras)
    ]

    ids_ancoras = {a.token_ref.id_token for a in ancoras if a.token_ref.id_token is not None}
    tokens_atribuidos = set()

    for token in documento.tokens:
        if token.id_token in ids_ancoras:
            continue

        if not token.has_geometry or token.bbox is None:
            continue

        melhor_regiao: Optional[EvidenceRegion] = None
        menor_distancia = float("inf")

        for reg in regioes:
            ancora = reg.ancora
            if not ancora or not ancora.bbox:
                continue

            ancora_box = ancora.bbox
            dx = abs(token.bbox.centro_x - ancora_box.centro_x)
            dy = abs(token.bbox.centro_y - ancora_box.centro_y)

            # Verificação de limites máximos
            if dx > max_dx_px or dy > max_dy_px:
                reg.tokens_rejeitados.append({
                    "token_id": token.id_token,
                    "texto": token.texto,
                    "motivo": f"distancia_excessiva_dx_{dx:.1f}_dy_{dy:.1f}"
                })
                continue

            # Favorece fortemente tokens na mesma coluna (dx ponderado) e acima/no nível da âncora
            fator_vertical = 1.0 if token.bbox.centro_y <= ancora_box.centro_y else 2.0
            dist_ponderada = math.hypot(dx * 1.6, dy * fator_vertical)

            if dist_ponderada < menor_distancia:
                menor_distancia = dist_ponderada
                melhor_regiao = reg

        if melhor_regiao is not None:
            melhor_regiao.tokens_incluidos.append(token)
            tokens_atribuidos.add(token.id_token)

    # Finalização das regiões com âncoras
    regioes_validas: List[EvidenceRegion] = []
    for r in regioes:
        r.tokens_incluidos = sorted(
            r.tokens_incluidos,
            key=lambda t: (t.bbox.y_min if t.bbox else 0, t.bbox.x_min if t.bbox else 0)
        )
        r.calcular_bbox_envolvente()

        if len(r.tokens_incluidos) >= 1:
            r.scores["densidade_tokens"] = len(r.tokens_incluidos)
            regioes_validas.append(r)

    # Ordena as regiões por linha e coluna
    regioes_ordenadas = sorted(
        regioes_validas,
        key=lambda r: (
            int(r.ancora.bbox.centro_y / (0.15 * altura_doc)) if r.ancora and r.ancora.bbox else 0,
            r.ancora.bbox.centro_x if r.ancora and r.ancora.bbox else 0
        )
    )

    # -------------------------------------------------------------
    # CASO C: Regiões sem Âncora (Blocos textuais puros se habilitado)
    # -------------------------------------------------------------
    if permitir_regioes_sem_ancora:
        tokens_restantes = [t for t in documento.tokens if t.id_token not in tokens_atribuidos and t.id_token not in ids_ancoras and t.has_geometry]
        if tokens_restantes:
            reg_sem_ancora = EvidenceRegion(
                identificador="regiao_sem_ancora_1",
                ancoras=[],
                tokens_incluidos=tokens_restantes[:max_tokens_por_regiao_sem_ancora],
                motivos_decisao=["bloco_textual_sem_ancora"]
            )
            reg_sem_ancora.calcular_bbox_envolvente()
            regioes_ordenadas.append(reg_sem_ancora)

    return regioes_ordenadas
