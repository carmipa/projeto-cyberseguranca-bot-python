"""
Smoke tests básicos para verificar que o projeto está configurado corretamente.
Não testa lógica complexa para evitar dependências do Discord token.
"""
import os
import json


def test_config_files_exist():
    """Verifica que arquivos de configuração existem."""
    assert os.path.exists("data/sources.json"), "data/sources.json deve existir"
    assert os.path.exists("app/settings.py"), "app/settings.py deve existir"
    assert os.path.exists("app/main.py"), "app/main.py deve existir"


def test_sources_json_structure():
    """Verifica estrutura básica do sources.json."""
    with open("data/sources.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert isinstance(data, dict), "sources.json deve ser um objeto"
    
    # Deve ter pelo menos rss_feeds ou youtube_feeds
    has_feeds = "rss_feeds" in data or "youtube_feeds" in data
    assert has_feeds, "Deve ter pelo menos rss_feeds ou youtube_feeds"
    
    # Se tiver rss_feeds, deve ser lista (formato simples) ou dict (formato agrupado).
    if "rss_feeds" in data:
        assert isinstance(data["rss_feeds"], (list, dict)), "rss_feeds deve ser lista ou objeto agrupado"
    
    # Se tiver youtube_feeds, deve ser lista (simples) ou dict (agrupado).
    if "youtube_feeds" in data:
        assert isinstance(data["youtube_feeds"], (list, dict)), "youtube_feeds deve ser lista ou objeto agrupado"


def test_no_invalid_youtube_urls():
    """Nenhuma fonte ATIVA do YouTube pode ser handle (@) ou página: só feed Atom por channel_id."""
    with open("data/sources.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    grupos = data.get("youtube_feeds", {})
    itens = [i for g in grupos.values() for i in g] if isinstance(grupos, dict) else grupos
    assert itens, "catálogo sem fontes do YouTube: o teste não teria o que verificar"
    for it in itens:
        url = it["url"] if isinstance(it, dict) else it
        if isinstance(it, dict) and it.get("enabled") is False:
            continue
        assert "@" not in url and "/feeds/videos.xml?channel_id=" in url, f"YouTube URL inválida: {url}"


def test_requirements_has_dependencies():
    """Verifica que requirements.txt tem dependências essenciais."""
    # Tenta diferentes encodings (requirements pode ser UTF-16 no Windows)
    for encoding in ["utf-8", "utf-16", "latin-1"]:
        try:
            with open("deploy/requirements.txt", "r", encoding=encoding) as f:
                content = f.read().lower()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    assert "discord" in content, "deploy/requirements.txt deve incluir discord.py"
    assert "feedparser" in content, "deploy/requirements.txt deve incluir feedparser"
    assert "aiohttp" in content, "deploy/requirements.txt deve incluir aiohttp"


def test_scanner_has_ssl_fix():
    """Verifica que core/scanner.py usa certifi para SSL."""
    with open("core/scanner.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Deve usar certifi
    assert "certifi" in content, "core/scanner.py deve importar certifi para SSL seguro"
    
    # NÃO deve ter CERT_NONE (inseguro)
    assert "CERT_NONE" not in content, "core/scanner.py não deve usar CERT_NONE (inseguro)"

