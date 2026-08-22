# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Inteligência Acionável, Priorização, Consolidação, Need Gate e Governança.
Camada pura de domínio downstream para transformar fatos e deltas em hipóteses estratégicas,
recomendações analíticas para decisão humana, priorização executiva unificada,
consolidação temática de redundâncias e salvaguardas contratuais estritas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from domain.models import Fonte
from domain.identity import sha1
from domain.normalizer import score_clamp, normalizar
from domain.deltas import (
    MemoriaEntrega,
    calcular_relevancia_nicho,
    DEFAULT_DIMENSION_WEIGHTS,
    ESTADO_EVENTO_NOVO,
    ESTADO_EVENTO_ATUALIZADO,
    ESTADO_EVENTO_CONTINUIDADE,
    ESTADO_EVENTO_SEM_MUDANCA,
    TEMPORAL_TREND_INEDITO,
    TEMPORAL_TREND_ACELERANDO,
    TEMPORAL_TREND_ESTABILIZADO,
    TEMPORAL_TREND_MARCO_CONCLUIDO,
    TEMPORAL_TREND_REATIVADO,
    determinar_tendencia_temporal,
)

# Estados e Categorias Declarativas de Governança de Escopo
SCOPE_CONTRACTED_INTELLIGENCE: str = "CONTRACTED_INTELLIGENCE"
SCOPE_ANALYTICAL_RECOMMENDATION: str = "ANALYTICAL_RECOMMENDATION"
SCOPE_POSSIBLE_SOLUTION: str = "POSSIBLE_SOLUTION"
SCOPE_OPTIONAL_EXPANSION_SERVICE: str = "OPTIONAL_EXPANSION_SERVICE"

# Subtipos Declarativos de Solução Potencial
SOLUTION_SOFTWARE_CUSTOMIZADO: str = "SOFTWARE_CUSTOMIZADO"
SOLUTION_PROCESSO_INTERNO: str = "PROCESSO_INTERNO"
SOLUTION_CONSULTORIA_ADICIONAL: str = "CONSULTORIA_ADICIONAL"
SOLUTION_INFRAESTRUTURA_INTEGRACAO: str = "INFRAESTRUTURA_OU_INTEGRACAO"
SOLUTION_OUTRO: str = "OUTRO"

# Dimensões e Tipologias Adequadas para Oportunidade e Contato
OPPORTUNITY_ACTION_TYPES: Dict[str, str] = {
    "EXPANSÃO": "EXPANSAO_COMERCIAL",
    "PARCERIA": "PARCERIA_ESTRATEGICA",
    "PRODUTO/SERVIÇO": "PROPOSTA_SERVICO",
    "DIGITAL": "TRANSFORMACAO_DIGITAL",
    "REGULAÇÃO": "COMPLIANCE_REGULATORIO",
    "PESSOAS": "ATRACAO_TALENTOS",
    "PREÇO": "REACAO_COMPETITIVA",
    "MARKETING": "POSICIONAMENTO_MERCADO",
    "REPUTAÇÃO": "MONITORAMENTO_REPUTACIONAL",
    "ATENDIMENTO": "MELHORIA_OPERACIONAL",
}

# Dimensões inadequadas para abordagem comercial direta
CONTACT_UNSUITABLE_KINDS: Set[str] = {"REPUTAÇÃO", "ATENDIMENTO"}


@dataclass(frozen=True)
class ScopeGovernance:
    """
    Metadados imutáveis de governança de escopo e salvaguarda contratual.
    Garante a fronteira formal entre inteligência entregue e eventuais projetos adicionais.
    """
    scope_type: str = SCOPE_ANALYTICAL_RECOMMENDATION
    solution_type: Optional[str] = None
    in_contracted_scope: bool = False
    requires_separate_agreement: bool = True
    human_validation_required: bool = True
    execution_nature: str = "CLIENT_DECISION"
    disclaimer: str = "Recomendação analítica para avaliação e decisão estratégica do cliente."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope_type": self.scope_type,
            "solution_type": self.solution_type,
            "in_contracted_scope": self.in_contracted_scope,
            "requires_separate_agreement": self.requires_separate_agreement,
            "human_validation_required": self.human_validation_required,
            "execution_nature": self.execution_nature,
            "disclaimer": self.disclaimer,
        }


