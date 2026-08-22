# -*- coding: utf-8 -*-
"""
Camada de Renderização HTML — Agente Sniper
Gera o Dashboard Executivo e Inteligência Visual em HTML autônomo com CSS moderno embutido.
"""
from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from domain.models import Fonte
from domain.opportunities import selecionar_oportunidades_executivas


def ref_text(ids: Sequence[int]) -> str:
    """Formata citações forenses de fontes."""
    return " ".join(f"[FONTE {int(x)}]" for x in ids)


def fonte_por_id(fontes: List[Fonte]) -> Dict[int, Fonte]:
    """Mapeia lista de fontes por ID."""
    return {f.id: f for f in fontes}


def html_escape(s: Any) -> str:
    """Sanitiza entidades HTML para renderização segura."""
    return html.escape(str(s or ""))


def rotulo_dimensao(k: str) -> str:
    """Normaliza o rótulo de dimensão para exibição."""
    return k.title().replace("Serviço", "Serviço")


def gerar_html(
    pacote: Dict[str, Any],
    fontes: List[Fonte],
    events: List[Dict[str, Any]],
    ambiente: Dict[str, Any],
    memoria: Dict[str, Any],
    empresa_alvo: Optional[str] = None,
    cidade: Optional[str] = None,
    estado: Optional[str] = None,
    perfil_label: Optional[str] = None,
    app_version: Optional[str] = None,
    data_ref: Optional[datetime] = None,
) -> str:
    """
    Renderiza o dashboard executivo HTML completo do Agente Sniper.
    """
    empresa = empresa_alvo or os.getenv("EMPRESA_ALVO", "CARVALHO SUPERMERCADO")
    cid = cidade if cidade is not None else os.getenv("CIDADE", "TERESINA")
    est = estado if estado is not None else os.getenv("ESTADO", "PI")
    label_perfil = perfil_label or "Varejo alimentar"
    versao = app_version or os.getenv("APP_VERSION", "11.8.0")
    hoje = data_ref or datetime.now()

    fmap = fonte_por_id(fontes)
    sinais = pacote.get("sinais", [])[:8]
    resumo = pacote.get("resumo_executivo", [])[:5]
    dims = ambiente.get("dimensoes", {})
    concorrencia = pacote.get("concorrencia", [])[:8]
    score = ambiente["score"]
    cor_score = "bad" if score >= 70 else "warn" if score >= 45 else "good"

    delta_evt = memoria.get("eventos_delta", {}) if isinstance(memoria, dict) else {}
    n_novos = len(delta_evt.get("novos", []))
    n_rec = len(delta_evt.get("recorrentes", []))
    if n_novos or n_rec:
        resumo_eventos = f"{len(fontes)} evidências · {n_novos} novos · {n_rec} recorrentes"
    else:
        resumo_eventos = f"{len(fontes)} evidências auditáveis · {memoria.get('novas_fontes', 0) if isinstance(memoria, dict) else 0} novas"

    html_out = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Agente Sniper — {html_escape(empresa)}</title>
