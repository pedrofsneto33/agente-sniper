"""
AGENTE SNIPER - MODULO BROWSER-USE v5.0 (DEFINITIVO)
- Usa Groq como LLM principal (cota separada do OpenRouter)
- Extrai apenas o resultado util (sem o log verboso)
- Fontes: Reclame Aqui, Google Maps, Tiendeo

DEPENDENCIAS:
  py -3.13 -m pip install browser-use langchain-groq python-dotenv
  py -3.13 -m playwright install chromium
"""

import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# ============================================
# IMPORTACAO DO BROWSER-USE
# ============================================
try:
    from browser_use import Agent
    print("[OK] browser_use.Agent importado")
except ImportError as e:
    print("[ERRO] browser-use nao instalado: " + str(e))
    sys.exit(1)

# ============================================
# IMPORTACAO DOS LLMS (GROQ como principal)
# ============================================
tem_groq = False
tem_openrouter = False
ChatGroq = None
ChatOpenAI = None

try:
    from langchain_groq import ChatGroq
    tem_groq = True
    print("[OK] langchain_groq importado")
except ImportError:
    print("[AVISO] langchain_groq nao instalado")
    print("   Instale com: py -3.13 -m pip install langchain-groq")

try:
    from browser_use import ChatOpenAI
    tem_openrouter = True
    print("[OK] browser_use.ChatOpenAI importado")
except ImportError:
    print("[AVISO] browser_use.ChatOpenAI nao disponivel")

if not tem_groq and not tem_openrouter:
    print("[ERRO] Nenhum LLM disponivel. Instale langchain-groq ou reinstale browser-use")
    sys.exit(1)

# ============================================
# CONFIGURACAO
# ============================================
load_dotenv()

CHAVE_GROQ = os.getenv("CHAVE_GROQ")
CHAVE_OPENROUTER = os.getenv("CHAVE_OPENROUTER")

if not CHAVE_GROQ and not CHAVE_OPENROUTER:
    print("[ERRO] Nenhuma chave encontrada no .env (CHAVE_GROQ ou CHAVE_OPENROUTER)")
    sys.exit(1)

PASTA_RESULTADOS = "dados_browser"
os.makedirs(PASTA_RESULTADOS, exist_ok=True)

# ============================================
# CRIACAO DO LLM (GROQ preferencial)
# ============================================
def criar_llm():
    """Cria o LLM. Tenta Groq primeiro (cota separada), depois OpenRouter."""
    
    # Tentativa 1: Groq (preferencial - tem cota separada)
    if tem_groq and CHAVE_GROQ:
        try:
            llm = ChatGroq(
                model="llama-3.3-70b-versatile",
                api_key=CHAVE_GROQ,
                temperature=0.1,
            )
            print("[LLM] Groq criado com sucesso (cota separada)")
            return llm
        except Exception as e:
            print("[AVISO] Nao foi possivel criar Groq: " + str(e)[:100])
    
    # Tentativa 2: OpenRouter (fallback)
    if tem_openrouter and CHAVE_OPENROUTER:
        try:
            llm = ChatOpenAI(
                model="openrouter/free",
                base_url="https://openrouter.ai/api/v1",
                api_key=CHAVE_OPENROUTER,
            )
            print("[LLM] OpenRouter criado como fallback")
            return llm
        except Exception as e:
            print("[AVISO] Nao foi possivel criar OpenRouter: " + str(e)[:100])
    
    print("[ERRO] Nenhum LLM pode ser criado")
    sys.exit(1)

