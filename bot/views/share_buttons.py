import discord
import urllib.parse

from utils.html import safe_discord_url

class ShareButtons(discord.ui.View):
    def __init__(self, news_title: str, news_url: str, is_critical: bool = False):
        super().__init__()
        
        # 1. Botão Original "Leia Mais" (Obrigatório, mas pode ser None se muito longo)
        clean_news_url = safe_discord_url(news_url)
        if clean_news_url:
            self.add_item(discord.ui.Button(
                label="Leia Mais", 
                emoji="📖", 
                url=clean_news_url,
                style=discord.ButtonStyle.link
            ))

        if is_critical:
            base_text = f"🚨 *ALERTA URGENTE detectado no SOC do Paulo!* 🚨\n\n{news_title}\n🔗 {news_url}"
        else:
            base_text = f"🚨 *Alerta CyberIntel*\n\n{news_title}\n🔗 {news_url}"
            
        safe_text_encoded = urllib.parse.quote(base_text)
        
        # WhatsApp Button
        wa_url = f"https://api.whatsapp.com/send?text={safe_text_encoded}"
        clean_wa = safe_discord_url(wa_url)
        if clean_wa:
            self.add_item(discord.ui.Button(
                label="WhatsApp", 
                emoji="🟢", 
                url=clean_wa,
                style=discord.ButtonStyle.link
            ))
        
        # Email Button
        mail_subject = urllib.parse.quote(f"⚠️ Alerta CyberIntel: {news_title}")
        mail_body = urllib.parse.quote(f"Prezados,\n\nIdentificamos um alerta de segurança relevante:\n\n{news_title}\n\nLink Original: {news_url}\n\n--\nCyberIntel SOC Bot")
        gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&tf=1&su={mail_subject}&body={mail_body}"
        
        clean_gmail = safe_discord_url(gmail_url)
        if clean_gmail:
            self.add_item(discord.ui.Button(
                label="E-mail", 
                emoji="📧", 
                url=clean_gmail,
                style=discord.ButtonStyle.link
            ))

