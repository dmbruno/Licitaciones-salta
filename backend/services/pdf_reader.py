"""
Descarga un PDF desde una URL y extrae texto con pdfplumber.
Devuelve un resumen básico (primeras N palabras + métricas).
"""

from __future__ import annotations

import io
from typing import Optional
import httpx
import pdfplumber
from models import PligoResumen

TIMEOUT = httpx.Timeout(60.0)
MAX_CHARS = 4000  # caracteres máx para el resumen


async def descargar_y_resumir(url: str) -> PligoResumen:
    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; LicitacionesSalta/0.1)"},
    ) as client:
        r = await client.get(url)

    if r.status_code != 200:
        raise ValueError(f"HTTP {r.status_code} al descargar {url}")

    content_type = r.headers.get("content-type", "")
    if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
        raise ValueError(f"La URL no parece ser un PDF (content-type: {content_type})")

    pdf_bytes = r.content
    texto_completo = ""
    paginas = 0

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        paginas = len(pdf.pages)
        partes = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                partes.append(t)
        texto_completo = "\n".join(partes)

    texto_limpio = " ".join(texto_completo.split())  # colapsar whitespace

    resumen = _generar_resumen(texto_limpio)

    return PligoResumen(
        url=url,
        texto_raw=texto_limpio[:MAX_CHARS * 2],
        resumen=resumen,
        paginas=paginas,
    )


def _generar_resumen(texto: str) -> str:
    """
    Resumen básico: extrae secciones clave del pliego.
    Sin LLM — solo heurísticas de texto.
    """
    if not texto:
        return "No se pudo extraer texto del PDF."

    lineas = [l.strip() for l in texto.split(".") if len(l.strip()) > 20]

    # Buscar secciones relevantes
    secciones = {
        "objeto": _buscar_seccion(texto, ["objeto de la licitación", "objeto del llamado", "objeto:"]),
        "monto": _buscar_seccion(texto, ["presupuesto oficial", "monto estimado", "valor estimado", "$"]),
        "plazo": _buscar_seccion(texto, ["plazo de ejecución", "plazo de entrega", "duración del contrato"]),
        "apertura": _buscar_seccion(texto, ["fecha de apertura", "acto de apertura", "apertura de ofertas"]),
        "requisitos": _buscar_seccion(texto, ["requisitos", "condiciones de admisibilidad", "documentación requerida"]),
    }

    partes = []
    if secciones["objeto"]:
        partes.append(f"**Objeto:** {secciones['objeto']}")
    if secciones["monto"]:
        partes.append(f"**Monto/Presupuesto:** {secciones['monto']}")
    if secciones["apertura"]:
        partes.append(f"**Apertura:** {secciones['apertura']}")
    if secciones["plazo"]:
        partes.append(f"**Plazo:** {secciones['plazo']}")
    if secciones["requisitos"]:
        partes.append(f"**Requisitos:** {secciones['requisitos']}")

    if not partes:
        # Fallback: primeros MAX_CHARS caracteres
        return texto[:MAX_CHARS] + ("..." if len(texto) > MAX_CHARS else "")

    return "\n\n".join(partes)


def _buscar_seccion(texto: str, claves: list[str], ventana: int = 300) -> str | None:
    texto_lower = texto.lower()
    for clave in claves:
        idx = texto_lower.find(clave)
        if idx != -1:
            fragmento = texto[idx: idx + ventana]
            # Limpiar y truncar al primer punto o salto de sección
            fragmento = fragmento.split("\n")[0].strip()
            if len(fragmento) > 10:
                return fragmento[:250]
    return None
