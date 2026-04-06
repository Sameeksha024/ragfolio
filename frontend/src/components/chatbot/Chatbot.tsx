import { useState, useRef, useEffect } from 'react'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { motion, AnimatePresence } from 'framer-motion'

// Backend status indicator colors
const STATUS_COLORS = {
  online: 'text-green-500',
  offline: 'text-red-500',
  unknown: 'text-zinc-400',
};

type Message = { role: 'user' | 'assistant'; content: string }

export function Chatbot() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState<'online' | 'offline' | 'unknown'>('unknown');
  const [healthCheckError, setHealthCheckError] = useState<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Get backend URL from Vite env or fallback
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api';

  // Auto-scroll to bottom on new messages or loading
  const scrollToBottom = () => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Health check logic
  useEffect(() => {
    let abortController: AbortController | null = null;
    let timeoutId: ReturnType<typeof setTimeout> | null = null; // ✅ FIXED
    let isMounted = true;

    const checkHealth = async () => {
      abortController = new AbortController();
      setHealthCheckError(null);
      try {
        timeoutId = setTimeout(() => {
          abortController?.abort();
        }, 4000); // 4s timeout

        const res = await fetch(`${apiBaseUrl}/health`, {
          method: 'GET',
          signal: abortController.signal,
        });

        if (!res.ok) throw new Error('Backend returned error');
        if (isMounted) setBackendStatus('online');
      } catch (err: any) {
        if (isMounted) {
          setBackendStatus('offline');
          setHealthCheckError(
            err.name === 'AbortError' ? 'Timeout' : err.message || 'Unknown error'
          );
        }
      } finally {
        if (timeoutId) clearTimeout(timeoutId);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 10000); // poll every 10s

    return () => {
      isMounted = false;
      if (abortController) abortController.abort();
      if (timeoutId) clearTimeout(timeoutId);
      clearInterval(interval);
    };
  }, [apiBaseUrl]);

  // Send message to backend
  const handleSend = async (content: string) => {
    if (!content.trim()) return;

    const userMessage: Message = { role: 'user', content };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const response = await fetch(`${apiBaseUrl}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: content }),
      });

      let data: any = null;
      try {
        data = await response.json();
      } catch {
        data = {};
      }

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to get an answer from the AI.');
      }

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.answer }
      ]);
    } catch (error: any) {
      const errorMessage =
        error?.message || 'Network error. Please make sure the backend is running.';
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Sorry, I encountered an error: ${errorMessage}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="py-12 px-4 border-t border-zinc-800/50 relative">
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-4xl h-px bg-gradient-to-r from-transparent via-blue-500/50 to-transparent" />

      <div className="max-w-4xl mx-auto">
        {/* Navbar/status area */}
        <div className="flex items-center justify-between px-2 py-2 mb-2">
          <div className="font-semibold text-lg text-zinc-100">Chatbot</div>
          <div className={`flex items-center gap-2 text-sm font-medium ${STATUS_COLORS[backendStatus]}`}>
            <span
              className={`w-2 h-2 rounded-full ${
                backendStatus === 'online'
                  ? 'bg-green-500'
                  : backendStatus === 'offline'
                  ? 'bg-red-500'
                  : 'bg-zinc-400'
              }`}
            />
            Backend: {backendStatus.charAt(0).toUpperCase() + backendStatus.slice(1)}
            {backendStatus === 'offline' && healthCheckError && (
              <span className="ml-2 text-zinc-400">({healthCheckError})</span>
            )}
          </div>
        </div>

        <motion.div
          layout
          initial={false}
          animate={{ height: messages.length === 0 ? 240 : 500 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="rounded-3xl border border-zinc-800 bg-zinc-900/40 backdrop-blur-xl overflow-hidden flex flex-col shadow-2xl shadow-blue-500/5 ring-1 ring-white/5"
        >
          <div
            ref={scrollContainerRef}
            className="flex-1 overflow-y-auto p-6 space-y-2 custom-scrollbar"
          >
            <AnimatePresence initial={false}>
              {messages.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="h-full flex flex-col items-center justify-center text-center px-4"
                >
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-zinc-800 to-zinc-900 flex items-center justify-center mb-4 border border-zinc-700/50 shadow-inner">
                    <span className="text-2xl">✨</span>
                  </div>
                  <div>
                    <h3 className="text-zinc-100 font-semibold text-lg mb-1">
                      Get to know me
                    </h3>
                    <p className="text-zinc-500 text-sm max-w-[280px] leading-relaxed">
                      Ask about my specific skills, professional experience, or previous projects.
                    </p>
                  </div>
                </motion.div>
              ) : (
                messages.map((m, i) => (
                  <ChatMessage key={i} role={m.role} content={m.content} />
                ))
              )}
            </AnimatePresence>

            {loading && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex justify-start mb-4"
              >
                <div className="bg-zinc-800/80 rounded-2xl rounded-tl-none px-5 py-3 border border-zinc-700/50">
                  <div className="flex gap-1.5">
                    <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
                    <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" />
                  </div>
                </div>
              </motion.div>
            )}
          </div>

          <ChatInput
            onSend={handleSend}
            disabled={loading}
            isFirstTime={messages.length === 0}
          />
        </motion.div>
      </div>
    </section>
  );
}