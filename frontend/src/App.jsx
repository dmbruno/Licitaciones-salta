import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { getLicitaciones, getPliego, clearCache } from "./api";
import Login from "./Login";
import Admin from "./Admin";
import "./App.css";

// ─── Auth gate ───────────────────────────────────────────────────────────────

function parseStoredUser() {
  try { return JSON.parse(localStorage.getItem("ls_user") || "null"); }
  catch { return null; }
}

function AuthGate() {
  const [user, setUser] = useState(parseStoredUser);
  const [view, setView] = useState(() => {
    const u = parseStoredUser();
    return (u?.es_admin && window.location.hash === "#admin") ? "admin" : "dashboard";
  });

  function handleLogin(data) {
    const u = { username: data.username, nombre: data.nombre, es_admin: data.es_admin };
    localStorage.setItem("ls_user", JSON.stringify(u));
    setUser(u);
    setView("dashboard");
    window.location.hash = "";
  }

  function handleLogout() {
    localStorage.removeItem("ls_token");
    localStorage.removeItem("ls_user");
    window.location.hash = "";
    setUser(null);
    setView("dashboard");
  }

  function goAdmin() {
    window.location.hash = "#admin";
    setView("admin");
  }

  function goDashboard() {
    window.location.hash = "";
    setView("dashboard");
  }

  if (!user) return <Login onLogin={handleLogin} />;
  if (view === "admin") return <Admin onLogout={handleLogout} onBack={goDashboard} />;
  return <Dashboard user={user} onLogout={handleLogout} onGoAdmin={goAdmin} />;
}

export default AuthGate;

// ─── Constantes ──────────────────────────────────────────────────────────────

const FUENTES = [
  { value: "municipalidad",   label: "Municipalidad",    color: "var(--src-municipalidad)" },
  { value: "compras_salta",   label: "Compras Salta",    color: "var(--src-compras_salta)" },
  { value: "boletin_oficial", label: "Boletín Oficial",  color: "var(--src-boletin_oficial)" },
  { value: "comprar_gob",     label: "Comprar.gob.ar",   color: "var(--src-comprar_gob)" },
];

const FUENTE_MAP = Object.fromEntries(FUENTES.map(f => [f.value, f]));

const PERIODOS = [
  { value: 1,  label: "Hoy" },
  { value: 7,  label: "Esta semana" },
  { value: 30, label: "Este mes" },
  { value: 90, label: "3 meses" },
];

const TIPOS_GRUPOS = [
  { key: "lp",      label: "Licitación Pública",   match: /licitaci[oó]n\s+p[uú]blica/i },
  { key: "lpriv",   label: "Licitación Privada",    match: /licitaci[oó]n\s+privada/i },
  { key: "concurso",label: "Concurso de Precios",   match: /concurso/i },
  { key: "cd",      label: "Contratación Directa",  match: /contrataci[oó]n\s+directa|adjudicaci[oó]n\s+simple/i },
  { key: "ca",      label: "Contratación Abreviada",match: /contrataci[oó]n\s+abreviada/i },
  { key: "otro",    label: "Otro",                  match: null },
];

