# -*- coding: utf-8 -*-
"""
Bridge / Adapter de Integração Controlada do Motor Extractors — Fase 6A
Fornece alternância controlada por feature flag (EXTRACTION_ENGINE: legacy | generic).
Garante retrocompatibilidade total com PriceItem e todos os seus campos downstream (incluindo price_confidence).
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from extractors.models import (
    BoundingBox,
    SpatialToken,
    RawSpatialDocument,
    ExtractedEntity,
    ExtractionResult,
)
from extractors.adapters.flyer_product_adapter import FlyerProductAdapter
from domain.models import PriceItem


# Feature Flag Global: Padrão operacional promovido é 'generic'
EXTRACTION_ENGINE_DEFAULT = "generic"


def obter_engine_ativo() -> str:
    """Retorna o motor configurado via variável de ambiente (legacy | generic)."""
    return os.getenv("EXTRACTION_ENGINE", EXTRACTION_ENGINE_DEFAULT).strip().lower()


def carregar_ocr_bruto(origem: Union[str, Path, Dict[str, Any]]) -> RawSpatialDocument:
    """
    Adapter de Entrada: Carrega e converte o JSON do OCR bruto (ex: dados_browser/ocr_bruto/*.json)
    em um RawSpatialDocument canônico.
    """
    if isinstance(origem, (str, Path)):
        caminho = Path(origem)
        identificador = caminho.stem
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    elif isinstance(origem, dict):
        identificador = origem.get("arquivo", "documento_ocr")
        dados = origem
    else:
        raise TypeError(f"Origem inválida para OCR bruto: {type(origem)}")

    deteccoes = dados.get("deteccoes", [])
    tokens: List[SpatialToken] = []

    max_x = 1.0
    max_y = 1.0

    for d in deteccoes:
        x_min = float(d.get("x_min", 0.0))
        y_min = float(d.get("y_min", 0.0))
        x_max = float(d.get("x_max", 0.0))
        y_max = float(d.get("y_max", 0.0))

        if x_max > max_x:
            max_x = x_max
        if y_max > max_y:
            max_y = y_max

        bbox = BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)
        tokens.append(SpatialToken(
            texto=str(d.get("texto", "")),
            bbox=bbox,
            confianca=float(d.get("confianca", 1.0)),
            id_token=int(d.get("id", len(tokens) + 1))
        ))

    return RawSpatialDocument(
        identificador=identificador,
        origem="ocr_bruto",
        dimensoes=(max(1.0, max_x), max(1.0, max_y)),
        tokens=tokens,
        metadados={"arquivo_origem": dados.get("arquivo", identificador)}
    )


def converter_entidades_para_price_items(
    entidades: Sequence[ExtractedEntity],
    source: str = "Assai",
    role: str = "competitor",
    page_url: str = "",
    location_note: str = "extracao_espacial"
) -> List[PriceItem]:
    """
    Adapter de Saída / Compatibilidade: Converte entidades canônicas do extractors
    no modelo PriceItem nativo de domínio do Agente Sniper com todos os campos preenchidos.
    """
    price_items: List[PriceItem] = []
    for ent in entidades:
        nome_produto = str(ent.atributos.get("nome", "")).strip()
        peso_volume = str(ent.atributos.get("peso_volume", "") or "").strip()
        marca = str(ent.atributos.get("marca", "") or "").strip()
        valor_float = float(ent.valor) if ent.valor is not None else None
        confianca = float(ent.confianca)

        item = PriceItem(
            source=source,
            role=role,
            name=nome_produto,
            url=page_url,
            price=valor_float,
            old_price=None,
            promotion=False,
            brand=marca,
            unit=peso_volume,
            sku="",
            matched_name="",
            competitor=source,
            similarity=confianca,
            availability="in_stock" if valor_float is not None else "unknown",
            location_note=location_note,
            evidence_url="",
            page_type="flyer_ocr",
            price_confidence=confianca
        )
        price_items.append(item)

    return price_items


def converter_para_schema_legacy_cards(resultado: ExtractionResult) -> Dict[str, Any]:
    """
    Adapter de Compatibilidade Reversa: Serializa o resultado no schema de cards_candidatos_v2.
    """
    cards: List[Dict[str, Any]] = []
    for idx, ent in enumerate(resultado.entidades):
        regiao = ent.atributos.get("regiao_card", {}) or {}
        card_dict = {
            "id": idx + 1,
            "linha": 1,
            "preco": {
                "texto": f"{ent.valor:.2f}".replace(".", ",") if ent.valor is not None else "",
                "valor": ent.valor,
            },
            "regiao": regiao,
            "textos": [
                {"texto": ev.texto_bruto, "confianca": ev.confianca, "bbox": ev.bbox.to_dict() if ev.bbox else None}
                for ev in ent.evidencias if ev.tipo == "texto_produto"
            ],
            "produto_normalizado": {
                "nome": ent.atributos.get("nome", ""),
                "peso_volume": ent.atributos.get("peso_volume", ""),
                "confianca": ent.confianca
            }
        }
        cards.append(card_dict)

    return {
        "arquivo": resultado.documento_id,
        "total_precos": len(cards),
        "total_cards": len(cards),
        "engine_utilizado": "extractors_v2_generic",
        "cards": cards
    }


def executar_pipeline_extracao(
    origem_ocr: Union[str, Path, Dict[str, Any]],
    engine: Optional[str] = None,
    source: str = "Assai",
    role: str = "competitor",
    page_url: str = ""
) -> Dict[str, Any]:
    """
    Ponto de Entrada Unificado da Ponte: Executa o extrator de acordo com a feature flag.
    Retorna tanto os PriceItems para o domínio quanto o JSON estruturado.
    """
    motor_escolhido = (engine or obter_engine_ativo()).strip().lower()
    doc_espacial = carregar_ocr_bruto(origem_ocr)

    if motor_escolhido == "generic":
        adapter = FlyerProductAdapter()
        resultado = adapter.processar_documento(doc_espacial)
        price_items = converter_entidades_para_price_items(
            resultado.entidades,
            source=source,
            role=role,
            page_url=page_url,
            location_note="extractors_generic"
        )
        return {
            "engine": "generic",
            "documento_id": doc_espacial.identificador,
            "price_items": price_items,
            "resultado_canonico": resultado,
            "total_itens": len(price_items),
            "metricas": resultado.metricas
        }
    else:
        # Modo LEGACY: leitura direta ou conversão básica a partir dos cards existentes
        caminho_legacy = Path(r"C:\Users\User\Desktop\Agente sniper\dados_browser\cards_candidatos_v2") / f"{doc_espacial.identificador}.json"
        if caminho_legacy.exists():
            with open(caminho_legacy, "r", encoding="utf-8") as f:
                dados_legacy = json.load(f)
            cards = dados_legacy.get("cards", [])
            price_items = []
            for c in cards:
                preco_txt = c.get("preco", {}).get("texto", "")
                try:
                    preco_float = float(preco_txt.replace("R$", "").replace(" ", "").replace(",", "."))
                except Exception:
                    preco_float = None

                textos_card = [t.get("texto", "") for t in c.get("textos", [])]
                nome_candidato = " ".join(textos_card[:2]) if textos_card else "Produto sem nome"

                item = PriceItem(
                    source=source,
                    role=role,
                    name=nome_candidato,
                    url=page_url,
                    price=preco_float,
                    old_price=None,
                    promotion=False,
                    brand="",
                    unit="",
                    sku="",
                    matched_name="",
                    competitor=source,
                    similarity=0.80,
                    availability="in_stock" if preco_float is not None else "unknown",
                    location_note="legacy_cards_v2",
                    page_type="flyer_ocr",
                    price_confidence=0.80
                )
                price_items.append(item)

            return {
                "engine": "legacy",
                "documento_id": doc_espacial.identificador,
                "price_items": price_items,
                "dados_legacy": dados_legacy,
                "total_itens": len(price_items),
                "metricas": {"total_cards": len(cards)}
            }
        else:
            return {
                "engine": "legacy",
                "documento_id": doc_espacial.identificador,
                "price_items": [],
                "total_itens": 0,
                "metricas": {"status": "arquivo_legado_nao_encontrado"}
            }
