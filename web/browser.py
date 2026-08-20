# -*- coding: utf-8 -*-
"""
Subsistema de Automação de Navegador Web — Agente Sniper
Gerenciamento do ciclo de vida de instâncias Chromium/Playwright com isolamento entre contextos.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("agente_sniper")

PLAYWRIGHT_ATIVO = os.getenv("PLAYWRIGHT_ATIVO", "1") == "1"
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
PRICE_PLAYWRIGHT_TIMEOUT = int(os.getenv("PRICE_PLAYWRIGHT_TIMEOUT", "35000"))


class PersistentPlaywrightManager:
    """Gerencia uma única instância persistente de Playwright/Chromium por run com isolamento entre páginas."""

    def __init__(self, ativo: Optional[bool] = None):
        self._ativo = PLAYWRIGHT_ATIVO if ativo is None else ativo
        self._pw = None
        self._browser = None
        self._lock = threading.Lock()
        self._initialized = False

        # Telemetria
        self.launch_count = 0
        self.contexts_created = 0
        self.pages_created = 0
        self.pages_closed = 0
        self.startup_time = 0.0
        self.navigation_time = 0.0
        self.render_time = 0.0
        self.success_count = 0
        self.fail_count = 0
        self.timeout_count = 0

    def get_browser(self):
        if not self._ativo:
            return None
        with self._lock:
            if self._browser is None and not self._initialized:
                t0 = time.perf_counter()
                try:
                    from playwright.sync_api import sync_playwright
                    self._pw = sync_playwright().start()
                    self._browser = self._pw.chromium.launch(headless=True)
                    self.launch_count += 1
                    self.startup_time = time.perf_counter() - t0
                    self._initialized = True
                    logger.info("[PLAYWRIGHT POOL] Chromium persistente inicializado em %.2fs", self.startup_time)
                except Exception as e:
                    self._initialized = True
                    logger.warning("[PLAYWRIGHT POOL] Falha ao inicializar Chromium: %s", str(e)[:150])
                    self._browser = None
                    self._pw = None
            return self._browser

    def new_isolated_context(self, user_agent: str = USER_AGENT, locale: str = "pt-BR"):
        browser = self.get_browser()
        if not browser:
            return None
        with self._lock:
            try:
                context = browser.new_context(user_agent=user_agent, locale=locale)
                self.contexts_created += 1
                return context
            except Exception as e:
                logger.debug("[PLAYWRIGHT POOL] Erro ao criar contexto isolado: %s", str(e)[:120])
                return None

    def extrair_pagina_playwright(self, url: str, timeout: int = 30000) -> Optional[Dict[str, Any]]:
        context = self.new_isolated_context()
        if not context:
            return None
        page = None
        try:
            with self._lock:
                self.pages_created += 1
            page = context.new_page()

            t_nav = time.perf_counter()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            with self._lock:
                self.navigation_time += (time.perf_counter() - t_nav)

            t_rend = time.perf_counter()
            texto = page.locator("body").inner_text(timeout=12000)
            title = page.title()
            final_url = page.url
            with self._lock:
                self.render_time += (time.perf_counter() - t_rend)
                self.success_count += 1

            return {"conteudo": texto, "titulo": title, "final_url": final_url, "data_publicacao": ""}
        except Exception as e:
            with self._lock:
                self.fail_count += 1
                if "timeout" in str(e).lower():
                    self.timeout_count += 1
            logger.debug("[PLAYWRIGHT POOL] Falha ao extrair %s: %s", url[:80], str(e)[:120])
            return None
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
                with self._lock:
                    self.pages_closed += 1
            try:
                context.close()
            except Exception:
                pass

    def extrair_html_preco(self, url: str, timeout: int = PRICE_PLAYWRIGHT_TIMEOUT) -> Tuple[str, str]:
        context = self.new_isolated_context()
        if not context:
            return "", url
        page = None
        try:
            with self._lock:
                self.pages_created += 1
            page = context.new_page()

            t_nav = time.perf_counter()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            with self._lock:
                self.navigation_time += (time.perf_counter() - t_nav)

            t_rend = time.perf_counter()
            html = page.content()
            final_url = page.url
            with self._lock:
                self.render_time += (time.perf_counter() - t_rend)
                self.success_count += 1

            return html, final_url
        except Exception as e:
            with self._lock:
                self.fail_count += 1
                if "timeout" in str(e).lower():
                    self.timeout_count += 1
            logger.warning("[PLAYWRIGHT POOL PREÇO] Falha %s: %s", url[:80], str(e)[:150])
            return "", url
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
                with self._lock:
                    self.pages_closed += 1
            try:
                context.close()
            except Exception:
                pass

    def session_search(
        self,
        base_url: str,
        search_url_template: str,
        queries: List[str],
        location_hint: str = "",
        buscar_preco_fn: Optional[Callable[[str, str], str]] = None,
        extract_products_fn: Optional[Callable[..., List[Any]]] = None,
        cidade: Optional[str] = None,
        normalizar_fn: Optional[Callable[[str], str]] = None,
        max_results: int = 15,
    ) -> Dict[str, List[Any]]:
        results: Dict[str, List[Any]] = {}
        context = self.new_isolated_context()
        if not context:
            return results
        page = None
        try:
            with self._lock:
                self.pages_created += 1
            page = context.new_page()

            t_nav = time.perf_counter()
            page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
            base_text = page.locator("body").inner_text(timeout=12000) if page.locator("body") else ""
            norm = normalizar_fn or (lambda s: s.lower())
            location_confirmed = bool(cidade and norm(cidade) in norm(base_text))
            with self._lock:
                self.navigation_time += (time.perf_counter() - t_nav)

            for query in queries:
                try:
                    if buscar_preco_fn:
                        target_url = buscar_preco_fn(search_url_template, query)
                    else:
                        target_url = search_url_template.format(query=query) if "{query}" in search_url_template else search_url_template

                    t_q = time.perf_counter()
                    page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1200)
                    html = page.content()
                    final_url = page.url
                    with self._lock:
                        self.navigation_time += (time.perf_counter() - t_q)
                        self.success_count += 1
                    note = location_hint
                    if location_confirmed and cidade:
                        note = (note + " | localização confirmada no contexto da sessão: " + cidade + ").").strip(" |")

                    if extract_products_fn:
                        items = extract_products_fn(html, "", "competitor", final_url, note)
                    else:
                        items = []
                    for item in items:
                        if hasattr(item, "location_note"):
                            item.location_note = note
                    results[query] = items[:max_results]
                except Exception as e:
                    with self._lock:
                        self.fail_count += 1
                        if "timeout" in str(e).lower():
                            self.timeout_count += 1
                    logger.warning("[PLAYWRIGHT SESSION] busca '%s': %s", query[:80], str(e)[:120])
                    results[query] = []
        except Exception as e:
            with self._lock:
                self.fail_count += 1
            logger.warning("[PLAYWRIGHT SESSION] falhou base %s: %s", base_url[:80], str(e)[:150])
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
                with self._lock:
                    self.pages_closed += 1
            try:
                context.close()
            except Exception:
                pass
        return results

    def close_all(self):
        with self._lock:
            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._pw:
                try:
                    self._pw.stop()
                except Exception:
                    pass
                self._pw = None
            self._initialized = False


_PLAYWRIGHT_MGR = PersistentPlaywrightManager()
