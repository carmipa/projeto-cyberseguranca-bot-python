import os
import json
import requests
from datetime import datetime
from utils.storage import p, load_json_safe, save_json_safe
from settings import NODE_RED_ENDPOINT

DB_PATH = p("database.json")  # Usa função p() para garantir caminho correto

import logging

log = logging.getLogger("CyberIntel")

def init_db():
    """
    Inicializa o arquivo JSON de banco de dados se não existir.
    Cria a estrutura básica com 'sent_news' e 'stats'.
    Usa funções seguras de storage para garantir integridade.
    """
    default_data = {"sent_news": [], "stats": {"total_processed": 0}}
    
    if not os.path.exists(DB_PATH):
        try:
            save_json_safe(DB_PATH, default_data, atomic=True)
            log.info(f"✅ Database inicializado: {DB_PATH}")
        except Exception as e:
            log.exception(f"❌ Erro ao inicializar DB JSON: {e}")

def load_db():
    """
    Carrega banco de dados usando funções seguras com validação.
    """
    if not os.path.exists(DB_PATH):
        init_db()
    
    return load_json_safe(DB_PATH, {"sent_news": [], "stats": {"total_processed": 0}}, validate=True)

def save_db(data):
    """
    Salva banco de dados usando escrita atômica e file locking.
    Garante integridade para auditoria e compliance.
    """
    save_json_safe(DB_PATH, data, atomic=True)

def is_news_sent(link):
    """
    Verifica se um link já foi enviado anteriormente.
    
    Args:
        link (str): URL da notícia.
        
    Returns:
        bool: True se já estiver no banco, False caso contrário.
    """
    db = load_db()
    # Verifica se o link está na lista de enviados
    # Otimização: para muitos dados, usar set seria melhor, mas para JSON simples list comprehension serve
    return any(item['link'] == link for item in db.get('sent_news', []))

def notify_nodered(item):
    """Envia a nova notícia para o dashboard do Node-RED"""
    try:
        # Timeout curto para não travar o bot se o Node-RED estiver offline
        requests.post(NODE_RED_ENDPOINT, json=item, timeout=2)
    except Exception as e:
        log.warning(f"⚠️ Erro ao comunicar com Node-RED: {e}")

def mark_news_as_sent(link, title="Sem Título"):
    """
    Registra uma notícia como enviada no banco de dados e notifica o Node-RED via webhook.
    
    Args:
        link (str): URL da notícia.
        title (str): Título da notícia.
    """
    db = load_db()
    
    # Verifica duplicidade antes de adicionar
    if not any(item['link'] == link for item in db.get('sent_news', [])):
        entry = {
            "title": title,
            "link": link,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        db.setdefault('sent_news', []).append(entry)
        
        if 'stats' not in db:
            db['stats'] = {"total_processed": 0}
            
        db['stats']['total_processed'] = db['stats'].get('total_processed', 0) + 1
        
        save_db(db)
        
        # Envia para o SOC Dashboard
        notify_nodered(entry)

def get_db_stats():
    db = load_db()
    total = db.get('stats', {}).get('total_processed', 0)
    
    sent_news = db.get('sent_news', [])
    if sent_news:
        # Assume que o último adicionado é o mais recente
        last_date = sent_news[-1].get('timestamp', "N/A")
    else:
        last_date = "N/A"
        
    return total, last_date
