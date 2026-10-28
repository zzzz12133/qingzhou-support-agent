import React, { useEffect, useRef, useState } from 'react';
import Icon from './components/Icons.jsx';
import Sidebar from './components/Sidebar.jsx';
import Welcome from './components/Welcome.jsx';
import ChatMessage from './components/ChatMessage.jsx';
import Composer from './components/Composer.jsx';
import Inspector from './components/Inspector.jsx';
import SettingsMenu from './components/SettingsMenu.jsx';
import { api, clientId, streamChat } from './api.js';
import { compactTitle, errorMessage, providerLabel, sessionDate } from './utils.js';

const THEME_KEY = 'lightdesk-theme';
const FONT_KEY = 'qingzhou-font-size';
const DENSITY_KEY = 'qingzhou-density';
const MOTION_KEY = 'qingzhou-motion';
const THEME_VALUES = new Set(['warm', 'dusk', 'system']);
const FONT_VALUES = new Set(['sm', 'md', 'lg', 'xl']);
const DENSITY_VALUES = new Set(['comfortable', 'compact']);
const MOTION_VALUES = new Set(['full', 'reduced']);

function readThemePreference() {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return THEME_VALUES.has(stored) ? stored : 'warm';
  } catch {
    return 'warm';
  }
}

function readFontPreference() {
  try {
    const stored = localStorage.getItem(FONT_KEY);
    return FONT_VALUES.has(stored) ? stored : 'md';
  } catch {
    return 'md';
  }
}

function readPreference(key, values, fallback) {
  try {
    const stored = localStorage.getItem(key);
    return values.has(stored) ? stored : fallback;
  } catch {
    return fallback;
  }
}

const EMPTY_INSPECTOR = {
  trace: [],
  citations: [],
  memory: null,
  usage: null,
  grounding: null,
  cacheHit: false,
  provider: null,
};

function normalizeMessage(message) {
  const metadata = message.metadata || {};
  return {
    ...message,
    clientKey: message.clientKey || message.id || `loaded-${Math.random().toString(16).slice(2)}`,
    metadata: {
      ...metadata,
      trace: metadata.trace || [],
      citations: metadata.citations || [],
    },
    status: message.status || 'done',
  };
}

function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className={`toast ${toast.type || 'info'}`} role="status">
      <span className="toast-icon">
        <Icon name={toast.type === 'error' ? 'alert' : toast.type === 'success' ? 'check' : 'spark'} size={15} />
      </span>
      {toast.message}
    </div>
  );
}

