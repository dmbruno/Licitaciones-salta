# Migración SQLite → Supabase

Guía paso a paso para reemplazar la base de datos SQLite (efímera en Render) por Supabase (PostgreSQL persistente en la nube).

---

## Por qué migrar

Render Free usa disco efímero: cada redeploy borra `users.db` y con ella todos los usuarios y suscripciones. Supabase ofrece PostgreSQL gratuito con persistencia real.

---

## Paso 1 — Crear el proyecto en Supabase

1. Ir a [supabase.com](https://supabase.com) → **New project**
2. Elegir nombre: `licitaciones-salta`
3. Elegir región: **South America (São Paulo)** — la más cercana a Salta
4. Generar una contraseña segura para la DB (guardala, la vas a necesitar)
5. Esperar ~2 minutos a que el proyecto se cree

---

## Paso 2 — Crear la tabla en Supabase

En el panel de Supabase → **SQL Editor** → pegar y ejecutar:

```sql
CREATE TABLE IF NOT EXISTS users (
    id                SERIAL PRIMARY KEY,
    username          TEXT    UNIQUE NOT NULL,
    email             TEXT    DEFAULT '',
    password_hash     TEXT    NOT NULL,
    nombre            TEXT    DEFAULT '',
    plan              TEXT    DEFAULT 'beta',
    activo            BOOLEAN DEFAULT TRUE,
    es_admin          BOOLEAN DEFAULT FALSE,
    fecha_creacion    TIMESTAMP DEFAULT NOW(),
    ultimo_acceso     TEXT,
    fecha_vencimiento TEXT
);
```

---

## Paso 3 — Obtener la connection string

En Supabase → **Project Settings → Database → Connection string → URI**

Hay dos opciones:

| Modo | URL | Cuándo usar |
|---|---|---|
| **Direct** | `postgresql://postgres:[pass]@db.[ref].supabase.co:5432/postgres` | Servidor tradicional (Render) |
| **Pooler (Session)** | `postgresql://postgres.[ref]:[pass]@aws-0-sa-east-1.pooler.supabase.com:5432/postgres` | Serverless / muchas conexiones |

Para Render usar **Direct** o **Pooler Session mode** (puerto 5432, no 6543).

Guardar la URL — va a ir como variable de entorno `DATABASE_URL`.

---

## Paso 4 — Actualizar `requirements.txt`

Agregar `psycopg2-binary` y quitar dependencia implícita de sqlite3 (es stdlib, no necesita estar listado):

```
fastapi==0.115.5
uvicorn[standard]==0.32.1
httpx==0.28.1
beautifulsoup4==4.12.3
lxml==5.3.0
pdfplumber==0.11.4
python-dotenv==1.0.1
pydantic==2.11.5
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.0.1
psycopg2-binary==2.9.9
```

---

## Paso 5 — Reescribir `database.py`

Reemplazar el archivo completo:

```python
from __future__ import annotations

import os
import psycopg2
import psycopg2.extras
from datetime import datetime, date, timedelta
from typing import Optional

DATABASE_URL = os.getenv("DATABASE_URL")


def _conn():
    c = psycopg2.connect(DATABASE_URL)
    c.autocommit = False
    return c


def init_db() -> None:
    # La tabla ya existe en Supabase (creada en el Paso 2)
    # Solo aseguramos que el admin exista
    _ensure_admin()


def _ensure_admin() -> None:
    from auth import hash_password
    admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = 'admin'")
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO users (username,email,password_hash,nombre,es_admin) VALUES (%s,%s,%s,%s,%s)",
                    ("admin", "dmbruno61@gmail.com", hash_password(admin_pass), "Diego Bruno", True),
                )
        c.commit()


def _row_to_dict(cur, row) -> dict:
    cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


def get_user(username: str) -> Optional[dict]:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            return _row_to_dict(cur, row) if row else None


def list_users() -> list[dict]:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                SELECT id, username, email, nombre, plan,
                       activo, es_admin, fecha_creacion, ultimo_acceso, fecha_vencimiento
                FROM users ORDER BY fecha_creacion DESC
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def create_user(
    username: str,
    password: str,
    nombre: str = "",
    email: str = "",
    plan: str = "beta",
) -> dict:
    from auth import hash_password
    vencimiento = (date.today() + timedelta(days=30)).isoformat()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """INSERT INTO users (username,email,password_hash,nombre,plan,fecha_vencimiento)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id,username,email,nombre,plan,activo,es_admin,fecha_creacion,fecha_vencimiento""",
                (username, email, hash_password(password), nombre, plan, vencimiento),
            )
            row = cur.fetchone()
            result = _row_to_dict(cur, row)
        c.commit()
    return result


def toggle_user(username: str) -> bool:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT activo FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            if not row:
                return False
            new_state = not row[0]
            cur.execute("UPDATE users SET activo = %s WHERE username = %s", (new_state, username))
        c.commit()
    return new_state


def renew_user(username: str) -> str:
    nueva_fecha = (date.today() + timedelta(days=30)).isoformat()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE users SET activo = TRUE, fecha_vencimiento = %s WHERE username = %s AND es_admin = FALSE",
                (nueva_fecha, username),
            )
        c.commit()
    return nueva_fecha


def pause_expired_user(username: str) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("UPDATE users SET activo = FALSE WHERE username = %s", (username,))
        c.commit()


def delete_user(username: str) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s AND es_admin = FALSE", (username,))
        c.commit()


def update_ultimo_acceso(username: str) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE users SET ultimo_acceso = %s WHERE username = %s",
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M"), username),
            )
        c.commit()
```

---

## Paso 6 — Actualizar variables de entorno

### En `.env` local (para probar):
```
DATABASE_URL=postgresql://postgres:[tu-password]@db.[tu-ref].supabase.co:5432/postgres
```

### En Render (producción):
1. Ir a Render → tu servicio → **Environment**
2. Agregar variable: `DATABASE_URL` = (tu connection string de Supabase)
3. Las otras variables (`SECRET_KEY`, `ADMIN_PASSWORD`, etc.) se mantienen igual

---

## Paso 7 — Migrar usuarios existentes (si los hay)

Si ya tenés usuarios en SQLite que querés conservar, antes de tirar el servidor actual:

```bash
# 1. Exportar desde SQLite
cd backend
python -c "
import sqlite3, json
c = sqlite3.connect('users.db')
c.row_factory = sqlite3.Row
rows = c.execute('SELECT * FROM users').fetchall()
data = [dict(r) for r in rows]
print(json.dumps(data, indent=2))
" > usuarios_backup.json

# 2. Revisar el JSON generado

# 3. Insertar en Supabase via SQL Editor
# (copiar los datos manualmente o escribir un script de inserción)
```

Para usuarios beta sin datos críticos, lo más simple es recrearlos directamente desde el panel admin después de la migración.

---

## Paso 8 — Commitear y deployar

```bash
git add backend/requirements.txt backend/database.py
git commit -m "feat: migrate database from SQLite to Supabase (PostgreSQL)"
git push origin main
```

Render va a detectar el push y redeploy automáticamente con la nueva DB.

---

## Paso 9 — Verificar

1. Ir a la URL del backend: `https://licitaciones-salta-api.onrender.com/docs`
2. Probar `POST /auth/login` con admin
3. En Supabase → **Table Editor → users**: verificar que el usuario admin se creó
4. Probar crear un usuario desde el panel admin
5. Verificar que persiste después de un redeploy

---

## Notas importantes

- **Supabase Free**: 500MB de storage, suficiente para miles de usuarios. Sin límite de tiempo (no expira como el free de Heroku).
- **Conexiones**: el free de Supabase permite hasta 60 conexiones directas. Si en el futuro el backend escala a múltiples workers, usar el **Pooler** (puerto 6543, modo Transaction).
- **Backups**: Supabase hace backups diarios automáticos en el plan Pro ($25/mes). En free, hacer backups manuales con el SQL Editor → **Export**.
- **RLS (Row Level Security)**: Supabase lo habilita por defecto. Como accedemos con la connection string directa (rol `postgres`), no afecta. No activar políticas RLS para esta tabla a menos que uses el cliente JS de Supabase.
