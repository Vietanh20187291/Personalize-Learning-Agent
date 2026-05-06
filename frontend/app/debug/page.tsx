'use client';

import { useEffect, useRef, useState } from 'react';

type DebugEvent = {
  type: 'llm_request' | 'llm_response' | 'llm_error';
  timestamp: string;
  prompt?: string;
  system_prompt?: string;
  response?: string;
  error?: string;
  duration_ms?: number;
};

export default function DebugPage() {
  const [connected, setConnected] = useState(false);
  const [statusText, setStatusText] = useState('Disconnected');
  const [events, setEvents] = useState<DebugEvent[]>([]);
  const [provider, setProvider] = useState<'ollama' | 'openai' | 'groq'>('groq');
  const [model, setModel] = useState('llama-3.1-8b-instant');
  const [message, setMessage] = useState('Tóm tắt ngắn tình hình lớp IT1 theo 3 ý chính.');
  const [systemPrompt, setSystemPrompt] = useState('Bạn là trợ lý test LLM. Trả lời ngắn gọn, chính xác.');
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState('');
  const logsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const eventSource = new EventSource('http://localhost:8010/debug/stream');

    eventSource.onopen = () => {
      setConnected(true);
      setStatusText('Connected');
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as DebugEvent;
        console.log('SSE data:', data);
        setEvents((prev) => [...prev, data]);
        setConnected(true);
        setStatusText('Connected');
      } catch (error) {
        console.error('Failed to parse SSE data:', error);
      }
    };

    eventSource.onerror = () => {
      setConnected(false);
      setStatusText('Disconnected');
    };

    return () => eventSource.close();
  }, []);

  useEffect(() => {
    setConnected(false);
    setStatusText('Disconnected');
  }, []);

  useEffect(() => {
    logsRef.current?.scrollTo({ top: logsRef.current.scrollHeight, behavior: 'smooth' });
  }, [events]);

  const requestCount = events.filter((event) => event.type === 'llm_request').length;
  const responseCount = events.filter((event) => event.type === 'llm_response').length;

  const handleSendDebugChat = async () => {
    if (!message.trim()) return;
    setSending(true);
    setSendResult('');

    try {
      const response = await fetch('http://localhost:8010/debug/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
          provider,
          model,
          message,
          system_prompt: systemPrompt,
        }),
      });

      const data = await response.json();
      if (data.ok) {
        setSendResult(`OK (${data.provider}:${data.model}) - ${data.duration_ms} ms`);
      } else {
        setSendResult(`ERROR (${data.provider || provider}:${data.model || model}) - ${data.error || 'unknown error'}`);
      }
    } catch (error) {
      setSendResult(`ERROR - ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSending(false);
    }
  };

  const handleProviderChange = (nextProvider: 'ollama' | 'openai' | 'groq') => {
    setProvider(nextProvider);
    setModel(nextProvider === 'ollama' ? 'qwen2.5:14b' : nextProvider === 'openai' ? 'gpt-4o-mini' : 'llama-3.1-8b-instant');
  };

  return (
    <div style={{ fontFamily: 'monospace', padding: 16, background: '#111', color: '#eee', minHeight: '100vh' }}>
      <h1>LLM Debug Viewer</h1>
      <div style={{ marginBottom: 16 }}>
        Status: {statusText} | Requests: {requestCount} | Responses: {responseCount}
      </div>

      <div style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 8, fontWeight: 700 }}>Manual LLM Debug Send</div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
          <label>
            Provider:{' '}
            <select
              value={provider}
              onChange={(event) => handleProviderChange(event.target.value as 'ollama' | 'openai' | 'groq')}
              style={{ background: '#222', color: '#eee', border: '1px solid #555', padding: '4px 8px' }}
            >
              <option value="ollama">Ollama</option>
              <option value="groq">Groq</option>
              <option value="openai">GPT-4o-mini (OpenAI)</option>
            </select>
          </label>

          <label>
            Model:{' '}
            <input
              value={model}
              onChange={(event) => setModel(event.target.value)}
              style={{ background: '#222', color: '#eee', border: '1px solid #555', padding: '4px 8px', minWidth: 220 }}
            />
          </label>
        </div>

        <div style={{ marginBottom: 8 }}>
          <div style={{ marginBottom: 4 }}>System prompt</div>
          <textarea
            value={systemPrompt}
            onChange={(event) => setSystemPrompt(event.target.value)}
            rows={2}
            style={{ width: '100%', background: '#222', color: '#eee', border: '1px solid #555', padding: 8 }}
          />
        </div>

        <div style={{ marginBottom: 8 }}>
          <div style={{ marginBottom: 4 }}>Your message</div>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            rows={4}
            style={{ width: '100%', background: '#222', color: '#eee', border: '1px solid #555', padding: 8 }}
          />
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <button
            onClick={handleSendDebugChat}
            disabled={sending || !message.trim()}
            style={{
              padding: '8px 12px',
              background: sending ? '#555' : '#0a7',
              color: '#fff',
              border: '1px solid #055',
              cursor: sending ? 'not-allowed' : 'pointer',
            }}
          >
            {sending ? 'Sending...' : 'Send To Provider'}
          </button>
          {sendResult ? <span style={{ color: sendResult.startsWith('OK') ? '#7CFC00' : '#ff7f7f' }}>{sendResult}</span> : null}
        </div>

        <button
          onClick={async () => {
            const response = await fetch('http://localhost:8010/debug/test');
            const data = await response.json();
            console.log('SSE data:', data);
          }}
          style={{ padding: '8px 12px', background: '#333', color: '#fff', border: '1px solid #555', cursor: 'pointer' }}
        >
          Send Test Event
        </button>
      </div>

      <div
        ref={logsRef}
        style={{ border: '1px solid #444', background: '#1b1b1b', height: 500, overflowY: 'auto', padding: 12 }}
      >
        {events.length === 0 ? (
          <div>Waiting for events...</div>
        ) : (
          events.map((event, index) => {
            const time = new Date(event.timestamp).toLocaleTimeString();
            if (event.type === 'llm_request') {
              return (
                <div key={index} style={{ marginBottom: 12, padding: 12, borderLeft: '4px solid #f1c40f', background: '#222' }}>
                  <div>[{time}] ➜ Prompt:</div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{event.prompt}</div>
                  <div style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>System: {event.system_prompt}</div>
                </div>
              );
            }

            if (event.type === 'llm_response') {
              return (
                <div key={index} style={{ marginBottom: 12, padding: 12, borderLeft: '4px solid #2ecc71', background: '#222' }}>
                  <div>[{time}] ⬅ Response ({event.duration_ms} ms):</div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{event.response}</div>
                </div>
              );
            }

            return (
              <div key={index} style={{ marginBottom: 12, padding: 12, borderLeft: '4px solid #e74c3c', background: '#222' }}>
                <div>[{time}] ✕ Error ({event.duration_ms} ms):</div>
                <div style={{ whiteSpace: 'pre-wrap' }}>{event.error}</div>
              </div>
            );
          })
        )}
      </div>

      <div style={{ marginTop: 12, color: '#888' }}>
        Open DevTools and check console for <code>SSE data:</code> logs. Connected: {String(connected)}
      </div>
    </div>
  );
}