@dataclass(frozen=True)
class ActionableOpportunity:
    """
    Representação estruturada, determinística e imutável de uma oportunidade acionável.
    """
    id: str
    event_id: str
    category: str
    action_type: str
    title: str
    underlying_fact: str
    detected_change: str
    contextual_impact: str
    recommended_action: str
    contact_suggestion: Optional[str]
    target_entity: str
    evidence_ids: Tuple[int, ...]
    evidence_confidence: float
    opportunity_confidence: float
    relevance_score: float
    should_deliver: bool
    delivery_fingerprint: str
    identified_need: Optional[str] = None
    need_rationale: Optional[str] = None
    intelligence_priority: float = 0.0
    temporal_trend: str = TEMPORAL_TREND_INEDITO
    governance: ScopeGovernance = field(default_factory=ScopeGovernance)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "category": self.category,
            "action_type": self.action_type,
            "title": self.title,
            "underlying_fact": self.underlying_fact,
            "detected_change": self.detected_change,
            "contextual_impact": self.contextual_impact,
            "recommended_action": self.recommended_action,
            "contact_suggestion": self.contact_suggestion,
            "target_entity": self.target_entity,
            "evidence_ids": list(self.evidence_ids),
            "evidence_confidence": round(self.evidence_confidence, 4),
            "opportunity_confidence": round(self.opportunity_confidence, 4),
            "relevance_score": round(self.relevance_score, 2),
            "should_deliver": self.should_deliver,
            "delivery_fingerprint": self.delivery_fingerprint,
            "identified_need": self.identified_need,
            "need_rationale": self.need_rationale,
            "intelligence_priority": round(self.intelligence_priority, 2),
            "temporal_trend": self.temporal_trend,
            "governance": self.governance.to_dict(),
            "metadata": self.metadata,
        }


def calcular_prioridade_inteligencia(
    relevance_score: float,
    opportunity_confidence: float,
    is_material: bool = False,
    independent_sources: int = 1,
) -> float:
    """
    Calcula determinística e monotonicamente o índice de prioridade de inteligência [0.0 a 100.0].
    Pondera relevância do nicho, confiança da hipótese, materialidade recente e corroboração de fontes.
    Garante monotonicidade estrita: aumentos em relevância, confiança, materialidade ou fontes nunca reduzem a prioridade.
    """
    rel_clamped = min(100.0, max(0.0, float(relevance_score)))
    conf_clamped = min(1.0, max(0.0, float(opportunity_confidence)))
    sources_clamped = max(1, int(independent_sources))

    # Componentes aditivos rigorosamente crescentes
    rel_part = rel_clamped * 0.45                         # Max: 45.0
    conf_part = conf_clamped * 25.0                       # Max: 25.0
    mat_part = 20.0 if bool(is_material) else 0.0         # Max: 20.0
    src_part = min(10.0, max(0.0, (sources_clamped - 1) * 5.0))  # 1 src: 0.0, 2 src: 5.0, 3+ src: 10.0

    raw_priority = rel_part + conf_part + mat_part + src_part
    return round(min(100.0, max(0.0, raw_priority)), 2)


def formular_necessidade_e_fundamentacao(
    kind: str,
    title: str,
    target_entity: str,
    profile_label: str,
    independent_sources: int,
    relevance_score: float,
    detected_change: str = "",
) -> Tuple[str, str]:
    """
    Formula determinística e causalmente a necessidade/lacuna identificada e sua justificativa.
    Retorna (identified_need, need_rationale).
    """
    ent = target_entity.strip() or "o mercado"

    if kind == "EXPANSÃO":
        need = f"Acompanhamento sistemático da expansão territorial e densidade de concorrência na área de atuação de {ent}."
        rationale = f"Inferido a partir de movimento de expansão sustentado por {independent_sources} fonte(s) e relevância {relevance_score:.1f}/100 em {profile_label}."
    elif kind == "PARCERIA":
        need = f"Mapeamento de alianças estratégicas e novas rotas de distribuição desenvolvidas por {ent}."
        rationale = f"Acordo ou aliança comercial formalizada com potencial de impacto em canais de {profile_label}."
    elif kind == "PRODUTO/SERVIÇO":
        need = f"Auditoria contínua de mix, lançamentos e diferenciais competitivos ofertados por {ent}."
        rationale = f"Lançamento de produto/serviço no segmento de {profile_label} com necessidade de monitoramento de atributos e proposta de valor."
    elif kind == "DIGITAL":
        need = f"Avaliação de atrito e competitividade em canais digitais, e-commerce ou plataformas em relação a {ent}."
        rationale = f"Inovação digital observada no setor com relevância {relevance_score:.1f}/100."
    elif kind == "REGULAÇÃO":
        need = f"Auditoria de conformidade técnica e adequação operacional aos atos normativos do segmento de {profile_label}."
        rationale = f"Ato normativo ou fiscalização formal com aplicabilidade operacional ao segmento."
    elif kind == "PESSOAS":
        need = f"Monitoramento de movimentação de talentos-chave e políticas de retenção frente ao crescimento de {ent}."
        rationale = f"Abertura de vagas e contratações estratégicas indicando direcionamento de mercado."
    elif kind == "PREÇO":
        need = f"Acompanhamento da volatilidade e sensibilidade promocional em itens concorrentes de {ent}."
        rationale = f"Movimentação de preços e pressão promocional verificada em dados observáveis."
    elif kind == "MARKETING":
        need = f"Aferição do posicionamento e resposta do público às campanhas ativas de {ent}."
        rationale = f"Campanha publicitária/institucional com exposição no segmento de {profile_label}."
    elif kind == "REPUTAÇÃO":
        need = f"Prevenção e auditoria preventiva de vulnerabilidades de imagem e queixas de consumidores correlatas a {ent}."
        rationale = f"Registros de atrito ou queixas observadas no mercado com necessidade de prevenção operacional."
    elif kind == "ATENDIMENTO":
        need = f"Reforço de SLAs de suporte e mitigação de gargalos de atendimento ao cliente."
        rationale = f"Relatos de qualidade e fricção de atendimento observados no segmento."
    else:
        need = f"Monitoramento analítico de desdobramentos de mercado envolvendo {ent}."
        rationale = f"Movimento de mercado relevante registrado para {ent}."

    if detected_change and detected_change != "sem_mudanca_material":
        rationale += f" [Evolução material recente: {detected_change}]."

    return need, rationale


