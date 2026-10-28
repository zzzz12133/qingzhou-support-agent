import React from 'react';
import Icon from './Icons.jsx';
import { formatDuration, formatNumber, providerDescription, providerLabel } from '../utils.js';

const PROFILE_LABELS = {
  name: '称呼',
  memberTier: '会员',
  city: '城市',
  contactPreference: '联系偏好',
  recipient: '收件人',
  lastProduct: '最近商品',
  lastOrderId: '当前订单',
  interest: '关注点',
};

const GROUNDING_STYLES = {
  grounded: { icon: 'shield', tone: 'good', label: '知识库已引用' },
  tool_grounded: { icon: 'check', tone: 'good', label: '工具事实已校验' },
  partially_grounded: { icon: 'alert', tone: 'warn', label: '依据未标注' },
  flagged: { icon: 'alert', tone: 'warn', label: '引用待复核' },
  unverified: { icon: 'spark', tone: 'muted', label: '一般说明' },
  blocked: { icon: 'shield', tone: 'blocked', label: '安全拦截' },
};

function EmptyState({ icon, title, text }) {
  return (
    <div className="inspector-empty">
      <span className="inspector-empty-icon">
        <Icon name={icon} size={22} />
      </span>
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}

function TraceTab({ inspector, streaming }) {
  const trace = inspector.trace || [];
  const memory = inspector.memory;
  const steps = [];

  if (memory || trace.length) {
    steps.push({
      name: 'context',
      label: '理解与装配记忆',
      status: 'done',
      summary: memory
        ? `${memory.totalMessages || 0} 条消息 · 估算 ${formatNumber(memory.tokenEstimate)} tokens`
        : '已装载历史上下文',
    });
  }

  for (const item of trace) {
    steps.push({
      name: item.name,
      label: item.label || item.name,
      status: item.status === 'error' ? 'error' : item.status === 'running' ? 'running' : 'done',
      summary: item.summary,
      durationMs: item.durationMs,
    });
  }

  if (steps.length) {
    const grounding = inspector.grounding;
    steps.push({
      name: 'compose',
      label: '生成与核对依据',
      status: streaming ? 'running' : grounding?.status === 'flagged' ? 'error' : 'done',
      summary: grounding?.label || (streaming ? '等待模型输出' : '回答已生成'),
    });
  }

  if (!steps.length) {
    return (
      <EmptyState
        icon="route"
        title="还没有执行轨迹"
        text="发一条订单或售后问题，这里会展示 Agent 的每一步工具调用、耗时与结果。"
      />
    );
  }

  return (
    <div className="trace-view">
      <div className="inspector-note">
        <Icon name="spark" size={13} />
        工具执行与上下文装配是实时事件，不是事后编造的时间线。
      </div>
      <div className="timeline">
        {steps.map((step, index) => (
          <div className={`timeline-item ${step.status}`} key={`${step.name}-${index}`}>
            <div className="timeline-rail">
              <span className="timeline-node">
                {step.status === 'running' ? (
                  <span className="node-spinner" />
                ) : step.status === 'error' ? (
                  <Icon name="alert" size={11} />
                ) : (
                  <Icon name="check" size={11} />
                )}
              </span>
              {index < steps.length - 1 && <span className="timeline-line" />}
            </div>
            <div className="timeline-body">
              <div className="timeline-head">
                <strong>{step.label}</strong>
                <span className={`timeline-status ${step.status}`}>
                  {step.status === 'running' ? '执行中' : step.status === 'error' ? '需关注' : '完成'}
                </span>
              </div>
              {step.summary && <p>{step.summary}</p>}
              {step.durationMs != null && (
                <span className="timeline-meta">
                  <Icon name="clock" size={11} /> {formatDuration(step.durationMs)}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
      {inspector.provider && (
        <div className="provider-card">
          <span className="provider-card-label">本轮模型路由</span>
          <strong>{providerLabel(inspector.provider)}</strong>
          <p>{providerDescription(inspector.provider)}</p>
        </div>
      )}
    </div>
  );
}

function MemoryTab({ memory }) {
  if (!memory) {
    return (
      <EmptyState
        icon="brain"
        title="记忆将在对话中形成"
        text="长期画像、对话摘要和最近窗口会在每轮请求前重新装配。"
      />
    );
  }

  const profileEntries = Object.entries(memory.profile || {}).filter(
    ([key, value]) => PROFILE_LABELS[key] && value
  );
  const used = Number(memory.tokenEstimate || 0);
  const budget = Math.max(1, Number(memory.tokenBudget || 1));
  const percent = Math.min(100, Math.round((used / budget) * 100));
  const layers = memory.layers || [];

  return (
    <div className="memory-view">
      <div className="memory-section">
        <div className="memory-section-head">
          <span>长期画像</span>
          <span className="live-chip">
            <i /> LIVE
          </span>
        </div>
        {profileEntries.length ? (
          <div className="profile-chips">
            {profileEntries.map(([key, value]) => (
              <span className="profile-chip" key={key}>
                <span>{PROFILE_LABELS[key]}</span>
                {String(value)}
              </span>
            ))}
          </div>
        ) : (
          <p className="memory-muted">还没有提取到稳定偏好。告诉晴舟称呼、城市或联系习惯试试。</p>
        )}
      </div>

      <div className="memory-section">
        <div className="memory-section-head">
          <span>历史摘要</span>
          <span className="memory-count">
            {memory.summarizedMessages || 0} 条已压缩
          </span>
        </div>
        <div className="summary-block">
          {memory.summary || '当前对话较短，还没有触发摘要压缩。'}
        </div>
        <p className="memory-hint">
          <Icon name="spark" size={12} />
          窗口默认保留最近 12 条消息；更早内容抽取为摘要，放在系统提示前。
        </p>
      </div>

      <div className="memory-section">
        <div className="memory-section-head">
          <span>上下文预算</span>
          <span className="memory-count">
            {formatNumber(used)} / {formatNumber(budget)} tokens
          </span>
        </div>
        <div className="budget-bar">
          <span style={{ width: `${percent}%` }} />
        </div>
        <div className="budget-legend">
          <span>已装配 {percent}%</span>
          <span>{memory.droppedMessages ? `裁剪 ${memory.droppedMessages} 条` : '未触发裁剪'}</span>
        </div>
      </div>

      <div className="memory-section">
        <div className="memory-section-head">
          <span>七段式上下文</span>
        </div>
        <div className="layer-list">
          {layers.map((layer, index) => (
            <span className="layer-item" key={layer}>
              <span>{index + 1}</span>
              {layer}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function EvidenceTab({ inspector, highlight, onClearHighlight }) {
  const citations = inspector.citations || [];
  const grounding = inspector.grounding;
  const style = grounding ? GROUNDING_STYLES[grounding.status] || GROUNDING_STYLES.unverified : null;

  if (!citations.length && !grounding) {
    return (
      <EmptyState
        icon="book"
        title="回答会带上依据"
        text="政策类问题会先检索知识库；订单类问题会先调用工具，再生成回答。"
      />
    );
  }

  return (
    <div className="evidence-view">
      {style && (
        <div className={`grounding-card ${style.tone}`}>
          <span className="grounding-icon">
            <Icon name={style.icon} size={17} />
          </span>
          <div>
            <strong>{style.label}</strong>
            <p>{grounding.detail || '依据校验结果'}</p>
          </div>
        </div>
      )}

      {!citations.length && (
        <EmptyState
          icon="wrench"
          title="本轮没有引用知识库"
          text="回答基于订单工具返回的结构化事实，或属于无需检索的问候。"
        />
      )}

      {citations.map((citation, index) => {
        const number = citation.index || index + 1;
        return (
          <article
            className={`citation-card ${highlight === number ? 'highlight' : ''}`}
            key={`${citation.id || index}-${number}`}
            onClick={() => onClearHighlight?.()}
          >
            <div className="citation-head">
              <span className="citation-index">{number}</span>
              <strong>{citation.title || '平台规则'}</strong>
              {citation.score != null && (
                <span className="citation-score">{Number(citation.score).toFixed(1)}</span>
              )}
            </div>
            <p>{citation.snippet || ''}</p>
            <span className="citation-id">{citation.id || `KB-${number}`}</span>
          </article>
        );
      })}

      <div className="evidence-foot">
        <span>
          <Icon name="shield" size={12} /> 只引用检索结果
        </span>
        <span>{inspector.cacheHit ? '本次命中语义缓存' : '知识库版本随引用返回'}</span>
      </div>
    </div>
  );
}

export default function Inspector({
  open,
  onClose,
  tab,
  onTab,
  inspector,
  streaming,
  highlight,
  onClearHighlight,
}) {
  const traceCount = (inspector.trace || []).length;
  const citationCount = (inspector.citations || []).length;

  return (
    <>
      <div
        className={`inspector-backdrop ${open ? 'is-visible' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className={`inspector ${open ? 'is-open' : ''}`}>
        <header className="inspector-head">
          <div>
            <span className="inspector-kicker">AGENT OBSERVABILITY</span>
            <h2>Agent 观察窗</h2>
          </div>
          <button className="icon-button inspector-close" type="button" onClick={onClose} aria-label="关闭观察窗">
            <Icon name="close" size={18} />
          </button>
        </header>
        <p className="inspector-sub">
          看它如何查、如何记、引用了什么。所有数据来自本轮真实事件。
        </p>

        <div className="inspector-tabs" role="tablist" aria-label="Agent 观察窗">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'trace'}
            className={tab === 'trace' ? 'active' : ''}
            onClick={() => onTab('trace')}
          >
            <Icon name="route" size={14} /> 轨迹
            {traceCount > 0 && <span>{traceCount}</span>}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'memory'}
            className={tab === 'memory' ? 'active' : ''}
            onClick={() => onTab('memory')}
          >
            <Icon name="brain" size={14} /> 记忆
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'evidence'}
            className={tab === 'evidence' ? 'active' : ''}
            onClick={() => onTab('evidence')}
          >
            <Icon name="book" size={14} /> 依据
            {citationCount > 0 && <span>{citationCount}</span>}
          </button>
        </div>

        <div className="inspector-body">
          {tab === 'trace' && <TraceTab inspector={inspector} streaming={streaming} />}
          {tab === 'memory' && <MemoryTab memory={inspector.memory} />}
          {tab === 'evidence' && (
            <EvidenceTab
              inspector={inspector}
              highlight={highlight}
              onClearHighlight={onClearHighlight}
            />
          )}
        </div>

        <footer className="inspector-foot">
          <span className="live-dot" />
          实时观察 · 只读
          <span className="inspector-foot-sep">·</span>
          Agent v0.1
        </footer>
      </aside>
    </>
  );
}
