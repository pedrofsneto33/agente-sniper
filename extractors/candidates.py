# -*- coding: utf-8 -*-
"""
Motor de Detecção e Discriminação de Âncoras Candidatas — Fase 3
Suporta regras plugáveis para múltiplos domínios: Moeda, Processo Judicial, Percentuais, Salários, CNPJ e Datas.
"""

from abc import ABC, abstractmethod
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from extractors.models import BoundingBox, SpatialToken, CandidateAnchor, RawSpatialDocument, AnchorEvidenceKind, AnchorRole


class CandidateRule(ABC):
    """Contrato abstrato para regras de detecção de âncoras."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def detect(self, tokens: Sequence[SpatialToken], document: RawSpatialDocument) -> List[CandidateAnchor]:
        pass


class StrictCurrencyRule(CandidateRule):
    """
    Regra estrita para detecção de valores monetários e cadências de preços multi-nicho.
    Discrimina rigorosamente contra gramaturas, volumes, dimensões, percentuais, datas, CNPJs e processos judiciais.
    Classifica âncoras em EXPLICIT_CURRENCY, CADENCE_PRICE e BARE_DECIMAL, além de identificar papéis relacionais (OLD_PRICE, CURRENT_PRICE).
    """
    
    def __init__(self, default_currency: str = "BRL", min_val: float = 0.05, max_val: float = 999999.0):
        self.default_currency = default_currency
        self.min_val = min_val
        self.max_val = max_val

        self._re_simbolo_moeda = re.compile(r'(?:R\$|\$|€|£|US\$)', re.IGNORECASE)
        self._re_cadencia = re.compile(
            r'(?:/\s*(?:m[eê]s|ano|dia|di[aá]ria|sess[aã]o|hora|un|unidade|kg|g|l|litro|pe[cç]a|item|m[23]|km|pax|noite)|'
            r'(?:\s+(?:por|ao|a cada|cada)\s+(?:m[eê]s|ano|dia|di[aá]ria|sess[aã]o|hora|un|unidade|kg|g|l|litro|pe[cç]a|item|m[23]|km|pax|noite))|'
            r'\s+CADA|\s+POR\s+M[EÊ]S|\s+MENSAL|\s+ANUAL|\s+DI[AÁ]RIO|\s+POR\s+DIA)',
            re.IGNORECASE
        )
        self._re_old_price_token = re.compile(r'^(?:de|de:|antes|era|antigo|normal)$', re.IGNORECASE)
        self._re_old_price_inline = re.compile(r'(?:^\s*de\s*:\s*|^\s*de\s+(?:R\$|\$|€|£|US\$|\d)|\bantes\b|\bera\b|\bde:\b)', re.IGNORECASE)
        self._re_current_price_token = re.compile(r'^(?:por|por:|agora|oferta|promocional|pague|promo[cç][aã]o|por:)$', re.IGNORECASE)
        self._re_current_price_inline = re.compile(r'(?:^\s*por\s*:\s*|^\s*por\s+(?:R\$|\$|€|£|US\$|\d)|\bagora\b|\bpague\b|\bpor:\b)', re.IGNORECASE)
        self._re_unidades_medida = re.compile(
            r'(\b|\d)(g|kg|mg|ml|l|litro|litros|sach[eê]s?|c[aá]psulas?|unidades?|un|cm|mm|m|w|v|hz|pct|pack|anos?|meses|dias|h|min|s)\b',
            re.IGNORECASE
        )
        self._re_dimensao_composta = re.compile(
            r'(\d+x\d+([.,]\d+)?|\d+w\d+|\d+v\d+|\d+k\d+)',
            re.IGNORECASE
        )
        self._re_nao_moeda = re.compile(r'(%|\d+-\d+|\.\d{4,}|\b\d{1,2}/\d{1,2}/\d{2,4}\b)')
        self._re_preco_padrao = re.compile(
            r'(?:R\$\s*|\$\s*|€\s*|£\s*|US\$\s*)?(\b(?:\d{1,3}(?:\.\d{3})+,\d{2}|\d{1,5}[.,]\d{2})\b)(?:[^\w\s]*\s*(?:m[eê]s|ano|dia|di[aá]ria|sess[aã]o|hora|un|unidade|kg|g|l|litro|pe[cç]a|item|m[23]|km|pax|noite)|\s+CADA|\s+KG|\s+UN)?',
            re.IGNORECASE
        )

    @property
    def name(self) -> str:
        return "StrictCurrencyRule"

    def detect(self, tokens: Sequence[SpatialToken], document: RawSpatialDocument) -> List[CandidateAnchor]:
        ancoras: List[CandidateAnchor] = []
        n_tokens = len(tokens)
        if n_tokens == 0:
            return ancoras

        w_doc, h_doc = document.dimensoes if document and document.dimensoes else (2000.0, 3000.0)
        if w_doc <= 1.0:
            w_doc = 2000.0
        if h_doc <= 1.0:
            h_doc = 3000.0

        dist_max_px = 0.060 * w_doc
        dy_max_px = 0.015 * h_doc

        # Pass 1: Pré-computa atributos com pré-filtros rápidos O(1)
        token_info = []
        for idx, token in enumerate(tokens):
            texto = token.texto.strip()
            bbox = token.bbox
            has_geom = token.has_geometry and bbox is not None
            if has_geom:
                cx, cy, ymin, ymax = bbox.centro_x, bbox.centro_y, bbox.y_min, bbox.y_max
            else:
                cx, cy, ymin, ymax = 0.0, 0.0, 0.0, 0.0

            # Fast check para símbolo de moeda
            if '$' in texto or '€' in texto or '£' in texto:
                m_sym = bool(self._re_simbolo_moeda.search(texto))
            else:
                m_sym = False

            # Cadência
            m_cad = self._re_cadencia.search(texto)
            cad_str = m_cad.group(0).strip() if m_cad else None

            # Fast check para marcadores de preço antigo e atual
            t_lower = texto.lower()
            if 'de' in t_lower or 'antes' in t_lower or 'era' in t_lower or 'antigo' in t_lower or 'normal' in t_lower:
                m_old = bool(self._re_old_price_token.match(texto) or self._re_old_price_inline.search(texto))
            else:
                m_old = False

            if 'por' in t_lower or 'agora' in t_lower or 'oferta' in t_lower or 'promocional' in t_lower or 'pague' in t_lower or 'promo' in t_lower:
                m_curr = bool(self._re_current_price_token.match(texto) or self._re_current_price_inline.search(texto))
            else:
                m_curr = False

            has_digit = any(c.isdigit() for c in texto)

            token_info.append((
                token, texto, bbox, has_geom, cx, cy, ymin, ymax,
                m_sym, bool(m_cad), cad_str, m_old, m_curr, has_digit
            ))

        # Pass 2: Detecção de âncoras com busca de vizinhança sem reavaliação de regex
        for idx in range(n_tokens):
            (token, texto, bbox, has_geom, cx, cy, ymin, ymax,
             tem_simbolo_moeda, tem_cadencia, cadencia_str,
             tem_marcador_old, tem_marcador_curr, has_digit) = token_info[idx]

            # Descarte imediato O(1): se o token não possui dígitos, não pode ser âncora de preço
            if not has_digit:
                continue

            # 2. Contexto vizinho imediato e espacial 2D (mesma linha na janela local)
            inicio_janela = max(0, idx - 15)
            fim_janela = min(n_tokens, idx + 16)

            if has_geom:
                for v_idx in range(inicio_janela, fim_janela):
                    if v_idx == idx:
                        continue
                    v_info = token_info[v_idx]
                    if v_info[3]:  # v has_geom
                        v_dy = cy - v_info[5]
                        if v_dy < 0.0:
                            v_dy = -v_dy
                        if v_dy <= dy_max_px:
                            d = math.hypot(cx - v_info[4], cy - v_info[5])
                            if d <= dist_max_px:
                                if not tem_simbolo_moeda and v_info[8]:  # v m_sym
                                    tem_simbolo_moeda = True
                                if not tem_cadencia and v_info[9]:      # v has_cad
                                    tem_cadencia = True
                                    cadencia_str = v_info[10]
            else:
                if idx > 0:
                    v_info = token_info[idx - 1]
                    if not tem_simbolo_moeda and v_info[8]:
                        tem_simbolo_moeda = True
                    if not tem_cadencia and v_info[9]:
                        tem_cadencia = True
                        cadencia_str = v_info[10]
                if idx + 1 < n_tokens:
                    v_info = token_info[idx + 1]
                    if not tem_simbolo_moeda and v_info[8]:
                        tem_simbolo_moeda = True
                    if not tem_cadencia and v_info[9]:
                        tem_cadencia = True
                        cadencia_str = v_info[10]

            # Se o próprio token não tiver marcador, checa tokens precedentes imediatos (v_idx < idx) na mesma linha
            if not (tem_marcador_old or tem_marcador_curr):
                inicio_precedentes = max(0, idx - 5)
                for v_idx in range(inicio_precedentes, idx):
                    v_info = token_info[v_idx]
                    dist_ok = True
                    if has_geom and v_info[3]:
                        y_top = ymin if ymin >= v_info[6] else v_info[6]
                        y_bot = ymax if ymax <= v_info[7] else v_info[7]
                        y_overlap = (y_bot - y_top) if (y_bot > y_top) else 0.0
                        d = math.hypot(cx - v_info[4], cy - v_info[5])
                        dist_ok = (y_overlap > 0.0) and (d <= dist_max_px or idx - v_idx <= 2)

                    if dist_ok:
                        if v_info[11]:  # v m_old
                            tem_marcador_old = True
                        if v_info[12]:  # v m_curr
                            tem_marcador_curr = True

            # 3. Busca padrão de preço FIRST (evita executar regexes de rejeição em tokens que nem são preços)
            match = self._re_preco_padrao.search(texto)
            if not match:
                continue

            # Rejeição de unidades isoladas, percentuais, datas e identificadores (apenas se match de preço passou)
            if not tem_simbolo_moeda and not tem_cadencia:
                if self._re_unidades_medida.search(texto):
                    continue
                if self._re_dimensao_composta.search(texto):
                    continue
                if self._re_nao_moeda.search(texto):
                    continue

            raw_str = match.group(1)
            if "." in raw_str and "," in raw_str:
                valor_str = raw_str.replace(".", "").replace(",", ".")
            else:
                valor_str = raw_str.replace(",", ".")
            try:
                valor_float = float(valor_str)
            except ValueError:
                continue

            if valor_float < self.min_val or valor_float > self.max_val:
                continue

            # 4. Contexto vizinho: verificar se o token posterior é uma unidade de medida
            tem_sufixo_medida_vizinho = False
            if idx + 1 < n_tokens:
                proximo_texto = token_info[idx + 1][1].lower()
                if proximo_texto in {"g", "kg", "mg", "ml", "l", "litro", "litros", "sachê", "sache", "sachês", "saches", "un", "unidades", "cm", "mm", "%"}:
                    if has_geom and token_info[idx + 1][3]:
                        d = math.hypot(cx - token_info[idx + 1][4], cy - token_info[idx + 1][5])
                        if d < dist_max_px:
                            tem_sufixo_medida_vizinho = True
                    else:
                        tem_sufixo_medida_vizinho = True

            if tem_sufixo_medida_vizinho and not (tem_simbolo_moeda or tem_cadencia):
                continue

            # 5. Classificação canônica de AnchorEvidenceKind
            if tem_simbolo_moeda:
                evidence_kind = AnchorEvidenceKind.EXPLICIT_CURRENCY
            elif tem_cadencia:
                evidence_kind = AnchorEvidenceKind.CADENCE_PRICE
            else:
                evidence_kind = AnchorEvidenceKind.BARE_DECIMAL

            # 6. Classificação do papel relacional (AnchorRole)
            if tem_marcador_old and not tem_marcador_curr:
                role = AnchorRole.OLD_PRICE
            elif tem_marcador_curr and not tem_marcador_old:
                role = AnchorRole.CURRENT_PRICE
            else:
                role = AnchorRole.STANDALONE

            # 7. Confiança da âncora
            conf_base = token.confianca
            if evidence_kind == AnchorEvidenceKind.EXPLICIT_CURRENCY:
                conf_base = min(1.0, conf_base + 0.15)
            elif evidence_kind == AnchorEvidenceKind.CADENCE_PRICE:
                conf_base = min(1.0, conf_base + 0.10)

            ancora = CandidateAnchor(
                tipo="CURRENCY",
                texto_bruto=texto,
                valor_normalizado=round(valor_float, 2),
                unidade=self.default_currency,
                confianca=round(min(1.0, conf_base), 4),
                token_ref=token,
                bbox=token.bbox,
                evidence_kind=evidence_kind,
                cadencia=cadencia_str,
                role=role,
                metadados={
                    "valor_formatado": f"{valor_float:.2f}",
                    "evidence_kind": evidence_kind.value,
                    "cadencia": cadencia_str,
                    "role": role.value,
                    "regra_origem": self.name
                }
            )
            ancoras.append(ancora)

        return ancoras


class LegalProcessRule(CandidateRule):
    """
    Detecta números de processos judiciais no formato unificado CNJ (ex: 0812345-67.2026.8.18.0001).
    """

    def __init__(self):
        self._re_processo = re.compile(
            r'\b(\d{7}-\d{2}\.\d{4}(?:\.\d\.\d{2}\.\d{4})?|\d{7}-\d{2}\.\d{4})\b'
        )

    @property
    def name(self) -> str:
        return "LegalProcessRule"

    def detect(self, tokens: Sequence[SpatialToken], document: RawSpatialDocument) -> List[CandidateAnchor]:
        ancoras: List[CandidateAnchor] = []
        for token in tokens:
            texto = token.texto.strip()
            match = self._re_processo.search(texto)
            if match:
                num_proc = match.group(1)
                ancoras.append(CandidateAnchor(
                    tipo="LEGAL_PROCESS",
                    texto_bruto=texto,
                    valor_normalizado=num_proc,
                    unidade="PROCESSO_CNJ",
                    evidence_kind=AnchorEvidenceKind.TEMPORAL_OR_CODE,
                    confianca=min(1.0, token.confianca + 0.10),
                    token_ref=token,
                    bbox=token.bbox,
                    metadados={
                        "tipo_identificador": "processo_judicial",
                        "regra_origem": self.name
                    }
                ))
        return ancoras


class PercentageRule(CandidateRule):
    """
    Detecta indicadores e percentuais financeiros ou estatísticos (ex: 15,5%, +12.4%, -3.0%).
    """

    def __init__(self):
        self._re_percent = re.compile(r'([+-]?\d+(?:[.,]\d+)?)\s*%')

    @property
    def name(self) -> str:
        return "PercentageRule"

    def detect(self, tokens: Sequence[SpatialToken], document: RawSpatialDocument) -> List[CandidateAnchor]:
        ancoras: List[CandidateAnchor] = []
        for token in tokens:
            texto = token.texto.strip()
            match = self._re_percent.search(texto)
            if match:
                val_str = match.group(1).replace(",", ".")
                try:
                    val_float = float(val_str)
                except ValueError:
                    continue

                ancoras.append(CandidateAnchor(
                    tipo="PERCENTAGE",
                    texto_bruto=texto,
                    valor_normalizado=round(val_float, 2),
                    unidade="PERCENT",
                    confianca=min(1.0, token.confianca + 0.05),
                    token_ref=token,
                    bbox=token.bbox,
                    metadados={
                        "tipo_indicador": "taxa_percentual",
                        "regra_origem": self.name
                    }
                ))
        return ancoras


class SalaryRule(CandidateRule):
    """
    Detecta faixas salariais e remunerações em anúncios de emprego.
    """

    def __init__(self, default_currency: str = "BRL"):
        self.default_currency = default_currency
        self._re_salario = re.compile(
            r'(?:R\$\s*|\$\s*)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d{3,6}(?:,\d{2})?)(?:\s*(?:mensal|/m[eê]s|clt|pj|bruto|l[ií]quido))?',
            re.IGNORECASE
        )
        self._re_contexto_salario = re.compile(r'\b(sal[aá]rio|remunera[cç][aã]o|vencimento|bolsa|honor[aá]rios)\b', re.IGNORECASE)

    @property
    def name(self) -> str:
        return "SalaryRule"

    def detect(self, tokens: Sequence[SpatialToken], document: RawSpatialDocument) -> List[CandidateAnchor]:
        ancoras: List[CandidateAnchor] = []
        for idx, token in enumerate(tokens):
            texto = token.texto.strip()

            tem_termo_salario = bool(self._re_contexto_salario.search(texto))
            if not tem_termo_salario and idx > 0:
                tem_termo_salario = bool(self._re_contexto_salario.search(tokens[idx - 1].texto))

            match = self._re_salario.search(texto)
            if match and (tem_termo_salario or "R$" in texto or "$" in texto):
                raw_num = match.group(1).replace(".", "").replace(",", ".")
                try:
                    val_float = float(raw_num)
                except ValueError:
                    continue

                if val_float >= 500.0:  # Salário mínimo / limiar de remuneração
                    ancoras.append(CandidateAnchor(
                        tipo="SALARY",
                        texto_bruto=texto,
                        valor_normalizado=round(val_float, 2),
                        unidade=self.default_currency,
                        confianca=min(1.0, token.confianca + 0.15),
                        token_ref=token,
                        bbox=token.bbox,
                        metadados={
                            "tipo_remuneracao": "salario_anuncio",
                            "regra_origem": self.name
                        }
                    ))
        return ancoras


class TaxIdRule(CandidateRule):
    """
    Detecta CNPJ (00.000.000/0001-00) ou CPF (000.000.000-00).
    """

    def __init__(self):
        self._re_cnpj = re.compile(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b')
        self._re_cpf = re.compile(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b')

    @property
    def name(self) -> str:
        return "TaxIdRule"

    def detect(self, tokens: Sequence[SpatialToken], document: RawSpatialDocument) -> List[CandidateAnchor]:
        ancoras: List[CandidateAnchor] = []
        for token in tokens:
            texto = token.texto.strip()
            match_cnpj = self._re_cnpj.search(texto)
            if match_cnpj:
                ancoras.append(CandidateAnchor(
                    tipo="TAX_ID",
                    texto_bruto=texto,
                    valor_normalizado=match_cnpj.group(0),
                    unidade="CNPJ",
                    evidence_kind=AnchorEvidenceKind.TEMPORAL_OR_CODE,
                    confianca=token.confianca,
                    token_ref=token,
                    bbox=token.bbox,
                    metadados={"tipo_documento": "CNPJ", "regra_origem": self.name}
                ))
                continue

            match_cpf = self._re_cpf.search(texto)
            if match_cpf:
                ancoras.append(CandidateAnchor(
                    tipo="TAX_ID",
                    texto_bruto=texto,
                    valor_normalizado=match_cpf.group(0),
                    unidade="CPF",
                    evidence_kind=AnchorEvidenceKind.TEMPORAL_OR_CODE,
                    confianca=token.confianca,
                    token_ref=token,
                    bbox=token.bbox,
                    metadados={"tipo_documento": "CPF", "regra_origem": self.name}
                ))
        return ancoras


class DateRule(CandidateRule):
    """
    Detecta datas nos formatos DD/MM/AAAA ou AAAA-MM-DD.
    """

    def __init__(self):
        self._re_data = re.compile(r'\b(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b')

    @property
    def name(self) -> str:
        return "DateRule"

    def detect(self, tokens: Sequence[SpatialToken], document: RawSpatialDocument) -> List[CandidateAnchor]:
        ancoras: List[CandidateAnchor] = []
        for token in tokens:
            texto = token.texto.strip()
            match = self._re_data.search(texto)
            if match:
                ancoras.append(CandidateAnchor(
                    tipo="DATE",
                    texto_bruto=texto,
                    valor_normalizado=match.group(1),
                    unidade="DATE_ISO",
                    evidence_kind=AnchorEvidenceKind.TEMPORAL_OR_CODE,
                    confianca=token.confianca,
                    token_ref=token,
                    bbox=token.bbox,
                    metadados={"formato_detectado": "data_calendario", "regra_origem": self.name}
                ))
        return ancoras


class MeasurementContextRule(CandidateRule):
    """
    Detecta unidades de medida e especificações contextuais (gramatura, volume, dimensões).
    Não cria âncoras de valor primário, mas cataloga atributos para enriquecer as entidades.
    """

    def __init__(self):
        self._re_medida = re.compile(
            r'(\b\d+(?:[.,]\d+)?\s*(?:kg|g|mg|ml|l|litros?|sach[eê]s?|c[aá]psulas?|unidades?|un|cm|mm|m)\b|\b\d+x\d+(?:[.,]\d+)?\s*(?:g|ml|cm|mm)?\b)',
            re.IGNORECASE
        )

    @property
    def name(self) -> str:
        return "MeasurementContextRule"

    def detect(self, tokens: Sequence[SpatialToken], document: RawSpatialDocument) -> List[CandidateAnchor]:
        atributos: List[CandidateAnchor] = []
        for token in tokens:
            texto = token.texto.strip()
            match = self._re_medida.search(texto)
            if match:
                atributos.append(CandidateAnchor(
                    tipo="MEASUREMENT",
                    texto_bruto=match.group(1),
                    valor_normalizado=match.group(1),
                    unidade=None,
                    evidence_kind=AnchorEvidenceKind.SPECIFICATION,
                    confianca=token.confianca,
                    token_ref=token,
                    bbox=token.bbox,
                    metadados={"tipo_medida": "peso_volume_dimensao", "regra_origem": self.name}
                ))
        return atributos


class CandidateDetector:
    """Orquestrador de regras de candidatos espaciais."""

    def __init__(self, rules: Optional[Sequence[CandidateRule]] = None):
        self.rules: List[CandidateRule] = list(rules or [StrictCurrencyRule()])

    def detect_anchors(self, document: RawSpatialDocument) -> List[CandidateAnchor]:
        todas_ancoras: List[CandidateAnchor] = []
        for rule in self.rules:
            ancoras = rule.detect(document.tokens, document)
            todas_ancoras.extend(ancoras)

        # Desduplicação por sobreposição espacial (IoU > 0.6) quando houver BBox
        ancoras_desduplicadas: List[CandidateAnchor] = []
        for a in sorted(todas_ancoras, key=lambda x: x.confianca, reverse=True):
            sobreposto = False
            for existente in ancoras_desduplicadas:
                if a.bbox and existente.bbox and a.bbox.iou(existente.bbox) > 0.60:
                    sobreposto = True
                    break
            if not sobreposto:
                ancoras_desduplicadas.append(a)

        return ancoras_desduplicadas
