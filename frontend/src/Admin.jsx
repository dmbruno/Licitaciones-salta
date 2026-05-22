import { useState, useEffect, useCallback } from "react";
import { getUsers, createUser, toggleUser, deleteUser } from "./api";
import "./Admin.css";

function generatePassword() {
  const chars = "abcdefhjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
  return Array.from({ length: 10 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}

function fmtDate(d) {
  if (!d) return "—";
  return d.replace("T", " ").slice(0, 16);
}

export default function Admin({ onLogout, onBack }) {
  const [users,   setUsers]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [copied,   setCopied]  = useState(null);

  const [form, setForm] = useState({
    username: "", password: "", nombre: "", email: "", plan: "beta",
  });

  const load = useCallback(async () => {
    try {
      const data = await getUsers();
      setUsers(data);
    } catch {
      setError("No se pudieron cargar los usuarios.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function genPass() {
    setForm(f => ({ ...f, password: generatePassword() }));
  }

  function copyText(text, key) {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1800);
  }

  async function handleCreate(e) {
    e.preventDefault();
    setCreating(true);
    try {
      await createUser(form);
      setForm({ username: "", password: "", nombre: "", email: "", plan: "beta" });
      setShowForm(false);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Error al crear usuario");
    } finally {
      setCreating(false);
    }
  }

  async function handleToggle(username) {
    await toggleUser(username);
    load();
  }

  async function handleDelete(username) {
    if (!confirm(`¿Eliminar al usuario "${username}"? Esta acción no se puede deshacer.`)) return;
    await deleteUser(username);
    load();
  }

  const activos   = users.filter(u => u.activo && !u.es_admin).length;
  const inactivos = users.filter(u => !u.activo).length;

  return (
    <div className="admin-wrap">
      {/* ── Topbar ── */}
      <header className="admin-top">
        <div className="admin-logo">
          Licitaciones<span>·</span>Salta
          <em>Admin</em>
        </div>
        <div className="admin-top-right">
          <button className="admin-btn-ghost" onClick={onBack}>← Ir al dashboard</button>
          <button className="admin-btn-ghost" onClick={onLogout}>Cerrar sesión</button>
        </div>
      </header>

      <div className="admin-body">
        {/* ── Stats ── */}
        <div className="admin-stats">
          <div className="astat">
            <div className="astat-num">{users.filter(u => !u.es_admin).length}</div>
            <div className="astat-lbl">Clientes totales</div>
          </div>
          <div className="astat">
            <div className="astat-num" style={{ color: "var(--green)" }}>{activos}</div>
            <div className="astat-lbl">Activos</div>
          </div>
          <div className="astat">
            <div className="astat-num" style={{ color: "var(--text-muted)" }}>{inactivos}</div>
            <div className="astat-lbl">Inactivos</div>
          </div>
        </div>

        {/* ── Crear usuario ── */}
        <div className="admin-section">
          <div className="admin-section-header">
            <span className="admin-section-title">Usuarios</span>
            <button
              className="admin-btn-primary"
              onClick={() => setShowForm(v => !v)}
            >
              {showForm ? "Cancelar" : "+ Nuevo usuario"}
            </button>
          </div>

          {showForm && (
            <form className="create-form" onSubmit={handleCreate}>
              <div className="cf-grid">
                <div className="cf-group">
                  <label className="cf-label">Usuario *</label>
                  <input
                    className="cf-input"
                    value={form.username}
                    onChange={e => setForm(f => ({ ...f, username: e.target.value.trim().toLowerCase() }))}
                    placeholder="juanperez"
                    required
                  />
                </div>
                <div className="cf-group">
                  <label className="cf-label">Contraseña *</label>
                  <div className="cf-input-row">
                    <input
                      className="cf-input"
                      value={form.password}
                      onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                      placeholder="contraseña"
                      required
                    />
                    <button type="button" className="cf-gen-btn" onClick={genPass} title="Generar contraseña">
                      ⟳
                    </button>
                    {form.password && (
                      <button
                        type="button"
                        className="cf-copy-btn"
                        onClick={() => copyText(form.password, "newpass")}
                      >
                        {copied === "newpass" ? "✓" : "⎘"}
                      </button>
                    )}
                  </div>
                </div>
                <div className="cf-group">
                  <label className="cf-label">Nombre</label>
                  <input
                    className="cf-input"
                    value={form.nombre}
                    onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))}
                    placeholder="Juan Pérez"
                  />
                </div>
                <div className="cf-group">
                  <label className="cf-label">Email</label>
                  <input
                    className="cf-input"
                    type="email"
                    value={form.email}
                    onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                    placeholder="juan@empresa.com"
                  />
                </div>
                <div className="cf-group">
                  <label className="cf-label">Plan</label>
                  <select
                    className="cf-input"
                    value={form.plan}
                    onChange={e => setForm(f => ({ ...f, plan: e.target.value }))}
                  >
                    <option value="beta">Beta</option>
                    <option value="mensual">Mensual</option>
                    <option value="anual">Anual</option>
                  </select>
                </div>
              </div>

              {form.username && form.password && (
                <div className="cf-preview">
                  <span className="cf-preview-label">Credenciales a enviar:</span>
                  <code>Usuario: {form.username} · Contraseña: {form.password}</code>
                  <button
                    type="button"
                    className="cf-copy-btn"
                    onClick={() => copyText(`Usuario: ${form.username}\nContraseña: ${form.password}`, "creds")}
                  >
                    {copied === "creds" ? "✓ Copiado" : "⎘ Copiar"}
                  </button>
                </div>
              )}

              <button className="admin-btn-primary" type="submit" disabled={creating}>
                {creating ? "Creando…" : "Crear usuario"}
              </button>
            </form>
          )}

          {/* ── Tabla ── */}
          {loading && <div className="admin-loading">Cargando usuarios…</div>}
          {error   && <div className="admin-error">{error}</div>}

          {!loading && (
            <div className="users-table-wrap">
              <table className="users-table">
                <thead>
                  <tr>
                    <th>Usuario</th>
                    <th>Nombre / Email</th>
                    <th>Plan</th>
                    <th>Último acceso</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id} className={!u.activo ? "row-inactive" : ""}>
                      <td>
                        <span className="u-username">{u.username}</span>
                        {u.es_admin && <span className="u-admin-badge">admin</span>}
                      </td>
                      <td>
                        <div className="u-nombre">{u.nombre || "—"}</div>
                        <div className="u-email">{u.email || "—"}</div>
                      </td>
                      <td>
                        <span className={`plan-badge plan-${u.plan}`}>{u.plan}</span>
                      </td>
                      <td className="u-date">{fmtDate(u.ultimo_acceso)}</td>
                      <td>
                        <span className={`status-dot ${u.activo ? "active" : "inactive"}`}>
                          {u.activo ? "Activo" : "Inactivo"}
                        </span>
                      </td>
                      <td>
                        {!u.es_admin && (
                          <div className="row-actions">
                            <button
                              className={`act-btn ${u.activo ? "act-disable" : "act-enable"}`}
                              onClick={() => handleToggle(u.username)}
                              title={u.activo ? "Desactivar" : "Activar"}
                            >
                              {u.activo ? "Pausar" : "Activar"}
                            </button>
                            <button
                              className="act-btn act-delete"
                              onClick={() => handleDelete(u.username)}
                              title="Eliminar"
                            >
                              ✕
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
