import json

from src.services import dbService


def test_json_db(dados_isolados, monkeypatch):
    """database.json nasce, registra a notícia uma vez só e grava no DATA_DIR vigente."""
    monkeypatch.setattr(dbService, "notify_nodered", lambda item: None)
    dbService.init_db()
    link = "https://example.com/test-news"
    assert not dbService.is_news_sent(link)
    dbService.mark_news_as_sent(link, "Test News CVE-9999")
    dbService.mark_news_as_sent(link, "Test News CVE-9999")
    assert dbService.is_news_sent(link)
    total, last = dbService.get_db_stats()
    assert total == 1
    assert last != "N/A"
    gravado = json.loads((dados_isolados / "database.json").read_text(encoding="utf-8"))
    assert [n["link"] for n in gravado["sent_news"]] == [link]
