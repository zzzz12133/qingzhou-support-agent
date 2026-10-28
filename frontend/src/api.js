export class ApiError extends Error {
  constructor(message, { status = 0, code = 'UNKNOWN', retryAfter = null, retryable = true } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
    this.retryable = retryable;
  }
}

export const USER_ID =
  (typeof localStorage !== 'undefined' && localStorage.getItem('lightdesk-user')) || 'demo-user';

export function clientId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      // 保留空对象，下面按状态码兜底。
    }
    throw new ApiError(payload.message || `请求失败（HTTP ${response.status}）`, {
      status: response.status,
      code: payload.code || `HTTP_${response.status}`,
      retryAfter: payload.retryAfter || Number(response.headers.get('Retry-After')) || null,
      retryable: payload.retryable !== false,
    });
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export const api = {
  health: () => request('/api/health'),
  listSessions: () => request(`/api/sessions?userId=${encodeURIComponent(USER_ID)}`),
  createSession: (title) =>
    request('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ userId: USER_ID, title }),
    }),
  getSession: (id) =>
    request(`/api/sessions/${encodeURIComponent(id)}?userId=${encodeURIComponent(USER_ID)}`),
  getMemory: (id) =>
    request(`/api/sessions/${encodeURIComponent(id)}/memory?userId=${encodeURIComponent(USER_ID)}`),
  deleteSession: (id) =>
    request(`/api/sessions/${encodeURIComponent(id)}?userId=${encodeURIComponent(USER_ID)}`, {
      method: 'DELETE',
    }),
  cancel: (messageId) =>
    request(`/api/chat/${encodeURIComponent(messageId)}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ userId: USER_ID }),
    }),
};

/**
 * 用 fetch + ReadableStream 消费 SSE。
 * 不用 EventSource，因为这里需要 POST，并且要能主动 abort 后再通知后端取消。
 */
export async function streamChat({ sessionId, message, clientMessageId, signal, onEvent }) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      conversationId: sessionId,
      userId: USER_ID,
      message,
      clientMessageId,
    }),
    signal,
  });

  if (!response.ok) {
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      // 忽略非 JSON 错误体。
    }
    throw new ApiError(payload.message || `无法开始对话（HTTP ${response.status}）`, {
      status: response.status,
      code: payload.code || `HTTP_${response.status}`,
      retryAfter: payload.retryAfter || null,
      retryable: payload.retryable !== false,
    });
  }
  if (!response.body) {
    throw new ApiError('浏览器不支持流式响应。');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const dispatch = (block) => {
    const data = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
      .join('\n');
    if (!data.trim()) return;
    let payload;
    try {
      payload = JSON.parse(data);
    } catch (error) {
      console.warn('忽略无法解析的 SSE 事件', error, data.slice(0, 200));
      return;
    }
    onEvent?.(payload);
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || '';
    for (const block of blocks) {
      dispatch(block);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) {
    dispatch(buffer);
  }
}
