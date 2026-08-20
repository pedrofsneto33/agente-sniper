# -*- coding: utf-8 -*-
"""
Módulo de Decisão Estratégica e Validação Forense de Evidências — Agente Sniper
Responsável por gerar o pacote executivo determinístico e validar integridade de sinais e evidências.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from domain.models import Fonte
from domain.normalizer import normalizar
from domain.scoring import gerar_sinais_deterministicos


def inteligencia_deterministica(
    fontes: Sequence[Fonte],
    events: Sequence[Dict[str, Any]],
    ambiente: Dict[str, Any]
) -> Dict[str, Any]:
    """Gera o pacote executivo de inteligência competitiva determinístico."""
    sinais = gerar_sinais_deterministicos(fontes, events)
    dims = ambiente.get("dimensoes", {})
    melhor_dim = sorted(dims.items(), key=lambda kv: kv[1].get("score", 0), reverse=True)
    lacunas = []
    if dims.get("PREÇO", {}).get("score", 0) < 35:
        lacunas.append("Não há comparação confiável de preço suficiente nesta execução.")
    if dims.get("REPUTAÇÃO", {}).get("score", 0) < 35:
        lacunas.append("Não há amostra suficiente para inferir tendência de reputação.")
    if dims.get("EXPANSÃO", {}).get("score", 0) < 35:
        lacunas.append("Não há evidência suficiente de expansão recente.")
    if not any(e.get("date") for e in events):
        lacunas.append("A maior parte das evidências não possui data verificável.")
    top = melhor_dim[0][0] if melhor_dim else "dados insuficientes"
    pc = ambiente.get("pressao_competitiva", {})
    vb = ambiente.get("vulnerabilidade_empresa", {})
    resumo = [
        f"O radar identificou {len(fontes)} evidências válidas e {len(events)} eventos canônicos, agrupando múltiplas fontes do mesmo fato.",
        f"A atividade observável da empresa está em {ambiente.get('score', 0)}/100 ({ambiente.get('label', 'INDETERMINADA')}) e a vulnerabilidade externa/operacional estimada está em {vb.get('score',0)}/100 ({vb.get('label','BAIXA')}).",
        (f"A pressão competitiva externa está em {pc.get('score')}/100 ({pc.get('label')})." if pc.get('score') is not None else "A pressão competitiva externa não foi calculada por falta de evidência independente suficiente."),
        f"A dimensão com maior sinal nesta execução é {top}; isso representa atenção de monitoramento, não prova automática de perda financeira.",
    ]
    return {
        "resumo_executivo": resumo,
        "sinais": sinais,
        "concorrencia": [],
        "prioridades_30": [
            "Validar os 3 sinais de maior impacto com dados internos e contexto operacional.",
            "Definir concorrentes prioritários e iniciar uma linha de base comparativa.",
        ],
        "prioridades_60": [
            "Comparar tendência de preço, reputação, produto/serviço e movimento dos concorrentes.",
            "Transformar o principal sinal em um teste mensurável.",
        ],
        "prioridades_90": [
            "Consolidar indicadores em rotina semanal de decisão e alertas.",
            "Recalibrar scores com resultados observados na execução anterior.",
        ],
        "lacunas": lacunas or ["Não foram detectadas lacunas críticas nas dimensões monitoradas."],
    }


def validar_ids_sinais(pacote: Dict[str, Any], ids_validos: Set[int]) -> Tuple[bool, str]:
    """Valida se todos os evidence_ids citados em sinais e concorrência pertencem aos IDs válidos."""
    invalidos = []
    for campo in ("sinais", "concorrencia"):
        for item in pacote.get(campo, []) or []:
            if not isinstance(item, dict):
                continue
            for x in item.get("evidence_ids", []) or []:
                if str(x).isdigit() and int(x) not in ids_validos:
                    invalidos.append(int(x))
    if invalidos:
        return False, f"IDs inválidos: {sorted(set(invalidos))}"
    return True, "ok"


def validar_pacote(pacote: Dict[str, Any], fontes: Sequence[Fonte]) -> Dict[str, Any]:
    """Realiza validação forense e saneamento do pacote de inteligência contra as fontes reais."""
    ids = {f.id for f in fontes}
    ok, reason = validar_ids_sinais(pacote, ids)
    sinais_validos = []
    for s in pacote.get("sinais", []) or []:
        if not isinstance(s, dict):
            continue
        refs = [int(x) for x in s.get("evidence_ids", []) if str(x).isdigit() and int(x) in ids]
        if refs:
            # Confiança não pode superar a melhor confiança das evidências.
            max_conf = max((fontes[i-1].confianca for i in refs if 0 < i <= len(fontes)), default=0.0)
            try:
                s["confianca"] = min(float(s.get("confianca", max_conf)), max_conf)
            except Exception:
                s["confianca"] = max_conf
            s["evidence_ids"] = sorted(set(refs))
            sinais_validos.append(s)
    pacote["sinais"] = sinais_validos
    concorrentes_validos = []
    corpus = " ".join(f.texto() for f in fontes).lower()
    for c in pacote.get("concorrencia", []) or []:
        if not isinstance(c, dict):
            continue
        nome = str(c.get("nome", "")).strip()
        refs = [int(x) for x in c.get("evidence_ids", []) if str(x).isdigit() and int(x) in ids]
        if not nome or not refs:
            continue
        if normalizar(nome) in normalizar(corpus):
            c["evidence_ids"] = sorted(set(refs))
            concorrentes_validos.append(c)
    pacote["concorrencia"] = concorrentes_validos
    return {
        "valido": ok and bool(sinais_validos),
        "sinais": len(sinais_validos),
        "motivo": reason,
        "ids_validos": len(ids),
    }