def avaliar_need_gate(
    kind: str,
    action_type: str,
    evidence_confidence: float,
    independent_sources: int,
    relevance_score: float,
    is_material_change: bool,
    target_entity: str,
    contract_config: Optional[Dict[str, Any]] = None,
) -> ScopeGovernance:
    """
    Need Gate Puro e Determinístico: Avalia se existe sustentação probatória,
    relevância e coerência causal para promover uma oportunidade a POSSIBLE_SOLUTION.
    Se não houver sustentação probatória, rebaixa para ANALYTICAL_RECOMMENDATION (solution_type=None).
    """
    # 1. Se houver configuração contratual explícita
    if contract_config and isinstance(contract_config, dict):
        contracted_services = set(contract_config.get("contracted_services") or [])
        if action_type in contracted_services:
            return ScopeGovernance(
                scope_type=SCOPE_CONTRACTED_INTELLIGENCE,
                solution_type=None,
                in_contracted_scope=True,
                requires_separate_agreement=False,
                human_validation_required=True,
                execution_nature="CONTRACTED_EXECUTION",
                disclaimer="Item integrado ao escopo contratual ativo do cliente.",
            )

    # 2. Guardrails Probatórios e de Relevância do Need Gate
    ent = target_entity.strip().lower()
    ent_invalida = not ent or ent in {"mercado", "concorrentes", "setor", "desconhecido"}

    suficiencia_probatoria = (
        evidence_confidence >= 0.70
        and independent_sources >= 2
        and relevance_score >= 60.0
        and not ent_invalida
        and (is_material_change or independent_sources >= 3 or relevance_score >= 75.0)
    )

    # 3. Dimensões elegíveis para promoção a POSSIBLE_SOLUTION
    if suficiencia_probatoria and action_type in {"TRANSFORMACAO_DIGITAL", "EXPANSAO_COMERCIAL", "PROPOSTA_SERVICO", "PARCERIA_ESTRATEGICA"}:
        if action_type == "TRANSFORMACAO_DIGITAL":
            sol_type = SOLUTION_SOFTWARE_CUSTOMIZADO
        elif action_type == "EXPANSAO_COMERCIAL":
            sol_type = SOLUTION_INFRAESTRUTURA_INTEGRACAO
        else:
            sol_type = SOLUTION_CONSULTORIA_ADICIONAL

        return ScopeGovernance(
            scope_type=SCOPE_POSSIBLE_SOLUTION,
            solution_type=sol_type,
            in_contracted_scope=False,
            requires_separate_agreement=True,
            human_validation_required=True,
            execution_nature="OPTIONAL_PROJECT",
            disclaimer="Hipótese consultiva para avaliação humana. Não constitui obrigação de execução técnica sem contratação e escopo específicos.",
        )

    # 4. Caso padrão / Rejeitado pelo Need Gate: Permanece recomendação analítica pura
    return ScopeGovernance(
        scope_type=SCOPE_ANALYTICAL_RECOMMENDATION,
        solution_type=None,
        in_contracted_scope=False,
        requires_separate_agreement=True,
        human_validation_required=True,
        execution_nature="CLIENT_DECISION",
        disclaimer="Recomendação analítica para avaliação e decisão estratégica do cliente.",
    )


