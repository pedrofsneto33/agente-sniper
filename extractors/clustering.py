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
    max_dx_padrao_px = max_distancia_horizontal_rel * largura_doc
    max_dy_px = max_distancia_vertical_rel * altura_doc
    max_dx_linha_px = 0.88 * largura_doc
    min_altura_linha_ref = 0.015 * altura_doc

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

    # Pré-computa geometria somente das âncoras válidas
    ancoras_geom = []
    for reg in regioes:
        ancora = reg.ancora
        if ancora and ancora.bbox:
            abox = ancora.bbox
            ancoras_geom.append((
                reg,
                abox.centro_x,
                abox.centro_y,
                abox.y_min,
                abox.y_max,
                abox.altura
            ))

    for token in documento.tokens:
        t_id = token.id_token
        if t_id in ids_ancoras:
            continue

        tbox = token.bbox
        if not token.has_geometry or tbox is None:
            continue

        t_text = token.texto
        t_cx = tbox.centro_x
        t_cy = tbox.centro_y
        t_ymin = tbox.y_min
        t_ymax = tbox.y_max
        t_altura = tbox.altura

        melhor_regiao: Optional[EvidenceRegion] = None
        menor_distancia_sq = float("inf")

        for reg, a_cx, a_cy, a_ymin, a_ymax, a_altura in ancoras_geom:
            # Early-Exit Vertical (Alteração A + Inlining de abs - Alteração B)
            dy = (t_cy - a_cy) if t_cy >= a_cy else (a_cy - t_cy)
            if dy > max_dy_px:
                dx = (t_cx - a_cx) if t_cx >= a_cx else (a_cx - t_cx)
                reg.tokens_rejeitados.append({
                    "token_id": t_id,
                    "texto": t_text,
                    "motivo": f"distancia_excessiva_dx_{dx:.1f}_dy_{dy:.1f}"
                })
                continue

            dx = (t_cx - a_cx) if t_cx >= a_cx else (a_cx - t_cx)

            # Inlining de min/max para sobreposição vertical e altura de linha (Alteração C)
            y_top = t_ymin if t_ymin >= a_ymin else a_ymin
            y_bot = t_ymax if t_ymax <= a_ymax else a_ymax
            y_diff = y_bot - y_top
            y_overlap = y_diff if y_diff > 0.0 else 0.0

            h_max = t_altura if t_altura >= a_altura else a_altura
            altura_linha_ref = h_max if h_max >= min_altura_linha_ref else min_altura_linha_ref
            is_same_line = (y_overlap > 0.0) or (dy <= altura_linha_ref * 0.8)

            # Tolerância horizontal adaptativa à linha (em leitura ocidental, descrições tabulares precedem o preço à esquerda)
            is_preceding_left = (t_cx <= a_cx + 20.0)
            max_dx_permitido = max_dx_linha_px if (is_same_line and is_preceding_left) else max_dx_padrao_px

            # Verificação de limites máximos
            if dx > max_dx_permitido:
                reg.tokens_rejeitados.append({
                    "token_id": t_id,
                    "texto": t_text,
                    "motivo": f"distancia_excessiva_dx_{dx:.1f}_dy_{dy:.1f}"
                })
                continue

            # Verificação de âncora intermediária bloqueante na mesma linha
            if is_same_line and dx > max_dx_padrao_px:
                x_min_seg = t_cx if t_cx <= a_cx else a_cx
                x_max_seg = t_cx if t_cx >= a_cx else a_cx
                tem_ancora_intermediaria = False
                for outra_reg, o_cx, o_cy, o_ymin, o_ymax, o_altura in ancoras_geom:
                    if outra_reg is reg:
                        continue
                    o_top = t_ymin if t_ymin >= o_ymin else o_ymin
                    o_bot = t_ymax if t_ymax <= o_ymax else o_ymax
                    o_diff = o_bot - o_top
                    o_y_overlap = o_diff if o_diff > 0.0 else 0.0
                    o_dy = (t_cy - o_cy) if t_cy >= o_cy else (o_cy - t_cy)
                    o_is_same_line = (o_y_overlap > 0.0) or (o_dy <= altura_linha_ref * 0.8)
                    if o_is_same_line and (x_min_seg + 10.0 < o_cx < x_max_seg - 10.0):
                        tem_ancora_intermediaria = True
                        break
                if tem_ancora_intermediaria:
                    reg.tokens_rejeitados.append({
                        "token_id": t_id,
                        "texto": t_text,
                        "motivo": "ancora_intermediaria_bloqueante"
                    })
                    continue

            # Cálculo da distância ponderada quadrada (inlined sem chamada math.hypot)
            if is_same_line and is_preceding_left:
                w_dx = dx * 0.45
                w_dy = dy * 3.0
            elif is_same_line:
                w_dx = dx * 1.8
                w_dy = dy * 2.0
            else:
                fator_vertical = 1.0 if t_cy <= a_cy else 2.0
                w_dx = dx * 1.6
                w_dy = dy * fator_vertical

            dist_ponderada_sq = w_dx * w_dx + w_dy * w_dy

            if dist_ponderada_sq < menor_distancia_sq:
                menor_distancia_sq = dist_ponderada_sq
                melhor_regiao = reg

        if melhor_regiao is not None:
            melhor_regiao.tokens_incluidos.append(token)
            tokens_atribuidos.add(t_id)

    # Finalização das regiões com âncoras
    regioes_validas: List[EvidenceRegion] = []
    inv_slot_h = 1.0 / (0.15 * altura_doc) if altura_doc > 0 else 1.0
    for r in regioes:
        r.tokens_incluidos.sort(
            key=lambda t: (t.bbox.y_min if t.bbox else 0, t.bbox.x_min if t.bbox else 0)
        )
        r.calcular_bbox_envolvente()

        # Preserva a região se contiver uma âncora válida ou tokens de texto atribuídos
        if r.ancora is not None or len(r.tokens_incluidos) >= 1:
            r.scores["densidade_tokens"] = len(r.tokens_incluidos)
            regioes_validas.append(r)

    # Ordena as regiões por linha e coluna
    regioes_ordenadas = sorted(
        regioes_validas,
        key=lambda r: (
            int(r.ancora.bbox.centro_y * inv_slot_h) if r.ancora and r.ancora.bbox else 0,
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
