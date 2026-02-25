
import sys
import os

# Adiciona o diretório raiz ao path para importar os módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.newsService import get_latest_security_news

def test_news_service():
    print("Testando serviço de notícias...")
    news = get_latest_security_news()
    
    if not news:
        print("❌ Nenhuma notícia retornada (pode ser problema de rede ou feed vazio).")
        return

    print(f"✅ Recebidas {len(news)} notícias:")
    for item in news:
        print(f"- {item['title']} ({item['link']})")

if __name__ == "__main__":
    test_news_service()