def determinar_governanca_escopo(
    action_type: str,
    contract_config: Optional[Dict[str, Any]] = None,
    evidence_confidence: float = 0.80,
    independent_sources: int = 2,
    relevance_score: float = 70.0,
    is_material_change: bool = True,
    target_entity: str = "Entidade",
    kind: str = "EXPANSÃO",
) -> ScopeGovernance:
    """
    Função de conveniência/compatibilidade que delega ao Need Gate.
    """
    return avaliar_need_gate(
        kind=kind,
        action_type=action_type,
        evidence_confidence=evidence_confidence,
        independent_sources=independent_sources,
        relevance_score=relevance_score,
        is_material_change=is_material_change,
        target_entity=target_entity,
        contract_config=contract_config,
    )


def calcular_confianca_oportunidade(
    evidence_confidence: float,
    kind: str,
    target_entity: str,
    independent_sources: int,
    relevance_weight: float,
    is_material_change: bool = False,
    is_isolated: bool = False,
) -> float:
    """
    Calcula determinística e independentemente a confiança da hipótese comercial.
    Garante que a confiança do fato nunca seja copiada cegamente como confiança da oportunidade.
    """
    base_fact = min(1.0, max(0.0, float(evidence_confidence)))

    # Fator de especificidade da entidade alvo
    ent_norm = target_entity.strip().lower()
    if not ent_norm or ent_norm in {"mercado", "concorrentes", "setor", "desconhecido"}:
        entity_factor = 0.60
    else:
        entity_factor = 1.00

    # Fator de corroboração independente
    corrob_factor = 1.00 if independent_sources >= 2 else (0.75 if is_isolated else 0.85)

    # Fator de novidade material
    material_factor = 1.00 if is_material_change else 0.90

    # Ponderação pela dimensão estratégica
    dim_factor = min(1.0, max(0.50, float(relevance_weight)))

    raw_conf = base_fact * entity_factor * corrob_factor * material_factor * dim_factor
    return round(min(1.0, max(0.0, raw_conf)), 4)


def formular_recomendacao_contextual(
    kind: str,
    title: str,
    target_entity: str,
    profile_label: str,
    detected_change: str = "",
) -> Tuple[str, str]:
    """
    Produz a interpretação contextual e a ação recomendada específica para decisão humana.
    Retorna (contextual_impact, recommended_action).
    """
    ent = target_entity.strip() or "o mercado"

    if kind == "EXPANSÃO":
        impacto = f"Movimento de expansão observável de {ent}, afetando a dinâmica de captação e alcance em {profile_label}."
        acao = f"Mapear a cobertura e densidade de clientes na região de atuação de {ent} e avaliar reforço de presença ou proposta de valor concorrente."
    elif kind == "PARCERIA":
        impacto = f"Aliança estratégica ou acordo comercial formalizado por {ent} com impacto em distribuição ou canais."
        acao = f"Analisar eventuais lacunas de canal decorrentes da parceria de {ent} e avaliar iniciativas conjuntas com outros players do ecossistema."
    elif kind == "PRODUTO/SERVIÇO":
        impacto = f"Novidade no mix, oferta ou lançamento anunciado por {ent} no segmento de {profile_label}."
        acao = f"Comparar atributos, diferenciais e precificação do novo produto/serviço de {ent} antes de ajustar o catálogo próprio."
    elif kind == "REGULAÇÃO":
        impacto = f"Ato normativo, fiscalização ou exigência regulatória aplicável ao segmento de {profile_label} envolvendo {ent}."
        acao = f"Validar o teor da norma/decisão diretamente em canal oficial e auditar conformidade interna nos processos correspondentes."
    elif kind == "PESSOAS":
        impacto = f"Movimentação de profissionais, contratações ou vagas estratégicas abertas por {ent}."
        acao = f"Monitorar o direcionamento de crescimento de {ent} indicado pelas contratações e fortalecer políticas de retenção de talentos-chave."
    elif kind == "PREÇO":
        impacto = f"Alteração ou posicionamento promocional relevante de {ent} em itens do setor."
        acao = f"Verificar a elasticidade e aderência dos itens sensíveis antes de qualquer decisão de repasse ou desconto defensivo."
    elif kind == "DIGITAL":
        impacto = f"Inovação em canais digitais, aplicativos ou e-commerce implementada por {ent}."
        acao = f"Avaliar a usabilidade e atrito na jornada digital comparada com a solução adotada por {ent}."
    elif kind == "MARKETING":
        impacto = f"Campanha institucional ou publicitária de {ent} direcionada ao público de {profile_label}."
        acao = f"Acompanhar a resposta de engajamento do público à campanha de {ent} e afinar mensagens de posicionamento."
    elif kind == "REPUTAÇÃO":
        impacto = f"Exposição reputacional ou registros de queixas de consumidores envolvendo {ent}."
        acao = f"Auditar pontos de atrito similares na operação interna para prevenir vulnerabilidades de reputação correlatas."
    elif kind == "ATENDIMENTO":
        impacto = f"Gargalos ou relatos de qualidade de atendimento observados em {ent}."
        acao = f"Reforçar SLAs de suporte e atendimento ao cliente nos canais de maior fricção."
    else:
        impacto = f"Movimento de mercado relevante registrado para {ent}."
        acao = f"Investigar a evolução factual do evento com evidências adicionais antes de qualquer deliberação."

    if detected_change and detected_change != "sem_mudanca_material":
        impacto += f" [Evolução material recente: {detected_change}]."

    return impacto, acao


