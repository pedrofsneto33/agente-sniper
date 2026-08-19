# -*- coding: utf-8 -*-
"""
Motor de Detecção e Discriminação de Âncoras Candidatas — Fase 3
Suporta regras plugáveis para múltiplos domínios: Moeda, Processo Judicial, Percentuais, Salários, CNPJ e Datas.
"""

from abc import ABC, abstractmethod
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from extractors.models import BoundingBox, SpatialToken, CandidateAnchor, RawSpatialDocument, AnchorEvidenceKind


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
    Classifica âncoras em EXPLICIT_CURRENCY, CADENCE_PRICE e BARE_DECIMAL.
    """
    
    def __init__(self, default_currency: str = "BRL", min_val: float = 0.05, max_val: float = 999999.0):
        self.default_currency = default_currency
        self.min_val = min_val
        self.max_val = max_val

        self._re_simbolo_moeda = re.compile(r'(?:R\$|\$|€|£|US\$)', re.IGNORECASE)
        self._re_cadencia = re.compile(
            r'(?:/(?:m[eê]s|ano|dia|di[aá]ria|sess[aã]o|hora|un|unidade|kg|g|l|litro|pe[cç]a|item|m[23]|km|pax|noite)|'
            r'(?:\s+(?:por|ao|a cada|cada)\s+(?:m[eê]s|ano|dia|di[aá]ria|sess[aã]o|hora|un|unidade|kg|g|l|litro|pe[cç]a|item|m[23]|km|pax|noite))|'
            r'\s+CADA|\s+POR\s+M[EÊ]S|\s+MENSAL|\s+ANUAL|\s+DI[AÁ]RIO|\s+POR\s+DIA)',
            re.IGNORECASE
        )
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
            r'(?:R\$\s*|\$\s*|€\s*|£\s*|US\$\s*)?(\b(?:\d{1,3}(?:\.\d{3})+,\d{2}|\d{1,5}[.,]\d{2})\b)(?:[^\w\s]?(?:m[eê]s|ano|dia|di[aá]ria|sess[aã]o|hora|un|unidade|kg|g|l|litro|pe[cç]a|item|m[23]|km|pax|noite)|\s+CADA|\s+KG|\s+UN)?',
            re.IGNORECASE
        )

    @property
    def name(self) -> str:
        return "StrictCurrencyRule"

    def detect(self, tokens: Sequence[SpatialToken], document: RawSpatialDocument) -> List[CandidateAnchor]:
        ancoras: List[CandidateAnchor] = []

        for idx, token in enumerate(tokens):
            texto = token.texto.strip()

            # 1. Identificação do tipo de evidência monetária no próprio token
            tem_simbolo_moeda = bool(self._re_simbolo_moeda.search(texto))
            match_cadencia = self._re_cadencia.search(texto)
            tem_cadencia = bool(match_cadencia)
            cadencia_str = match_cadencia.group(0).strip() if match_cadencia else None

            # 2. Contexto vizinho imediato e espacial 2D (mesma linha na janela local)
            vizinhos_a_checar = []
            inicio_janela = max(0, idx - 15)
            fim_janela = min(len(tokens), idx + 16)

            if token.has_geometry and token.bbox:
                for v_idx in range(inicio_janela, fim_janela):
                    if v_idx == idx:
                        continue
                    v = tokens[v_idx]
                    if v.has_geometry and v.bbox:
                        if token.bbox.distance_to(v.bbox) <= 120.0 and abs(token.bbox.centro_y - v.bbox.centro_y) <= 40.0:
                            vizinhos_a_checar.append(v)
            else:
                if idx > 0:
                    vizinhos_a_checar.append(tokens[idx - 1])
                if idx + 1 < len(tokens):
                    vizinhos_a_checar.append(tokens[idx + 1])

            for v in vizinhos_a_checar:
                v_txt = v.texto.strip()
                dist_ok = True
                if token.has_geometry and v.has_geometry and token.bbox and v.bbox:
                    dist_ok = token.bbox.distance_to(v.bbox) <= 120.0

                if dist_ok:
                    if not tem_simbolo_moeda and self._re_simbolo_moeda.search(v_txt):
                        tem_simbolo_moeda = True
                    if not tem_cadencia:
                        m_cad = self._re_cadencia.search(v_txt)
                        if m_cad:
                            tem_cadencia = True
                            cadencia_str = m_cad.group(0).strip()

            # Rejeição de unidades isoladas, percentuais, datas e identificadores
            if not tem_simbolo_moeda and not tem_cadencia:
                if self._re_unidades_medida.search(texto):
                    continue
                if self._re_dimensao_composta.search(texto):
                    continue
                if self._re_nao_moeda.search(texto):
                    continue

            # 3. Busca padrão de preço
            match = self._re_preco_padrao.search(texto)
            if not match:
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
            if idx + 1 < len(tokens):
                proximo_texto = tokens[idx + 1].texto.strip().lower()
                if proximo_texto in {"g", "kg", "mg", "ml", "l", "litro", "litros", "sachê", "sache", "sachês", "saches", "un", "unidades", "cm", "mm", "%"}:
                    if token.has_geometry and tokens[idx + 1].has_geometry and token.bbox and tokens[idx + 1].bbox:
                        if token.bbox.distance_to(tokens[idx + 1].bbox) < 120.0:
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

            # 6. Confiança da âncora
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
                metadados={
                    "valor_formatado": f"{valor_float:.2f}",
                    "evidence_kind": evidence_kind.value,
                    "cadencia": cadencia_str,
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
