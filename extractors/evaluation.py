# -*- coding: utf-8 -*-
"""
Infraestrutura de Avaliação Quantitativa e Gold Dataset (Benchmark) — Fase 2
Calcula métricas formais: Precision, Recall, F1-Score, Falsos Positivos, Falsos Negativos e Taxa de Duplicação.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
import math
from extractors.models import ExtractedEntity, RawSpatialDocument


@dataclass(frozen=True)
class GroundTruthItem:
    """Item gabarito esperado para validação de acurácia."""
    entidade: str
    valor: Optional[Any] = None
    unidade: Optional[str] = None
    atributos_chave: Dict[str, Any] = field(default_factory=dict)
    identificador_item: Optional[str] = None


@dataclass
class GoldDataset:
    """Conjunto gabarito anotado para um documento de teste."""
    identificador: str
    documento: RawSpatialDocument
    itens_esperados: List[GroundTruthItem]


@dataclass
class EvaluationMetrics:
    """Relatório quantitativo consolidado de acurácia."""
    total_esperado: int
    total_extraido: int
    verdadeiros_positivos: int
    falsos_positivos: int
    falsos_negativos: int
    duplicados: int
    precision: float
    recall: float
    f1_score: float
    taxa_duplicacao: float
    detalhes_erros: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_esperado": self.total_esperado,
            "total_extraido": self.total_extraido,
            "verdadeiros_positivos": self.verdadeiros_positivos,
            "falsos_positivos": self.falsos_positivos,
            "falsos_negativos": self.falsos_negativos,
            "duplicados": self.duplicados,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "taxa_duplicacao": round(self.taxa_duplicacao, 4),
            "detalhes_erros": self.detalhes_erros,
        }


def avaliar_extracao(
    extraidos: Sequence[ExtractedEntity],
    esperados: Sequence[GroundTruthItem],
    tolerancia_numerica: float = 0.02
) -> EvaluationMetrics:
    """
    Compara a lista de entidades extraídas com o gabarito (Ground Truth).
    Calcula matriz de confusão e métricas balanceadas de qualidade.
    """
    total_exp = len(esperados)
    total_ext = len(extraidos)

    if total_exp == 0 and total_ext == 0:
        return EvaluationMetrics(
            total_esperado=0,
            total_extraido=0,
            verdadeiros_positivos=0,
            falsos_positivos=0,
            falsos_negativos=0,
            duplicados=0,
            precision=1.0,
            recall=1.0,
            f1_score=1.0,
            taxa_duplicacao=0.0
        )

    esperados_pareados = set()
    duplicados_count = 0
    verdadeiros_positivos = 0
    falsos_positivos = 0
    detalhes: List[Dict[str, Any]] = []

    for ext in extraidos:
        # Busca primeiro um item compatível AINDA NÃO PAREADO
        indice_pareado: Optional[int] = None
        indice_candidato_duplicado: Optional[int] = None

        for idx_esp, esp in enumerate(esperados):
            if ext.entidade != esp.entidade:
                continue

            valor_compativel = False
            if ext.valor is None and esp.valor is None:
                valor_compativel = True
            elif isinstance(ext.valor, (int, float)) and isinstance(esp.valor, (int, float)):
                if abs(float(ext.valor) - float(esp.valor)) <= tolerancia_numerica:
                    valor_compativel = True
            elif str(ext.valor).strip().lower() == str(esp.valor).strip().lower():
                valor_compativel = True

            if valor_compativel:
                if idx_esp not in esperados_pareados:
                    indice_pareado = idx_esp
                    break
                else:
                    indice_candidato_duplicado = idx_esp

        if indice_pareado is not None:
            verdadeiros_positivos += 1
            esperados_pareados.add(indice_pareado)
        elif indice_candidato_duplicado is not None:
            duplicados_count += 1
            detalhes.append({
                "tipo_erro": "duplicacao",
                "entidade_extraida": ext.to_dict(),
                "esperado_pareado_anteriormente": esperados[indice_candidato_duplicado].identificador_item
            })
        else:
            falsos_positivos += 1
            detalhes.append({
                "tipo_erro": "falso_positivo",
                "entidade_extraida": ext.to_dict()
            })

    falsos_negativos = total_exp - len(esperados_pareados)
    for idx_esp, esp in enumerate(esperados):
        if idx_esp not in esperados_pareados:
            detalhes.append({
                "tipo_erro": "falso_negativo",
                "esperado_nao_encontrado": {
                    "entidade": esp.entidade,
                    "valor": esp.valor,
                    "id": esp.identificador_item
                }
            })

    # Cálculo formal das métricas
    precision = verdadeiros_positivos / max(1, (verdadeiros_positivos + falsos_positivos))
    recall = verdadeiros_positivos / max(1, (verdadeiros_positivos + falsos_negativos))
    f1 = (2 * precision * recall) / max(0.0001, (precision + recall)) if (precision + recall) > 0 else 0.0
    taxa_dup = duplicados_count / max(1, total_ext)

    return EvaluationMetrics(
        total_esperado=total_exp,
        total_extraido=total_ext,
        verdadeiros_positivos=verdadeiros_positivos,
        falsos_positivos=falsos_positivos,
        falsos_negativos=falsos_negativos,
        duplicados=duplicados_count,
        precision=precision,
        recall=recall,
        f1_score=f1,
        taxa_duplicacao=taxa_dup,
        detalhes_erros=detalhes
    )