# ============================================
# EXTRACAO DO RESULTADO UTIL (SEM LOG VERBOSO)
# ============================================
def extrair_resultado_util(resultado_agente):
    """
    Extrai apenas o conteudo util do resultado do agente,
    ignorando todo o log verboso de passos intermediarios.
    """
    if resultado_agente is None:
        return "[AVISO] Agente retornou None"
    
    texto_resultado = str(resultado_agente)
    
    # Tenta 1: Procurar o texto da acao 'done' (resultado final)
    try:
        import re
        # Procura padrao: 'done': {'text': '...', 'success': True
        match = re.search(r"'done':\s*\{'text':\s*'([^']+)'", texto_resultado, re.DOTALL)
        if match:
            texto = match.group(1)
            # Limpa escapes
            texto = texto.replace("\\n", "\n").replace("\\'", "'")
            return texto
    except Exception:
        pass
    
    # Tenta 2: Procurar extracted_content do ultimo passo util
    try:
        import re
        # Pega todos os extracted_content
        matches = re.findall(r"extracted_content='([^']+)'", texto_resultado)
        if matches:
            # Pega o ultimo que tem conteudo substancial
            for match in reversed(matches):
                if len(match) > 200 and "<url>" in match or "NOME_" in match or "NOTA_" in match:
                    return match.replace("\\n", "\n").replace("\\'", "'")
            # Se nao achou o "grande", retorna o ultimo
            return matches[-1].replace("\\n", "\n").replace("\\'", "'")
    except Exception:
        pass
    
    # Tenta 3: Procurar long_term_memory do ultimo passo com dados
    try:
        import re
        matches = re.findall(r"long_term_memory='([^']+)'", texto_resultado)
        if matches:
            for match in reversed(matches):
                if len(match) > 100:
                    return match.replace("\\n", "\n").replace("\\'", "'")
    except Exception:
        pass
    
    # Fallback: retorna texto bruto truncado
    if len(texto_resultado) > 3000:
        return texto_resultado[:3000] + "\n\n[TEXTO TRUNCADO - resultado muito longo]"
    return texto_resultado

# ============================================
# CRIACAO DO AGENTE
# ============================================
def criar_agent(task_text):
    llm = criar_llm()
    try:
        agent = Agent(task=task_text, llm=llm)
        return agent
    except Exception as e:
        print("[ERRO] Nao foi possivel criar agente: " + str(e)[:150])
        return None

# ============================================
# SALVAR RESULTADO
# ============================================
def salvar_resultado(nome_arquivo, titulo, empresa, cidade, resultado):
    caminho = os.path.join(PASTA_RESULTADOS, nome_arquivo)
    try:
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write("=== " + titulo + " ===\n")
            f.write("Empresa: " + empresa + "\n")
            if cidade:
                f.write("Cidade: " + cidade + "\n")
            f.write("Data extracao: " + datetime.now().strftime('%d/%m/%Y %H:%M') + "\n")
            f.write("=" * 50 + "\n\n")
            f.write(resultado)
        print("[OK] Salvo em: " + caminho)
    except Exception as e:
        print("[ERRO] Ao salvar: " + str(e)[:100])

