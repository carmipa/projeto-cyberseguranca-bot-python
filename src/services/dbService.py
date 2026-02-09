import json
import os
import requests
from datetime import datetime

DB_PATH = "data/database.json"
NODE_RED_ENDPOINT = os.getenv("NODE_RED_ENDPOINT", "http://nodered:1880/update-news")

def init_db():
    """Inicializa o arquivo JSON se não existir"""
    if not os.path.exists("data"):
        os.makedirs("data", exist_ok=True)
    
    if not os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'w', encoding='utf-8') as f:
                json.dump({"sent_news": [], "stats": {"total_processed": 0}}, f, indent=4)
        except Exception as e:
            print(f"Erro ao inicializar DB JSON: {e}")

def load_db():
    try:
        if not os.path.exists(DB_PATH):
            init_db()
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao carregar DB: {e}")
        return {"sent_news": [], "stats": {"total_processed": 0}}

def save_db(data):
    try:
        with open(DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Erro ao salvar DB: {e}")

def is_news_sent(link):
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
        print(f"Erro ao comunicar com Node-RED: {e}")

def mark_news_as_sent(link, title="Sem Título"):
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
