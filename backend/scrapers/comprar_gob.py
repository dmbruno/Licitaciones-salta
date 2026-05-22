"""
Scraper para comprar.gob.ar — licitaciones nacionales filtradas por Salta

Estrategia (inspeccionada):
  1. GET  BuscarAvanzado.aspx        → obtener ViewState + ScriptManager ID
  2. POST BuscarAvanzado.aspx        → búsqueda UpdatePanel con:
       - txtNombrePliego = "Salta"
       - ddlJurisdicion  = -2 (todas)
       - rango de fechas de apertura
       - __ASYNCPOST = true  /  ScriptManager header
  3. Parsear UpdatePanel1 (ctl00_CPH1_UpdatePanel1) → tabla de resultados
  4. Filtrar filas donde "salta" aparece en Unidad Ejecutora o SAF
  5. Paginar via PostBack de la tabla interna

Panel de resultados: ctl00_CPH1_UpdatePanel1
Tabla cols: Número proceso | Expediente | Nombre | Tipo | Fecha apertura | Estado | Unidad Ejecutora | SAF

Jurisdicción UNSAL (id=1544): Universidad Nacional de Salta
"""

from __future__ import annotations

import re
import hashlib
from datetime import date, datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from scrapers.base import ScraperBase, HEADERS
from models import Licitacion

BASE_URL    = "https://comprar.gob.ar"
BUSCAR_URL  = f"{BASE_URL}/BuscarAvanzado.aspx"

GRID_PANEL_ID = "ctl00_CPH1_UpdatePanel1"
GRID_CTRL_ID  = "ctl00$CPH1$GridListaProcesosAvanzado"   # probable; fallback regex

AJAX_HEADERS = {
    **HEADERS,
    "X-MicrosoftAjax": "Delta=true",
    "Content-Type": "application/x-www-form-urlencoded",
}


def _make_id(numero: str) -> str:
    return "comprar_gob:" + hashlib.md5(numero.encode()).hexdigest()[:10]


def _parse_fecha(texto: str) -> Optional[date]:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def _extract_viewstate(soup: BeautifulSoup) -> dict:
    d: dict[str, str] = {}
    for nm in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
        tag = soup.find("input", {"name": nm})
        d[nm] = tag.get("value", "") if tag else ""
    d.setdefault("__EVENTTARGET", "")
    d.setdefault("__EVENTARGUMENT", "")
    return d


def _find_scriptmanager_id(html: str) -> str:
    m = re.search(r"PageRequestManager\._initialize\('([^']+)'", html)
    return m.group(1) if m else "ctl00$ScriptManager1"


def _parse_update_panel(raw: str) -> dict[str, str]:
    """Parsea respuesta UpdatePanel: length|updatePanel|id|content|..."""
    panels: dict[str, str] = {}
    pattern = re.compile(r"(\d+)\|updatePanel\|([^\|]+)\|")
    for m in pattern.finditer(raw):
        length = int(m.group(1))
        panel_id = m.group(2)
        start = m.end()
        panels[panel_id] = raw[start: start + length]
    return panels


def _parse_tabla_avanzada(html_panel: str, cutoff: Optional[date] = None) -> list[Licitacion]:
    soup = BeautifulSoup(html_panel, "lxml")
    tabla = soup.find("table")
    if not tabla:
        return []

    resultados: list[Licitacion] = []
    filas = tabla.find_all("tr")
    for fila in filas[1:]:
        celdas = fila.find_all("td")
        if len(celdas) < 6:
            continue

        def cel(i: int) -> str:
            return celdas[i].get_text(strip=True) if i < len(celdas) else ""

        numero        = cel(0)
        nombre        = cel(2)
        tipo          = cel(3)
        fecha_str     = cel(4)
        estado_raw    = cel(5)
        unidad        = cel(6)
        saf           = cel(7)

        # Verificar que "salta" aparece en algún campo (el servidor filtra por nombre,
        # pero queremos confirmar relevancia)
        texto_fila = fila.get_text(" ", strip=True)
        if "salta" not in texto_fila.lower():
            continue

        fecha_apertura = _parse_fecha(fecha_str)

        url_detalle: Optional[str] = None
        a = fila.find("a", href=True)
        if a:
            href = a["href"]
            if href.startswith("http"):
                url_detalle = href
            elif not href.startswith("javascript"):
                url_detalle = BASE_URL + "/" + href.lstrip("/")

        resultados.append(Licitacion(
            id=_make_id(numero or nombre),
            titulo=nombre or f"Proceso {numero}",
            organismo=unidad or saf or "Administración Nacional",
            tipo=tipo or "Licitación Nacional",
            fecha_apertura=fecha_apertura,
            estado=estado_raw.lower() if estado_raw else "vigente",
            fuente="comprar_gob",
            url_detalle=url_detalle,
        ))

    return resultados


