# -*- coding: utf-8 -*-
"""
Motor Genérico de Fusão de Tokens OCR Fragmentados
Reconstrói palavras e termos quebrados (ex: C A F E, A L U M I N I O) por alinhamento e proximidade geométrica.
"""

from typing import List, Optional, Sequence
from extractors.models import BoundingBox, SpatialToken, RawSpatialDocument


def fundir_tokens_fragmentados(
    tokens: Sequence[SpatialToken],
    fator_gap_max_sem_espaco: float = 0.45,
    fator_gap_max_com_espaco: float = 1.20,
    tolerancia_alinhamento_y: float = 0.40
) -> List[SpatialToken]:
    """
    Reconstrói e funde tokens espaciais fragmentados com base em alinhamento horizontal e gap.
    1. Trata caracteres soltos (C A F E -> CAFE).
    2. Trata sílabas/morfemas quebrados (ALUM + INIO -> ALUMINIO).
    3. Preserva termos naturalmente separados por espaços normais.
    """
    if not tokens:
        return []

    # Separa tokens com e sem geometria
    tokens_com_geo = [t for t in tokens if t.has_geometry]
    tokens_sem_geo = [t for t in tokens if not t.has_geometry]

    if not tokens_com_geo:
        # Sem geometria: tenta fusão simples de caracteres individuais consecutivos
        resultado_sem_geo: List[SpatialToken] = []
        buffer_chars: List[SpatialToken] = []

        for t in tokens_sem_geo:
            if len(t.texto.strip()) == 1 and t.texto.strip().isalnum():
                buffer_chars.append(t)
            else:
                if buffer_chars:
                    if len(buffer_chars) > 1:
                        texto_fundido = "".join(c.texto.strip() for c in buffer_chars)
                        conf_media = sum(c.confianca for c in buffer_chars) / len(buffer_chars)
                        resultado_sem_geo.append(SpatialToken(
                            texto=texto_fundido,
                            bbox=None,
                            confianca=conf_media,
                            id_token=buffer_chars[0].id_token,
                            metadados={"tokens_fundidos": [c.id_token for c in buffer_chars]}
                        ))
                    else:
                        resultado_sem_geo.append(buffer_chars[0])
                    buffer_chars = []
                resultado_sem_geo.append(t)

        if buffer_chars:
            if len(buffer_chars) > 1:
                texto_fundido = "".join(c.texto.strip() for c in buffer_chars)
                conf_media = sum(c.confianca for c in buffer_chars) / len(buffer_chars)
                resultado_sem_geo.append(SpatialToken(
                    texto=texto_fundido,
                    bbox=None,
                    confianca=conf_media,
                    id_token=buffer_chars[0].id_token,
                    metadados={"tokens_fundidos": [c.id_token for c in buffer_chars]}
                ))
            else:
                resultado_sem_geo.append(buffer_chars[0])

        return resultado_sem_geo

    # 1. Agrupamento em linhas por proximidade vertical
    # Ordena primariamente por Y e secundariamente por X
    tokens_ordenados = sorted(
        tokens_com_geo,
        key=lambda t: (t.bbox.y_min if t.bbox else 0, t.bbox.x_min if t.bbox else 0)
    )

    linhas: List[List[SpatialToken]] = []
    for t in tokens_ordenados:
        if not t.bbox:
            continue
        adicionado = False
        for linha in linhas:
            # Compara com o primeiro token da linha
            ref_bbox = linha[0].bbox
            if not ref_bbox:
                continue
            alt_media = (ref_bbox.altura + t.bbox.altura) / 2.0
            dy = abs(ref_bbox.centro_y - t.bbox.centro_y)
            if dy <= max(10.0, alt_media * tolerancia_alinhamento_y):
                linha.append(t)
                adicionado = True
                break
        if not adicionado:
            linhas.append([t])

    tokens_fundidos_total: List[SpatialToken] = []

    # 2. Processamento horizontal dentro de cada linha
    for linha in linhas:
        # Ordena a linha estritamente por X
        linha_ordenada = sorted(linha, key=lambda t: t.bbox.x_min if t.bbox else 0)
        
        buffer_atual: Optional[SpatialToken] = None
        
        for prox in linha_ordenada:
            if buffer_atual is None:
                buffer_atual = prox
                continue

            b_box = buffer_atual.bbox
            p_box = prox.bbox

            if b_box is None or p_box is None:
                tokens_fundidos_total.append(buffer_atual)
                buffer_atual = prox
                continue

            alt_ref = max(1.0, (b_box.altura + p_box.altura) / 2.0)
            gap_horizontal = p_box.x_min - b_box.x_max

            # Decisão de fusão:
            # Caso 1: Tokens com sobreposição ou gap muito curto (caracteres soltos ou sílabas quebradas)
            eh_char_isolado = (len(buffer_atual.texto.strip()) == 1 or len(prox.texto.strip()) == 1)
            limite_sem_espaco = alt_ref * (fator_gap_max_sem_espaco * (1.8 if eh_char_isolado else 1.0))

            if gap_horizontal <= limite_sem_espaco and gap_horizontal >= -alt_ref * 0.5:
                # Fusão direta SEM espaço (ex: "C" + "A" -> "CA" ou "ALUM" + "INIO" -> "ALUMINIO")
                novo_texto = buffer_atual.texto + prox.texto
                novo_bbox = b_box.expand(p_box)
                len_b = max(1, len(buffer_atual.texto))
                len_p = max(1, len(prox.texto))
                nova_conf = (buffer_atual.confianca * len_b + prox.confianca * len_p) / (len_b + len_p)
                ids_anteriores = buffer_atual.metadados.get("tokens_fundidos", [buffer_atual.id_token])
                
                buffer_atual = SpatialToken(
                    texto=novo_texto,
                    bbox=novo_bbox,
                    confianca=round(nova_conf, 4),
                    id_token=buffer_atual.id_token,
                    metadados={
                        **buffer_atual.metadados,
                        "tokens_fundidos": ids_anteriores + [prox.id_token],
                        "foi_fundido": True
                    }
                )
            else:
                tokens_fundidos_total.append(buffer_atual)
                buffer_atual = prox

        if buffer_atual is not None:
            tokens_fundidos_total.append(buffer_atual)

    # Reanexa tokens sem geometria se existirem
    return tokens_fundidos_total + tokens_sem_geo
