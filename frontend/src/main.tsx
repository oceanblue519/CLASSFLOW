import React from "react";import{Capacitor}from"@capacitor/core";import{createRoot}from"react-dom/client";import App from "./App";import "./style.css";
import{GraduationCap}from"lucide-react";

class StartupErrorBoundary extends React.Component<React.PropsWithChildren, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <main style={{ padding: 24, color: "#252924", fontFamily: "sans-serif" }}>
        <h1>Classflow could not start</h1>
        <p>{this.state.error.message}</p>
        <button onClick={() => window.location.reload()}>Reload app</button>
      </main>;
    }

    return this.props.children;
  }
}

function NativeIntro() {
  const [visible, setVisible] = React.useState(true);
  const [leaving, setLeaving] = React.useState(false);

  React.useEffect(() => {
    const fadeTimer = window.setTimeout(() => setLeaving(true), 1550);
    const removeTimer = window.setTimeout(() => setVisible(false), 2100);
    return () => {
      window.clearTimeout(fadeTimer);
      window.clearTimeout(removeTimer);
    };
  }, []);

  if (!visible) return null;
  return <div className={`native-intro${leaving ? " is-leaving" : ""}`} aria-label="Opening Classflow">
    <div className="native-intro-mark"><GraduationCap size={34} strokeWidth={1.8}/></div>
    <strong>classflow</strong>
    <small>LEARNING, IN RHYTHM</small>
    <span className="native-intro-progress"><i/></span>
  </div>;
}

const isNative = Capacitor.isNativePlatform();
if (isNative) document.documentElement.classList.add("native-app");
const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Classflow root element is missing.");
createRoot(rootElement).render(<React.StrictMode><StartupErrorBoundary><App/></StartupErrorBoundary>{isNative&&<NativeIntro/>}</React.StrictMode>);

if (isNative && "serviceWorker" in navigator) {
  navigator.serviceWorker.getRegistrations().then(async (registrations) => {
    await Promise.all(registrations.map((registration) => registration.unregister()));
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames.filter((name) => name.startsWith("classflow-shell-")).map((name) => caches.delete(name)));
  }).catch((error: unknown) => {
    console.error("Classflow could not clear old web caches.", error);
  });
} else if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((error: unknown) => {
      console.error("Classflow service worker registration failed.", error);
    });
  });
}
