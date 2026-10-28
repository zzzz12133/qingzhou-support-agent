import React, { useMemo, useState } from 'react';
import Icon, { BoatMark } from './Icons.jsx';
import Markdown from './Markdown.jsx';
import {
  formatDuration,
  formatNumber,
  formatTime,
  providerDescription,
  providerLabel,
} from '../utils.js';

const GROUNDING_STYLES = {
  grounded: { icon: 'shield', tone: 'good', label: '知识库已引用' },
  tool_grounded: { icon: 'check', tone: 'good', label: '工具事实已校验' },
  partially_grounded: { icon: 'alert', tone: 'warn', label: '依据未标注' },
  flagged: { icon: 'alert', tone: 'warn', label: '引用待复核' },
  unverified: { icon: 'spark', tone: 'muted', label: '一般说明' },
  blocked: { icon: 'shield', tone: 'blocked', label: '安全拦截' },
};

export default function ChatMessage({
  message,
  onCitationClick,
  onOpenTrace,
  onToast,
}) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const isUser = message.role === 'user';
  const meta = message.metadata || {};
  const trace = meta.trace || [];
  const citations = meta.citations || [];
  const usage = meta.usage || {};
  const grounding = meta.grounding;
  const streaming = message.status === 'streaming';
  const stopped = message.status === 'stopped';
  const failed = message.status === 'error';

  const toolCount = useMemo(
    () => trace.filter((item) => item && item.name !== 'semantic_cache').length,
    [trace]
  );
  const duration = meta.durationMs;
  const groundingStyle = grounding ? GROUNDING_STYLES[grounding.status] || GROUNDING_STYLES.unverified : null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content || '');
      setCopied(true);
      onToast?.('已复制回复');
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      onToast?.('复制失败，请手动选择文本');
    }
  };

  const leaveFeedback = (value) => {
    setFeedback(value);
    onToast?.(value === 'up' ? '谢谢反馈，已记录为有帮助' : '谢谢反馈，我们会继续改进');
  };

  if (isUser) {
    return (
      <article className="message-row user-row">
        <div className="user-message">
          <div className="user-bubble">{message.content}</div>
          <div className="user-meta">
            <span>{formatTime(message.createdAt)}</span>
            <span className="user-delivered">
              <Icon name="check" size={11} /> 已送达
            </span>
          </div>
        </div>
      </article>
    );
  }

  return (
    <article className={`message-row assistant-row ${streaming ? 'is-streaming' : ''}`}>
      <div className="assistant-avatar">
        <BoatMark size={28} />
      </div>
      <div className="assistant-message">
        <div className="assistant-head">
          <div className="assistant-identity">
            <strong>晴舟</strong>
            <span className="ai-tag">AI 客服</span>
            {meta.intentLabel && !streaming && <span className="intent-tag">{meta.intentLabel}</span>}
            {meta.cacheHit && <span className="cache-tag">缓存命中</span>}
            {meta.degraded && <span className="degraded-tag">已降级</span>}
          </div>
          <span className="assistant-time">{formatTime(message.createdAt)}</span>
        </div>

        {(toolCount > 0 || (streaming && meta.stage)) && (
          <button
            type="button"
            className="trace-strip"
            onClick={() => onOpenTrace?.(message)}
            title="在右侧查看执行轨迹"
          >
            <span className={`trace-strip-icon ${streaming ? 'working' : ''}`}>
              <Icon name={streaming ? 'spark' : 'route'} size={13} />
            </span>
            <span className="trace-strip-text">
              {streaming && meta.stage
                ? meta.stage
                : `已调用 ${toolCount} 个工具${duration ? ` · ${formatDuration(duration)}` : ''}`}
            </span>
            <Icon name="chevronRight" size={13} />
          </button>
        )}

        {streaming && !message.content && (
          <div className="thinking-block">
            <span className="thinking-dots" aria-label="正在生成">
              <i />
              <i />
              <i />
            </span>
            <span>{meta.stage || '正在连接 Agent'}</span>
          </div>
        )}

        {failed && !message.content ? (
          <div className="message-error">
            <span className="error-icon">
              <Icon name="alert" size={16} />
            </span>
            <div>
              <strong>这次没有生成完成</strong>
              <p>{message.error || '连接中断了，请重新发送。'}</p>
            </div>
          </div>
        ) : stopped && !message.content ? (
          <div className="stopped-block">
            <span className="stopped-icon">
              <Icon name="stop" size={12} />
            </span>
            已停止生成。你可以换个问法，或重新发送。
          </div>
        ) : (
          <div className={`message-content ${streaming && message.content ? 'is-streaming' : ''}`}>
            <Markdown text={message.content} onCitationClick={onCitationClick} />
          </div>
        )}

        {failed && message.content && (
          <div className="inline-error">
            <Icon name="alert" size={12} />
            {message.error || '回答中断，以上内容可能不完整。'}
          </div>
        )}

        {meta.notice && (
          <div className="notice-line">
            <Icon name="alert" size={13} /> {meta.notice}
          </div>
        )}

        {citations.length > 0 && (
          <div className="answer-sources">
            <span className="sources-label">
              <Icon name="book" size={13} /> 依据
            </span>
            <div className="source-chips">
              {citations.map((citation, index) => (
                <button
                  type="button"
                  className="source-chip"
                  key={`${citation.id || index}-${index}`}
                  onClick={() => onCitationClick?.(citation.index || index + 1)}
                  title={citation.title}
                >
                  <span>{citation.index || index + 1}</span>
                  {citation.title?.split(' · ').pop() || '平台规则'}
                </button>
              ))}
            </div>
          </div>
        )}

        {!streaming && (grounding || usage.totalTokens || trace.length > 0) && (
          <div className="message-foot">
            {groundingStyle && (
              <button
                type="button"
                className={`grounding-pill ${groundingStyle.tone}`}
                onClick={() => onCitationClick?.(1)}
                title={grounding.detail}
              >
                <Icon name={groundingStyle.icon} size={12} />
                {groundingStyle.label}
              </button>
            )}
            {usage.totalTokens ? (
              <span className="foot-meta" title={usage.estimated ? '按字符估算' : '来自模型用量'}>
                ≈ {formatNumber(usage.totalTokens)} tokens
              </span>
            ) : null}
            {duration ? <span className="foot-meta">{formatDuration(duration)}</span> : null}
            {meta.provider && (
              <span className="foot-meta provider" title={providerDescription(meta.provider)}>
                {providerLabel(meta.provider)}
              </span>
            )}
            {stopped && (
              <span className="stopped-tag">
                <Icon name="stop" size={10} /> 已停止
              </span>
            )}
            <span className="foot-spacer" />
            <div className="message-actions">
              <button
                type="button"
                className={`mini-action ${copied ? 'active' : ''}`}
                onClick={copy}
                title="复制"
                aria-label="复制回复"
              >
                <Icon name={copied ? 'check' : 'copy'} size={14} />
              </button>
              <button
                type="button"
                className={`mini-action ${feedback === 'up' ? 'active' : ''}`}
                onClick={() => leaveFeedback('up')}
                title="有帮助"
                aria-label="标记有帮助"
              >
                <Icon name="thumbsUp" size={14} />
              </button>
              <button
                type="button"
                className={`mini-action ${feedback === 'down' ? 'active' : ''}`}
                onClick={() => leaveFeedback('down')}
                title="需改进"
                aria-label="标记需改进"
              >
                <Icon name="thumbsDown" size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}
