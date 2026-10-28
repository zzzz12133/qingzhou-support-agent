import React from 'react';
import Icon from './Icons.jsx';

const CAPABILITIES = [
  {
    icon: 'package',
    tone: 'mint',
    title: '订单与物流',
    text: '先查真实轨迹，再回答到哪了',
  },
  {
    icon: 'rotate',
    tone: 'sand',
    title: '退换判定',
    text: '签收天数 × 会员权益，不靠猜',
  },
  {
    icon: 'wrench',
    tone: 'blue',
    title: '改址与保修',
    text: '能在线办的办，办不了就建单',
  },
  {
    icon: 'shield',
    tone: 'rose',
    title: '安全与依据',
    text: '知识库引用，注入请求会被拦下',
  },
];

const PROMPTS = [
  {
    icon: 'package',
    label: '查物流',
    text: '帮我查一下 A1001 到哪了',
    meta: '订单 · 运输中',
  },
  {
    icon: 'rotate',
    label: '试退货',
    text: 'A1002 能退货吗？',
    meta: '售后 · 已签收第 4 天',
  },
  {
    icon: 'wrench',
    label: '改地址',
    text: 'A1003 帮我改地址',
    meta: '工单 · 待发货',
  },
  {
    icon: 'clock',
    label: '问规则',
    text: '退款多久到账？',
    meta: '知识库 · 政策咨询',
  },
];

export default function Welcome({ onPrompt, health }) {
  const kbChunks = health?.agent?.knowledge?.chunks;
  const primary = health?.agent?.providers?.primary;
  const online = health?.agent?.status === 'up';

  return (
    <section className="welcome">
      <div className="welcome-inner">
        <div className="welcome-eyebrow">
          <span className="eyebrow-pulse" />
          <span>晴舟售后 · AI 客服工作台</span>
          <span className="eyebrow-divider">/</span>
          <span className="eyebrow-muted">MVP 可运行版</span>
        </div>

        <h1>
          把每一次售后，
          <br />
          <em>都处理得明明白白。</em>
        </h1>
        <p className="welcome-lead">
          晴舟会先查订单、再查规则，最后才回答。
          每一步工具调用、每一条知识依据，你都能在右侧看见。
        </p>

        <div className="weather-strip">
          <div className="weather-cell weather-now">
            <div className="weather-now-head">
              <span>服务天气</span>
              <span className={`weather-live ${online ? 'on' : ''}`}>
                <i />
                LIVE
              </span>
            </div>
            <strong>{online ? '晴朗' : '多云'}</strong>
            <span className="weather-caption">
              {online ? 'Agent 在线 · 工具就绪' : '正在连接 Agent'}
            </span>
          </div>
          <div className="weather-cell weather-metric">
            <span className="weather-icon blue">
              <Icon name="wrench" size={16} />
            </span>
            <div>
              <strong>5</strong>
              <span>可调用工具</span>
            </div>
          </div>
          <div className="weather-cell weather-metric">
            <span className="weather-icon gold">
              <Icon name="book" size={16} />
            </span>
            <div>
              <strong>{kbChunks || '—'}</strong>
              <span>知识切片</span>
            </div>
          </div>
        </div>

        <div className="capability-grid">
          {CAPABILITIES.map((item) => (
            <div className={`capability ${item.tone}`} key={item.title}>
              <span className="capability-icon">
                <Icon name={item.icon} size={18} />
              </span>
              <div>
                <strong>{item.title}</strong>
                <span>{item.text}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="prompt-heading">
          <div>
            <span className="section-kicker">TRY A SCENARIO</span>
            <h2>从一个具体问题开始</h2>
          </div>
          <span className="demo-orders">演示订单 A1001–A1005</span>
        </div>

        <div className="prompt-grid">
          {PROMPTS.map((prompt) => (
            <button
              type="button"
              className="prompt-card"
              key={prompt.text}
              onClick={() => onPrompt(prompt.text)}
            >
              <span className="prompt-icon">
                <Icon name={prompt.icon} size={17} />
              </span>
              <span className="prompt-copy">
                <span className="prompt-meta">{prompt.label} · {prompt.meta}</span>
                <strong>{prompt.text}</strong>
              </span>
              <span className="prompt-arrow">
                <Icon name="chevronRight" size={15} />
              </span>
            </button>
          ))}
        </div>

        <div className="welcome-foot">
          <span>
            <Icon name="lock" size={13} /> 不索取密码或验证码
          </span>
          <span>
            <Icon name="book" size={13} /> {kbChunks ? `${kbChunks} 个知识切片已加载` : '知识库加载中'}
          </span>
          <span>
            <Icon name="spark" size={13} /> 14 个工程难点 · {primary || '演示模型'}
          </span>
        </div>
      </div>
    </section>
  );
}
