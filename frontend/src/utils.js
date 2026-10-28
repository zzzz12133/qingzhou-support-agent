export function formatTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

export function dayLabel(iso) {
  if (!iso) return '更早';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '更早';
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diff = Math.round((start - target) / 86_400_000);
  if (diff <= 0) return '今天';
  if (diff === 1) return '昨天';
  if (diff < 7) return `${diff} 天前`;
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
}

export function groupSessions(sessions) {
  const groups = [];
  for (const session of sessions || []) {
    const label = dayLabel(session.updatedAt);
    let group = groups.find((item) => item.label === label);
    if (!group) {
      group = { label, items: [] };
      groups.push(group);
    }
    group.items.push(session);
  }
  return groups;
}

export function formatRelative(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return '刚刚';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} 小时前`;
  return dayLabel(iso);
}

export function formatDuration(ms) {
  if (ms == null) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
}

export function formatNumber(value) {
  if (value == null || Number.isNaN(Number(value))) return '0';
  return new Intl.NumberFormat('zh-CN').format(Number(value));
}

export function providerLabel(provider) {
  if (!provider) return 'AGENT';
  if (provider.includes('缓存')) return 'CACHE';
  if (provider.includes('安全')) return 'GUARD';
  if (provider.includes('本地') || provider.includes('降级') || provider.includes('mock')) return 'MOCK';
  if (provider.toLowerCase().includes('deepseek')) return 'DEEPSEEK';
  if (provider.toLowerCase().includes('openai')) return 'OPENAI';
  return provider.length > 10 ? provider.slice(0, 10) : provider;
}

export function providerDescription(provider) {
  if (!provider) return '等待 Agent 状态';
  if (provider.includes('缓存')) return '语义缓存命中，未重复调用模型';
  if (provider.includes('安全')) return '安全护栏直接拦截，未调用模型';
  if (provider.includes('本地') || provider.includes('降级')) return '未配置模型 Key 时的确定性演示路径';
  return provider;
}

export function sessionDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' });
}

export function compactTitle(title) {
  return title && title.trim() ? title.trim() : '新对话';
}

export function errorMessage(error) {
  if (!error) return '出了点问题，请稍后重试。';
  if (error.name === 'AbortError') return '已停止生成。';
  if (error.status === 429) {
    return error.retryAfter
      ? `发送太频繁，请 ${error.retryAfter} 秒后再试。`
      : '发送太频繁，请稍后再试。';
  }
  return error.message || '网络连接失败，请检查服务是否启动。';
}
