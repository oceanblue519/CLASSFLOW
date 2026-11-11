import { useState } from "react";
import { api, getConfiguredApiBase, saveConfiguredApiBase } from "./api";

export default function AppServerSettings() {
  const [value, setValue] = useState(getConfiguredApiBase());
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);

  async function connect() {
    setError("");
    try {
      saveConfiguredApiBase(value);
      if (!value.trim()) {
        setError("Enter your Classflow server's HTTPS address.");
        return;
      }

      setChecking(true);
      const health = await api("/health");
      if (health.service !== "Classflow" || health.status !== "ok") {
        throw new Error("This address did not respond as a Classflow server.");
      }
      window.location.reload();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Could not connect to this server.";
      setError(message === "Failed to fetch"
        ? "Could not reach the server. Check its HTTPS address and try again."
        : message);
    } finally {
      setChecking(false);
    }
  }

  return <section className="app-server-settings">
    <div>
      <strong>Connect to your Classflow server</strong>
      <small>The app needs an online HTTPS server before you can sign in. “localhost” only refers to this phone.</small>
    </div>
    <label htmlFor="app-server-address">Server address</label>
    <div className="app-server-input">
      <input
        id="app-server-address"
        type="url"
        inputMode="url"
        autoCapitalize="none"
        autoCorrect="off"
        value={value}
        onChange={event => setValue(event.target.value)}
        placeholder="https://your-classflow-server.com"
        aria-describedby={error ? "app-server-error" : "app-server-help"}
      />
      <button type="button" className="secondary" onClick={() => void connect()} disabled={checking}>
        {checking ? "Checking…" : "Connect"}
      </button>
    </div>
    <small id="app-server-help">Ask your administrator for the public Classflow HTTPS address.</small>
    {error && <p className="error" id="app-server-error" role="alert">{error}</p>}
  </section>;
}
