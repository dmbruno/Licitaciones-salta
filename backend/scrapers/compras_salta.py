"""
Scraper para compras.salta.gob.ar

Estructura real (inspeccionada):
- Listado paginado: GET /publico/publicacionactual/panelfiltrobusqueda/{offset}
  Stride de 5 por página: offset 1, 5, 10, 15 ...
- Cada ítem es <article class="publicacion"> con:
    - encabezado: tipo+número (span sin float), fecha/hora apertura (span float-right)
    - cuerpo: divs .publicacion-fila con .publicacion-fila-titulo / .publicacion-fila-descripcion
    - botón Ver más: onclick="window.location = 'publico/publicacionactual/verpublicacion1/{id}/1'"
"""

from __future__ import annotations

import re
import hashlib
from datetime import date, datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from scrapers.base import ScraperBase
from models import Licitacion

BASE_URL = "https://compras.salta.gob.ar"
LIST_URL = f"{BASE_URL}/publico/publicacionactual/panelfiltrobusqueda"
DETAIL_PREFIX = f"{BASE_URL}/publico/publicacionactual/verpublicacion1"


def _parse_fecha(texto: str) -> Optional[date]:
    m = re.search(r"(\d{2}/\d{2}/\d{4})", texto)
    if not m:
        return None
    try:
        d = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        if d.year <= 2099:
            return d
        # Año > 2099: el sitio usa año de 2 dígitos y los dígitos de la hora
        # se concatenaron al año (ej: "22/06/22 00:30" → "22/06/2200")
        parts = m.group(1).split("/")
        return datetime.strptime(f"{parts[0]}/{parts[1]}/{parts[2][:2]}", "%d/%m/%y").date()
    except ValueError:
        return None


def _make_id(raw: str) -> str:
    return "compras_salta:" + hashlib.md5(raw.encode()).hexdigest()[:10]


def _campo(art, label: str) -> str:
    """Extrae el texto de la publicacion-fila-descripcion cuyo titulo coincide."""
    for fila in art.find_all("div", class_="publicacion-fila"):
        titulo_el = fila.find("span", class_="publicacion-fila-titulo")
        desc_el   = fila.find("span", class_="publicacion-fila-descripcion")
        if titulo_el and desc_el:
            if label.lower() in titulo_el.get_text(strip=True).lower():
                return desc_el.get_text(" ", strip=True)
    return ""


def _parse_article(art) -> Optional[dict]:
    # ── Encabezado ──────────────────────────────────────────────────────────
    encab = art.find("div", class_="publicacion-encabezado")
    if not encab:
        return None

    fecha_apertura: Optional[date] = None
    tipo_numero = ""

    for span in encab.find_all("span", recursive=False):
        style = span.get("style", "")
        if "float" in style:
            fecha_apertura = _parse_fecha(span.get_text(" "))
        else:
            txt = span.get_text(strip=True)
            if txt:
                tipo_numero = txt   # e.g. "Contratación Abreviada N° 078/26"

    # ── Campos del cuerpo ───────────────────────────────────────────────────
    objeto    = _campo(art, "Objeto")
    organismo = _campo(art, "Organismo")
    expte     = _campo(art, "Expte")

    # url_pliego: solo si hay <a> real en la fila de pliego
    url_pliego: Optional[str] = None
    for fila in art.find_all("div", class_="publicacion-fila"):
        titulo_el = fila.find("span", class_="publicacion-fila-titulo")
        if titulo_el and "pliego" in titulo_el.get_text(strip=True).lower():
            a = fila.find("a", href=True)
            if a:
                href = a["href"]
                url_pliego = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
            break

    # url_detalle: extraída del onclick del botón "Ver más"
    url_detalle: Optional[str] = None
    btn = art.find("input", class_="clsSubmit")
    if btn:
        onclick = btn.get("onclick", "")
        m = re.search(r"verpublicacion1/(\d+)/", onclick)
        if m:
            url_detalle = f"{DETAIL_PREFIX}/{m.group(1)}/1"

    # Tipo: la parte antes de "N°"
    tipo = "Otro"
    m_tipo = re.match(r"(.+?)\s+N[°º]?\s*[\d/\-]+", tipo_numero)
    if m_tipo:
        tipo = m_tipo.group(1).strip()
    elif tipo_numero:
        tipo = tipo_numero

    titulo = objeto or tipo_numero or tipo

    if not titulo:
        return None

    return {
        "titulo":       titulo,
        "tipo":         tipo,
        "organismo":    organismo or "Provincia de Salta",
        "expte":        expte,
        "fecha_apertura": fecha_apertura,
        "url_pliego":   url_pliego,
        "url_detalle":  url_detalle,
        "id_raw":       tipo_numero or titulo,
    }


class ComprasSaltaScraper(ScraperBase):
    fuente = "compras_salta"

    async def fetch(self, dias: int = 7) -> list[Licitacion]:
        cutoff = date.today() - timedelta(days=dias)
        licitaciones: list[Licitacion] = []
        seen_ids: set[str] = set()

        async with self._client() as client:
            # La paginación real usa stride 5: offset 1, 5, 10, 15...
            offsets = [1] + list(range(5, 305, 5))  # hasta ~300 items

            for offset in offsets:
                url = f"{LIST_URL}/{offset}"
                try:
                    r = await client.get(url)
                except Exception:
                    break

                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                articles = soup.find_all("article", class_="publicacion")

                if not articles:
                    break

                found_any = False
                found_old = False

                for art in articles:
                    data = _parse_article(art)
                    if not data:
                        continue

                    fa = data["fecha_apertura"]
                    if fa and fa < cutoff:
                        found_old = True
                        continue

                    found_any = True
                    id_str = _make_id(data["id_raw"])
                    if id_str in seen_ids:
                        continue
                    seen_ids.add(id_str)

                    licitaciones.append(Licitacion(
                        id=id_str,
                        titulo=data["titulo"],
                        organismo=data["organismo"],
                        tipo=data["tipo"],
                        fecha_apertura=fa,
                        estado="vigente",
                        fuente=self.fuente,
                        url_pliego=data["url_pliego"],
                        url_detalle=data["url_detalle"],
                    ))

                if not found_any or found_old:
                    break

        return licitaciones
