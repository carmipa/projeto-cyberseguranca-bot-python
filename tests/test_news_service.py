import asyncio

import pytest

from src.services.newsService import get_latest_security_news


@pytest.mark.network
def test_news_service():
    news = asyncio.run(get_latest_security_news())
    assert isinstance(news, list)
    for item in news:
        assert item["link"].startswith(("http://", "https://"))
