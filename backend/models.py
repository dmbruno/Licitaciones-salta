from __future__ import annotations

from pydantic import BaseModel
from datetime import date
from typing import Optional


class Licitacion(BaseModel):
    id: str
    titulo: str
    organismo: str
    tipo: str
    monto: Optional[str] = None
    fecha_publicacion: Optional[date] = None
    fecha_apertura: Optional[date] = None
    vencimiento: Optional[date] = None
    estado: str = "vigente"
    fuente: str
    url_detalle: Optional[str] = None
    url_pliego: Optional[str] = None


class PligoResumen(BaseModel):
    url: str
    texto_raw: str
    resumen: str
    paginas: int