def formular_sugestao_contato(
    kind: str,
    target_entity: str,
    action_type: str,
    evidence_confidence: float,
    opportunity_confidence: float,
    relevance_score: float,
    motivo_contextual: str,
) -> Optional[str]:
    """
    Aplica guardrails estritos para gerar exclusivamente uma sugestão informativa de contato humano.
    Retorna None se qualquer critério de segurança, reputação ou confiança não for atendido.
    """
    # Guardrail 1: Proibição estrita em crises reputacionais, acusações ou processos penais
    if kind in CONTACT_UNSUITABLE_KINDS:
        return None

    # Guardrail 2: Entidade deve ser específica e identificável
    ent = target_entity.strip()
    if not ent or ent.lower() in {"mercado", "concorrentes", "setor", "desconhecido"}:
        return None

    # Guardrail 3: Limiares mínimos de confiança e relevância
    if evidence_confidence < 0.70 or opportunity_confidence < 0.70 or relevance_score < 65.0:
        return None

    # Guardrail 4: Formulação estritamente humana e não-autoritária
    if action_type == "PARCERIA_ESTRATEGICA":
        motivo = "exploração de sinergias institucionais e alianças de distribuição"
    elif action_type == "EXPANSAO_COMERCIAL":
        motivo = "mapeamento de fornecimento local e expansão conjunta de canais"
    elif action_type == "PROPOSTA_SERVICO":
        motivo = "apresentação de soluções complementares ao portfólio anunciado"
    elif action_type == "COMPLIANCE_REGULATORIO":
        motivo = "alinhamento institucional sobre os impactos da norma do setor"
    elif action_type == "ATRACAO_TALENTOS":
        motivo = "aproximação institucional com lideranças do segmento"
    else:
        motivo = f"avaliação de oportunidades estratégicas decorrentes de {motivo_contextual}"

    return f"Caso haja interesse comercial, avaliar contato institucional com {ent} referente a {motivo}."


def _as_opp_obj(o: Any) -> ActionableOpportunity:
    if isinstance(o, ActionableOpportunity):
        return o
    if isinstance(o, dict):
        gov = o.get("governance", {})
        if isinstance(gov, dict):
            gov_obj = ScopeGovernance(**{k: v for k, v in gov.items() if k in ScopeGovernance.__annotations__})
        else:
            gov_obj = ScopeGovernance()
        return ActionableOpportunity(
            id=str(o.get("id", "")),
            event_id=str(o.get("event_id", "")),
            category=str(o.get("category", "OPORTUNIDADE")),
            action_type=str(o.get("action_type", "")),
            title=str(o.get("title", "")),
            underlying_fact=str(o.get("underlying_fact", "")),
            detected_change=str(o.get("detected_change", "")),
            contextual_impact=str(o.get("contextual_impact", "")),
            recommended_action=str(o.get("recommended_action", "")),
            contact_suggestion=o.get("contact_suggestion"),
            target_entity=str(o.get("target_entity", "")),
            evidence_ids=tuple(o.get("evidence_ids") or ()),
            evidence_confidence=float(o.get("evidence_confidence") or 0.0),
            opportunity_confidence=float(o.get("opportunity_confidence") or 0.0),
            relevance_score=float(o.get("relevance_score") or 0.0),
            should_deliver=bool(o.get("should_deliver", True)),
            delivery_fingerprint=str(o.get("delivery_fingerprint", "")),
            identified_need=o.get("identified_need"),
            need_rationale=o.get("need_rationale"),
            intelligence_priority=float(o.get("intelligence_priority") or 0.0),
            temporal_trend=str(o.get("temporal_trend") or TEMPORAL_TREND_INEDITO),
            governance=gov_obj,
            metadata=dict(o.get("metadata") or {}),
        )
    return o


