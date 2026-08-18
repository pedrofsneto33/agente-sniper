# -*- coding: utf-8 -*-
"""
Módulo de Inteligência de Scoring e Métricas Competitivas — Agente Sniper
Responsável por medir dimensões estratégicas, calcular pressão competitiva,
vulnerabilidade, momentum de mercado e sinais determinísticos sem dependências de infraestrutura.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from domain.models import Fonte
from domain.normalizer import score_clamp
from domain.events import (
    EVENT_RULES,
    RISK_KINDS,
    OPPORTUNITY_KINDS,
    recencia_score,
)


def medir_dimensoes(
    fontes: Sequence[Fonte],
    events: Sequence[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Calcula scores e métricas de cobertura para as 10 dimensões canônicas do radar.
    """
    out = {}
    for kind, rule in EVENT_RULES.items():
        evs = [e for e in events if e.get("kind") == kind and e.get("current", False)]
        uniq = len({i for e in evs for i in e.get("evidence_ids", [])})
        confirmed = sum(1 for e in evs if e.get("independent_source_count", 1) >= 2)
        rec = sum(float(e.get("confidence", 0.0)) for e in evs[:8]) / max(1, len(evs)) if evs else 0
        volume = min(1.0, uniq / 5.0)
        score = rule["base"] * (0.42 + 0.30 * volume + 0.18 * rec + 0.10 * min(1.0, confirmed / 2)) if evs else 0
        valid_ids = [x for e in evs for x in e.get("evidence_ids", []) if 0 < x <= len(fontes)]
        if valid_ids and all(not fontes[i - 1].data_publicacao for i in valid_ids):
            score *= 0.72
        out[kind] = {
            "score": score_clamp(score),
            "eventos": len(evs),
            "evidencias": uniq,
            "eventos_correlacionados": confirmed,
            "confianca_media": round(rec, 2),
        }
    return out