<style>
:root{{--bg:#f4f6fa;--ink:#17212b;--muted:#667487;--card:#fff;--line:#e4e9ef;--navy:#0b1d33;--blue:#1e5eff;--red:#c62828;--orange:#a86200;--green:#147a45}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}} .wrap{{max-width:1240px;margin:auto;padding:24px}}
.hero{{background:linear-gradient(135deg,#091522,#173c63);color:#fff;border-radius:24px;padding:32px;box-shadow:0 16px 40px rgba(5,20,40,.18)}} .kicker{{font-size:11px;letter-spacing:.16em;text-transform:uppercase;opacity:.74}} h1{{font-size:38px;margin:10px 0 4px}} .sub{{opacity:.86}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:16px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 6px 20px rgba(24,33,43,.05)}} .metric{{font-size:30px;font-weight:850}} .label{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}
.section{{margin-top:28px}} h2{{font-size:21px;margin:0 0 12px}} .lead{{font-size:15px;line-height:1.55}} .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.score{{border-radius:18px;padding:16px;background:#fff;border:1px solid var(--line)}} .scorebar{{height:10px;background:#edf1f5;border-radius:99px;overflow:hidden;margin-top:9px}} .scorefill{{height:100%}} .fillgood{{background:var(--green)}} .fillwarn{{background:#d28a10}} .fillbad{{background:var(--red)}}
.signal{{background:#fff;border:1px solid var(--line);border-left:5px solid var(--blue);border-radius:16px;padding:16px;margin:10px 0}} .risk{{border-left-color:var(--red)}} .opp{{border-left-color:var(--green)}} .move{{border-left-color:#c48a15}} .pill{{display:inline-block;padding:5px 8px;border-radius:999px;background:#eef2f7;font-size:10px;font-weight:800;margin-right:5px}} .muted{{color:var(--muted);font-size:12px}} .action{{font-weight:700;margin-top:8px}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:16px;overflow:hidden}} th,td{{padding:11px;border-bottom:1px solid #edf1f4;text-align:left;font-size:12px}} th{{background:#f7f9fb;color:#506072}} .source{{margin:10px 0;padding:11px;border-bottom:1px solid #edf1f4}} .source a{{color:#1e5eff;text-decoration:none;word-break:break-all}} .footer{{margin-top:28px;color:var(--muted);font-size:11px}}
@media(max-width:900px){{.grid{{grid-template-columns:repeat(2,1fr)}}.grid2{{grid-template-columns:1fr}}}} @media(max-width:560px){{.grid{{grid-template-columns:1fr}}.wrap{{padding:12px}}h1{{font-size:28px}}}}
</style></head><body><div class='wrap'>
<div class='hero'><div class='kicker'>AGENTE SNIPER · RADAR DE INTELIGÊNCIA COMPETITIVA v{versao}</div><h1>{html_escape(empresa)}</h1><div class='sub'>{html_escape(cid)}-{html_escape(est)} · {html_escape(label_perfil)} · {hoje.strftime('%d/%m/%Y %H:%M')}</div></div>
<div class='grid'>
<div class='card'><div class='label'>Pressão competitiva</div><div class='metric'>{('—' if ambiente.get('pressao_competitiva',{}).get('score') is None else str(ambiente['pressao_competitiva']['score'])+'/100')}</div><div>{html_escape(ambiente.get('pressao_competitiva',{}).get('label','NÃO CALCULADO'))}</div></div>
<div class='card'><div class='label'>Vulnerabilidade</div><div class='metric'>{ambiente.get('vulnerabilidade_empresa',{}).get('score',0)}/100</div><div>{html_escape(ambiente.get('vulnerabilidade_empresa',{}).get('label','BAIXA'))}</div></div>
<div class='card'><div class='label'>Momentum do mercado</div><div class='metric'>{ambiente.get('momentum_mercado',0)}/100</div><div>movimentos recentes datados</div></div>
<div class='card'><div class='label'>Eventos canônicos</div><div class='metric'>{len(events)}</div><div>{resumo_eventos}</div></div></div>
<div class='section'><h2>Decisão em 15 minutos</h2><div class='grid2'><div class='card lead'>{''.join('<p>'+html_escape(x)+'</p>' for x in resumo)}</div>
<div class='score'><div class='label'>Cobertura do radar</div><div class='metric'>{int(ambiente.get('cobertura',0)*100)}%</div><div class='muted'>quanto das dimensões tem evidência suficiente para influenciar o índice</div><div class='scorebar'><div class='scorefill fill{cor_score}' style='width:{int(ambiente.get('cobertura',0)*100)}%'></div></div></div></div></div>
<div class='section'><h2>Onde está a pressão</h2><div class='card lead'><b>Leitura dos índices:</b> pressão competitiva mede movimentos externos; vulnerabilidade mede sinais de risco da empresa monitorada; momentum mede velocidade de movimentos recentes. Eles não são equivalentes.</div><div class='grid2'>"""
    for k, d in sorted(dims.items(), key=lambda kv: kv[1].get("score", 0), reverse=True):
        s = d.get("score", 0)
        cl = "bad" if s >= 70 else "warn" if s >= 45 else "good"
        html_out += f"<div class='score'><div class='label'>{html_escape(rotulo_dimensao(k))}</div><div class='metric'>{s}/100</div><div class='muted'>{d.get('eventos',0)} eventos · {d.get('evidencias',0)} evidências · {d.get('eventos_correlacionados',0)} corroborados</div><div class='scorebar'><div class='scorefill fill{cl}' style='width:{s}%'></div></div></div>"
    html_out += "</div></div>"
    cp = pacote.get("comparacao_precos", {})
    if cp.get("enabled"):
        html_out += "<div class='section'><h2>Comparador de preços e promoções</h2>"
        html_out += "<div class='card lead'><b>Status:</b> " + html_escape(str(cp.get("status", ""))) + " · <b>Produtos-base:</b> " + str(cp.get("produtos_alvo", 0)) + " · <b>Comparáveis:</b> " + str(cp.get("comparaveis", 0)) + "</div>"
        html_out += "<div class='grid2'>"
        for x in cp.get("maiores_gaps", [])[:6]:
            dp = x.get("dif_percent")
            sinal = "concorrente mais barato" if dp is not None and dp < 0 else "alvo mais barato" if dp is not None and dp > 0 else "sem diferença"
            html_out += f"<div class='score'><div class='label'>{html_escape(x.get('produto_alvo',''))}</div><div class='metric'>{'—' if dp is None else f'{dp:+.1f}%'} </div><div>{html_escape(sinal)}</div><div class='muted'>{html_escape(x.get('concorrente',''))} · match {int(float(x.get('similaridade',0))*100)}% · {html_escape(x.get('location_note',''))}</div></div>"
        html_out += "</div><div class='card lead'><b>Promoções:</b> alvo " + str(cp.get("promocoes_alvo", 0)) + " · concorrentes " + str(cp.get("promocoes_concorrentes", 0)) + "</div></div>"
        html_out += "<div class='section'><h3>Guerra de preços — histórico</h3>"
        html_out += "<div class='card lead'><b>Snapshots:</b> " + str(cp.get("snapshots_observados", 0)) + " · <b>Mudanças desde a última execução:</b> " + str(len(cp.get("historico", {}).get("mudancas", []))) + "</div>"
        if cp.get("guerra_de_precos"):
            html_out += "<table><thead><tr><th>Concorrente</th><th>Comparáveis</th><th>Concorrente mais barato</th><th>Alvo mais barato</th><th>Diferença média</th></tr></thead><tbody>"
            for g in cp.get("guerra_de_precos", [])[:10]:
                html_out += f"<tr><td>{html_escape(g.get('concorrente'))}</td><td>{g.get('comparaveis',0)}</td><td>{g.get('concorrente_mais_barato',0)}</td><td>{g.get('alvo_mais_barato',0)}</td><td>{g.get('dif_media_percent',0)}%</td></tr>"
            html_out += "</tbody></table>"
        for ch in cp.get("historico", {}).get("mudancas", [])[:12]:
            sinal = "subiu" if float(ch.get("change_pct") or 0) > 0 else "caiu"
            html_out += f"<div class='source'><b>{html_escape(ch.get('entity'))}</b> — {html_escape(ch.get('product_name'))}: {sinal} {abs(float(ch.get('change_pct') or 0)):.1f}% · R$ {float(ch.get('previous_price') or 0):.2f} → R$ {float(ch.get('current_price') or 0):.2f}</div>"
        series_hist = cp.get("series_temporais", {})
        if series_hist:
            html_out += "<h4>Séries Temporais e Tendências de Preços</h4>"
            html_out += "<table><thead><tr><th>Produto</th><th>Entidade</th><th>Atual</th><th>Δ7d</th><th>Δ15d</th><th>Δ30d</th><th>Volatilidade</th><th>Tendência</th></tr></thead><tbody>"
            for k_s, s in list(series_hist.items())[:12]:
                d7 = f"{s['deltas_janela'][7]:+.1f}%" if s.get('deltas_janela',{}).get(7) is not None else "—"
                d15 = f"{s['deltas_janela'][15]:+.1f}%" if s.get('deltas_janela',{}).get(15) is not None else "—"
                d30 = f"{s['deltas_janela'][30]:+.1f}%" if s.get('deltas_janela',{}).get(30) is not None else "—"
                tend = s.get('tendencia', 'INSUFICIENTE')
                cor_tend = "var(--green)" if tend=="QUEDA" else "var(--red)" if tend=="ALTA" else "var(--ink)"
                p_nome = html_escape(s.get('product_name') or s.get('product_key') or k_s)
                html_out += f"<tr><td><b>{p_nome}</b></td><td>{html_escape(s.get('entity',''))}</td><td>R$ {s.get('preco_atual',0.0):.2f}</td><td>{d7}</td><td>{d15}</td><td>{d30}</td><td>{s.get('volatilidade',0.0):.2f}</td><td style='color:{cor_tend};font-weight:700'>{tend}</td></tr>"
            html_out += "</tbody></table>"
        html_out += "</div>"
    opps = pacote.get("oportunidades", [])
    opps_deliv = selecionar_oportunidades_executivas(opps, limite=8)
    html_out += "<div class='section'><h2>Inteligência Acionável & Oportunidades</h2>"
    html_out += "<div class='card lead' style='background:#fcfdfe;border-left:4px solid var(--muted);margin-bottom:12px;font-size:12px;color:var(--muted)'><b>Salvaguarda de Escopo:</b> A inteligência analítica e as ações recomendadas têm caráter consultivo para decisão estratégica humana. Eventuais soluções ou projetos adicionais identificados não integram automaticamente o escopo contratado de inteligência competitiva e demandam escopo e contratação específicos.</div>"
    if opps_deliv:
        html_out += "<div class='grid2'>"
        for o in opps_deliv[:8]:
            cat = html_escape(o.get("category", "OPORTUNIDADE"))
            act_type = html_escape(o.get("action_type", "").replace("_", " "))
            title = html_escape(o.get("title", ""))
            fact = html_escape(o.get("underlying_fact", ""))
            impact = html_escape(o.get("contextual_impact", ""))
            action = html_escape(o.get("recommended_action", ""))
            target = html_escape(o.get("target_entity", ""))
            ev_conf = int(float(o.get("evidence_confidence", 0)) * 100)
            opp_conf = int(float(o.get("opportunity_confidence", 0)) * 100)
            rel_score = float(o.get("relevance_score", 0))
            refs = [x for x in o.get("evidence_ids", []) if x in fmap]
            cit = html_escape(ref_text(refs))
            gov = o.get("governance", {})
            gov_badge = "<span class='pill' style='background:#e8f5e9;color:#1b5e20'>Escopo Contratado</span>" if gov.get("in_contracted_scope") else "<span class='pill' style='background:#fff3e0;color:#e65100'>Decisão Consultiva</span>"
            sol_type_badge = ""
            if gov.get("solution_type") and gov.get("solution_type") != "OUTRO":
                sol_type_badge = f"<span class='pill' style='background:#f3e5f5;color:#4a148c'>{html_escape(gov.get('solution_type', '').replace('_', ' '))}</span>"
            prio_badge = f"<span class='pill' style='background:#e8eaf6;color:#1a237e'>Prioridade: {int(o.get('intelligence_priority', 0))}/100</span>" if o.get("intelligence_priority") else ""
            trend_val = o.get("temporal_trend", "INEDITO")
            trend_map = {
                "INEDITO": ("#e0f2fe", "#0369a1"),
                "ACELERANDO": ("#fef3c7", "#b45309"),
                "ESTABILIZADO": ("#f1f5f9", "#475569"),
                "MARCO_CONCLUIDO": ("#dcfce7", "#15803d"),
                "REATIVADO": ("#fae8ff", "#86198f"),
            }
            bg_t, fg_t = trend_map.get(trend_val, ("#f1f5f9", "#475569"))
            trend_badge = f"<span class='pill' style='background:{bg_t};color:{fg_t}'>{html_escape(trend_val.replace('_', ' '))}</span>"
            contact_box = ""
            if o.get("contact_suggestion"):
                contact_box = f"<div style='margin-top:10px;padding:10px;background:#eef6ff;border:1px solid #c8e1ff;border-radius:10px;font-size:12px;color:#0b4280'><b>Sugestão de Contato:</b> {html_escape(o['contact_suggestion'])}</div>"
            det_change = ""
            if o.get("detected_change") and o.get("detected_change") != "sem_mudanca_material":
                det_change = f"<div style='font-size:11px;color:#a86200;font-weight:700;margin-top:4px'>Desdobramento: {html_escape(o['detected_change'])}</div>"
            need_box = ""
            if o.get("identified_need"):
                need_box = f"<div style='font-size:12px;margin:4px 0'><b>Necessidade/Lacuna:</b> {html_escape(o['identified_need'])}</div>"
            rationale_box = ""
            if o.get("need_rationale"):
                rationale_box = f"<div style='font-size:11px;color:var(--muted);margin-bottom:4px'><b>Fundamentação:</b> {html_escape(o['need_rationale'])}</div>"
            html_out += f"<div class='card' style='border-left:5px solid var(--blue)'><div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px'><span class='pill'>{cat}</span><span class='pill' style='background:#e3f2fd;color:#0d47a1'>{act_type}</span>{trend_badge}{prio_badge}<span class='pill' style='background:#f1f8e9;color:#33691e'>Relevância: {rel_score:.1f}/100</span>{gov_badge}{sol_type_badge}</div><h3 style='margin:4px 0 8px;font-size:16px'>{title}</h3><div style='font-size:12px;color:var(--muted);margin-bottom:6px'><b>Fato:</b> {fact}</div>{det_change}<div style='font-size:12px;margin:6px 0'><b>Impacto Estratégico:</b> {impact}</div>{need_box}{rationale_box}<div class='action' style='font-size:13px;color:var(--ink);margin:8px 0'><b>AÇÃO RECOMENDADA:</b> {action}</div><div style='font-size:11px;color:var(--muted);margin-top:6px'>Confiança do Fato: {ev_conf}% · Confiança da Hipótese: {opp_conf}% · Entidade: {target} · {cit}</div>{contact_box}</div>"
        html_out += "</div>"
    else:
        html_out += "<div class='card'><p class='muted'>Nenhuma oportunidade acionável nova ou atualizada identificada neste ciclo.</p></div>"
    html_out += "</div>"
    html_out += "<div class='section'><h2>Sinais Prioritários de Observação & Decisão</h2>"
    html_out += "<div class='card lead' style='background:#fcfdfe;border-left:4px solid var(--muted);margin-bottom:12px;font-size:12px;color:var(--muted)'><b>Salvaguarda de Sinais:</b> Sinais indicam prioridade de monitoramento analítico para deliberação estratégica do cliente. Ações sugeridas têm caráter consultivo e não representam ordens operacionais nem obrigação de execução técnica.</div>"
    for s in sinais:
        typ = str(s.get('tipo', 'MOVIMENTO')).upper()
        cls = 'risk' if typ == 'RISCO' else 'opp' if typ == 'OPORTUNIDADE' else 'move'
        urg = html_escape(str(s.get('urgencia', '')).upper())
        imp = html_escape(str(s.get('impacto', '')).upper())
        refs = [x for x in s.get('evidence_ids', []) if x in fmap]
        html_out += f"<div class='signal {cls}'><span class='pill'>{html_escape(typ)}</span><span class='pill'>Impacto: {imp}</span><span class='pill'>Urgência de Monitoramento: {urg}</span><h3>{html_escape(s.get('titulo'))}</h3><div class='muted'>Janela de avaliação: {html_escape(s.get('limite'))} · Confiança factual: {int(float(s.get('confianca',0))*100)}%</div><p><b>Racional:</b> {html_escape(s.get('racional'))}</p><p class='action'>AÇÃO SUGERIDA PARA AVALIAÇÃO: {html_escape(s.get('acao'))}</p><div class='muted'>Evidência: {html_escape(ref_text(refs))}</div></div>"
    html_out += "</div>"
    html_out += "<div class='section'><h2>Radar de concorrência</h2>"
    if concorrencia:
        html_out += "<table><thead><tr><th>Concorrente</th><th>Movimento</th><th>Confiança</th><th>Evidência</th></tr></thead><tbody>"
        for c in concorrencia:
            html_out += f"<tr><td>{html_escape(c.get('nome'))}</td><td>{html_escape(c.get('movimento'))}</td><td>{int(float(c.get('confianca',0))*100)}%</td><td>{html_escape(ref_text(c.get('evidence_ids',[])))}</td></tr>"
        html_out += "</tbody></table>"
    else:
        html_out += "<div class='card'><b>Ainda não há concorrentes suficientemente identificados nesta execução.</b><p class='muted'>Configure CONCORRENTES ou aumente a coleta específica de mercado antes de tomar decisões ofensivas.</p></div>"
    html_out += "</div><div class='section'><h2>Plano 30 / 60 / 90 dias</h2><div class='grid2'>"
    for label, arr in [("30 dias", pacote.get('prioridades_30', [])), ("60 dias", pacote.get('prioridades_60', [])), ("90 dias", pacote.get('prioridades_90', []))]:
        html_out += f"<div class='card'><div class='label'>{label}</div>{''.join('<p>• '+html_escape(x)+'</p>' for x in arr[:5])}</div>"
    html_out += "</div></div><div class='section'><h2>Lacunas de informação</h2><div class='card'>" + ''.join(f"<p>• {html_escape(x)}</p>" for x in pacote.get('lacunas', [])) + "</div></div>"
    html_out += "<div class='section'><h2>Eventos mais relevantes</h2>"
    for e in events[:15]:
        est = e.get("estado_temporal")
        badge = f"<span class='pill'>{html_escape(est)}</span> " if est else ""
        html_out += f"<div class='source'>{badge}<b>{html_escape(e['kind'])}</b> — {html_escape(e['title'])}<div class='muted'>{e['importance']}/100 · confiança {int(float(e.get('confidence',0))*100)}% · {e.get('independent_source_count',1)} fonte(s) independente(s) · {html_escape(e.get('date') or 'data não identificada')} · {html_escape(ref_text(e.get('evidence_ids',[])))}</div></div>"
    html_out += "</div><div class='section'><h2>Evidências auditáveis</h2><table><thead><tr><th>ID</th><th>Escopo</th><th>Data</th><th>Fonte</th><th>Título</th><th>Score</th></tr></thead><tbody>"
    for f in fontes[:80]:
        html_out += f"<tr><td>{f.id}</td><td>{html_escape(f.escopo)}</td><td>{html_escape(f.data_publicacao or 'não identificada')}</td><td>{html_escape(f.dominio)}</td><td>{html_escape(f.titulo)}</td><td>{f.score:.1f}</td></tr>"
    html_out += f"</tbody></table></div><div class='footer'>Agente Sniper v{versao}. Fatos devem ser interpretados junto das evidências referenciadas. Um sinal não é prova de causalidade financeira.</div></div></body></html>"
    return html_out
