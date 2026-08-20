# -*- coding: utf-8 -*-
"""
Suíte de Testes Formais de Confiança e Corroboração de Evidências.
Valida os 10 requisitos obrigatórios da Fase 32:
1. Duas fontes independentes -> CONFIRMADO
2. Duas URLs com mesmo domínio/fingerprint -> 1 fonte independente
3. Fonte oficial/primária forte -> CONFIRMADO
4. Fonte de alta autoridade específica -> PROVÁVEL
5. Evidência única relevante -> SINAL
6. Evidência fraca/ambígua -> INSUFICIENTE
7. Determinismo estrito em múltiplas execuções
8. Invariância à ordem das fontes
9. Fontes duplicadas não inflam corroboração
10. Rastreabilidade reversa completa preservada
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import agente_sniper_v11_8 as sniper
from domain.models import Fonte
from domain.events import (
    CONFIANCA_CONFIRMADO,
    CONFIANCA_PROVAVEL,
    CONFIANCA_SINAL,
    CONFIANCA_INSUFICIENTE,
    identificar_independencia_fontes,
    possui_fonte_oficial,
    classificar_confianca_evento,
    enriquecer_evento_com_confianca,
    criar_eventos,
)


class TestEventCorroboration(unittest.TestCase):
    """Suíte oficial de testes para corroboração e classificação de confiança de evidências."""

    def test_01_duas_fontes_independentes_confirmado(self):
        """1. Duas fontes realmente independentes (domínios e fingerprints distintos) resultam em CONFIRMADO."""
        f1 = Fonte(id=1, titulo="Abertura de nova loja", url="https://g1.globo.com/pi/1", origem="web", dominio="g1.globo.com", fingerprint="fp_g1_01", entidade="Mateus", data_publicacao="2026-08-10")
        f2 = Fonte(id=2, titulo="Grupo Mateus inaugura loja", url="https://cidadeverde.com/noticia/2", origem="web", dominio="cidadeverde.com", fingerprint="fp_cv_02", entidade="Mateus", data_publicacao="2026-08-10")
        ev = {"title": "Inauguração Mix Mateus", "confidence": 0.70, "importance": 60, "date": "2026-08-10", "entity": "Mateus", "evidence_ids": [1, 2]}
        self.assertEqual(classificar_confianca_evento(ev, [f1, f2]), CONFIANCA_CONFIRMADO)

    def test_02_republicacao_mesmo_fingerprint_nao_duplica_independencia(self):
        """2. Duas URLs com mesmo fingerprint/mesmo domínio contam como 1 única fonte independente."""
        f1 = Fonte(id=1, titulo="Abertura de loja", url="https://g1.globo.com/pi/1", origem="web", dominio="g1.globo.com", fingerprint="fp_syndicated", entidade="Mateus")
        f2 = Fonte(id=2, titulo="Abertura de loja cópia", url="https://g1.globo.com/pi/1_mirror", origem="web", dominio="g1.globo.com", fingerprint="fp_syndicated", entidade="Mateus")
        indep = identificar_independencia_fontes([f1, f2])
        self.assertEqual(len(indep), 1)

    def test_03_fonte_oficial_primaria_confirmado(self):
        """3. Uma única fonte oficial/primária forte (governo/regulador) resulta em CONFIRMADO."""
        f_gov = Fonte(id=4, titulo="Fiscalização e Notificação do Procon", url="https://procon.pi.gov.br/noticia/100", origem="web", dominio="procon.pi.gov.br", entidade="Mateus")
        ev = {"title": "Procon fiscaliza supermercados", "confidence": 0.65, "importance": 55, "date": "2026-08-10", "entity": "Mateus", "evidence_ids": [4]}
        self.assertTrue(possui_fonte_oficial([f_gov]))
        self.assertEqual(classificar_confianca_evento(ev, [f_gov]), CONFIANCA_CONFIRMADO)

    def test_04_fonte_alta_autoridade_especifica_provavel(self):
        """4. Uma única fonte de alta autoridade com contexto e data específicos resulta em PROVÁVEL."""
        f_valor = Fonte(id=5, titulo="Grupo Mateus acelera abertura no Piauí", url="https://valor.globo.com/empresas/1", origem="web", dominio="valor.globo.com", fingerprint="fp_val_01", entidade="Mateus", data_publicacao="2026-08-10")
        ev = {"title": "Grupo Mateus acelera expansão no PI", "confidence": 0.75, "importance": 58, "date": "2026-08-10", "entity": "Mateus", "evidence_ids": [5]}
        self.assertEqual(classificar_confianca_evento(ev, [f_valor]), CONFIANCA_PROVAVEL)

    def test_05_evidencia_unica_relevante_sinal(self):
        """5. Uma evidência única relevante mas de autoridade moderada/sem corroboração resulta em SINAL."""
        f_blog = Fonte(id=6, titulo="Rumor de nova filial no interior", url="https://blogteresina.com/1", origem="web", dominio="blogteresina.com", entidade="mercado")
        ev = {"title": "Rumor de expansão no interior", "confidence": 0.45, "importance": 35, "date": "", "entity": "mercado", "evidence_ids": [6]}
        self.assertEqual(classificar_confianca_evento(ev, [f_blog]), CONFIANCA_SINAL)

    def test_06_evidencia_fraca_ambigua_insuficiente(self):
        """6. Evidência fraca, ambígua ou sem contexto material resulta em INSUFICIENTE."""
        ev_fraco = {"title": "Notícia vaga e não verificada", "confidence": 0.20, "importance": 15, "date": "", "entity": "", "evidence_ids": []}
        self.assertEqual(classificar_confianca_evento(ev_fraco, []), CONFIANCA_INSUFICIENTE)

    def test_07_determinismo_classificacao(self):
        """7. A classificação de confiança é rigorosamente determinística em 10 execuções."""
        f = Fonte(id=7, titulo="Notícia Econômica", url="https://economia.uol.com.br/1", origem="web", dominio="uol.com.br", fingerprint="fp_uol", entidade="Mateus", data_publicacao="2026-08-10")
        ev = {"title": "Notícia Econômica", "confidence": 0.70, "importance": 55, "date": "2026-08-10", "entity": "Mateus", "evidence_ids": [7]}
        res = [classificar_confianca_evento(ev, [f]) for _ in range(10)]
        self.assertTrue(all(r == res[0] for r in res))

    def test_08_invariancia_ordem_fontes(self):
        """8. Ordem diferente das fontes produz exatamente a mesma classificação de confiança."""
        f1 = Fonte(id=1, titulo="Notícia 1", url="https://a.com/1", origem="web", dominio="a.com", fingerprint="fp_a", entidade="Mateus")
        f2 = Fonte(id=2, titulo="Notícia 2", url="https://b.com/2", origem="web", dominio="b.com", fingerprint="fp_b", entidade="Mateus")
        f_gov = Fonte(id=3, titulo="Portaria Procon", url="https://procon.pi.gov.br/p", origem="web", dominio="procon.pi.gov.br", entidade="Mateus")
        ev = {"title": "Fiscalização Concorrente", "confidence": 0.70, "importance": 60, "date": "2026-08-10", "entity": "Mateus", "evidence_ids": [1, 2, 3]}

        r1 = classificar_confianca_evento(ev, [f1, f2, f_gov])
        r2 = classificar_confianca_evento(ev, [f_gov, f2, f1])
        r3 = classificar_confianca_evento(ev, [f2, f_gov, f1])
        self.assertEqual(r1, r2)
        self.assertEqual(r2, r3)

    def test_09_fontes_duplicadas_nao_inflam_corroboracao(self):
        """9. Passar a mesma fonte duplicada múltiplas vezes não infla artificialmente o status para CONFIRMADO."""
        f_single = Fonte(id=10, titulo="Expansão", url="https://site.com/1", origem="web", dominio="site.com", fingerprint="fp_same", entidade="Mateus", data_publicacao="2026-08-10")
        ev = {"title": "Expansão", "confidence": 0.75, "importance": 55, "date": "2026-08-10", "entity": "Mateus", "evidence_ids": [10]}
        res = classificar_confianca_evento(ev, [f_single, f_single, f_single, f_single])
        self.assertEqual(res, CONFIANCA_PROVAVEL)

    def test_10_enriquecimento_e_rastreabilidade_completa(self):
        """10. enriquecer_evento_com_confianca anexa metadados auditáveis mantendo 100% da rastreabilidade."""
        f1 = Fonte(id=1, titulo="Abertura", url="https://portal.com/1", origem="web", dominio="portal.com", fingerprint="fp_p1", entidade="Mateus", data_publicacao="2026-08-10")
        ev = {"title": "Abertura", "confidence": 0.70, "importance": 55, "date": "2026-08-10", "entity": "Mateus", "evidence_ids": [1]}
        f_map = {1: f1}
        enriched = enriquecer_evento_com_confianca(ev, f_map)
        self.assertIn("confianca_evidencia", enriched)
        self.assertIn("fontes_independentes", enriched)
        self.assertIn("possui_fonte_oficial", enriched)
        self.assertEqual(enriched["fontes_independentes"], 1)
        self.assertEqual(enriched["confianca_evidencia"], CONFIANCA_PROVAVEL)


if __name__ == "__main__":
    unittest.main()
