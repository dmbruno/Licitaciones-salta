import { useState } from "react";
import { login } from "./api";
import "./Login.css";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await login(username, password);
      localStorage.setItem("ls_token", data.access_token);
      localStorage.setItem("ls_user",  JSON.stringify({
        username: data.username,
        nombre:   data.nombre,
        es_admin: data.es_admin,
      }));
      onLogin(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Error al iniciar sesión");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-bg" />

      <div className="login-card">
        <div className="login-logo">
          Licitaciones<span>·</span>Salta
        </div>
        <p className="login-sub">Monitor de compras públicas</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="lf-group">
            <label className="lf-label">Usuario</label>
            <input
              className="lf-input"
              type="text"
              autoComplete="username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="tu usuario"
              required
            />
          </div>

          <div className="lf-group">
            <label className="lf-label">Contraseña</label>
            <input
              className="lf-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          {error && <div className="lf-error">{error}</div>}

          <button className="lf-submit" type="submit" disabled={loading}>
            {loading ? <span className="lf-loader" /> : "Ingresar →"}
          </button>
        </form>

        <p className="login-contact">
          ¿No tenés acceso?{" "}
          <a href="mailto:dmbruno61@gmail.com">Escribinos</a>
        </p>
      </div>
    </div>
  );
}