# ============================================
# EXTRACAO 1: RECLAME AQUI
# ============================================
async def extrair_reclame_aqui(nome_empresa, cidade):
    print("")
    print("[BROWSER] Extraindo Reclame Aqui: " + nome_empresa)

    task_text = (
        "Acesse o site https://www.reclameaqui.com.br e busque pela empresa '"
        + nome_empresa + "' na cidade de '" + cidade + "'. "
        "Clique no resultado correto da empresa. "
        "Na pagina da empresa, extraia EXATAMENTE estas informacoes:\n"
        "1. NOME_EMPRESA: nome completo da empresa\n"
        "2. NOTA_GERAL: nota de 0 a 10 (se existir)\n"
        "3. STATUS_REPUTACAO: RA1000, Otimo, Bom, Regular, Ruim, ou Sem Reputacao\n"
        "4. TOTAL_RECLAMACOES: numero total de reclamacoes\n"
        "5. PERCENTUAL_RESPONDIDAS: percentual de reclamacoes respondidas\n"
        "6. PERCENTUAL_RESOLVIDAS: percentual de reclamacoes resolvidas\n"
        "7. NOTA_CONSUMIDOR: nota dada pelos consumidores (se existir)\n"
        "8. RECLAMACOES_RECENTES: liste as 5 reclamacoes mais recentes com titulo e data\n"
        "9. TEMAS_RECORRENTES: quais sao os temas mais comuns nas reclamacoes\n\n"
        "IMPORTANTE:\n"
        "- Se a pagina pedir login ou captcha, diga 'BLOQUEADO_POR_LOGIN'\n"
        "- Se nao encontrar a empresa, diga 'EMPRESA_NAO_ENCONTRADA'\n"
        "- Retorne os dados em formato texto simples, um por linha\n"
        "- NAO invente dados. So reporte o que esta visivel na pagina."
    )

    try:
        agent = criar_agent(task_text)
        if agent is None:
            return "[AVISO] Nao foi possivel criar o agente"

        resultado_bruto = await agent.run()
        resultado_limpo = extrair_resultado_util(resultado_bruto)

        salvar_resultado(
            "reclame_aqui_" + nome_empresa.replace(' ', '_') + ".txt",
            "DADOS DO RECLAME AQUI",
            nome_empresa,
            cidade,
            resultado_limpo
        )

        return resultado_limpo

    except Exception as e:
        print("[ERRO] Reclame Aqui: " + str(e)[:150])
        return "[AVISO] Extracao falhou: " + str(e)[:200]

# ============================================
# EXTRACAO 2: GOOGLE MAPS
# ============================================
async def extrair_google_maps(nome_empresa, cidade):
    print("")
    print("[BROWSER] Extraindo Google Maps: " + nome_empresa)

    task_text = (
        "Acesse https://www.google.com/maps e busque por '"
        + nome_empresa + " " + cidade + "'. "
        "Clique no primeiro resultado que aparecer (o estabelecimento correto). "
        "Na pagina do estabelecimento, extraia EXATAMENTE estas informacoes:\n"
        "1. NOME_ESTABELECIMENTO: nome completo\n"
        "2. NOTA_ESTRELAS: nota de 1 a 5 estrelas\n"
        "3. TOTAL_AVALIACOES: numero total de avaliacoes\n"
        "4. CATEGORIA: tipo de estabelecimento\n"
        "5. ENDERECO: endereco completo\n"
        "6. HORARIO_FUNCIONAMENTO: dias e horarios\n"
        "7. TELEFONE: numero de telefone (se visivel)\n"
        "8. AVALIACOES_RECENTES: as 5 avaliacoes mais recentes com texto e nota\n"
        "9. TEMAS_ELOGIOS: o que os clientes elogiam\n"
        "10. TEMAS_CRITICAS: o que os clientes criticam\n\n"
        "IMPORTANTE:\n"
        "- Se aparecer mais de um resultado, escolha o que tem mais avaliacoes\n"
        "- Se nao encontrar, diga 'EMPRESA_NAO_ENCONTRADA'\n"
        "- NAO invente dados."
    )

    try:
        agent = criar_agent(task_text)
        if agent is None:
            return "[AVISO] Nao foi possivel criar o agente"

        resultado_bruto = await agent.run()
        resultado_limpo = extrair_resultado_util(resultado_bruto)

        salvar_resultado(
            "google_maps_" + nome_empresa.replace(' ', '_') + ".txt",
            "DADOS DO GOOGLE MAPS",
            nome_empresa,
            cidade,
            resultado_limpo
        )

        return resultado_limpo

    except Exception as e:
        print("[ERRO] Google Maps: " + str(e)[:150])
        return "[AVISO] Extracao falhou: " + str(e)[:200]