def consolidar_oportunidades_tematicas(
    oportunidades: Sequence[Any],
) -> List[Any]:
    """
    Consolida deterministicamente oportunidades redundantes da mesma entidade e mesmo tema/ação.
    Preserva a oportunidade de maior prioridade como base, agregando evidências e combinando sinais materiais.
    """
    if not oportunidades:
        return []

    is_dict_input = isinstance(oportunidades[0], dict)
    opp_objs = [_as_opp_obj(o) for o in oportunidades]

    grupos: Dict[Tuple[str, str, str], List[ActionableOpportunity]] = {}
    ordem_grupos: List[Tuple[str, str, str]] = []

    for opp in opp_objs:
        ent_norm = normalizar(opp.target_entity)
        act_norm = opp.action_type
        need_norm = normalizar(opp.identified_need or "")
        chave = (ent_norm, act_norm, need_norm)
        if chave not in grupos:
            grupos[chave] = []
            ordem_grupos.append(chave)
        grupos[chave].append(opp)

    consolidadas: List[ActionableOpportunity] = []
    for chave in ordem_grupos:
        itens = grupos[chave]
        if len(itens) == 1:
            consolidadas.append(itens[0])
            continue

        itens_ordenados = sorted(itens, key=lambda x: (-x.intelligence_priority, -x.opportunity_confidence, -x.relevance_score, x.id))
        base = itens_ordenados[0]

        todos_ev_ids = tuple(sorted({ev_id for it in itens for ev_id in it.evidence_ids}))
        any_material = any(it.metadata.get("is_material", False) or bool(it.detected_change and it.detected_change != "sem_mudanca_material") for it in itens)

        max_ev_conf = max(it.evidence_confidence for it in itens)
        max_opp_conf = max(it.opportunity_confidence for it in itens)
        max_rel_score = max(it.relevance_score for it in itens)
        total_independent_sources = max(it.metadata.get("independent_sources", len(it.evidence_ids)) for it in itens)

        gov_preferida = base.governance
        for it in itens:
            if it.governance.scope_type == SCOPE_POSSIBLE_SOLUTION:
                gov_preferida = it.governance
                break

        prio_recalc = calcular_prioridade_inteligencia(
            relevance_score=max_rel_score,
            opportunity_confidence=max_opp_conf,
            is_material=any_material,
            independent_sources=total_independent_sources,
        )

        # Determina a tendência temporal consolidada
        if any(it.temporal_trend == TEMPORAL_TREND_MARCO_CONCLUIDO for it in itens):
            trend_cons = TEMPORAL_TREND_MARCO_CONCLUIDO
        elif any(it.temporal_trend == TEMPORAL_TREND_ACELERANDO for it in itens):
            trend_cons = TEMPORAL_TREND_ACELERANDO
        elif any(it.temporal_trend == TEMPORAL_TREND_REATIVADO for it in itens):
            trend_cons = TEMPORAL_TREND_REATIVADO
        elif any(it.temporal_trend == TEMPORAL_TREND_ESTABILIZADO for it in itens):
            trend_cons = TEMPORAL_TREND_ESTABILIZADO
        else:
            trend_cons = base.temporal_trend

        meta_cons = dict(base.metadata)
        meta_cons["consolidated_count"] = len(itens)
        meta_cons["consolidated_event_ids"] = [it.event_id for it in itens]
        meta_cons["is_material"] = any_material
        meta_cons["independent_sources"] = total_independent_sources

        opp_consolidada = ActionableOpportunity(
            id=base.id,
            event_id=base.event_id,
            category=base.category,
            action_type=base.action_type,
            title=base.title,
            underlying_fact=base.underlying_fact,
            detected_change=base.detected_change if base.detected_change else (itens_ordenados[1].detected_change if len(itens_ordenados) > 1 else ""),
            contextual_impact=base.contextual_impact,
            recommended_action=base.recommended_action,
            contact_suggestion=base.contact_suggestion or next((it.contact_suggestion for it in itens if it.contact_suggestion), None),
            target_entity=base.target_entity,
            evidence_ids=todos_ev_ids,
            evidence_confidence=max_ev_conf,
            opportunity_confidence=max_opp_conf,
            relevance_score=max_rel_score,
            should_deliver=any(it.should_deliver for it in itens),
            delivery_fingerprint=base.delivery_fingerprint,
            identified_need=base.identified_need,
            need_rationale=base.need_rationale,
            intelligence_priority=prio_recalc,
            temporal_trend=trend_cons,
            governance=gov_preferida,
            metadata=meta_cons,
        )
        consolidadas.append(opp_consolidada)

    consolidadas.sort(key=lambda x: (-x.intelligence_priority, -x.opportunity_confidence, -x.relevance_score, x.id))
    if is_dict_input:
        return [o.to_dict() for o in consolidadas]
    return consolidadas


