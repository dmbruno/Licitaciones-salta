"""
Scraper para boletinoficialsalta.gob.ar

Form (inspeccionado):
  GET  busqueda_avisos.php  → obtener la página
  POST BuscarAvisosNew.php  → resultados

Campos del formulario (nombres exactos del HTML):
  cod_aviso   = código del tipo de aviso (ver tabla abajo)
  temario     = texto libre
  checkbox    = "1" si buscar frases exactas, vacío si no
  nroboletin  = número de boletín (vacío = todos)
  fdesde_p    = fecha desde DD/MM/YYYY
  fhasta_p    = fecha hasta  DD/MM/YYYY

Tipos relevantes (cod_aviso → texto):
  4  → LICITACIONES PUBLICAS
  48 → LICITACIONES
  39 → LICITACIONES PRIVADAS
  5  → CONCURSOS DE PRECIOS
  80 → ANULACIONES DE LICITACIONES

Respuesta: tabla HTML con columnas [Tipo de Aviso, Título, Fecha de Publicación]
  - Cada fila tiene link a instrumento.php?{b64_encoded_id}
  - El PDF del aviso vive en pdfs/{numero_edicion}.pdf (extraído del link de instrumento.php)
"""

from __future__ import annotations

import re
import base64
import hashlib
from datetime import date, datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from scrapers.base import ScraperBase
from models import Licitacion

BASE_URL = "https://boletinoficialsalta.gob.ar"
FORM_URL = f"{BASE_URL}/busqueda_avisos.php"
SEARCH_URL = f"{BASE_URL}/BuscarAvisosNew.php"

# Códigos de tipo de aviso que nos interesan
TIPOS_CODIGOS = [
    ("4",  "Licitación Pública"),
    ("48", "Licitación"),
    ("5",  "Concurso de Precios"),
]


def _make_id(titulo: str, fecha: str) -> str:
    return "boletin:" + hashlib.md5(f"{titulo}{fecha}".encode()).hexdigest()[:10]


def _parse_fecha(texto: str) -> Optional[date]:
    texto = texto.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def _extract_monto(texto: str) -> Optional[str]:
    m = re.search(r"\$\s*([\d\.,]+)", texto)
    return "$" + m.group(1) if m else None


def _extract_pdf_url(instrumento_href: str) -> Optional[str]:
    """
    El link de instrumento.php tiene la forma:
      instrumento.php?{base64_encoded_qs}
    donde el QS decodificado contiene 'data=NNNN'.
    Ejemplo:
      cXdlcnR5dGFibGU9QXwxMDAxMzYyMTAmZGF0YT0yMjE5
      → 'qwertytable=A|100136210&data=2219'
      → PDF: pdfs/2219.pdf
    """
    qs = instrumento_href.split("?")[-1] if "?" in instrumento_href else ""
    if not qs:
        return None
    try:
        padded = qs + "=" * (4 - len(qs) % 4)
        decoded = base64.b64decode(padded).decode("utf-8", errors="replace")
        m = re.search(r"data=(\d+)", decoded)
        if m:
            return f"{BASE_URL}/pdfs/{m.group(1)}.pdf"
    except Exception:
        pass
    return None


async def _fetch_tipo(client, cod: str, tipo_label: str, desde: date, hasta: date) -> list[dict]:
    """Hace el POST para un tipo de aviso y devuelve lista de dicts."""
    post_data = {
        "cod_aviso": cod,
        "temario": "",
        "checkbox": "",
        "nroboletin": "",
        "fdesde_p": desde.strftime("%d/%m/%Y"),
        "fhasta_p": hasta.strftime("%d/%m/%Y"),
    }
    try:
        r = await client.post(SEARCH_URL, data=post_data)
    except Exception:
        return []

    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "lxml")
    tabla = soup.find("table")
    if not tabla:
        return []

    resultados = []
    filas = tabla.find_all("tr")
    for fila in filas[1:]:  # saltar cabecera
        celdas = fila.find_all("td")
        if len(celdas) < 3:
            continue

        titulo = celdas[1].get_text(strip=True)
        fecha_str = celdas[2].get_text(strip=True)
        fecha_pub = _parse_fecha(fecha_str)

        # Link al instrumento
        a = fila.find("a", href=True)
        href = a["href"] if a else ""
        if href and not href.startswith("http"):
            href = BASE_URL + "/" + href.lstrip("/")

        url_pliego = _extract_pdf_url(href) if href else None

        resultados.append({
            "titulo": titulo,
            "tipo": tipo_label,
            "fecha_publicacion": fecha_pub,
            "url_detalle": href or None,
            "url_pliego": url_pliego or None,
        })

    return resultados


class BoletinOficialScraper(ScraperBase):
    fuente = "boletin_oficial"

    async def fetch(self, dias: int = 7) -> list[Licitacion]:
        hoy = date.today()
        desde = hoy - timedelta(days=dias)
        licitaciones: list[Licitacion] = []

        async with self._client() as client:
            for cod, tipo_label in TIPOS_CODIGOS:
                items = await _fetch_tipo(client, cod, tipo_label, desde, hoy)
                for item in items:
                    licitaciones.append(Licitacion(
                        id=_make_id(item["titulo"], str(item.get("fecha_publicacion", ""))),
                        titulo=item["titulo"] or "Sin título",
                        organismo="Provincia de Salta",
                        tipo=item["tipo"],
                        fecha_publicacion=item["fecha_publicacion"],
                        estado="vigente",
                        fuente=self.fuente,
                        url_detalle=item["url_detalle"],
                        url_pliego=item["url_pliego"],
                    ))

        # Deduplicar por id
        seen: set[str] = set()
        unique: list[Licitacion] = []
        for l in licitaciones:
            if l.id not in seen:
                seen.add(l.id)
                unique.append(l)
        return unique