const ESTADOS = [
  { value: "vigente",    label: "Vigente",    cls: "badge-estado-vigente" },
  { value: "suspendida", label: "Suspendida", cls: "badge-estado-suspendida" },
  { value: "adjudicada", label: "Adjudicada", cls: "badge-estado-adjudicada" },
  { value: "desierto",   label: "Desierto",   cls: "badge-estado-desierto" },
  { value: "publicado",  label: "Publicado",  cls: "badge-estado-vigente" },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getTipoKey(tipo) {
  for (const g of TIPOS_GRUPOS) {
    if (g.match && g.match.test(tipo)) return g.key;
  }
  return "otro";
}

function estadoCls(estado) {
  const e = ESTADOS.find(s => s.value === estado?.toLowerCase());
  return e?.cls ?? "badge-estado-default";
}

function estadoLabel(estado) {
  const e = ESTADOS.find(s => s.value === estado?.toLowerCase());
  return e?.label ?? estado;
}

function fmtFecha(fecha) {
  if (!fecha) return null;
  const [y, m, d] = fecha.split("-");
  return `${d}/${m}/${y}`;
}

function daysUntil(fecha) {
  if (!fecha) return null;
  const diff = Math.ceil((new Date(fecha) - new Date()) / 86400000);
  return diff;
}

// ─── Subcomponentes ───────────────────────────────────────────────────────────

function FuenteBadge({ fuente }) {
  const f = FUENTE_MAP[fuente];
  if (!f) return null;
  return (
    <span
      className="badge badge-fuente"
      style={{ "--src-color": f.color }}
    >
      {f.label}
    </span>
  );
}

function EstadoBadge({ estado }) {
  return (
    <span className={`badge ${estadoCls(estado)}`}>
      {estadoLabel(estado)}
    </span>
  );
}

function CheckItem({ label, checked, onChange, color, count }) {
  return (
    <div className={`check-item ${checked ? "checked" : ""}`} onClick={onChange}>
      <div className="check-box">{checked && "✓"}</div>
      <span className="check-label">
        {color && <span className="check-dot" style={{ background: color }} />}
        {label}
      </span>
      {count != null && <span className="check-count">{count}</span>}
    </div>
  );
}

function RadioItem({ label, active, onClick }) {
  return (
    <div className={`radio-item ${active ? "active" : ""}`} onClick={onClick}>
      <div className="radio-dot" />
      <span className="radio-label">{label}</span>
    </div>
  );
}

function ToggleItem({ label, on, onChange }) {
  return (
    <div className={`toggle-item ${on ? "on" : ""}`} onClick={onChange}>
      <div className="toggle-track"><div className="toggle-thumb" /></div>
      <span className="toggle-label">{label}</span>
    </div>
  );
}

function PanelPliego({ url, onClose }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  useEffect(() => {
    setLoading(true); setError(null);
    getPliego(url)
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || "No se pudo cargar el pliego"))
      .finally(() => setLoading(false));
  }, [url]);

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="panel" onClick={e => e.stopPropagation()}>
        <div className="panel-header">
          <span className="panel-header-title">Pliego / Documento</span>
          <button className="btn-close" onClick={onClose}>✕</button>
        </div>
        <div className="panel-body">
          {loading && (
            <div className="panel-spinner"><div className="loader" /></div>
          )}
          {error && (
            <div className="error-banner">{error}</div>
          )}
          {data && (
            <>
              <div className="panel-meta-row">
                <span className="panel-meta-item">📄 {data.paginas} página{data.paginas !== 1 ? "s" : ""}</span>
                <a className="panel-open-link" href={url} target="_blank" rel="noreferrer">
                  ↗ Abrir PDF
                </a>
              </div>
              <div className="panel-resumen">
                {data.resumen.split("\n\n").map((p, i) => (
                  <p key={i} dangerouslySetInnerHTML={{
                    __html: p.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                  }} />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function LicCard({ lic, onVerPliego }) {
  const f       = FUENTE_MAP[lic.fuente];
  const dias    = daysUntil(lic.fecha_apertura);
  const urgente = dias != null && dias >= 0 && dias <= 3;

  return (
    <div
      className="lic-card"
      style={{ borderLeftColor: f?.color ?? "var(--border2)" }}
    >
      <div className="card-top">
        <div className="card-title">
          {lic.url_detalle
            ? <a href={lic.url_detalle} target="_blank" rel="noreferrer">{lic.titulo}</a>
            : lic.titulo}
        </div>
        <div className="card-badges">
          <EstadoBadge estado={lic.estado} />
          <FuenteBadge fuente={lic.fuente} />
        </div>
      </div>

      <div className="card-meta">
        <span className="meta-item">
          {lic.organismo}
        </span>
        <span className="meta-item">
          {lic.tipo}
        </span>
        {lic.fecha_apertura && (
          <span className="meta-item">
            <span className="meta-label">Apertura</span>
            <span
              className="meta-date"
              style={urgente ? { color: "var(--amber)", fontWeight: 600 } : {}}
            >
              {fmtFecha(lic.fecha_apertura)}
              {urgente && dias === 0 && " · HOY"}
              {urgente && dias === 1 && " · MAÑANA"}
              {urgente && dias > 1  && ` · ${dias}d`}
            </span>
          </span>
        )}
        {lic.fecha_publicacion && !lic.fecha_apertura && (
          <span className="meta-item">
            <span className="meta-label">Publicado</span>
            <span className="meta-date">{fmtFecha(lic.fecha_publicacion)}</span>
          </span>
        )}
        {lic.monto && (
          <span className="meta-item">
            <span className="meta-label">Monto</span>
            <span style={{ color: "var(--gold)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {lic.monto}
            </span>
          </span>
        )}
      </div>

      {(lic.url_pliego || lic.url_detalle) && (
        <div className="card-actions">
          {lic.url_pliego && (
            <button className="btn-pliego" onClick={() => onVerPliego(lic.url_pliego)}>
              📄 Ver pliego
            </button>
          )}
          {lic.url_detalle && (
            <a className="btn-detalle" href={lic.url_detalle} target="_blank" rel="noreferrer">
              ↗ Ver detalle
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Dashboard principal ──────────────────────────────────────────────────────

function Dashboard({ user, onLogout, onGoAdmin }) {
  const [allData, setAllData]     = useState([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);
  const [pligoUrl, setPligoUrl]   = useState(null);

  // Filtros
  const [dias, setDias]               = useState(7);
  const [inputValue, setInputValue]   = useState("");
  const [query, setQuery]             = useState("");
  const [fuentes, setFuentes]         = useState(new Set());          // vacío = todas
  const [tipos, setTipos]             = useState(new Set());
  const [estados, setEstados]         = useState(new Set());
  const [soloConPliego, setSoloPliego]= useState(false);

  const searchTimer = useRef(null);

  // Carga desde API
  const cargar = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const data = await getLicitaciones(dias);
      setAllData(data);
    } catch {
      setError("No se pudo conectar con el backend en puerto 8000.");
    } finally {
      setLoading(false);
    }
  }, [dias]);

  useEffect(() => { cargar(); }, [cargar]);

  // Filtrado client-side
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allData.filter(l => {
      if (fuentes.size && !fuentes.has(l.fuente)) return false;
      if (tipos.size   && !tipos.has(getTipoKey(l.tipo))) return false;
      if (estados.size && !estados.has(l.estado?.toLowerCase())) return false;
      if (soloConPliego && !l.url_pliego) return false;
      if (q && !l.titulo.toLowerCase().includes(q) && !l.organismo.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [allData, fuentes, tipos, estados, soloConPliego, query]);

  // Conteos por fuente (sobre datos filtrados)
  const countByFuente = useMemo(() =>
    FUENTES.reduce((acc, f) => {
      acc[f.value] = filtered.filter(l => l.fuente === f.value).length;
      return acc;
    }, {}),
  [filtered]);

  // Conteos para checkboxes de tipos (sobre datos completos)
  const countByTipo = useMemo(() =>
    TIPOS_GRUPOS.reduce((acc, g) => {
      acc[g.key] = allData.filter(l => getTipoKey(l.tipo) === g.key).length;
      return acc;
    }, {}),
  [allData]);

  const countByEstado = useMemo(() =>
    ESTADOS.reduce((acc, e) => {
      acc[e.value] = allData.filter(l => l.estado?.toLowerCase() === e.value).length;
      return acc;
    }, {}),
  [allData]);

  // Togglers de filtro
  function toggleSet(setter, value) {
    setter(prev => {
      const next = new Set(prev);
      next.has(value) ? next.delete(value) : next.add(value);
      return next;
    });
  }

  // Chips activos
  const chips = useMemo(() => {
    const out = [];
    fuentes.forEach(v => out.push({ key: `f:${v}`, label: FUENTE_MAP[v]?.label ?? v, remove: () => toggleSet(setFuentes, v) }));
    tipos.forEach(v => {
      const g = TIPOS_GRUPOS.find(x => x.key === v);
      out.push({ key: `t:${v}`, label: g?.label ?? v, remove: () => toggleSet(setTipos, v) });
    });
    estados.forEach(v => {
      const e = ESTADOS.find(x => x.value === v);
      out.push({ key: `e:${v}`, label: e?.label ?? v, remove: () => toggleSet(setEstados, v) });
    });
    if (soloConPliego) out.push({ key: "pliego", label: "Con pliego", remove: () => setSoloPliego(false) });
    return out;
  }, [fuentes, tipos, estados, soloConPliego]);

  function clearAll() {
    setFuentes(new Set()); setTipos(new Set());
    setEstados(new Set()); setSoloPliego(false);
    setInputValue(""); setQuery("");
  }

  const activeCount = chips.length + (query ? 1 : 0);

  return (
    <div className="app">
      {/* ── Topbar ── */}
      <header className="topbar">
        <div className="logo">
          <span className="logo-title">Licitaciones<span>·</span>Salta</span>
          <span className="logo-sub">Monitor de compras</span>
        </div>

        <div className="topbar-search">
          <span className="search-icon">⌕</span>
          <input
            type="text"
            placeholder="Buscar por título u organismo…"
            value={inputValue}
            onChange={e => {
              const val = e.target.value;
              setInputValue(val);
              clearTimeout(searchTimer.current);
              searchTimer.current = setTimeout(() => setQuery(val), 250);
            }}
          />
        </div>

        <div className="topbar-right">
          <span className="result-count">
            <strong>{filtered.length}</strong> / {allData.length} licitaciones
          </span>
          <div className="topbar-user">
            <span className="topbar-welcome">Bienvenido,</span>
            <span className="topbar-username">{user?.nombre || user?.username}</span>
          </div>
          <button className="btn-refresh" onClick={async () => { await clearCache(); cargar(); }}>
            ↺ Actualizar
          </button>
          {user?.es_admin && (
            <button className="btn-refresh" onClick={onGoAdmin}>
              ⚙ Admin
            </button>
          )}
          <button className="btn-refresh" onClick={onLogout} style={{ color: "var(--red)", borderColor: "var(--red)" }}>
            Salir
          </button>
        </div>
      </header>

      <div className="body-split">
        {/* ── Sidebar filtros ── */}
        <aside className="sidebar">
          <div className="sidebar-header">
            <span className="sidebar-header-title">Filtros</span>
            {activeCount > 0
              ? <span className="active-count">{activeCount} activos</span>
              : <button className="btn-clear-all" onClick={clearAll} style={{ opacity: 0 }}>Limpiar</button>
            }
            {activeCount > 0 && (
              <button className="btn-clear-all" onClick={clearAll}>Limpiar</button>
            )}
          </div>

          {/* Período */}
          <div className="filter-section">
            <span className="filter-section-label">Período</span>
            <div className="radio-group">
              {PERIODOS.map(p => (
                <RadioItem
                  key={p.value}
                  label={p.label}
                  active={dias === p.value}
                  onClick={() => setDias(p.value)}
                />
              ))}
            </div>
          </div>

          {/* Fuente */}
          <div className="filter-section">
            <span className="filter-section-label">Fuente</span>
            <div className="check-group">
              {FUENTES.map(f => (
                <CheckItem
                  key={f.value}
                  label={f.label}
                  checked={fuentes.has(f.value)}
                  onChange={() => toggleSet(setFuentes, f.value)}
                  color={f.color}
                  count={countByFuente[f.value]}
                />
              ))}
            </div>
          </div>

          {/* Tipo de contratación */}
          <div className="filter-section">
            <span className="filter-section-label">Tipo</span>
            <div className="check-group">
              {TIPOS_GRUPOS.filter(g => countByTipo[g.key] > 0).map(g => (
                <CheckItem
                  key={g.key}
                  label={g.label}
                  checked={tipos.has(g.key)}
                  onChange={() => toggleSet(setTipos, g.key)}
                  count={countByTipo[g.key]}
                />
              ))}
            </div>
          </div>

          {/* Estado */}
          <div className="filter-section">
            <span className="filter-section-label">Estado</span>
            <div className="check-group">
              {ESTADOS.filter(e => countByEstado[e.value] > 0).map(e => (
                <CheckItem
                  key={e.value}
                  label={e.label}
                  checked={estados.has(e.value)}
                  onChange={() => toggleSet(setEstados, e.value)}
                  count={countByEstado[e.value]}
                />
              ))}
            </div>
          </div>

          {/* Extras */}
          <div className="filter-section">
            <span className="filter-section-label">Extras</span>
            <ToggleItem
              label="Solo con pliego"
              on={soloConPliego}
              onChange={() => setSoloPliego(v => !v)}
            />
          </div>
        </aside>

        {/* ── Contenido principal ── */}
        <div className="content">
          {/* Stats por fuente */}
          <div className="stats-strip">
            {FUENTES.map(f => (
              <div
                key={f.value}
                className={`stat-block ${fuentes.size && !fuentes.has(f.value) ? "dim" : ""}`}
                style={{ "--src-color": f.color }}
                onClick={() => toggleSet(setFuentes, f.value)}
              >
                <span className="stat-num">{countByFuente[f.value]}</span>
                <div className="stat-info">
                  <span className="stat-name">{f.label}</span>
                  <span className="stat-src">
                    {filtered.filter(l => l.fuente === f.value && l.url_pliego).length} con pliego
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Chips de filtros activos */}
          {chips.length > 0 && (
            <div className="filter-chips">
              {chips.map(c => (
                <div key={c.key} className="chip">
                  {c.label}
                  <span className="chip-x" onClick={c.remove}>×</span>
                </div>
              ))}
            </div>
          )}

          {/* Lista de resultados */}
          {loading && (
            <div className="loading-wrap">
              <div className="loader" />
              <span className="loading-text">Scrapeando portales…</span>
            </div>
          )}

          {!loading && error && (
            <div className="error-banner" style={{ margin: 16 }}>{error}</div>
          )}

          {!loading && !error && filtered.length === 0 && (
            <div className="empty-wrap">
              <span className="empty-icon">◎</span>
              <span className="empty-text">Sin resultados</span>
              <span className="empty-sub">Probá ajustando los filtros o ampliar el período</span>
            </div>
          )}

          {!loading && !error && filtered.length > 0 && (
            <div className="cards-wrap">
              {filtered.map(l => (
                <LicCard key={l.id} lic={l} onVerPliego={setPligoUrl} />
              ))}
            </div>
          )}
        </div>
      </div>

      {pligoUrl && <PanelPliego url={pligoUrl} onClose={() => setPligoUrl(null)} />}
    </div>
  );
}