def selecionar_oportunidades_executivas(
    oportunidades: Sequence[Any],
    limite: int = 8,
) -> List[Any]:
    """
    Seleciona deterministicamente as oportunidades para o relatório executivo com diversidade de entidades.
    1. Filtra should_deliver == True
    2. Consolida temas repetidos da mesma entidade
    3. Aplica seleção balanceada por diversidade sem ocultar itens altamente materiais
    """
    if not oportunidades:
        return []

    is_dict_input = isinstance(oportunidades[0], dict)
    opp_objs = [_as_opp_obj(o) for o in oportunidades]

    elegiveis = [o for o in opp_objs if o.should_deliver]
    if not elegiveis:
        return []

    consolidadas = consolidar_oportunidades_tematicas(elegiveis)
    if len(consolidadas) <= limite:
        if is_dict_input:
            return [o.to_dict() for o in consolidadas]
        return consolidadas

    selecionadas: List[ActionableOpportunity] = []
    entidades_vistas: Set[str] = set()
    restantes: List[ActionableOpportunity] = []

    # Passo 1: Oportunidade prioritária de cada entidade
    for opp in consolidadas:
        ent_chave = normalizar(opp.target_entity)
        if not ent_chave or ent_chave not in entidades_vistas:
            selecionadas.append(opp)
            if ent_chave:
                entidades_vistas.add(ent_chave)
            if len(selecionadas) >= limite:
                break
        else:
            restantes.append(opp)

    # Passo 2: Se ainda houver vagas, preenche com as melhores das já representadas
    if len(selecionadas) < limite and restantes:
        vagas = limite - len(selecionadas)
        selecionadas.extend(restantes[:vagas])

    # Ordenação final rigorosamente determinística por prioridade
    selecionadas.sort(key=lambda x: (-x.intelligence_priority, -x.opportunity_confidence, -x.relevance_score, x.id))
    if is_dict_input:
        return [o.to_dict() for o in selecionadas]
    return selecionadas


