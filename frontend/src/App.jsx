
import { useEffect, useRef, useState } from "react";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "";

const USER_ID =
  localStorage.getItem("promptcorn_user_id") ||
  `usuario_${crypto.randomUUID()}`;

localStorage.setItem("promptcorn_user_id", USER_ID);

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
  const messagesEndRef = useRef(null);

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
            usuario_id: USER_ID,
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
        </div>
      </header>

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
                  <div className="message-bubble">{message.content}</div>
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
