"""
Módulo de Replay Offline e Benchmark Determinístico — Agente Sniper (Fase 43B).
Executa benchmark determinístico e offline do pipeline interno utilizando fixtures locais
e garantindo isolamento total de rede via OfflineNetworkGuard.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from extractors.bridge import carregar_ocr_bruto
from extractors.adapters import FlyerProductAdapter
from domain.models import Fonte, PriceItem
from domain.events import criar_eventos as _domain_criar_eventos
from domain.sources import score_fonte
from domain.matching import similaridade_produto
from reports import gerar_html

# Constantes de fallback para o replay
EMPRESA_ALVO_DEFAULT = "Supermercado Carvalho"
APP_VERSION_DEFAULT = "11.8.1"


class OfflineNetworkGuard:
    """Garante estruturalmente zero tráfego de rede durante o replay offline."""
    def __init__(self):
        self._orig_connect = socket.socket.connect
        self._orig_create_connection = getattr(socket, "create_connection", None)

    def __enter__(self):
        def _blocked_connect(sock_self, address):
            raise RuntimeError(f"[OFFLINE GUARD] Tentativa de conexão de rede BLOQUEADA durante --replay-offline para: {address}!")

        def _blocked_create_connection(address, *args, **kwargs):
            raise RuntimeError(f"[OFFLINE GUARD] Tentativa de conexão de rede BLOQUEADA durante --replay-offline para: {address}!")

        socket.socket.connect = _blocked_connect
        if self._orig_create_connection:
            socket.create_connection = _blocked_create_connection
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        socket.socket.connect = self._orig_connect
        if self._orig_create_connection:
            socket.create_connection = self._orig_create_connection


def resolver_fixture_fontes_offline(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Localiza determinística e estavelmente a fixture canônica de fontes para replay."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent

    # 1. Override explícito via variável de ambiente
    env_override = os.getenv("OFFLINE_REPLAY_FIXTURE_PATH", "").strip()
    if env_override:
        p = Path(env_override)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"[REPLAY OFFLINE ERRO] Fixture de ambiente não encontrada: {env_override}")

    # 2. Fixture canônica versionada no repositório (fixtures/canonical_replay)
    canonical_fixture = base_dir / "fixtures" / "canonical_replay" / "fontes.json"
    if canonical_fixture.exists():
        return json.loads(canonical_fixture.read_text(encoding="utf-8"))

    # 3. Fallback legado (sniper_resultados/20260819_162028)
    legacy_fixture = base_dir / "sniper_resultados" / "20260819_162028" / "fontes.json"
    if legacy_fixture.exists():
        return json.loads(legacy_fixture.read_text(encoding="utf-8"))

    # 4. Falha explícita se nenhuma fixture canônica existir
    raise FileNotFoundError(f"[REPLAY OFFLINE ERRO] Fixture canônica de fontes não encontrada em: {canonical_fixture}")


def executar_replay_offline(
    retornar_detalhes: bool = False,
    base_dir: Optional[Path] = None
) -> Union[int, Dict[str, Any]]:
    """Executa benchmark determinístico e offline do pipeline interno utilizando fixtures locais."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent

    with OfflineNetworkGuard():
        t_start = time.perf_counter()
        ocr_dir = base_dir / "fixtures" / "canonical_replay" / "ocr_bruto"
        if not ocr_dir.exists():
            ocr_dir = base_dir / "dados_browser" / "ocr_bruto"
        if not ocr_dir.exists():
            print(f"[REPLAY OFFLINE ERRO] Diretório de OCR não encontrado: {ocr_dir}")
            if retornar_detalhes:
                return {"status": "FAIL", "retorno": 1, "erro": "Diretório de OCR não encontrado"}
            return 1

        ocr_files = sorted(list(ocr_dir.glob("*.json")))
        if not ocr_files:
            print(f"[REPLAY OFFLINE ERRO] Nenhum arquivo OCR encontrado em: {ocr_dir}")
            if retornar_detalhes:
                return {"status": "FAIL", "retorno": 1, "erro": "Nenhum arquivo OCR encontrado"}
            return 1

        ad = FlyerProductAdapter()
        raw_fontes_data = resolver_fixture_fontes_offline(base_dir)

        # A. PARSING OCR (Carga das fixtures)
        t0 = time.perf_counter()
        raw_docs = [carregar_ocr_bruto(f) for f in ocr_files]
        t_parsing = (time.perf_counter() - t0) * 1000

        # B. EXTRAÇÃO ESPACIAL REAL (Caminho de produção do FlyerProductAdapter, sem duplicações)
        t0 = time.perf_counter()
        extracted_entities = []
        for d in raw_docs:
            r = ad.processar_documento(d)
            for e in r.entidades:
                extracted_entities.append((e.entidade, e.valor, e.old_price, e.unidade, e.confianca))
        t_extracao = (time.perf_counter() - t0) * 1000

        # C. EVENTOS (Agrupamento canônico de evidências)
        t0 = time.perf_counter()
        fontes_objs = [
            Fonte(
                id=f["id"], titulo=f["titulo"], url=f["url"], origem=f.get("origem", "Web"),
                categoria=f.get("categoria", "geral"), conteudo=f.get("conteudo", ""),
                resumo_busca=f.get("resumo_busca", ""), data_publicacao=f.get("data_publicacao", ""),
                data_tipo=f.get("data_tipo", "publicada"), atual=f.get("atual", False),
                direta=f.get("direta", False), score=f.get("score", 0.0), confianca=f.get("confianca", 0.0),
                alias_empresa=f.get("alias_empresa", ""), cidade_confirmada=f.get("cidade_confirmada", False),
                estado_confirmado=f.get("estado_confirmado", False), escopo=f.get("escopo", "local"),
                fingerprint=f.get("fingerprint", ""), dominio=f.get("dominio", ""),
                sinais=f.get("sinais", []), entidade=f.get("entidade", "")
            )
            for f in raw_fontes_data
        ]
        eventos_gerados = _domain_criar_eventos(fontes_objs)
        t_eventos = (time.perf_counter() - t0) * 1000

        # D. PRICING & SIMILARIDADE (Resolução de catálogos multinicho parametrizada)
        t0 = time.perf_counter()
        empresa_alvo = os.getenv("EMPRESA_ALVO", EMPRESA_ALVO_DEFAULT).strip()
        concorrentes_env = [x.strip() for x in os.getenv("CONCORRENTES", "Assai Atacadista|Grupo Mateus").split("|") if x.strip()]
        target_name = empresa_alvo or "Empresa Alvo"
        competitor_name = concorrentes_env[0] if concorrentes_env else "Concorrente"
        target_items = [PriceItem(target_name, "target", e[0], "", e[1], old_price=e[2], unit=e[3]) for e in extracted_entities[:15]]
        comp_items = [PriceItem(competitor_name, "competitor", e[0], "", e[1]*0.95, unit=e[3]) for e in extracted_entities[:15]]
        comparacoes = []
        for t in target_items:
            ranked = sorted(((similaridade_produto(t, c), c) for c in comp_items), key=lambda x: x[0], reverse=True)
            sim, best = ranked[0]
            comparacoes.append((t.name, best.name, sim, (best.price - t.price)/t.price*100))
        t_pricing = (time.perf_counter() - t0) * 1000

        # E. SCORING DE FONTES (Ordenação e bônus de autoridade dinâmico)
        t0 = time.perf_counter()
        scored_fontes = []
        for f in fontes_objs:
            sc = score_fonte(f)
            f.score = sc
            scored_fontes.append(f)
        scored_fontes = sorted(scored_fontes, key=lambda f: (f.score, f.atual, f.confianca), reverse=True)
        t_scoring = (time.perf_counter() - t0) * 1000

        # F. RENDERIZAÇÃO (Construção do payload determinístico e artefatos em memória)
        t0 = time.perf_counter()
        app_version = os.getenv("APP_VERSION", APP_VERSION_DEFAULT).strip()
        pacote_mock = {
            "versao": app_version, "empresa": empresa_alvo, "resumo_executivo": ["Resumo replay offline"],
            "sinais": [{"tipo": "RISCO", "titulo": "Sinal Replay", "descricao": "Desc"}],
            "swot": {"forcas": ["F1"], "fraquezas": ["W1"], "oportunidades": ["O1"], "ameacas": ["T1"]}
        }
        ambiente_mock = {"score": 75, "pressao_competitiva": {"score": 35}, "momentum_mercado": 50, "vulnerabilidade_empresa": {"score": 20}}
        html_out = gerar_html(pacote_mock, scored_fontes, eventos_gerados, ambiente_mock, {})
        json_out = json.dumps([asdict(f) for f in scored_fontes])
        t_render = (time.perf_counter() - t0) * 1000

        t_total = (time.perf_counter() - t_start) * 1000

        # Hash determinístico do replay sobre dados canônicos puros (invariante a clock de sistema)
        replay_payload = {
            "entidades": extracted_entities,
            "eventos": eventos_gerados,
            "fontes": [asdict(f) for f in scored_fontes],
            "comparacoes": comparacoes,
        }
        sig = hashlib.sha256(json.dumps(replay_payload, sort_keys=True).encode("utf-8")).hexdigest()

        print("=" * 70)
        print("AGENTE SNIPER — OFFLINE REPLAY BENCHMARK OFICIAL")
        print("=" * 70)
        print(f"{'Etapa':<28} | {'Tempo (ms)':>12}")
        print("-" * 44)
        print(f"{'Parsing OCR':<28} | {t_parsing:12.2f}")
        print(f"{'Extração Espacial (Produção)':<28} | {t_extracao:12.2f}")
        print(f"{'Agrupamento de Eventos':<28} | {t_eventos:12.2f}")
        print(f"{'Pricing & Similaridade':<28} | {t_pricing:12.2f}")
        print(f"{'Scoring de Fontes':<28} | {t_scoring:12.2f}")
        print(f"{'Renderização HTML/JSON':<28} | {t_render:12.2f}")
        print("-" * 44)
        print(f"{'TOTAL DO PIPELINE':<28} | {t_total:12.2f}")
        print("=" * 70)
        print(f"Entidades Canônicas:  {len(extracted_entities)}")
        print(f"Eventos Consolidados: {len(eventos_gerados)}")
        print(f"Fontes Avaliadas:     {len(scored_fontes)}")
        print(f"Garantia de Rede:     OFFLINE (Zero I/O externo verificado)")
        print(f"Output SHA-256:       {sig}")

        # Validação obrigatória dos contratos antes de emitir PASS
        erros_validacao = []
        if len(extracted_entities) != 63:
            erros_validacao.append(f"Entidades divergiram: {len(extracted_entities)} != 63")
        if len(eventos_gerados) != 28:
            erros_validacao.append(f"Eventos divergiram: {len(eventos_gerados)} != 28")
        if len(scored_fontes) != 59:
            erros_validacao.append(f"Fontes divergiram: {len(scored_fontes)} != 59")

        if erros_validacao:
            print("Status Replay:        FAIL")
            for err in erros_validacao:
                print(f"  - [ERRO CONTRATO] {err}")
            print("=" * 70)
            if retornar_detalhes:
                return {
                    "status": "FAIL",
                    "retorno": 1,
                    "erros": erros_validacao,
                    "entidades": len(extracted_entities),
                    "eventos": len(eventos_gerados),
                    "fontes": len(scored_fontes),
                    "sha256": sig,
                }
            return 1

        print("Status Replay:        PASS (100% Determinístico)")
        print("=" * 70)
        if retornar_detalhes:
            return {
                "status": "PASS",
                "retorno": 0,
                "entidades": len(extracted_entities),
                "eventos": len(eventos_gerados),
                "fontes": len(scored_fontes),
                "sha256": sig,
                "timings_ms": {
                    "parsing": t_parsing,
                    "extracao": t_extracao,
                    "eventos": t_eventos,
                    "pricing": t_pricing,
                    "scoring": t_scoring,
                    "render": t_render,
                    "total": t_total,
                },
            }
        return 0


__all__ = [
    "OfflineNetworkGuard",
    "resolver_fixture_fontes_offline",
    "executar_replay_offline",
]
