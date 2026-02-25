
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.dbService import init_db, mark_news_as_sent, get_db_stats, is_news_sent

def test_json_db():
    print("Testando DB JSON...")
    
    # Inicializa
    init_db()
    
    # Simula adicionar notícia
    link = "https://example.com/test-news"
    title = "Test News CVE-9999"
    
    if not is_news_sent(link):
        print(f"Marcando notícia como enviada: {title}")
        mark_news_as_sent(link, title)
    else:
        print("Notícia já estava marcada.")
        
    # Verifica stats
    total, last = get_db_stats()
    print(f"Stats: Total={total}, Última={last}")
    
    # Verifica se arquivo existe
    if os.path.exists("data/database.json"):
        print("✅ Arquivo data/database.json existe!")
    else:
        print("❌ Arquivo JSON não encontrado.")

if __name__ == "__main__":
    test_json_db()
