# -*- coding: utf-8 -*-
"""
Camada de Renderização PDF — Agente Sniper
Gera relatórios executivos em PDF com paginação e formatação executiva.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from domain.models import Fonte
from domain.normalizer import remover_acentos
from reports.html import ref_text

try:
    from fpdf import FPDF, XPos, YPos
except Exception:
    FPDF = None
    XPos = None
    YPos = None

logger = logging.getLogger("agente_sniper")


def gerar_pdf(
    pacote: Dict[str, Any],
    fontes: List[Fonte],
    events: List[Dict[str, Any]],
    ambiente: Dict[str, Any],
    memoria: Dict[str, Any],
    empresa_alvo: Optional[str] = None,
    cidade: Optional[str] = None,
    estado: Optional[str] = None,
    pasta_execucao: Optional[Path] = None,
    run_id: Optional[str] = None,
    data_ref: Optional[datetime] = None,
) -> Optional[str]:
    """
    Gera o PDF executivo do Agente Sniper e retorna o caminho absoluto gravado.
    """
    if not FPDF:
        return None

    empresa = empresa_alvo or os.getenv("EMPRESA_ALVO", "CARVALHO SUPERMERCADO")
    cid = cidade if cidade is not None else os.getenv("CIDADE", "TERESINA")
    est = estado if estado is not None else os.getenv("ESTADO", "PI")
    rid = run_id or os.getenv("RUN_ID", "default")
    hoje = data_ref or datetime.now()
    pasta = pasta_execucao or Path("sniper_resultados")

    try:
        pdf = FPDF()
        pdf.set_auto_page_break(True, 14)
        pdf.add_page()
        pdf.set_fill_color(9, 21, 34)
        pdf.rect(0, 0, 210, 48, "F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_y(9)
        pdf.cell(0, 10, "AGENTE SNIPER", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.set_font("Helvetica", "B", 15)
        pdf.cell(0, 8, remover_acentos(empresa), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, remover_acentos(f"Radar competitivo | {cid}-{est} | {hoje.strftime('%d/%m/%Y %H:%M')}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.set_y(58)
        pdf.set_text_color(20, 30, 40)
        pdf.set_font("Helvetica", "B", 17)
        pp = ambiente.get("pressao_competitiva", {})
        pp_text = "Pressao competitiva: nao calculada" if pp.get("score") is None else f"Pressao competitiva: {pp.get('score')}/100 ({pp.get('label')})"
        pdf.cell(0, 9, remover_acentos(pp_text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, remover_acentos("Este relatório separa evidência, evento, interpretação e decisão. Scores não representam impacto financeiro sem dados internos."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        cp = pacote.get("comparacao_precos", {})
        if cp.get("enabled"):
            pdf.add_page()
            pdf.set_text_color(19, 67, 110)
            pdf.set_font("Helvetica", "B", 15)
            pdf.cell(0, 9, remover_acentos("COMPARADOR DE PREÇOS E PROMOÇÕES"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(25, 35, 45)
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5, remover_acentos(f"Status: {cp.get('status','')} | Produtos-base: {cp.get('produtos_alvo',0)} | Comparáveis: {cp.get('comparaveis',0)}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            for x in cp.get("maiores_gaps", [])[:10]:
                dp = x.get("dif_percent")
                txt = f"{x.get('produto_alvo','')} | {x.get('concorrente','')} | alvo R$ {x.get('alvo_preco','—')} | concorrente R$ {x.get('concorrente_preco','—')} | diferença {('—' if dp is None else f'{dp:+.1f}%')} | match {int(float(x.get('similaridade',0))*100)}%"
                pdf.multi_cell(0, 5, remover_acentos(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(3)
            pdf.multi_cell(0, 5, remover_acentos(f"Promoções detectadas: alvo {cp.get('promocoes_alvo',0)} | concorrentes {cp.get('promocoes_concorrentes',0)}. Preços sem correspondência confiável não entram no ranking."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        for title, content in [("RESUMO EXECUTIVO", pacote.get('resumo_executivo', [])), ("SINAIS DE DECISÃO", pacote.get('sinais', [])), ("RADAR DE DIMENSÕES", []), ("RADAR DE EVENTOS", events[:25]), ("PLANO 30 / 60 / 90 DIAS", None)]:
            pdf.add_page()
            pdf.set_text_color(19, 67, 110)
            pdf.set_font("Helvetica", "B", 15)
            pdf.cell(0, 9, remover_acentos(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(25, 35, 45)
            if title == "RADAR DE DIMENSÕES":
                pdf.set_font("Helvetica", "", 9)
                for k, d in sorted(ambiente.get('dimensoes', {}).items(), key=lambda kv: kv[1].get('score', 0), reverse=True):
                    pdf.multi_cell(0, 5, remover_acentos(f"{k}: {d.get('score',0)}/100 | {d.get('eventos',0)} eventos | {d.get('evidencias',0)} evidencias"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif title == "PLANO 30 / 60 / 90 DIAS":
                pdf.set_font("Helvetica", "", 9)
                for lab, arr in [("30 DIAS", pacote.get('prioridades_30', [])), ("60 DIAS", pacote.get('prioridades_60', [])), ("90 DIAS", pacote.get('prioridades_90', []))]:
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.cell(0, 7, lab, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.set_font("Helvetica", "", 9)
                    for x in arr[:6]:
                        pdf.multi_cell(0, 5, "- " + remover_acentos(x), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.set_font("Helvetica", "", 9)
                if content and title == "SINAIS DE DECISÃO":
                    for s in content[:10]:
                        pdf.set_font("Helvetica", "B", 10)
                        pdf.multi_cell(0, 5, remover_acentos(f"{s.get('tipo')} | {s.get('impacto')} | {s.get('urgencia')} | {s.get('titulo')}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.set_font("Helvetica", "", 9)
                        pdf.multi_cell(0, 5, remover_acentos("Racional: " + str(s.get('racional', ''))), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.multi_cell(0, 5, remover_acentos("Acao: " + str(s.get('acao', ''))), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.set_font("Helvetica", "I", 8)
                        pdf.multi_cell(0, 4, remover_acentos("Evidencia: " + ref_text(s.get('evidence_ids', []))), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.ln(2)
                        pdf.set_font("Helvetica", "", 9)
                elif title == "RADAR DE EVENTOS":
                    for e in content:
                        pdf.multi_cell(0, 4.5, remover_acentos(f"{e['kind']} | {e['importance']}/100 | conf. {int(float(e.get('confidence',0))*100)}% | {e.get('date') or 'sem data'} | {e['title']} | {ref_text(e.get('evidence_ids',[]))}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                else:
                    for x in (content or []):
                        pdf.multi_cell(0, 5, "- " + remover_acentos(x), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.add_page()
        pdf.set_text_color(19, 67, 110)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "ANEXO - EVIDENCIAS AUDITAVEIS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(25, 35, 45)
        for f in fontes:
            pdf.set_font("Helvetica", "B", 8)
            pdf.multi_cell(0, 4.5, remover_acentos(f"[FONTE {f.id}] {f.titulo}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 7)
            pdf.multi_cell(0, 4, remover_acentos(f"{f.url} | Data: {f.data_publicacao or 'nao identificada'} | Escopo: {f.escopo} | Confianca: {f.confianca:.2f}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

        caminho = pasta / f"Sniper_{re.sub(r'[^A-Za-z0-9_-]+', '_', empresa)}_{rid}.pdf"
        pasta.mkdir(parents=True, exist_ok=True)
        pdf.output(str(caminho))
        return str(caminho.resolve())
    except Exception as e:
        logger.error("[PDF] %s", str(e)[:200])
        return None
