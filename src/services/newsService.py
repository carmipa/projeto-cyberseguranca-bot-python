
import logging

log = logging.getLogger("CyberIntel")

def get_latest_security_news():
    """
    Busca as últimas notícias de segurança de fontes confiáveis.
    
    Esta função é usada pelo monitor de ameaças (Monitor Cog) para
    gerar alertas rápidos, independentes do ciclo principal do scanner.
    
    Returns:
        List[Dict]: Lista de dicionários contendo title, link e summary.
    """
    # Feeds confiáveis
    feeds = [
        "https://feeds.feedburner.com/TheHackersNews",
        "https://www.bleepingcomputer.com/feed/"
    ]
    
    news_list = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]: # Pega as 3 últimas de cada
                news_list.append({
                    "title": entry.title,
                    "link": entry.link,
                    "summary": (entry.description[:200] + "...") if hasattr(entry, 'description') else "Sem resumo disponível."
                })
        except Exception as e:
            log.warning(f"Erro ao ler feed {url}: {e}")
            
    return news_list