def _panel_has_next(html_panel: str, current_page: int) -> bool:
    """True si hay un link a la página siguiente en el paginador del panel."""
    m = re.search(rf"Page\${current_page + 1}", html_panel)
    return m is not None


class ComprarGobScraper(ScraperBase):
    fuente = "comprar_gob"

    async def fetch(self, dias: int = 7) -> list[Licitacion]:
        cutoff = date.today() - timedelta(days=dias)
        hasta  = date.today() + timedelta(days=30)
        licitaciones: list[Licitacion] = []

        async with self._client() as client:
            # 1. GET inicial para ViewState y ScriptManager
            try:
                r0 = await client.get(BUSCAR_URL)
            except Exception:
                return []

            if r0.status_code != 200:
                return []

            soup0 = BeautifulSoup(r0.text, "lxml")
            vs = _extract_viewstate(soup0)
            sm_id = _find_scriptmanager_id(r0.text)

            base_post = {
                **vs,
                "__ASYNCPOST": "true",
                sm_id: f"{sm_id}|ctl00$CPH1$btnListarPliegoAvanzado",
                "__EVENTTARGET": "ctl00$CPH1$btnListarPliegoAvanzado",
                "__EVENTARGUMENT": "",
                "ctl00$CPH1$txtNombrePliego": "Salta",
                "ctl00$CPH1$ddlJurisdicion": "-2",
                "ctl00$CPH1$ddlUnidadEjecutora": "-2",
                "ctl00$CPH1$ddlTipoProceso": "-2",
                "ctl00$CPH1$ddlEstadoProceso": "6",   # 6 = Publicado (activo)
                "ctl00$CPH1$ddlRubro": "-2",
            }

            # 2. Búsqueda inicial
            try:
                r1 = await client.post(BUSCAR_URL, data=base_post, headers={
                    "X-MicrosoftAjax": "Delta=true",
                    "X-Requested-With": "XMLHttpRequest",
                })
            except Exception:
                return []

            if r1.status_code != 200:
                return []

            panels = _parse_update_panel(r1.text)
            panel_html = panels.get(GRID_PANEL_ID, "")
            if not panel_html:
                return []

            licitaciones.extend(_parse_tabla_avanzada(panel_html))

            # Actualizar ViewState desde la respuesta UpdatePanel
            vs_m = re.search(r"\d+\|hiddenField\|__VIEWSTATE\|([^\|]+)\|", r1.text)
            if vs_m:
                vs["__VIEWSTATE"] = vs_m.group(1)

            # 3. Paginación del grid (máx 5 páginas)
            for pagina in range(2, 7):
                if not _panel_has_next(panel_html, pagina - 1):
                    break

                grid_ctrl = self._find_grid_ctrl(panel_html)
                page_post = {
                    **vs,
                    "__ASYNCPOST": "true",
                    sm_id: f"{sm_id}|{grid_ctrl}",
                    "__EVENTTARGET": grid_ctrl,
                    "__EVENTARGUMENT": f"Page${pagina}",
                    "ctl00$CPH1$txtNombrePliego": "Salta",
                    "ctl00$CPH1$ddlJurisdicion": "-2",
                    "ctl00$CPH1$ddlUnidadEjecutora": "-2",
                    "ctl00$CPH1$ddlTipoProceso": "-2",
                    "ctl00$CPH1$ddlEstadoProceso": "6",
                    "ctl00$CPH1$ddlRubro": "-2",
                }
                try:
                    rp = await client.post(BUSCAR_URL, data=page_post, headers={
                        "X-MicrosoftAjax": "Delta=true",
                    })
                except Exception:
                    break

                panels = _parse_update_panel(rp.text)
                panel_html = panels.get(GRID_PANEL_ID, "")
                if not panel_html:
                    break

                nuevas = _parse_tabla_avanzada(panel_html)
                if not nuevas:
                    break
                licitaciones.extend(nuevas)

                vs_m = re.search(r"\d+\|hiddenField\|__VIEWSTATE\|([^\|]+)\|", rp.text)
                if vs_m:
                    vs["__VIEWSTATE"] = vs_m.group(1)

        return licitaciones

    def _find_grid_ctrl(self, panel_html: str) -> str:
        """Detecta el ID del control GridView en el panel."""
        m = re.search(r"__doPostBack\('(ctl00[^']*Grid[^']*)'", panel_html)
        return m.group(1) if m else GRID_CTRL_ID
