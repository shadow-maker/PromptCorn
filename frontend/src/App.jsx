
import { useEffect, useRef, useState } from "react";
import "./App.css";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = import.meta.env.VITE_API_URL || "";
// Misma API que el chat: .../chat -> .../reiniciar_usuario
const RESET_URL = API_URL ? API_URL.replace(/\/chat\/?$/, "") + "/reiniciar_usuario" : "";

// crypto.randomUUID solo existe en páginas HTTPS (o localhost); el sitio en S3 es HTTP.
// getRandomValues sí está disponible en ambos.
function nuevoId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  const bytes = window.crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function leerUsuario() {
  try {
    const guardado = localStorage.getItem("promptcorn_user_id");
    if (guardado) return guardado;
    const nuevo = `usuario_${nuevoId()}`;
    localStorage.setItem("promptcorn_user_id", nuevo);
    return nuevo;
  } catch {
    return `usuario_${nuevoId()}`; // sin localStorage (modo privado estricto): id solo para esta sesión
  }
}

// Id nuevo de conversación: la memoria del bot empieza de cero.
function nuevoUsuario() {
  const nuevo = `usuario_${nuevoId()}`;
  try {
    localStorage.setItem("promptcorn_user_id", nuevo);
  } catch {
    // sin localStorage: el id vale solo para esta sesión
  }
  return nuevo;
}

const INITIAL_MESSAGE = {
  id: 1,
  role: "assistant",
  content:
    "¡Hola! Soy PromptCorn 🍿. Puedo ayudarte a descubrir películas, encontrar recomendaciones y saber dónde verlas. ¿Qué te gustaría ver hoy?",
};