def gerar_oportunidades_acionaveis(
    events: Sequence[Dict[str, Any]],
    fontes: Sequence[Fonte],
    profile: Optional[Dict[str, Any]] = None,
    memoria_entrega: Optional[MemoriaEntrega] = None,
    delivered_to: str = "default",
    contract_config: Optional[Dict[str, Any]] = None,
) -> List[ActionableOpportunity]:
    """
    Gera deterministicamente oportunidades estratégicas acionáveis a partir de eventos consolidados.
    Aplica o Need Gate para filtrar soluções potenciais, formular fundamentação causal e calcular prioridade de inteligência.
    """
    fmap = {f.id: f for f in fontes}
    oportunidades: List[ActionableOpportunity] = []
    profile_label = str(profile.get("label", "empresa")) if isinstance(profile, dict) else "empresa"
    weights = profile.get("relevance_weights") if isinstance(profile, dict) else DEFAULT_DIMENSION_WEIGHTS
    weights = weights or DEFAULT_DIMENSION_WEIGHTS

    for ev in events:
        kind = str(ev.get("kind") or "MOVIMENTO").upper()
        ev_id = str(ev.get("event_id") or ev.get("event_key") or "")
        title = str(ev.get("title") or "")
        target_ent = str(ev.get("entity") or "").strip()

        # 1. Rastreabilidade de evidências válidas
        raw_ids = ev.get("evidence_ids") or []
        valid_ids = tuple(sorted({int(x) for x in raw_ids if str(x).isdigit() and int(x) in fmap}))
        if not valid_ids:
            continue

        evidence_conf = float(ev.get("confidence") or 0.0)
        independent_sources = int(ev.get("independent_source_count", len(valid_ids)))
        is_material = bool(ev.get("mudanca_material", False))
        is_isolated = independent_sources < 2

        # 2. Relevância contextual pelo perfil de nicho
        relevance_score = calcular_relevancia_nicho(ev, profile=profile)
        dim_weight = float(weights.get(kind, 0.70))

        # 3. Cálculo independente da confiança da oportunidade (2 níveis)
        opp_conf = calcular_confianca_oportunidade(
            evidence_confidence=evidence_conf,
            kind=kind,
            target_entity=target_ent,
            independent_sources=independent_sources,
            relevance_weight=dim_weight,
            is_material_change=is_material,
            is_isolated=is_isolated,
        )

        # 4. Política de Supressão: Oportunidades fracas ou irrelevantes são suprimidas
        if opp_conf < 0.25 or relevance_score < 25.0:
            continue

        # 5. Classificação da Ação e Formulação de Recomendações
        action_type = OPPORTUNITY_ACTION_TYPES.get(kind, "INVESTIGACAO_ESTRATEGICA")
        categoria = "OPORTUNIDADE" if kind in {"EXPANSÃO", "PARCERIA", "PRODUTO/SERVIÇO", "DIGITAL"} else ("RISCO" if kind in {"REGULAÇÃO", "REPUTAÇÃO", "ATENDIMENTO"} else "MOVIMENTO")

        detected_change = str(ev.get("motivo_mudanca") or "")
        impacto, acao = formular_recomendacao_contextual(
            kind=kind,
            title=title,
            target_entity=target_ent,
            profile_label=profile_label,
            detected_change=detected_change,
        )

        # 6. Fundamentação Causal da Necessidade / Lacuna
        identified_need, need_rationale = formular_necessidade_e_fundamentacao(
            kind=kind,
            title=title,
            target_entity=target_ent,
            profile_label=profile_label,
            independent_sources=independent_sources,
            relevance_score=relevance_score,
            detected_change=detected_change,
        )

        # 7. Avaliação do Need Gate e Governança de Escopo
        gov = avaliar_need_gate(
            kind=kind,
            action_type=action_type,
            evidence_confidence=evidence_conf,
            independent_sources=independent_sources,
            relevance_score=relevance_score,
            is_material_change=is_material,
            target_entity=target_ent,
            contract_config=contract_config,
        )

        # 8. Cálculo de Prioridade de Inteligência
        prio = calcular_prioridade_inteligencia(
            relevance_score=relevance_score,
            opportunity_confidence=opp_conf,
            is_material=is_material,
            independent_sources=independent_sources,
        )

        # 9. Sugestão de Contato com Guardrails Estritos
        contact_sug = formular_sugestao_contato(
            kind=kind,
            target_entity=target_ent,
            action_type=action_type,
            evidence_confidence=evidence_conf,
            opportunity_confidence=opp_conf,
            relevance_score=relevance_score,
            motivo_contextual=title,
        )

        # 10. Classificação Declarativa de Tendência Temporal
        trend = determinar_tendencia_temporal(
            estado_incremental=ev.get("estado_incremental", ESTADO_EVENTO_NOVO),
            motivo_mudanca=detected_change,
            is_material=is_material,
            entregue_anteriormente=bool(ev.get("entregue_anteriormente", False)),
            continuity_cycles=int(ev.get("continuity_cycles", 0)),
            title=title,
        )

        # 11. Fingerprint Determinístico e Memória de Entrega
        opp_id = f"opp_{sha1(f'{ev_id}|{action_type}|{target_ent}|{normalizar(title)}')[:16]}"
        delivery_fp = sha1(f"{opp_id}|{round(opp_conf, 2)}|{round(relevance_score, 1)}|{action_type}|{gov.scope_type}|{gov.solution_type}")

        should_deliver = True
        if memoria_entrega and memoria_entrega.foi_entregue(ev_id, delivered_to=delivered_to):
            # Se já foi entregue anteriormente e NÃO houve mudança material factual
            if not is_material:
                reg = memoria_entrega.obter_registro(ev_id, delivered_to=delivered_to)
                if reg and reg.fingerprint_entrega and reg.fingerprint_entrega != delivery_fp and reg.metadata.get("evolucao_hipotese"):
                    should_deliver = True
                else:
                    should_deliver = False

        opp = ActionableOpportunity(
            id=opp_id,
            event_id=ev_id,
            category=categoria,
            action_type=action_type,
            title=f"Oportunidade [{kind}]: {title}",
            underlying_fact=title,
            detected_change=detected_change,
            contextual_impact=impacto,
            recommended_action=acao,
            contact_suggestion=contact_sug,
            target_entity=target_ent,
            evidence_ids=valid_ids,
            evidence_confidence=evidence_conf,
            opportunity_confidence=opp_conf,
            relevance_score=relevance_score,
            should_deliver=should_deliver,
            delivery_fingerprint=delivery_fp,
            identified_need=identified_need,
            need_rationale=need_rationale,
            intelligence_priority=prio,
            temporal_trend=trend,
            governance=gov,
            metadata={
                "kind": kind,
                "independent_sources": independent_sources,
                "is_material": is_material,
                "profile_label": profile_label,
            },
        )
        oportunidades.append(opp)

    # Ordenação determinística por prioridade de inteligência
    oportunidades.sort(key=lambda o: (-o.intelligence_priority, -o.opportunity_confidence, -o.relevance_score, o.id))
    return oportunidades
