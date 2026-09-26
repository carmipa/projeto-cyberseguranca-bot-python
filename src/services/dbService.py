import os
from datetime import datetime
from utils.storage import p, load_json_safe, save_json_safe


def db_path() -> str:
    """
    Caminho do database.json, resolvido NA CHAMADA.

    PROPÓSITO DE NEGÓCIO:
        O database.json alimenta o painel Windows e a vps_api (mesmo volume).

    INVARIANTES DO DOMÍNIO:
        Segue o DATA_DIR vigente. Era uma constante calculada no import: um
        DATA_DIR definido depois era ignorado em silêncio — foi assim que um
        teste com diretório temporário escreveu no database.json versionado.

    COMPORTAMENTO EM CASO DE FALHA:
        Nunca levanta.
    """
    return p("database.json")

import logging

log = logging.getLogger("CyberIntel")


def _log_db_path_once():
    """Registra o caminho real do database.json na inicialização (diagnóstico)."""
    if getattr(init_db, "_path_logged", False):
        return
    try:
        log.info("database.json path (para painel/vps_api): %s", os.path.abspath(db_path()))
        init_db._path_logged = True
    except Exception:
        pass


def init_db():
    """
    Inicializa o arquivo JSON de banco de dados se não existir.
    Cria a estrutura básica com 'sent_news' e 'stats'.
    Usa funções seguras de storage para garantir integridade.
    """
    default_data = {"sent_news": [], "stats": {"total_processed": 0}}
    
    _log_db_path_once()
    if not os.path.exists(db_path()):
        try:
            save_json_safe(db_path(), default_data, atomic=True)
            log.info(f"✅ Database inicializado: {db_path()}")
        except Exception as e:
            log.exception(f"❌ Erro ao inicializar DB JSON: {e}")

def load_db():
    """
    Carrega banco de dados usando funções seguras com validação.
    """
    if not os.path.exists(db_path()):
        init_db()
    
    return load_json_safe(db_path(), {"sent_news": [], "stats": {"total_processed": 0}}, validate=True)

def save_db(data):
    """
    Salva banco de dados usando escrita atômica e file locking.
    Garante integridade para auditoria e compliance.
    """
    save_json_safe(db_path(), data, atomic=True)

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

def mark_news_as_sent(link, title="Sem Título", description=""):
    """
    Registra uma notícia como enviada no database.json (painel Windows e vps_api).

    SÍNCRONA e pesada (lê e regrava o arquivo inteiro): quem está no event loop
    chama via asyncio.to_thread. O push ao Node-RED saiu daqui: era um
    requests.post síncrono no event loop, duplicava o push que o scanner já faz,
    e disparava para cada item do sync_from_discord.
    
    Args:
        link (str): URL da notícia.
        title (str): Título da notícia.
        description (str): Descrição/resumo (opcional, para o dashboard).
    """
    db = load_db()
    
    # Verifica duplicidade antes de adicionar
    if not any(item['link'] == link for item in db.get('sent_news', [])):
        entry = {
            "title": title,
            "link": link,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if description:
            entry["description"] = str(description)[:500]  # Limite para dashboard
        db.setdefault('sent_news', []).append(entry)
        
        if 'stats' not in db:
            db['stats'] = {"total_processed": 0}
            
        db['stats']['total_processed'] = db['stats'].get('total_processed', 0) + 1
        
        save_db(db)
        log.info(f"✅ database.json atualizado: {title[:50]}... (total={len(db['sent_news'])})")
    else:
        log.debug(f"Link já em database.json (duplicado): {link[:60]}...")

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
