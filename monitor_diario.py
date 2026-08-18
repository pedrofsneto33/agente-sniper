import os
from datetime import datetime
from dotenv import load_dotenv
from tavily import TavilyClient
from groq import Groq

# ============================================
# CONFIGURAÇÃO DE CHAVES (.env)
# ============================================
load_dotenv()

chave_groq = os.getenv("CHAVE_GROQ") or os.getenv("GROQ_API_KEY")
chave_tavily = os.getenv("CHAVE_TAVILY") or os.getenv("TAVILY_API_KEY")

if not chave_groq or not chave_tavily:
    print("❌ ERRO: Configure CHAVE_GROQ e CHAVE_TAVILY no arquivo .env")
    exit(1)

client_groq = Groq(api_key=chave_groq)
client_tavily = TavilyClient(api_key=chave_tavily)

# ============================================
# LISTA DE TEMAS PARA MONITORAR
# Adicione ou remova temas conforme necessário
# ============================================
TEMAS_DE_MONITORAMENTO = [
    "reclamações sistemas para academias não funciona",
    "alternativas ao software de gestão médica ruim",
    "empresas insatisfeitas com agência de marketing",
    "problemas com sistema de gestão financeira",
]

# ============================================
# FUNÇÃO DO AGENTE SNIPER
# ============================================
def sniper_de_leads(tema_busca):
    print(f"\n🔍 Buscando: '{tema_busca}'...")
    
    try:
        response = client_tavily.search(
            query=tema_busca, 
            max_results=3,
            search_depth="basic"
        )
    except Exception as e:
        return f"Erro na busca do Tavily: {e}"
    
    contexto = ""
    for r in response['results']:
        contexto += f"Titulo: {r['title']}\nConteudo: {r['content']}\nLink: {r['url']}\n\n"
        
    print("🧠 Analisando com IA...")
    
    chat_completion = client_groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Você é um Agente de Vendas B2B analítico. Analise os dados e forneça: 1) As maiores dores dos clientes. 2) Um script de abordagem profissional para WhatsApp."},
            {"role": "user", "content": f"Dados coletados sobre '{tema_busca}':\n\n{contexto}"}
        ],
        temperature=0.7,
        max_tokens=1000
    )
    
    return chat_completion.choices[0].message.content

# ============================================
# FUNÇÃO PARA SALVAR RELATÓRIOS
# ============================================
def salvar_relatorio(tema, conteudo):
    # Cria pasta de relatórios se não existir
    pasta = "relatorios"
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    
    # Limpa o nome do tema para usar como nome de arquivo
    nome_arquivo = tema.replace(" ", "_").replace("/", "-")[:50]
    data_hora = datetime.now().strftime("%Y-%m-%d_%H-%M")
    
    caminho = os.path.join(pasta, f"{nome_arquivo}_{data_hora}.txt")
    
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(f"RELATÓRIO DE INTELIGÊNCIA\n")
        f.write(f"Tema: {tema}\n")
        f.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write(f"{'='*50}\n\n")
        f.write(conteudo)
    
    print(f"✅ Salvo em: {caminho}")
    return caminho

# ============================================
# EXECUÇÃO PRINCIPAL
# ============================================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 INICIANDO MONITOR DIÁRIO DE INTELIGÊNCIA")
    print(f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"📋 Total de temas: {len(TEMAS_DE_MONITORAMENTO)}")
    print("=" * 50)
    
    total_processados = 0
    
    for i, tema in enumerate(TEMAS_DE_MONITORAMENTO, 1):
        print(f"\n[{i}/{len(TEMAS_DE_MONITORAMENTO)}] Processando...")
        
        try:
            relatorio = sniper_de_leads(tema)
            salvar_relatorio(tema, relatorio)
            total_processados += 1
        except Exception as e:
            print(f"❌ Erro no tema '{tema}': {e}")
    
    print("\n" + "=" * 50)
    print(f"🎉 MONITOR CONCLUÍDO!")
    print(f"✅ {total_processados}/{len(TEMAS_DE_MONITORAMENTO)} relatórios gerados com sucesso.")
    print(f"📁 Confira a pasta 'relatorios' na sua Área de Trabalho.")
    print("=" * 50)