# ============================================
# EXTRACAO 3: TIENDEO
# ============================================
async def extrair_tiendeo(nome_empresa):
    print("")
    print("[BROWSER] Extraindo Tiendeo: " + nome_empresa)

    task_text = (
        "Acesse https://www.tiendeo.com.br e busque por '"
        + nome_empresa + "'. "
        "Encontre o encarte ou catalogo atual da empresa. "
        "Extraia EXATAMENTE estas informacoes:\n"
        "1. NOME_LOJA: nome da empresa no Tiendeo\n"
        "2. DATA_VALIDADE: periodo de validade das ofertas\n"
        "3. PRODUTOS_EM_PROMOCAO: liste TODOS os produtos com precos que encontrar\n"
        "   Formato: Nome do Produto - Preco Normal - Preco Promocional\n"
        "4. CATEGORIAS: categorias de produtos em promocao\n"
        "5. QUANTIDADE_PRODUTOS: total de produtos em promocao\n\n"
        "IMPORTANTE:\n"
        "- Se nao encontrar encarte, diga 'ENCARTE_NAO_ENCONTRADO'\n"
        "- Liste o MAXIMO de produtos que conseguir ver\n"
        "- NAO invente precos."
    )

    try:
        agent = criar_agent(task_text)
        if agent is None:
            return "[AVISO] Nao foi possivel criar o agente"

        resultado_bruto = await agent.run()
        resultado_limpo = extrair_resultado_util(resultado_bruto)

        salvar_resultado(
            "tiendeo_" + nome_empresa.replace(' ', '_') + ".txt",
            "DADOS DO TIENDEO (ENCARTES)",
            nome_empresa,
            None,
            resultado_limpo
        )

        return resultado_limpo

    except Exception as e:
        print("[ERRO] Tiendeo: " + str(e)[:150])
        return "[AVISO] Extracao falhou: " + str(e)[:200]

# ============================================
# EXTRACAO COMPLETA
# ============================================
async def extrair_tudo(nome_empresa, cidade):
    print("=" * 60)
    print("EXTRACAO COM BROWSER-USE v5.0")
    print("Empresa: " + nome_empresa)
    print("Cidade: " + cidade)
    print("LLM preferencial: Groq (cota separada)")
    print("=" * 60)

    dados = {}

    # 1. Reclame Aqui
    dados['reclame_aqui'] = await extrair_reclame_aqui(nome_empresa, cidade)
    await asyncio.sleep(5)

    # 2. Google Maps
    dados['google_maps'] = await extrair_google_maps(nome_empresa, cidade)
    await asyncio.sleep(5)

    # 3. Tiendeo
    dados['tiendeo'] = await extrair_tiendeo(nome_empresa)

    # Salvar arquivo completo
    arquivo_completo = os.path.join(
        PASTA_RESULTADOS,
        "extracao_completa_" + nome_empresa.replace(' ', '_') + ".txt"
    )
    try:
        with open(arquivo_completo, 'w', encoding='utf-8') as f:
            f.write("EXTRACAO COMPLETA - " + nome_empresa + "\n")
            f.write("Data: " + datetime.now().strftime('%d/%m/%Y %H:%M') + "\n")
            f.write("=" * 60 + "\n\n")
            f.write("=== RECLAME AQUI ===\n")
            f.write(dados['reclame_aqui'] + "\n\n")
            f.write("=== GOOGLE MAPS ===\n")
            f.write(dados['google_maps'] + "\n\n")
            f.write("=== TIENDEO ===\n")
            f.write(dados['tiendeo'] + "\n")
        print("")
        print("[OK] Extracao completa salva em: " + arquivo_completo)
    except Exception as e:
        print("[ERRO] Ao salvar arquivo completo: " + str(e)[:100])

    return dados

# ============================================
# EXECUCAO DIRETA
# ============================================
async def main():
    empresa = "Supermercado Carvalho"
    cidade = "Teresina"

    dados = await extrair_tudo(empresa, cidade)

    print("")
    print("=" * 60)
    print("EXTRACAO CONCLUIDA!")
    print("Verifique a pasta: " + os.path.abspath(PASTA_RESULTADOS))
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())