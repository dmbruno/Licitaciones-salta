"""
Scraper para municipalidadsalta.gob.ar/oficina-contrataciones/

Estructura del sitio (WordPress):
- Listado: /oficina-contrataciones/page/{N}/
- Cada entrada: <article> con título, expediente, fecha, link a detalle
- Detalle: /contrataciones/{slug}/ — contiene links a PDFs
"""

from __future__ import annotations

import re
import hashlib
from datetime import date, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from scrapers.base import ScraperBase
from models import Licitacion

BASE_URL = "https://municipalidadsalta.gob.ar"
LIST_URL = f"{BASE_URL}/oficina-contrataciones/"

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _parse_fecha(texto: str) -> date | None:
    """Parsea 'DD de mes de YYYY' → date."""
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", texto.lower())
    if not m:
        return None
    try:
        return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
    except (KeyError, ValueError):
        return None


def _detectar_tipo(titulo: str) -> str:
    t = titulo.upper()
    if "LICITACIÓN PÚBLICA" in t or "L.P." in t or "LP " in t:
        return "Licitación Pública"
    if "LICITACIÓN PRIVADA" in t:
        return "Licitación Privada"
    if "CONCURSO" in t:
        return "Concurso de Precios"
    if "CONTRATACIÓN" in t or "ADJUDICACIÓN" in t:
        return "Contratación Directa"
    return "Otro"


def _make_id(url: str) -> str:
    return "municipalidad:" + hashlib.md5(url.encode()).hexdigest()[:10]


def _parse_articulo(article) -> dict | None:
    """Extrae datos de un <article> del listado."""
    title_tag = article.find(["h1", "h2", "h3", "h4", "a"])
    if not title_tag:
        return None

    titulo = title_tag.get_text(strip=True)
    if not titulo:
        return None

    link_tag = article.find("a", href=True)
    url_detalle = link_tag["href"] if link_tag else None

    # Fecha publicación (texto tipo "21 de mayo de 2026")
    fecha_pub = None
    for tag in article.find_all(["time", "span", "p", "div"]):
        texto = tag.get_text(strip=True)
        f = _parse_fecha(texto)
        if f:
            fecha_pub = f
            break

    # Estado: SUSPENDIDA aparece en el título o en badges
    estado = "vigente"
    texto_completo = article.get_text(" ", strip=True).upper()
    if "SUSPENDIDA" in texto_completo or "SUSPENDIDO" in texto_completo:
        estado = "suspendida"

    # Organismo: buscar en párrafos de descripción
    organismo = "Municipalidad de Salta"
    for p in article.find_all("p"):
        t = p.get_text(strip=True)
        if "SECRETARÍA" in t.upper() or "DIRECCIÓN" in t.upper() or "UNIDAD" in t.upper():
            organismo = t[:120]
            break

    return {
        "titulo": titulo,
        "url_detalle": url_detalle,
        "fecha_publicacion": fecha_pub,
        "estado": estado,
        "organismo": organismo,
    }


async def _fetch_pdf_from_detail(client, url: str) -> str | None:
    """Visita la página de detalle y extrae el primer link a PDF."""
    try:
        r = await client.get(url)
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf") or "pdf" in href.lower():
                if href.startswith("http"):
                    return href
                return BASE_URL + href
    except Exception:
        return None
    return None


class MunicipalidadScraper(ScraperBase):
    fuente = "municipalidad"

    async def fetch(self, dias: int = 7) -> list[Licitacion]:
        cutoff = date.today() - timedelta(days=dias)
        licitaciones: list[Licitacion] = []
        pagina = 1

        async with self._client() as client:
            while True:
                url = LIST_URL if pagina == 1 else f"{LIST_URL}page/{pagina}/"
                try:
                    r = await client.get(url)
                except Exception:
                    break

                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                articles = soup.find_all("article")

                if not articles:
                    break

                found_old = False
                for art in articles:
                    data = _parse_articulo(art)
                    if not data:
                        continue

                    fp = data["fecha_publicacion"]
                    if fp and fp < cutoff:
                        found_old = True
                        continue

                    url_detalle = data["url_detalle"]
                    url_pliego = None
                    if url_detalle:
                        url_pliego = await _fetch_pdf_from_detail(client, url_detalle)

                    licitaciones.append(Licitacion(
                        id=_make_id(url_detalle or data["titulo"]),
                        titulo=data["titulo"],
                        organismo=data["organismo"],
                        tipo=_detectar_tipo(data["titulo"]),
                        fecha_publicacion=data["fecha_publicacion"],
                        fecha_apertura=None,
                        vencimiento=None,
                        estado=data["estado"],
                        fuente=self.fuente,
                        url_detalle=url_detalle,
                        url_pliego=url_pliego,
                    ))

                # Si la página tiene solo artículos viejos y pasamos el cutoff, paramos
                if found_old and all(
                    (d := _parse_articulo(a)) and d.get("fecha_publicacion") and d["fecha_publicacion"] < cutoff
                    for a in articles if _parse_articulo(a)
                ):
                    break

                # Si no hay link "Siguiente Página", terminamos
                siguiente = soup.find("a", string=re.compile(r"siguiente|next", re.I))
                if not siguiente:
                    break

                pagina += 1
                if pagina > 10:  # máximo 10 páginas para no saturar
                    break

        return licitaciones