def score_ambiente_competitivo(dimensoes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcula o índice de atividade interna da empresa com base nas 10 dimensões.
    """
    pesos = {
        "PREÇO": .12,
        "EXPANSÃO": .16,
        "DIGITAL": .12,
        "MARKETING": .08,
        "PRODUTO/SERVIÇO": .10,
        "PARCERIA": .05,
        "REPUTAÇÃO": .14,
        "ATENDIMENTO": .08,
        "REGULAÇÃO": .08,
        "PESSOAS": .07
    }
    total = sum(dimensoes.get(k, {}).get("score", 0) * w for k, w in pesos.items())
    cobertura = sum(w for k, w in pesos.items() if dimensoes.get(k, {}).get("score", 0) > 0)
    penalty = 0.72 if cobertura < .40 else 0.86 if cobertura < .60 else 1.0
    total *= penalty
    return {
        "score": score_clamp(total),
        "label": "ALTA" if total >= 70 else "MÉDIA" if total >= 45 else "BAIXA",
        "cobertura": round(cobertura, 2),
        "tipo": "atividade_da_empresa"
    }


def score_pressao_competitiva(
    fontes: Sequence[Fonte],
    events: Sequence[Dict[str, Any]],
    empresa_alvo: str = "Supermercado Carvalho"
) -> Dict[str, Any]:
    """
    Mede o nível de pressão e movimentos externos de concorrentes.
    """
    externos = [e for e in events if e.get("current", False) and e.get("entity") not in {"", empresa_alvo}]
    externos = [e for e in externos if e.get("entity") != "mercado" or e.get("importance", 0) >= 55]
    if not externos:
        return {
            "score": None,
            "label": "NÃO CALCULADO",
            "cobertura": 0.0,
            "motivo": "Sem eventos externos relevantes."
        }
    by_entity: Dict[str, float] = {}
    for e in externos:
        ent = e.get("entity") or "mercado"
        by_entity[ent] = by_entity.get(ent, 0) + e["importance"] * max(.35, float(e.get("confidence", .5)))
    ranked = sorted(by_entity.items(), key=lambda kv: kv[1], reverse=True)
    leader = ranked[0][1]
    diversity = min(1.0, len(ranked) / 4)
    corroboration = min(1.0, sum(1 for e in externos if e.get("independent_source_count", 1) >= 2) / max(1, len(externos)))
    intensity = min(100, leader / 2.8)
    score = score_clamp(intensity * .58 + diversity * 24 + corroboration * 18)
    return {
        "score": score,
        "label": "ALTA" if score >= 70 else "MÉDIA" if score >= 45 else "BAIXA",
        "cobertura": round(diversity, 2),
        "corroboracao": round(corroboration, 2),
        "entidades": [x[0] for x in ranked[:5]],
        "tipo": "pressao_externa"
    }


def score_vulnerabilidade_empresa(
    events: Sequence[Dict[str, Any]],
    empresa_alvo: str = "Supermercado Carvalho"
) -> Dict[str, Any]:
    """
    Mede a exposição a riscos da empresa alvo com controle estrito anti-inflação.
    """
    riscos = [e for e in events if e.get("current", False) and e.get("entity") == empresa_alvo and e.get("kind") in RISK_KINDS]
    if not riscos:
        return {"score": 0, "label": "BAIXA", "cobertura": 0.0, "tipo": "vulnerabilidade_empresa"}
    total = 0.0
    recent = 0
    corroborated = 0
    kinds = set()
    for e in riscos[:10]:
        conf = float(e.get("confidence", 0.5))
        sources = int(e.get("independent_source_count", 1))
        dated = bool(e.get("date"))
        factor = conf
        if sources >= 2:
            factor *= 1.0
            corroborated += 1
        else:
            factor *= 0.50
        if dated:
            recent += 1
        else:
            factor *= 0.55
        total += float(e.get("importance", 0)) * factor
        kinds.add(e.get("kind"))
    raw = min(100.0, total / 2.4)
    if len(riscos) == 1 and corroborated == 0:
        raw = min(raw, 38.0)
    elif len(riscos) <= 2 and corroborated == 0:
        raw = min(raw, 52.0)
    elif corroborated == 0 and len(kinds) == 1:
        raw = min(raw, 62.0)
    score = score_clamp(raw)
    label = "ALTA" if score >= 70 else "MÉDIA" if score >= 40 else "BAIXA"
    return {
        "score": score,
        "label": label,
        "eventos_de_risco": len(riscos),
        "eventos_correlacionados": corroborated,
        "dimensoes_de_risco": len(kinds),
        "fontes_diferentes": sum(max(1, int(e.get("independent_source_count", 1))) for e in riscos),
        "cobertura": round(min(1.0, (len(riscos) + corroborated) / (4.0)), 2),
        "tipo": "vulnerabilidade_empresa",
        "regra": "evento isolado sem corroboracao limitado a 38/100; score alto exige recorrencia e/ou fontes independentes."
    }


def classificar_sinal(event: Dict[str, Any]) -> str:
    """Classifica a tipologia de um sinal (RISCO, OPORTUNIDADE ou MOVIMENTO)."""
    if event.get("kind") in RISK_KINDS:
        return "RISCO"
    if event.get("kind") in OPPORTUNITY_KINDS:
        return "OPORTUNIDADE"
    return "MOVIMENTO"


def acao_evento(kind: str) -> str:
    """Retorna a recomendação acionável padrão para uma dimensão de evento."""
    return {
        "PREÇO": "Medir preço/promoção em itens sensíveis antes de alterar margem.",
        "REPUTAÇÃO": "Quantificar recorrência e gravidade antes de tratar o tema como estrutural.",
        "ATENDIMENTO": "Monitorar por unidade/canal e criar KPI operacional.",
        "EXPANSÃO": "Mapear raio de impacto e comparar oferta/concorrência local.",
        "DIGITAL": "Comparar jornada, aquisição e conveniência digital.",
        "MARKETING": "Mapear mensagem, público e timing antes de reagir.",
        "PESSOAS": "Separar expansão de reposição antes de inferir crescimento.",
        "REGULAÇÃO": "Validar o ato diretamente em fonte oficial.",
        "PRODUTO/SERVIÇO": "Comparar mix, lançamento e proposta de valor.",
        "PARCERIA": "Avaliar impacto em distribuição, canal, tecnologia ou aquisição."
    }.get(kind, "Investigar o evento antes de agir.")


def gerar_sinais_deterministicos(
    fontes: Sequence[Fonte],
    events: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Gera até 12 sinais estratégicos auditáveis a partir de eventos e evidências."""
    fmap = {f.id: f for f in fontes}
    sinais = []
    for e in events[:18]:
        ids = [x for x in e.get("evidence_ids", []) if x in fmap]
        if not ids:
            continue
        independent = e.get("independent_source_count", 1)
        corroborado = independent >= 2
        importance = e.get("importance", 0)
        impacto = "ALTO" if importance >= 75 and corroborado else "MEDIO" if importance >= 55 else "BAIXO"
        if e.get("kind") in {"REPUTAÇÃO", "ATENDIMENTO"} and not corroborado:
            impacto = "BAIXO" if importance < 65 else "MEDIO"
        urg = "ALTA" if importance >= 78 and corroborado else "MEDIA" if importance >= 55 else "BAIXA"
        sinais.append({
            "titulo": e.get("title", ""),
            "tipo": classificar_sinal(e),
            "impacto": impacto,
            "urgencia": urg,
            "racional": f"Evento sustentado por {len(ids)} evidência(s) e {independent} fonte(s) independente(s). Isso é um sinal; não prova causalidade financeira.",
            "acao": acao_evento(e.get("kind", "")),
            "evidence_ids": ids,
            "confianca": e.get("confidence", 0.0),
            "limite": "corroborado" if corroborado else "sinal isolado",
            "event_id": e.get("event_id", ""),
            "entidade": e.get("entity")
        })
    return sinais[:12]


def score_momentum(
    events: Sequence[Dict[str, Any]],
    fontes: Sequence[Fonte],
    hoje: Optional[datetime] = None
) -> int:
    """Calcula a velocidade e intensidade dos movimentos recentes do mercado."""
    recent = [e for e in events if e.get("date") and e.get("current", False)]
    if not recent:
        return 0
    values = []
    fmap = {f.id: f for f in fontes}
    for e in recent[:15]:
        evidence_ids = e.get("evidence_ids", [])
        if evidence_ids:
            f = fmap.get(evidence_ids[0])
            values.append(e.get("importance", 0) * recencia_score(f, hoje=hoje) if f else 0)
        else:
            values.append(0)
    return score_clamp(sum(values) / max(1, len(values)))