function App() {
  const [messages, setMessages] = useState([INITIAL_MESSAGE]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [usuarioId, setUsuarioId] = useState(leerUsuario);
  const [confirmando, setConfirmando] = useState(false);
  const [reiniciando, setReiniciando] = useState(false);
  const [errorReinicio, setErrorReinicio] = useState("");
  const messagesEndRef = useRef(null);
  const cancelarRef = useRef(null);

  // Modal: foco en "Cancelar" (la opción segura) y Escape para cerrar
  useEffect(() => {
    if (!confirmando) return;
    cancelarRef.current?.focus();
    function onKey(event) {
      if (event.key === "Escape" && !reiniciando) {
        setConfirmando(false);
        setErrorReinicio("");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmando, reiniciando]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage(event) {
    event?.preventDefault();

    const message = input.trim();

    if (!message || loading) return;

    setInput("");
    setError("");

    setMessages((previous) => [
      ...previous,
      {
        id: Date.now(),
        role: "user",
        content: message,
      },
    ]);

    setLoading(true);

    try {
      let assistantResponse;

      if (!API_URL) {
        // Modo demostración mientras se configura API Gateway.
        await new Promise((resolve) => setTimeout(resolve, 900));

        assistantResponse =
          "¡Estoy listo para ayudarte! Actualmente estoy en modo demostración. Cuando conectemos la API de AWS, podré consultar películas y generar recomendaciones reales.";
      } else {
        const response = await fetch(API_URL, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            usuario_id: usuarioId,
            mensaje: message,
          }),
        });

        let data = await response.json();

        // Admite respuestas de Lambda/API Gateway con body anidado.
        if (typeof data.body === "string") {
          data = JSON.parse(data.body);
        }

        if (!response.ok) {
          throw new Error(
            data.error || data.message || `Error HTTP ${response.status}`
          );
        }

        assistantResponse =
          data.respuesta || data.response || data.message;

        if (!assistantResponse) {
          throw new Error("El servidor no devolvió una respuesta válida.");
        }
      }

      setMessages((previous) => [
        ...previous,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: assistantResponse,
        },
      ]);
    } catch (err) {
      setError(err.message || "No se pudo conectar con el servidor.");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  function clearChat() {
    setMessages([INITIAL_MESSAGE]);
    setError("");
  }

  function cerrarModal() {
    setConfirmando(false);
    setErrorReinicio("");
  }

  // Borra vistas, notas, plataformas y recomendaciones del usuario demo,
  // y empieza una conversación nueva (memoria del bot en blanco).
  async function reiniciarPerfil() {
    setReiniciando(true);
    setErrorReinicio("");
    try {
      if (RESET_URL) {
        const response = await fetch(RESET_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirmar: "BORRAR" }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
          throw new Error(data.error || `Error HTTP ${response.status}`);
        }
      }
      setUsuarioId(nuevoUsuario());
      setMessages([
        INITIAL_MESSAGE,
        {
          id: Date.now(),
          role: "assistant",
          content:
            "Listo: borré tu historial, tus notas y tus plataformas. Empezamos de cero 🍿. Cuéntame qué plataformas tienes y qué películas te gustaron.",
        },
      ]);
      setError("");
      setConfirmando(false);
    } catch (err) {
      setErrorReinicio(err.message || "No se pudo reiniciar el perfil.");
    } finally {
      setReiniciando(false);
    }
  }

  return (
    <main className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">🍿</div>
          <div>
            <h1>PromptCorn</h1>
            <span>Tu asistente cinematográfico</span>
          </div>
        </div>

        <div className="header-actions">
          <span className={`connection-status ${API_URL ? "connected" : "demo"}`}>
            <span className="status-dot"></span>
            {API_URL ? "API configurada" : "Modo demostración"}
          </span>
          <button className="clear-button" onClick={clearChat}>
            Nueva conversación
          </button>
          <button
            className="clear-button reset-button"
            onClick={() => setConfirmando(true)}
            disabled={loading}
          >
            Reiniciar perfil
          </button>
        </div>
      </header>

      {confirmando && (
        <div
          className="modal-backdrop"
          onClick={() => !reiniciando && cerrarModal()}
        >
          <div
            className="modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="modal-titulo"
            aria-describedby="modal-texto"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="modal-titulo">¿Borrar todo el historial?</h2>
            <div id="modal-texto">
              <p>Se borrará todo lo que PromptCorn sabe del usuario:</p>
              <ul>
                <li>Películas vistas y sus notas</li>
                <li>Plataformas guardadas</li>
                <li>Recomendaciones anteriores</li>
                <li>La memoria de esta conversación</li>
              </ul>
              <p>
                Las recomendaciones vuelven a empezar de cero.{" "}
                <strong>Esta acción no se puede deshacer.</strong>
              </p>
            </div>
            {errorReinicio && (
              <p className="modal-error" role="alert">
                {errorReinicio}
              </p>
            )}
            <div className="modal-actions">
              <button
                ref={cancelarRef}
                className="clear-button"
                onClick={cerrarModal}
                disabled={reiniciando}
              >
                Cancelar
              </button>
              <button
                className="danger-button"
                onClick={reiniciarPerfil}
                disabled={reiniciando}
              >
                {reiniciando ? "Borrando…" : "Sí, borrar todo"}
              </button>
            </div>
          </div>
        </div>
      )}

      <section className="chat-layout">
        <div className="welcome-section">
          <span className="eyebrow">DESCUBRE TU PRÓXIMA PELÍCULA</span>
          <h2>¿Qué te gustaría ver hoy?</h2>
          <p>
            Cuéntame tus gustos y encontraremos juntos una película para ti.
          </p>
        </div>

        <section className="chat-panel">
          <div className="messages">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`message-row ${message.role}`}
              >
                {message.role === "assistant" && (
                  <div className="avatar">🍿</div>
                )}

                <div className="message-content">
                  <span className="message-author">
                    {message.role === "assistant" ? "PromptCorn" : "Tú"}
                  </span>
                  <div className="message-bubble">
                    {message.role === "assistant" ? (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    ) : (
                      message.content
                    )}
                  </div>
                </div>
              </div>
            ))}

            {loading && (
              <div className="message-row assistant">
                <div className="avatar">🍿</div>
                <div className="message-content">
                  <span className="message-author">PromptCorn</span>
                  <div className="message-bubble typing">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {error && (
            <div className="error-message">
              <strong>Error:</strong> {error}
            </div>
          )}

          <form className="composer" onSubmit={sendMessage}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Escribe tu mensaje... Por ejemplo: recomiéndame una película de ciencia ficción"
              rows={2}
              disabled={loading}
            />

            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || loading}
            >
              {loading ? "..." : "Enviar ↑"}
            </button>
          </form>

          <div className="composer-footer">
            <span>Enter para enviar · Shift + Enter para nueva línea</span>
            <span>PromptCorn AI</span>
          </div>
        </section>

        <p className="privacy-note">
          Tus conversaciones se identifican mediante un usuario de sesión.
        </p>

        <footer className="credits">
          <p>
            Datos de películas:{" "}
            <a href="https://www.themoviedb.org/" target="_blank" rel="noreferrer">TMDB</a>
            {" · "}Disponibilidad en plataformas:{" "}
            <a href="https://www.justwatch.com/" target="_blank" rel="noreferrer">JustWatch</a>
            {" · "}Calificaciones:{" "}
            <a href="https://grouplens.org/datasets/movielens/" target="_blank" rel="noreferrer">MovieLens</a>{" "}
            (Harper y Konstan, 2015)
          </p>
          <p>
            Este producto usa la API de TMDB pero no está respaldado ni certificado por TMDB.
          </p>
        </footer>
      </section>
    </main>
  );
}

export default App;
