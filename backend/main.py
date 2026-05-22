from __future__ import annotations

from fastapi import FastAPI, Query, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import date, timedelta
from typing import Optional
import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

from models import Licitacion, PligoResumen
from cache import cache
from auth import verify_password, create_token, decode_token
from database import (
    init_db, get_user, list_users, create_user,
    toggle_user, delete_user, update_ultimo_acceso,
)
from scrapers.municipalidad import MunicipalidadScraper
from scrapers.compras_salta import ComprasSaltaScraper
from scrapers.boletin_oficial import BoletinOficialScraper
from scrapers.comprar_gob import ComprarGobScraper
from services.pdf_reader import descargar_y_resumir

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Licitaciones Salta API", version="0.2.0")

FRONTEND_ORIGINS = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCRAPERS = [
    MunicipalidadScraper(),
    ComprasSaltaScraper(),
    BoletinOficialScraper(),
    ComprarGobScraper(),
]


@app.on_event("startup")
def startup():
    init_db()


# ── Auth helpers ──────────────────────────────────────────────────────────────

security = HTTPBearer()


def require_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")
    user = get_user(payload["sub"])
    if not user or not user["activo"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if not user["es_admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo administradores")
    return user


# ── Auth endpoints ────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
def login(body: LoginBody):
    user = get_user(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")
    if not user["activo"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")
    update_ultimo_acceso(body.username)
    token = create_token(body.username, bool(user["es_admin"]))
    return {
        "access_token": token,
        "token_type":   "bearer",
        "username":     user["username"],
        "nombre":       user["nombre"],
        "es_admin":     bool(user["es_admin"]),
    }


@app.get("/auth/me")
def me(user: dict = Depends(require_user)):
    return {
        "username": user["username"],
        "nombre":   user["nombre"],
        "email":    user["email"],
        "plan":     user["plan"],
        "es_admin": bool(user["es_admin"]),
    }


# ── Admin endpoints ───────────────────────────────────────────────────────────

class CreateUserBody(BaseModel):
    username: str
    password: str
    nombre:   Optional[str] = ""
    email:    Optional[str] = ""
    plan:     Optional[str] = "beta"


@app.get("/admin/users")
def admin_list_users(admin: dict = Depends(require_admin)):
    return list_users()


@app.post("/admin/users", status_code=status.HTTP_201_CREATED)
def admin_create_user(body: CreateUserBody, admin: dict = Depends(require_admin)):
    existing = get_user(body.username)
    if existing:
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    return create_user(body.username, body.password, body.nombre, body.email, body.plan)


@app.patch("/admin/users/{username}/toggle")
def admin_toggle_user(username: str, admin: dict = Depends(require_admin)):
    if username == "admin":
        raise HTTPException(status_code=400, detail="No se puede modificar el admin")
    new_state = toggle_user(username)
    return {"username": username, "activo": new_state}


@app.delete("/admin/users/{username}")
def admin_delete_user(username: str, admin: dict = Depends(require_admin)):
    if username == "admin":
        raise HTTPException(status_code=400, detail="No se puede eliminar el admin")
    delete_user(username)
    return {"ok": True}


# ── API pública (protegida con JWT) ───────────────────────────────────────────

async def _fetch_all(dias: int) -> list[Licitacion]:
    cache_key = f"all:{dias}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    results = await asyncio.gather(
        *[s.fetch(dias=dias) for s in SCRAPERS],
        return_exceptions=True,
    )

    licitaciones: list[Licitacion] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        licitaciones.extend(r)

    licitaciones.sort(key=lambda x: x.fecha_apertura or date.min, reverse=True)
    cache.set(cache_key, licitaciones)
    return licitaciones


@app.get("/api/licitaciones", response_model=list[Licitacion])
async def get_licitaciones(
    dias: int = Query(default=7, ge=1, le=90),
    user: dict = Depends(require_user),
):
    return await _fetch_all(dias)


@app.get("/api/licitaciones/search", response_model=list[Licitacion])
async def search_licitaciones(
    q: str = Query(min_length=2),
    dias: int = Query(default=30, ge=1, le=90),
    user: dict = Depends(require_user),
):
    all_lics = await _fetch_all(dias)
    q_lower = q.lower()
    return [l for l in all_lics if q_lower in l.titulo.lower() or q_lower in l.organismo.lower()]


@app.get("/api/licitaciones/vencimientos", response_model=list[Licitacion])
async def get_vencimientos(
    dias: int = Query(default=7, ge=1, le=30),
    user: dict = Depends(require_user),
):
    all_lics = await _fetch_all(dias=90)
    hoy = date.today()
    limite = hoy + timedelta(days=dias)
    return [l for l in all_lics if l.vencimiento and hoy <= l.vencimiento <= limite]


@app.get("/api/pliego", response_model=PligoResumen)
async def get_pliego(
    url: str = Query(min_length=10),
    user: dict = Depends(require_user),
):
    cache_key = f"pliego:{url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        resumen = await descargar_y_resumir(url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    cache.set(cache_key, resumen, ttl=3600)
    return resumen


@app.delete("/api/cache")
async def clear_cache(user: dict = Depends(require_admin)):
    cache.clear()
    return {"ok": True}


@app.get("/api/status")
async def status_endpoint(user: dict = Depends(require_user)):
    return {"scrapers": [s.__class__.__name__ for s in SCRAPERS], "ok": True}
