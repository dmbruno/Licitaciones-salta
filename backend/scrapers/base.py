from abc import ABC, abstractmethod
import httpx
from models import Licitacion

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

TIMEOUT = httpx.Timeout(30.0)


class ScraperBase(ABC):
    fuente: str = ""

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )

    @abstractmethod
    async def fetch(self, dias: int = 7) -> list[Licitacion]:
        ...
