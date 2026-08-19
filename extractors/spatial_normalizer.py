# -*- coding: utf-8 -*-
"""
Normalizador Espacial e Filtro de Zonas de Exclusão — Fase 2
Suporta tokens com e sem geometria espacial (HTML, texto puro, PDFs).
"""

import re
from typing import List, Optional, Sequence
from extractors.models import BoundingBox, SpatialToken, ExclusionZone, RawSpatialDocument
from extractors.fusion import fundir_tokens_fragmentados


def normalizar_espacos(texto: str) -> str:
    """Colapsa múltiplos espaços em branco e remove espaços nas bordas."""
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def normalizar_documento_espacial(
    documento: RawSpatialDocument,
    zonas_exclusao: Optional[Sequence[ExclusionZone]] = None,
    confianca_minima: float = 0.20,
    quantizacao_linha_y: float = 0.02,
    fundir_fragmentos: bool = False
) -> RawSpatialDocument:
    """
    Normaliza os tokens espaciais do documento:
    1. Limpa espaços e valida strings.
    2. Aplica filtro de confiança mínima.
    3. Descarta tokens localizados dentro de zonas de exclusão (se tiverem geometria).
    4. Ordena tokens na ordem natural de leitura.
    5. Opcionalmente funde tokens fragmentados de OCR.
    """
    largura_doc, altura_doc = documento.dimensoes
    if largura_doc <= 0 or altura_doc <= 0:
        largura_doc, altura_doc = 1.0, 1.0

    tokens_validos: List[SpatialToken] = []
    zonas = list(zonas_exclusao or [])

    for idx, token in enumerate(documento.tokens):
        texto_limpo = normalizar_espacos(token.texto or "")
        if not texto_limpo:
            continue

        if token.confianca < confianca_minima:
            continue

        # Se tiver geometria, avalia zonas de exclusão
        if token.has_geometry and token.bbox is not None:
            cx_rel = token.bbox.centro_x / largura_doc
            cy_rel = token.bbox.centro_y / altura_doc

            ignorar = False
            for zona in zonas:
                if zona.relative_bbox.contains_point(cx_rel, cy_rel):
                    ignorar = True
                    break

            if ignorar:
                continue

            token_normalizado = SpatialToken(
                texto=texto_limpo,
                bbox=token.bbox,
                confianca=token.confianca,
                id_token=token.id_token if token.id_token is not None else (idx + 1),
                metadados={
                    **token.metadados,
                    "cx_rel": cx_rel,
                    "cy_rel": cy_rel,
                    "tem_geometria": True
                }
            )
        else:
            # Token textual puro sem geometria (nunca descartado por zona de exclusão 2D)
            token_normalizado = SpatialToken(
                texto=texto_limpo,
                bbox=None,
                confianca=token.confianca,
                id_token=token.id_token if token.id_token is not None else (idx + 1),
                metadados={
                    **token.metadados,
                    "tem_geometria": False
                }
            )

        tokens_validos.append(token_normalizado)

    # Ordenação natural por linha (quantização vertical) para tokens com geometria,
    # preservando a ordem original para tokens puramente textuais
    def chave_ordenacao(item: tuple[int, SpatialToken]):
        idx_orig, t = item
        if t.has_geometry and t.bbox is not None:
            cy = t.metadados.get("cy_rel", t.bbox.centro_y / altura_doc)
            cx = t.metadados.get("cx_rel", t.bbox.centro_x / largura_doc)
            linha_index = int(cy / max(0.001, quantizacao_linha_y))
            return (0, linha_index, cx)
        else:
            return (1, idx_orig, 0.0)

    tokens_ordenados = [t for _, t in sorted(enumerate(tokens_validos), key=chave_ordenacao)]

    # Opcional: fusão de caracteres e sílabas fragmentadas
    if fundir_fragmentos and tokens_ordenados:
        tokens_ordenados = fundir_tokens_fragmentados(tokens_ordenados)

    return RawSpatialDocument(
        identificador=documento.identificador,
        origem=documento.origem,
        dimensoes=documento.dimensoes,
        tokens=tokens_ordenados,
        metadados={
            **documento.metadados,
            "total_tokens_originais": len(documento.tokens),
            "total_tokens_filtrados": len(tokens_ordenados),
            "zonas_exclusao_aplicadas": len(zonas)
        }
    )
