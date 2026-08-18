import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from dotenv import load_dotenv

# ============================================
# CARREGAR CREDENCIAIS DO .env
# ============================================
load_dotenv()

EMAIL_REMETENTE = os.getenv("EMAIL_REMETENTE")
SENHA_APP = os.getenv("SENHA_APP_EMAIL")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO", "cinesynthreal@gmail.com")

if not EMAIL_REMETENTE or not SENHA_APP:
    print("❌ ERRO: Credenciais de e-mail não encontradas no .env!")
    exit(1)

PASTA_PDF = "relatorios_semanais"

def enviar_email_com_anexo(destinatario, assunto, corpo_email, arquivos_anexo):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMETENTE
        msg['To'] = destinatario
        msg['Subject'] = assunto
        
        msg.attach(MIMEText(corpo_email, 'html'))
        
        for arquivo in arquivos_anexo:
            caminho_completo = os.path.join(PASTA_PDF, arquivo)
            
            if not os.path.exists(caminho_completo):
                print(f"⚠️ Arquivo não encontrado: {arquivo}")
                continue
            
            with open(caminho_completo, "rb") as anexo:
                part = MIMEBase('application', 'pdf')
                part.set_payload(anexo.read())
            
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{arquivo}"')
            part.add_header('Content-Type', 'application/pdf')
            msg.attach(part)
        
        servidor = smtplib.SMTP('smtp.gmail.com', 587)
        servidor.starttls()
        servidor.ehlo()
        servidor.login(EMAIL_REMETENTE, SENHA_APP)
        servidor.sendmail(EMAIL_REMETENTE, destinatario, msg.as_string())
        servidor.quit()
        
        print(f"✅ E-mail enviado para: {destinatario}")
        print(f"📎 Anexos: {len(arquivos_anexo)} PDF(s)")
        return True
        
    except smtplib.SMTPAuthenticationError:
        print("❌ ERRO DE AUTENTICAÇÃO: Verifique e-mail e senha de app.")
        return False
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {e}")
        return False

def criar_corpo_email_profissional():
    data_hoje = datetime.now().strftime('%d/%m/%Y')
    
    corpo = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #2980b9;">Relatório de Inteligência de Mercado</h2>
        <p>Olá,</p>
        <p>Segue em anexo o <strong>Relatório de Inteligência de Mercado</strong> gerado automaticamente em <strong>{data_hoje}</strong>.</p>
        <p>Este relatório contém:</p>
        <ul>
            <li>Análise factual com citação de fontes</li>
            <li>Diagnóstico de reputação e preços</li>
            <li>Identificação de vulnerabilidades</li>
            <li>Plano de ação ou estratégias ofensivas</li>
        </ul>
        <p>Qualquer dúvida, estou à disposição.</p>
        <p>Atenciosamente,<br><strong>Equipe de Inteligência de Mercado</strong></p>
        <hr style="border: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 12px; color: #999;">
            Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}
        </p>
    </div>
    """
    return corpo

if __name__ == "__main__":
    print("=" * 60)
    print("📧 SISTEMA DE ENVIO AUTOMÁTICO DE RELATÓRIOS")
    print("=" * 60)
    
    if not os.path.exists(PASTA_PDF):
        print(f"❌ Pasta '{PASTA_PDF}' não encontrada!")
        exit()
    
    arquivos_pdf = [f for f in os.listdir(PASTA_PDF) if f.endswith('.pdf')]
    
    if not arquivos_pdf:
        print("⚠️ Nenhum PDF encontrado!")
        exit()
    
    print(f"📄 Encontrados {len(arquivos_pdf)} PDF(s) para enviar\n")
    
    assunto = f"Relatório de Inteligência - {datetime.now().strftime('%d/%m/%Y')}"
    corpo_email = criar_corpo_email_profissional()
    
    sucesso = enviar_email_com_anexo(
        destinatario=EMAIL_DESTINATARIO,
        assunto=assunto,
        corpo_email=corpo_email,
        arquivos_anexo=arquivos_pdf
    )
    
    print("\n" + "=" * 60)
    if sucesso:
        print("🎉 E-MAIL ENVIADO COM SUCESSO!")
    else:
        print("❌ FALHA AO ENVIAR E-MAIL")
    print("=" * 60)