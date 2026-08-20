# -*- coding: utf-8 -*-
"""
Adapter de Extração de Produtos e Preços de Encartes / Folhetos Digitais — Fase 2
Especializa o motor genérico espacial sem hardcode na camada central.
"""

import functools
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


_RE_RUIDO_ISOLADO = re.compile(
    r'^(?:r\$|cada|un|und|unid|cx|pct|kg|g|mg|ml|l|lt|de|por|em|no|na|do|da|dos|das|para|com|sem|e|ou|um|uma|compre|leve|pague)$',
    re.IGNORECASE
)
_RE_DATA_PERCENT_PADRAO = re.compile(
    r'^(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d+(?:[.,]\d+)?%|\d{2,3}\.\d{3}\.\d{3}[/-]\d{2,4}|(?:\(?\d{2}\)?\s*)?\d{4,5}-?\d{4})$'
)
_RE_NUMERO_PURO = re.compile(r'^\d+(?:[.,]\d+)?$')
_RE_PALAVRA_VALIDA = re.compile(r'[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{2,}')


@functools.lru_cache(maxsize=4096)
def _normalizar_espacos_cached(texto: str) -> str:
    return normalizar_espacos(texto)


@functools.lru_cache(maxsize=4096)
def _is_valid_candidate_text(texto: str) -> bool:
    """Valida se uma string é um candidato textual legítimo para nome/descrição de entidade."""
    s = texto.strip()
    if len(s) < 2:
        return False
    if not any(c.isalnum() for c in s):
        return False
    if _RE_NUMERO_PURO.match(s):
        return False
    if _RE_DATA_PERCENT_PADRAO.match(s):
        return False
    if _RE_RUIDO_ISOLADO.match(s):
        return False
    if not _RE_PALAVRA_VALIDA.search(s):
        return False
    return True


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

        # 1. Coleta e categorização de textos em passo único
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

        # Classifica os tokens de contexto em um único passo
        tokens_pass_filtro = []
        for t in tokens:
            t_raw = t.texto
            t_str = _normalizar_espacos_cached(t_raw) if t_raw else ""
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

            if _is_valid_candidate_text(t_str):
                textos_filtrados.append(t_str)
                evidencias.append(EvidenceItem(
                    tipo="texto_produto",
                    texto_bruto=t_str,
                    confianca=t.confianca,
                    bbox=t.bbox,
                    token_id=t.id_token
                ))

            is_valid_raw = _is_valid_candidate_text(t_raw)
            tokens_pass_filtro.append((t, t_raw.strip(), is_valid_raw))

        # 2. Heurística determinística de nome de produto:
        # Ordena por proximidade vertical em relação à âncora de preço
        if ancora.bbox:
            ancora_cy = ancora.bbox.centro_y
            tokens_com_bbox = [item for item in tokens_pass_filtro if item[0].bbox is not None]
            tokens_proximos = sorted(
                tokens_com_bbox,
                key=lambda item: abs(item[0].bbox.centro_y - ancora_cy)
            )
        else:
            tokens_proximos = tokens_pass_filtro

        linhas_candidatas = [item[1] for item in tokens_proximos if item[2]]
        nome_candidato = " ".join(linhas_candidatas[:2]) if linhas_candidatas else " ".join(textos_filtrados[:2])
        nome_limpo = _normalizar_espacos_cached(nome_candidato) if (linhas_candidatas or textos_filtrados) else ancora.texto_bruto

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


from extractors.adapters.general_spatial_adapter import GeneralSpatialAdapter


class FlyerProductAdapter(GeneralSpatialAdapter):
    """
    Fachada especializada do adaptador de encartes de supermercado/varejo.
    Especializa o GeneralSpatialAdapter com zonas de exclusão de cabeçalho e rodapé de tablóides.
    """

    def __init__(
        self,
        topo_exclusao_rel: float = 0.12,
        rodape_exclusao_rel: float = 0.88,
        min_preco: float = 0.10,
        max_preco: float = 999999.0,
        fundir_fragmentos_ocr: bool = False
    ):
        zonas = [
            ExclusionZone(
                nome="banner_topo_cabecalho",
                relative_bbox=BoundingBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=topo_exclusao_rel)
            ),
            ExclusionZone(
                nome="rodape_disclaimer_juridico",
                relative_bbox=BoundingBox(x_min=0.0, y_min=rodape_exclusao_rel, x_max=1.0, y_max=1.0)
            )
        ]
        super().__init__(
            zonas_exclusao=zonas,
            min_preco=min_preco,
            max_preco=max_preco,
            fundir_fragmentos_ocr=fundir_fragmentos_ocr,
            resolver=FlyerProductResolver()
        )
