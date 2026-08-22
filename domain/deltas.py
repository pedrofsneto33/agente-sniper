# -*- coding: utf-8 -*-
"""
Módulo de Deltas Factuais, Inteligência Incremental e Memória de Entrega — Agente Sniper
Responsável por calcular variações temporais, novidade factual, mudanças materiais,
relevância por nicho e rastrear histórico de entregas sem acoplamento a banco de dados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from domain.models import Fonte
from domain.identity import sha1, url_normalizada
from domain.normalizer import parse_data, normalizar
from domain.events import (
    EVENT_DATE_CLUSTER_DAYS,
    EVENT_CURRENT_WINDOW_DAYS,
    EVENT_CONTEXTUAL_MAX_DAYS,
    eventos_sao_mesmo_fato,
)

# Estados Canônicos de Inteligência Incremental
ESTADO_EVENTO_NOVO: str = "NOVO"
ESTADO_EVENTO_RECORRENTE: str = "RECORRENTE"
ESTADO_EVENTO_ATUALIZADO: str = "ATUALIZADO"
ESTADO_EVENTO_CONTINUIDADE: str = "CONTINUIDADE"
ESTADO_EVENTO_SEM_MUDANCA: str = "SEM_MUDANCA"
ESTADO_EVENTO_SUBSTITUIDO: str = "SUBSTITUIDO"
ESTADO_EVENTO_INATIVO_EXPIRADO: str = "INATIVO_EXPIRADO"

# Rótulos Declarativos de Tendência Temporal Longitudinal
TEMPORAL_TREND_INEDITO: str = "INEDITO"
TEMPORAL_TREND_ACELERANDO: str = "ACELERANDO"
TEMPORAL_TREND_ESTABILIZADO: str = "ESTABILIZADO"
TEMPORAL_TREND_MARCO_CONCLUIDO: str = "MARCO_CONCLUIDO"
TEMPORAL_TREND_REATIVADO: str = "REATIVADO"

# Pesos Padrão de Relevância por Dimensão Canônica
DEFAULT_DIMENSION_WEIGHTS: Dict[str, float] = {
    "REGULAÇÃO": 1.00,
    "PREÇO": 0.85,
    "EXPANSÃO": 0.85,
    "REPUTAÇÃO": 0.80,
    "DIGITAL": 0.75,
    "PESSOAS": 0.70,
    "ATENDIMENTO": 0.70,
    "PRODUTO/SERVIÇO": 0.70,
    "MARKETING": 0.60,
    "PARCERIA": 0.55,
}


@dataclass(frozen=True)
class RegistroEntrega:
    """
    Registro forense e auditável de uma entrega efetiva de evento/relatório.
    """
    event_id: str
    event_key: str
    delivered_at: str
    delivered_to: str
    fingerprint_entrega: str
    run_id: str = ""
    nicho: str = "generico"
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoriaEntrega:
    """
    Gerenciador puro de memória de entrega particionado por cliente/perfil.
    Permite registrar e consultar deterministicamente o que já foi apresentado.
    """

    def __init__(self, entregas_iniciais: Optional[Sequence[RegistroEntrega | Dict[str, Any]]] = None):
        self._entregas_por_cliente: Dict[str, Dict[str, RegistroEntrega]] = {}
        if entregas_iniciais:
            for item in entregas_iniciais:
                self.registrar(item)

    def registrar(self, entrega: RegistroEntrega | Dict[str, Any]) -> None:
        """Registra uma entrega efetiva para um cliente específico."""
        if isinstance(entrega, dict):
            reg = RegistroEntrega(
                event_id=str(entrega.get("event_id") or ""),
                event_key=str(entrega.get("event_key") or entrega.get("event_id") or ""),
                delivered_at=str(entrega.get("delivered_at") or ""),
                delivered_to=str(entrega.get("delivered_to") or "default"),
                fingerprint_entrega=str(entrega.get("fingerprint_entrega") or ""),
                run_id=str(entrega.get("run_id") or ""),
                nicho=str(entrega.get("nicho") or "generico"),
                metadata=dict(entrega.get("metadata") or {}),
            )
        else:
            reg = entrega
        cliente = reg.delivered_to.strip().lower()
        chave = reg.event_key or reg.event_id
        if cliente and chave:
            self._entregas_por_cliente.setdefault(cliente, {})[chave] = reg

    def foi_entregue(self, event_key_ou_id: str, delivered_to: str = "default") -> bool:
        """Verifica se um evento já foi entregue a determinado cliente."""
        cliente = delivered_to.strip().lower()
        return event_key_ou_id in self._entregas_por_cliente.get(cliente, {})

    def foi_entregue_com_fingerprint(self, event_key_ou_id: str, fingerprint: str, delivered_to: str = "default") -> bool:
        """
        Verifica se a mesma entrega específica (mesmo evento E mesmo fingerprint) já foi realizada.
        Se o fingerprint mudou (ex: hipótese/solução evoluiu), retorna False, permitindo reentrega.
        """
        reg = self.obter_registro(event_key_ou_id, delivered_to=delivered_to)
        if not reg:
            return False
        return reg.fingerprint_entrega == fingerprint

    def obter_registro(self, event_key_ou_id: str, delivered_to: str = "default") -> Optional[RegistroEntrega]:
        """Recupera o registro de entrega de um evento para determinado cliente."""
        cliente = delivered_to.strip().lower()
        return self._entregas_por_cliente.get(cliente, {}).get(event_key_ou_id)


def calcular_delta_fontes(
    fontes: Sequence[Fonte],
    hashes_anteriores: Optional[Mapping[str, str]] = None
) -> Dict[str, Any]:
    """
    Calcula fontes novas e fontes alteradas em relação aos hashes da execução anterior.
    """
    novos: Set[str] = set()
    alterados: Set[str] = set()

    if hashes_anteriores is not None:
        for f in fontes:
            if f.fingerprint not in hashes_anteriores:
                novos.add(f.fingerprint)
            elif hashes_anteriores[f.fingerprint] != sha1(f.conteudo):
                alterados.add(f.fingerprint)

    return {
        "novas_fontes": len(novos),
        "fontes_alteradas": len(alterados),
        "novos_fingerprints": novos,
        "alterados_fingerprints": alterados,
    }


def _extrair_data_evento(ev: Mapping[str, Any]) -> Optional[datetime]:
    """Extrai objeto datetime de um evento (date ou created_at)."""
    raw = ev.get("date") or ev.get("created_at") or ""
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw:
        return parse_data(raw[:10])
    return None


def verificar_mudanca_material(
    ev_atual: Mapping[str, Any],
    ev_hist: Mapping[str, Any]
) -> Tuple[bool, str]:
    """
    Determina se um evento recorrente sofreu alteração material ou se é repetição superficial.
    Retorna (is_material: bool, motivo: str).
    """
    # 1. Mudança de entidade
    ent_atual = str(ev_atual.get("entity") or "").strip().lower()
    ent_hist = str(ev_hist.get("entity") or "").strip().lower()
    if ent_atual and ent_hist and ent_atual != ent_hist:
        return True, f"entidade_alterada: {ent_hist} -> {ent_atual}"

    # 2. Identidade e corroboração de fontes independentes
    cur_urls = [url_normalizada(str(u)) for u in (ev_atual.get("source_urls") or []) if u]
    hist_urls = [url_normalizada(str(u)) for u in (ev_hist.get("source_urls") or []) if u]
    if cur_urls and hist_urls:
        novas_urls = set(cur_urls) - set(hist_urls)
        if novas_urls:
            return True, f"nova_corroboracao: {len(novas_urls)} nova(s) fonte(s)"

    cur_domains = set(ev_atual.get("source_domains") or [])
    hist_domains = set(ev_hist.get("source_domains") or [])
    if cur_domains and hist_domains:
        novos_doms = cur_domains - hist_domains
        if novos_doms:
            return True, f"novo_dominio_independente: {', '.join(sorted(novos_doms))}"

    fontes_atuais = int(ev_atual.get("independent_source_count") or ev_atual.get("fontes_independentes") or len(ev_atual.get("evidence_ids") or []))
    fontes_hist = int(ev_hist.get("independent_source_count") or ev_hist.get("fontes_independentes") or len(ev_hist.get("evidence_ids") or []))
    if fontes_atuais > fontes_hist:
        return True, f"nova_corroboracao: {fontes_hist} -> {fontes_atuais} fontes"

    # 3. Evolução de status de confiança (ex: SINAL -> PROVÁVEL / CONFIRMADO)
    conf_atual = str(ev_atual.get("confianca_evidencia") or "")
    conf_hist = str(ev_hist.get("confianca_evidencia") or "")
    if conf_atual and conf_hist and conf_atual != conf_hist:
        return True, f"status_confianca_alterado: {conf_hist} -> {conf_atual}"

    # 4. Variação material de importância (delta >= 10 pontos)
    imp_atual = float(ev_atual.get("importance") or 0)
    imp_hist = float(ev_hist.get("importance") or 0)
    if abs(imp_atual - imp_hist) >= 10.0:
        return True, f"variacao_importancia: {imp_hist:.0f} -> {imp_atual:.0f}"

    # 5. Desdobramento de título/fato
    t_atual = normalizar(str(ev_atual.get("title") or ""))
    t_hist = normalizar(str(ev_hist.get("title") or ""))
    status_keywords = [
        ("anuncia", "inaugura"), ("planeja", "abriu"), ("vai abrir", "abriu"),
        ("investigacao", "multa"), ("processo", "condenacao"), ("vaga", "contratado"),
        ("fechamento", "reabertura"),
    ]
    for k1, k2 in status_keywords:
        if (k1 in t_hist and k2 in t_atual) or (k2 in t_hist and k1 in t_atual):
            return True, f"evolucao_fato: {k1} -> {k2}"

    return False, "sem_mudanca_material"


def determinar_tendencia_temporal(
    estado_incremental: str = ESTADO_EVENTO_NOVO,
    motivo_mudanca: str = "",
    is_material: bool = True,
    entregue_anteriormente: bool = False,
    continuity_cycles: int = 0,
    title: str = "",
) -> str:
    """
    Classifica deterministicamente a tendência temporal de um evento/oportunidade.
    Retorna um dos 5 estados declarativos: INEDITO, ACELERANDO, ESTABILIZADO, MARCO_CONCLUIDO, REATIVADO.
    """
    motivo_norm = normalizar(motivo_mudanca or "")
    estado_norm = str(estado_incremental or ESTADO_EVENTO_NOVO).upper()
    title_norm = normalizar(title or "")

    # 1. Se não há mudança material ou está em continuidade/estabilização
    if not is_material or estado_norm in {ESTADO_EVENTO_CONTINUIDADE, ESTADO_EVENTO_SEM_MUDANCA} or motivo_norm == "sem_mudanca_material":
        return TEMPORAL_TREND_ESTABILIZADO

    # 2. Se é evolução factual de desfecho/marco concluído
    conclusao_tokens = ["inaugura", "abriu", "multa", "condenacao", "contratado", "concluid", "finaliz", "reabertura"]
    if "evolucao_fato" in motivo_norm or any(tok in title_norm for tok in ["inaugura", "abriu", "condenacao"]):
        if any(tok in motivo_norm or tok in title_norm for tok in conclusao_tokens):
            return TEMPORAL_TREND_MARCO_CONCLUIDO

    # 3. Se já foi entregue anteriormente ou estava condensado/latente e agora volta com mudança material
    if entregue_anteriormente and is_material:
        return TEMPORAL_TREND_REATIVADO

    # 4. Se é aceleração por corroboração, aumento de fontes, importância ou evolução de status
    if estado_norm == ESTADO_EVENTO_ATUALIZADO or any(k in motivo_norm for k in ["nova_corroboracao", "novo_dominio", "variacao_importancia", "status_confianca"]):
        return TEMPORAL_TREND_ACELERANDO

    # 5. Fato inédito / novo
    if estado_norm == ESTADO_EVENTO_NOVO or motivo_norm == "fato_inedito" or not motivo_norm:
        return TEMPORAL_TREND_INEDITO

    return TEMPORAL_TREND_INEDITO


def calcular_relevancia_nicho(
    evento: Mapping[str, Any],
    profile: Optional[Dict[str, Any]] = None
) -> float:
    """
    Calcula a relevância contextual do evento para o perfil de nicho ativo,
    desacoplando formalmente o conceito de relevância da dimensão de preço.
    """
    kind = str(evento.get("kind") or "MOVIMENTO").upper()
    importance = float(evento.get("importance") or 50.0)
    confidence = float(evento.get("confidence") or 0.60)

    weights = DEFAULT_DIMENSION_WEIGHTS
    if profile and isinstance(profile, dict):
        custom_weights = profile.get("relevance_weights")
        if isinstance(custom_weights, dict) and custom_weights:
            weights = custom_weights

    dim_weight = float(weights.get(kind, 0.70))
    conf_factor = 0.50 + 0.50 * min(1.0, max(0.0, confidence))
    raw_score = importance * dim_weight * conf_factor
    return round(min(100.0, max(0.0, raw_score)), 2)


def analisar_inteligencia_incremental(
    eventos_atuais: Sequence[Dict[str, Any]],
    eventos_historicos: Sequence[Dict[str, Any]],
    profile: Optional[Dict[str, Any]] = None,
    cadencia_dias: int = 7,
    cluster_days: int = EVENT_DATE_CLUSTER_DAYS,
    hoje: Optional[datetime] = None,
    memoria_entrega: Optional[MemoriaEntrega] = None,
    delivered_to: str = "default",
) -> Dict[str, Any]:
    """
    Motor determinístico de inteligência incremental, novidade e memória de entrega.
    Classifica cada evento observado em:
    - NOVO: fatos inéditos sem correspondência anterior
    - ATUALIZADO: fatos conhecidos com alteração material
    - CONTINUIDADE: fatos persistentes de alta relevância que permanecem vigentes
    - SEM_MUDANCA: fatos repetidos sem alteração factual
    - EXPIRADO: fatos que ultrapassaram a janela de vigência sem renovação
    """
    ref_hoje = hoje or datetime.now()

    novos: List[Dict[str, Any]] = []
    atualizados: List[Dict[str, Any]] = []
    continuidade: List[Dict[str, Any]] = []
    sem_mudanca: List[Dict[str, Any]] = []
    recorrentes: List[Dict[str, Any]] = []

    # Indexação histórica por event_key/event_id
    hist_por_key: Dict[str, Dict[str, Any]] = {}
    for h in eventos_historicos:
        k = h.get("event_key") or h.get("event_id")
        if k and k not in hist_por_key:
            hist_por_key[k] = h

    consumidos_hist_keys: Set[str] = set()

    for ev in eventos_atuais:
        ev_key = ev.get("event_key") or ev.get("event_id")
        pareado_hist = None

        # 1. Correspondência Exata por event_key (se não consumido)
        if ev_key and ev_key in hist_por_key and ev_key not in consumidos_hist_keys:
            pareado_hist = hist_por_key[ev_key]
        else:
            # 2. Resolução Semântico-Temporal
            for h in eventos_historicos:
                h_k = h.get("event_key") or h.get("event_id")
                if h_k and h_k in consumidos_hist_keys:
                    continue
                if eventos_sao_mesmo_fato(h, ev, cluster_days=cluster_days):
                    pareado_hist = h
                    break

        ev_copia = dict(ev)
        relevancia = calcular_relevancia_nicho(ev_copia, profile=profile)
        ev_copia["score_relevancia_nicho"] = relevancia

        # Consulta de memória de entrega (se configurada)
        chave_consulta = ev_key or ev_copia.get("event_id") or ""
        entregue_antes = False
        if memoria_entrega and chave_consulta:
            entregue_antes = memoria_entrega.foi_entregue(chave_consulta, delivered_to=delivered_to)
        ev_copia["entregue_anteriormente"] = entregue_antes

        if pareado_hist is not None:
            h_k = pareado_hist.get("event_key") or pareado_hist.get("event_id")
            if h_k:
                consumidos_hist_keys.add(h_k)
            ev_copia["estado_temporal"] = ESTADO_EVENTO_RECORRENTE
            ev_copia["evento_origem_id"] = pareado_hist.get("event_id") or pareado_hist.get("event_key")

            is_mat, motivo = verificar_mudanca_material(ev_copia, pareado_hist)
            ev_copia["mudanca_material"] = is_mat
            ev_copia["motivo_mudanca"] = motivo

            recorrentes.append(ev_copia)

            if is_mat:
                ev_copia["estado_incremental"] = ESTADO_EVENTO_ATUALIZADO
                ev_copia["continuity_cycles"] = 0
                ev_copia["condensado"] = False
                ev_copia["deve_reapresentar"] = True
                atualizados.append(ev_copia)
            elif relevancia >= 50.0:
                prev_cycles = int(pareado_hist.get("continuity_cycles", 0))
                current_cycles = prev_cycles + 1
                ev_copia["continuity_cycles"] = current_cycles
                ev_copia["estado_incremental"] = ESTADO_EVENTO_CONTINUIDADE
                # Após 3 ciclos sem mudança material, marca como condensado para evitar repetição visual integral
                ev_copia["condensado"] = (current_cycles > 3)
                ev_copia["deve_reapresentar"] = not ev_copia["condensado"]
                continuidade.append(ev_copia)
            else:
                ev_copia["estado_incremental"] = ESTADO_EVENTO_SEM_MUDANCA
                ev_copia["continuity_cycles"] = 0
                ev_copia["condensado"] = False
                ev_copia["deve_reapresentar"] = False
                sem_mudanca.append(ev_copia)
        else:
            ev_copia["estado_temporal"] = ESTADO_EVENTO_NOVO
            ev_copia["estado_incremental"] = ESTADO_EVENTO_NOVO
            ev_copia["mudanca_material"] = True
            ev_copia["motivo_mudanca"] = "fato_inedito"
            ev_copia["continuity_cycles"] = 0
            ev_copia["condensado"] = False
            ev_copia["deve_reapresentar"] = True
            novos.append(ev_copia)

    # 3. Históricos Expirados
    expirados: List[Dict[str, Any]] = []
    for h in eventos_historicos:
        h_k = h.get("event_key") or h.get("event_id")
        if h_k and h_k in consumidos_hist_keys:
            continue
        dt_h = _extrair_data_evento(h)
        if dt_h:
            idade_dias = (ref_hoje.date() - dt_h.date()).days
            if idade_dias > EVENT_CURRENT_WINDOW_DAYS:
                h_exp = dict(h)
                h_exp["estado_temporal"] = ESTADO_EVENTO_INATIVO_EXPIRADO
                h_exp["estado_incremental"] = ESTADO_EVENTO_INATIVO_EXPIRADO
                h_exp["idade_dias"] = idade_dias
                expirados.append(h_exp)

    # Ordenação determinística por relevância
    novos.sort(key=lambda x: x.get("score_relevancia_nicho", 0), reverse=True)
    atualizados.sort(key=lambda x: x.get("score_relevancia_nicho", 0), reverse=True)
    continuidade.sort(key=lambda x: x.get("score_relevancia_nicho", 0), reverse=True)

    total_ativos = len(novos) + len(recorrentes)
    taxa_renovacao = round(len(novos) / total_ativos, 4) if total_ativos > 0 else 0.0
    taxa_novidade = round((len(novos) + len(atualizados)) / total_ativos, 4) if total_ativos > 0 else 0.0
    tem_mudanca_material = bool(novos or atualizados)

    if tem_mudanca_material:
        resumo_incremental = f"{len(novos)} evento(s) inédito(s) e {len(atualizados)} atualizado(s) com alteração material."
    elif total_ativos > 0:
        resumo_incremental = f"Sem novidades materiais. {len(continuidade)} evento(s) em continuidade e {len(sem_mudanca)} sem alteração."
    else:
        resumo_incremental = "Nenhum evento ativo monitorado no ciclo."

    return {
        "novos": novos,
        "atualizados": atualizados,
        "continuidade": continuidade,
        "sem_mudanca": sem_mudanca,
        "recorrentes": recorrentes,
        "expirados": expirados,
        "total_ativos": total_ativos,
        "taxa_renovacao": taxa_renovacao,
        "taxa_novidade": taxa_novidade,
        "tem_mudanca_material": tem_mudanca_material,
        "resumo_incremental": resumo_incremental,
    }


def calcular_delta_eventos(
    eventos_atuais: Sequence[Dict[str, Any]],
    eventos_historicos: Sequence[Dict[str, Any]],
    cluster_days: int = EVENT_DATE_CLUSTER_DAYS,
    hoje: Optional[datetime] = None,
    profile: Optional[Dict[str, Any]] = None,
    cadencia_dias: int = 7,
    memoria_entrega: Optional[MemoriaEntrega] = None,
    delivered_to: str = "default",
) -> Dict[str, Any]:
    """
    Classifica deterministicamente os eventos da execução atual em relação ao histórico.
    Preserva 100% de compatibilidade retroativa e adiciona inteligência incremental.
    """
    return analisar_inteligencia_incremental(
        eventos_atuais=eventos_atuais,
        eventos_historicos=eventos_historicos,
        profile=profile,
        cadencia_dias=cadencia_dias,
        cluster_days=cluster_days,
        hoje=hoje,
        memoria_entrega=memoria_entrega,
        delivered_to=delivered_to,
    )