function ConfirmDialog({ session, onCancel, onConfirm, busy }) {
  if (!session) return null;
  return (
    <div className="modal-layer" role="presentation">
      <div className="confirm-dialog" role="dialog" aria-modal="true" aria-label="删除会话">
        <span className="confirm-icon">
          <Icon name="trash" size={20} />
        </span>
        <h3>删除这段对话？</h3>
        <p>
          「{compactTitle(session.title)}」的聊天记录会从本机删除，无法恢复。
        </p>
        <div className="confirm-actions">
          <button type="button" className="ghost-button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button type="button" className="danger-button" onClick={onConfirm} disabled={busy}>
            {busy ? '删除中…' : '确认删除'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [activeId, setActiveId] = useState(null);
  const [title, setTitle] = useState('新对话');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeRun, setActiveRun] = useState(null);
  const [health, setHealth] = useState(null);
  const [backendUp, setBackendUp] = useState(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [inspector, setInspector] = useState(EMPTY_INSPECTOR);
  const [tab, setTab] = useState('trace');
  const [highlight, setHighlight] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [showJump, setShowJump] = useState(false);
  const [theme, setTheme] = useState(readThemePreference);
  const [fontSize, setFontSize] = useState(readFontPreference);
  const [density, setDensity] = useState(() => readPreference(DENSITY_KEY, DENSITY_VALUES, 'comfortable'));
  const [motion, setMotion] = useState(() => readPreference(MOTION_KEY, MOTION_VALUES, 'full'));

  const abortRef = useRef(null);
  const activeRunRef = useRef(null);
  const streamSeqRef = useRef(0);
  const pendingKeyRef = useRef(null);
  const tokenBufferRef = useRef('');
  const rafRef = useRef(null);
  const sendLockRef = useRef(false);
  const scrollerRef = useRef(null);
  const nearBottomRef = useRef(true);
  const streamReasonRef = useRef(null);

  const notify = (message, type = 'info') => {
    setToast({ id: Date.now(), message, type });
  };

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      const resolved = theme === 'system' ? (media.matches ? 'dusk' : 'warm') : theme;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.style.colorScheme = resolved === 'dusk' ? 'dark' : 'light';
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute('content', resolved === 'dusk' ? '#1a0c07' : '#f3b25f');
      try {
        localStorage.setItem(THEME_KEY, theme);
      } catch {
        // 本地存储不可用时仍然应用当前主题。
      }
    };
    apply();
    if (theme === 'system') {
      media.addEventListener?.('change', apply);
      return () => media.removeEventListener?.('change', apply);
    }
    return undefined;
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.fontSize = fontSize;
    try {
      localStorage.setItem(FONT_KEY, fontSize);
    } catch {
      // 本地存储不可用时仍然应用当前字号。
    }
  }, [fontSize]);

  useEffect(() => {
    document.documentElement.dataset.density = density;
    document.documentElement.dataset.motion = motion;
    try {
      localStorage.setItem(DENSITY_KEY, density);
      localStorage.setItem(MOTION_KEY, motion);
    } catch {
      // 本地存储不可用时仍然应用当前设置。
    }
  }, [density, motion]);

  const resetAppearance = () => {
    setTheme('warm');
    setFontSize('md');
    setDensity('comfortable');
    setMotion('full');
    notify('已恢复默认设置', 'success');
  };

  const scrollToBottom = (smooth = false) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
    nearBottomRef.current = true;
    setShowJump(false);
  };

  const refreshHealth = async () => {
    try {
      const data = await api.health();
      setHealth(data);
      setBackendUp(true);
    } catch {
      setBackendUp(false);
      setHealth(null);
    }
  };

  const refreshSessions = async () => {
    try {
      const data = await api.listSessions();
      setSessions(data.sessions || []);
    } catch (error) {
      if (backendUp !== false) {
        notify(errorMessage(error), 'error');
      }
    } finally {
      setSessionsLoading(false);
    }
  };

  useEffect(() => {
    refreshHealth();
    refreshSessions();
    const timer = window.setInterval(refreshHealth, 25_000);
    return () => window.clearInterval(timer);
    // 只在首次挂载时建立连接状态轮询。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const sid = new URLSearchParams(window.location.search).get('session');
    if (sid && !activeId) {
      openSession(sid, { fromUrl: true });
    }
    // 只处理首屏深链。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  useEffect(() => {
    if (nearBottomRef.current) {
      requestAnimationFrame(() => scrollToBottom(false));
    }
  }, [messages]);

  const setRun = (run) => {
    activeRunRef.current = run;
    setActiveRun(run);
  };

  const flushTokenBuffer = () => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    const chunk = tokenBufferRef.current;
    tokenBufferRef.current = '';
    const key = pendingKeyRef.current;
    if (!chunk || !key) return;
    setMessages((prev) =>
      prev.map((message) =>
        message.clientKey === key
          ? {
              ...message,
              content: `${message.content || ''}${chunk}`,
              metadata: { ...message.metadata, stage: '正在生成答复' },
            }
          : message
      )
    );
  };

  const discardTokenBuffer = () => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    tokenBufferRef.current = '';
  };

  const enqueueToken = (text) => {
    tokenBufferRef.current += text;
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      flushTokenBuffer();
    });
  };

  const stopGeneration = (silent = false) => {
    const run = activeRunRef.current;
    const controller = abortRef.current;
    streamReasonRef.current = 'user';
    streamSeqRef.current += 1;
    flushTokenBuffer();
    const key = pendingKeyRef.current;
    if (key) {
      setMessages((prev) =>
        prev.map((message) =>
          message.clientKey === key
            ? {
                ...message,
                status: 'stopped',
                metadata: { ...message.metadata, stage: '已停止生成' },
              }
            : message
        )
      );
    }
    if (run?.messageId) {
      api.cancel(run.messageId).catch(() => {});
    }
    controller?.abort();
    abortRef.current = null;
    setRun(null);
    setIsStreaming(false);
    if (!silent) notify('已停止生成，未完成的回答会保留');
    window.setTimeout(refreshSessions, 600);
  };

  const ensureSession = async () => {
    if (activeId) return activeId;
    const created = await api.createSession();
    setActiveId(created.id);
    setTitle(created.title || '新对话');
    setSessions((prev) => [
      {
        id: created.id,
        title: created.title || '新对话',
        updatedAt: created.updatedAt,
        messageCount: 0,
        preview: '还没有消息',
      },
      ...prev.filter((item) => item.id !== created.id),
    ]);
    window.history.replaceState(null, '', `?session=${encodeURIComponent(created.id)}`);
    return created.id;
  };

  const sendText = async (rawText) => {
    const text = String(rawText ?? input).trim();
    if (!text || sendLockRef.current || isStreaming) return;
    sendLockRef.current = true;
    streamReasonRef.current = null;
    setInput('');

    let sessionId;
    try {
      sessionId = await ensureSession();
    } catch (error) {
      setInput(text);
      sendLockRef.current = false;
      notify(errorMessage(error), 'error');
      return;
    }

    const now = new Date().toISOString();
    const pendingKey = `pending-${clientId()}`;
    const userKey = `user-${clientId()}`;
    const clientMessageId = clientId();
    pendingKeyRef.current = pendingKey;
    tokenBufferRef.current = '';
    streamSeqRef.current += 1;
    const seq = streamSeqRef.current;

    const userMessage = {
      clientKey: userKey,
      id: userKey,
      role: 'user',
      content: text,
      createdAt: now,
      status: 'done',
      metadata: {},
    };
    const pendingMessage = {
      clientKey: pendingKey,
      id: pendingKey,
      role: 'assistant',
      content: '',
      createdAt: now,
      status: 'streaming',
      metadata: {
        trace: [],
        citations: [],
        stage: '正在连接 Agent',
      },
    };

    setMessages((prev) => [...prev, userMessage, pendingMessage]);
    setInspector((prev) => ({ ...EMPTY_INSPECTOR, memory: prev.memory }));
    setTab('trace');
    setHighlight(null);
    setIsStreaming(true);
    setRun(null);
    nearBottomRef.current = true;
    setShowJump(false);
    requestAnimationFrame(() => scrollToBottom(false));

    const patchPending = (updater) => {
      setMessages((prev) =>
        prev.map((message) =>
          message.clientKey === pendingKey
            ? {
                ...message,
                ...(typeof updater === 'function' ? updater(message) : updater),
              }
            : message
        )
      );
    };

    const patchMetadata = (patch) => {
      patchPending((message) => ({
        metadata: { ...message.metadata, ...patch },
      }));
    };

    const terminal = { done: false, error: false, stopped: false };

    const handleEvent = (event) => {
      if (seq !== streamSeqRef.current) return;
      switch (event.type) {
        case 'meta': {
          patchPending((message) => ({
            serverId: event.messageId,
            metadata: {
              ...message.metadata,
              conversationId: event.conversationId,
              stage: '正在理解问题',
            },
          }));
          setMessages((prev) =>
            prev.map((message) =>
              message.clientKey === userKey
                ? { ...message, id: event.userMessage?.id || message.id }
                : message
            )
          );
          setRun({ messageId: event.messageId, sessionId: event.conversationId });
          if (event.conversationId) {
            setActiveId(event.conversationId);
          }
          break;
        }
        case 'stage': {
          patchMetadata({ stage: event.label || '正在处理' });
          break;
        }
        case 'tool_start': {
          patchPending((message) => {
            const trace = [
              ...(message.metadata.trace || []),
              {
                id: event.callId,
                name: event.name,
                label: event.label,
                status: 'running',
                summary: event.arguments || '正在执行',
              },
            ];
            return {
              metadata: { ...message.metadata, trace, stage: `正在${event.label}` },
            };
          });
          setInspector((prev) => {
            const trace = [
              ...(prev.trace || []),
              {
                id: event.callId,
                name: event.name,
                label: event.label,
                status: 'running',
                summary: event.arguments || '正在执行',
              },
            ];
            return { ...prev, trace };
          });
          setTab('trace');
          break;
        }
        case 'tool_result': {
          patchPending((message) => {
            const trace = (message.metadata.trace || []).map((item) =>
              item.id === event.callId
                ? {
                    ...item,
                    status: event.ok ? 'success' : 'error',
                    summary: event.summary,
                    durationMs: event.durationMs,
                  }
                : item
            );
            return {
              metadata: {
                ...message.metadata,
                trace,
                stage: '正在核对工具结果',
              },
            };
          });
          setInspector((prev) => ({
            ...prev,
            trace: (prev.trace || []).map((item) =>
              item.id === event.callId
                ? {
                    ...item,
                    status: event.ok ? 'success' : 'error',
                    summary: event.summary,
                    durationMs: event.durationMs,
                  }
                : item
            ),
          }));
          break;
        }
        case 'memory': {
          setInspector((prev) => ({
            ...prev,
            memory: {
              profile: event.profile || {},
              summary: event.summary || '',
              summarizedMessages: event.summarizedMessages || 0,
              totalMessages: event.totalMessages || 0,
              tokenEstimate: event.tokenEstimate || 0,
              tokenBudget: event.tokenBudget || 3200,
              layers: event.layers || [],
              droppedMessages: event.droppedMessages || 0,
              summarySource: event.summarySource,
            },
          }));
          break;
        }
        case 'citations': {
          const citations = event.citations || [];
          patchMetadata({ citations });
          setInspector((prev) => ({ ...prev, citations }));
          break;
        }
        case 'cache': {
          patchMetadata({ cacheHit: true, stage: '命中语义缓存' });
          setInspector((prev) => ({ ...prev, cacheHit: true }));
          break;
        }
        case 'usage': {
          patchMetadata({ usage: event.usage });
          setInspector((prev) => ({ ...prev, usage: event.usage, provider: event.provider || prev.provider }));
          break;
        }
        case 'grounding': {
          patchMetadata({ grounding: event.grounding });
          setInspector((prev) => ({ ...prev, grounding: event.grounding }));
          break;
        }
        case 'guardrail': {
          const traceItem = {
            id: `guard-${Date.now()}`,
            name: 'guardrail',
            label: '输入安全护栏',
            status: 'success',
            summary: `命中 ${event.category}，未调用模型`,
          };
          patchPending((message) => ({
            metadata: {
              ...message.metadata,
              trace: [...(message.metadata.trace || []), traceItem],
              stage: '安全护栏已拦截',
            },
          }));
          setInspector((prev) => ({ ...prev, trace: [...(prev.trace || []), traceItem] }));
          break;
        }
        case 'notice': {
          patchMetadata({ notice: event.message, degraded: true });
          break;
        }
        case 'token': {
          enqueueToken(event.text || '');
          break;
        }
        case 'done': {
          terminal.done = true;
          discardTokenBuffer();
          const finalMeta = {
            provider: event.provider,
            citations: event.citations || [],
            usage: event.usage || null,
            grounding: event.grounding || null,
            trace: event.trace || [],
            cacheHit: Boolean(event.cacheHit),
            degraded: Boolean(event.degraded),
            durationMs: event.durationMs,
            intent: event.intent,
            intentLabel: event.intentLabel,
          };
          patchPending({
            id: event.message?.id || pendingKey,
            serverId: event.message?.id,
            content: event.content || '',
            status: 'done',
            createdAt: event.message?.createdAt || now,
            metadata: { ...finalMeta, stage: '' },
          });
          setInspector((prev) => ({
            ...prev,
            ...finalMeta,
            trace: finalMeta.trace,
            citations: finalMeta.citations,
            usage: finalMeta.usage,
            grounding: finalMeta.grounding,
            provider: finalMeta.provider,
            cacheHit: finalMeta.cacheHit,
          }));
          if (event.sessionTitle) {
            setTitle(event.sessionTitle);
            setSessions((prev) =>
              prev.map((item) =>
                item.id === sessionId
                  ? {
                      ...item,
                      title: event.sessionTitle,
                      updatedAt: new Date().toISOString(),
                      preview: (event.content || '').replace(/\n/g, ' ').slice(0, 54),
                      messageCount: item.messageCount + 2,
                    }
                  : item
              )
            );
          }
          setRun(null);
          setIsStreaming(false);
          abortRef.current = null;
          refreshSessions();
          break;
        }
        case 'error': {
          terminal.error = true;
          flushTokenBuffer();
          patchPending((message) => ({
            status: message.content ? 'error' : 'error',
            error: event.message || '生成失败',
            metadata: { ...message.metadata, stage: '生成中断' },
          }));
          notify(event.message || '生成失败，请稍后重试', 'error');
          setRun(null);
          setIsStreaming(false);
          abortRef.current = null;
          refreshSessions();
          break;
        }
        default:
          break;
      }
    };

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat({
        sessionId,
        message: text,
        clientMessageId,
        signal: controller.signal,
        onEvent: handleEvent,
      });
      if (seq === streamSeqRef.current && !terminal.done && !terminal.error) {
        flushTokenBuffer();
        patchPending((message) => ({
          ...message,
          status: message.content ? 'error' : 'error',
          error: '连接提前结束，回答可能不完整。',
        }));
        notify('连接提前结束，请重试', 'error');
        setRun(null);
        setIsStreaming(false);
      }
    } catch (error) {
      if (seq !== streamSeqRef.current) {
        // 已被停止或被新一轮对话接管，不再回写旧状态。
      } else if (error.name === 'AbortError') {
        if (!terminal.done && !terminal.error) {
          flushTokenBuffer();
          patchPending((message) => ({
            ...message,
            status: 'stopped',
            metadata: { ...message.metadata, stage: '已停止生成' },
          }));
        }
        setRun(null);
        setIsStreaming(false);
      } else if (!terminal.error) {
        const reason = errorMessage(error);
        flushTokenBuffer();
        patchPending((message) => ({
          ...message,
          status: 'error',
          error: reason,
        }));
        notify(reason, 'error');
        setRun(null);
        setIsStreaming(false);
        abortRef.current = null;
        window.setTimeout(refreshSessions, 500);
      }
    } finally {
      sendLockRef.current = false;
      if (seq === streamSeqRef.current) {
        abortRef.current = null;
      }
    }
  };

  const openSession = async (sessionId, { fromUrl = false } = {}) => {
    if (!sessionId) return;
    if (isStreaming) stopGeneration(true);
    setLoadingSession(true);
    setSidebarOpen(false);
    try {
      const data = await api.getSession(sessionId);
      const loaded = (data.messages || []).map(normalizeMessage);
      const lastAssistant = [...loaded].reverse().find((message) => message.role === 'assistant');
      const meta = lastAssistant?.metadata || {};
      setActiveId(data.id);
      setTitle(data.title || '新对话');
      setMessages(loaded);
      setInspector({
        trace: meta.trace || [],
        citations: meta.citations || [],
        memory: null,
        usage: meta.usage || null,
        grounding: meta.grounding || null,
        cacheHit: Boolean(meta.cacheHit),
        provider: meta.provider || null,
      });
      setTab('trace');
      setHighlight(null);
      window.history.replaceState(null, '', `?session=${encodeURIComponent(data.id)}`);
      nearBottomRef.current = true;
      requestAnimationFrame(() => scrollToBottom(false));

      if (loaded.length) {
        api
          .getMemory(data.id)
          .then((memory) => {
            if (!memory || memory.available === false) return;
            setInspector((prev) => ({
              ...prev,
              memory: {
                profile: { ...(memory.profile || {}), lastOrderId: memory.lastOrderId || memory.profile?.lastOrderId },
                summary: memory.summary || '',
                summarizedMessages: memory.summarizedCount || 0,
                totalMessages: memory.messageCount || 0,
                tokenEstimate: meta.usage?.inputTokens || 0,
                tokenBudget: 3200,
                layers: ['系统规则', '长期记忆', '历史摘要', '最近对话', '当前问题'],
                droppedMessages: 0,
              },
            }));
          })
          .catch(() => {});
      }
    } catch (error) {
      notify(errorMessage(error), 'error');
      if (fromUrl) {
        window.history.replaceState(null, '', window.location.pathname);
      }
    } finally {
      setLoadingSession(false);
    }
  };

  const newChat = () => {
    if (isStreaming) stopGeneration(true);
    streamSeqRef.current += 1;
    discardTokenBuffer();
    setActiveId(null);
    setTitle('新对话');
    setMessages([]);
    setInspector(EMPTY_INSPECTOR);
    setTab('trace');
    setHighlight(null);
    setInput('');
    setSidebarOpen(false);
    setInspectorOpen(false);
    setShowJump(false);
    window.history.replaceState(null, '', window.location.pathname);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteSession(deleteTarget.id);
      setSessions((prev) => prev.filter((item) => item.id !== deleteTarget.id));
      if (activeId === deleteTarget.id) {
        newChat();
      }
      notify('会话已删除', 'success');
      setDeleteTarget(null);
    } catch (error) {
      notify(errorMessage(error), 'error');
    } finally {
      setDeleting(false);
    }
  };

  const copyLink = async () => {
    if (!activeId) {
      notify('先开始一段对话，再复制会话链接');
      return;
    }
    const url = `${window.location.origin}${window.location.pathname}?session=${encodeURIComponent(activeId)}`;
    try {
      await navigator.clipboard.writeText(url);
      notify('会话链接已复制，可在另一台设备继续', 'success');
    } catch {
      notify('复制失败，请手动复制地址栏链接');
    }
  };

  const openTraceForMessage = (message) => {
    const meta = message.metadata || {};
    setInspector((prev) => ({
      ...prev,
      trace: meta.trace || prev.trace,
      citations: meta.citations || prev.citations,
      usage: meta.usage || prev.usage,
      grounding: meta.grounding || prev.grounding,
      provider: meta.provider || prev.provider,
      cacheHit: meta.cacheHit ?? prev.cacheHit,
    }));
    setTab('trace');
    if (window.innerWidth <= 1180) setInspectorOpen(true);
  };

  const handleCitationClick = (number) => {
    if (!number) return;
    setTab('evidence');
    setHighlight(number);
    if (window.innerWidth <= 1180) setInspectorOpen(true);
  };

  useEffect(() => {
    const onKeyDown = (event) => {
      const meta = event.metaKey || event.ctrlKey;
      if (meta && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        newChat();
      }
      if (event.key === 'Escape') {
        setSidebarOpen(false);
        setInspectorOpen(false);
        setDeleteTarget(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // 快捷键绑定最新的 newChat 行为。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming, activeId, activeRun]);

  const handleScroll = () => {
    const el = scrollerRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const near = distance < 140;
    nearBottomRef.current = near;
    setShowJump(!near && messages.length > 0);
  };

  const agent = health?.agent;
  const online = backendUp && agent?.status === 'up';
  const degraded = backendUp && agent && agent.status !== 'up';
  const provider = agent?.providers?.primary;
  const connectionLabel = backendUp === null ? '连接中' : online ? 'Agent 在线' : degraded ? '服务降级' : '服务离线';
  const connectionTone = backendUp === null ? 'pending' : online ? 'online' : 'danger';
  const statusHint =
    connectionLabel === 'Agent 在线'
      ? `${provider || 'Agent'} · 工具与知识库可用`
      : connectionLabel === '服务降级'
        ? '模型可能降级到本地规则引擎'
        : '请确认 Python 与 Spring Boot 都已启动';

  return (
    <div className="app-shell">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onNew={newChat}
        onOpen={openSession}
        onDelete={setDeleteTarget}
        health={health}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        loading={sessionsLoading}
      />

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="icon-button mobile-menu"
              onClick={() => setSidebarOpen(true)}
              aria-label="打开会话列表"
            >
              <Icon name="menu" size={19} />
            </button>
            <div className="topbar-title">
              <div className="breadcrumb">
                <span>售后工作台</span>
                <Icon name="chevronRight" size={11} />
                <span>{sessionDate(new Date().toISOString())}</span>
              </div>
              <h1>{compactTitle(title)}</h1>
            </div>
          </div>

          <div className="topbar-actions">
            <div className="connection-pill" title={statusHint}>
              <span className={`status-dot ${connectionTone}`} />
              <span>{connectionLabel}</span>
            </div>
            <span className="provider-pill" title={statusHint}>
              {providerLabel(provider)}
            </span>
            <span className="topbar-divider" />
            <SettingsMenu
              theme={theme}
              onThemeChange={setTheme}
              fontSize={fontSize}
              onFontSizeChange={setFontSize}
              density={density}
              onDensityChange={setDensity}
              motion={motion}
              onMotionChange={setMotion}
              onReset={resetAppearance}
            />
            <button
              type="button"
              className="icon-button"
              onClick={copyLink}
              title="复制会话链接"
              aria-label="复制会话链接"
            >
              <Icon name="copy" size={17} />
            </button>
            <button
              type="button"
              className="icon-button inspect-toggle"
              onClick={() => setInspectorOpen(true)}
              title="打开 Agent 观察窗"
              aria-label="打开 Agent 观察窗"
            >
              <Icon name="panel" size={18} />
              {(inspector.trace?.length > 0 || inspector.citations?.length > 0) && (
                <span className="inspect-badge" />
              )}
            </button>
          </div>
        </header>

        <div className="main-grid">
          <main className="chat-panel">
            {backendUp === false && (
              <div className="offline-banner">
                <span className="offline-icon">
                  <Icon name="alert" size={15} />
                </span>
                <div>
                  <strong>后端服务未连接</strong>
                  <span>请先运行 scripts\start.ps1，或检查 Spring Boot 8088 端口。</span>
                </div>
                <button type="button" onClick={refreshHealth}>
                  重试
                </button>
              </div>
            )}

            <div className="chat-scroll" ref={scrollerRef} onScroll={handleScroll}>
              {loadingSession ? (
                <div className="session-loading">
                  <span className="loading-ring" />
                  <span>正在恢复会话与记忆…</span>
                </div>
              ) : messages.length === 0 ? (
                <Welcome onPrompt={sendText} health={health} />
              ) : (
                <div className="message-list">
                  <div className="conversation-day">
                    <span />
                    今天
                    <span />
                  </div>
                  {messages.map((message) => (
                    <ChatMessage
                      key={message.clientKey}
                      message={message}
                      onCitationClick={handleCitationClick}
                      onOpenTrace={openTraceForMessage}
                      onToast={notify}
                    />
                  ))}
                </div>
              )}
            </div>

            {showJump && (
              <button
                type="button"
                className="jump-bottom"
                onClick={() => scrollToBottom(true)}
                aria-label="回到最新消息"
              >
                <Icon name="arrowDown" size={16} />
                最新
              </button>
            )}

            <div className="composer-area">
              <Composer
                value={input}
                onChange={setInput}
                onSend={() => sendText()}
                onStop={() => stopGeneration(false)}
                streaming={isStreaming}
                disabled={loadingSession}
                placeholder={
                  loadingSession
                    ? '正在恢复会话…'
                    : isStreaming
                      ? '晴舟正在处理，你可以先输入下一条'
                      : activeId
                        ? '继续补充问题，或发送一个订单号…'
                        : '描述你的售后问题，或直接发订单号…'
                }
              />
            </div>
          </main>

          <Inspector
            open={inspectorOpen}
            onClose={() => setInspectorOpen(false)}
            tab={tab}
            onTab={setTab}
            inspector={inspector}
            streaming={isStreaming}
            highlight={highlight}
            onClearHighlight={() => setHighlight(null)}
          />
        </div>
      </div>

      <Toast toast={toast} />
      <ConfirmDialog
        session={deleteTarget}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        busy={deleting}
      />
    </div>
  );
}
