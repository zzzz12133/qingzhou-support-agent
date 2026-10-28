import React from 'react';
import Icon, { BoatMark } from './Icons.jsx';
import { formatRelative, groupSessions, providerLabel } from '../utils.js';

export default function Sidebar({
  sessions,
  activeId,
  onNew,
  onOpen,
  onDelete,
  health,
  open,
  onClose,
  loading,
}) {
  const groups = groupSessions(sessions);
  const agent = health?.agent;
  const online = agent?.status === 'up';
  const primary = agent?.providers?.primary;
  const provider = primary || '等待连接';
  const kbChunks = agent?.knowledge?.chunks;

  return (
    <>
      <div
        className={`sidebar-backdrop ${open ? 'is-visible' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className={`sidebar ${open ? 'is-open' : ''}`}>
        <div className="brand">
          <BoatMark size={40} />
          <div className="brand-copy">
            <span className="brand-name">晴舟客服</span>
            <span className="brand-sub">QINGZHOU · AGENT</span>
          </div>
          <button className="icon-button sidebar-close" type="button" onClick={onClose} aria-label="关闭菜单">
            <Icon name="close" size={18} />
          </button>
        </div>

        <button className="new-chat" type="button" onClick={onNew}>
          <span className="new-chat-plus">
            <Icon name="plus" size={17} strokeWidth={2} />
          </span>
          <span>开启新对话</span>
          <kbd>Ctrl K</kbd>
        </button>

        <div className="session-heading">
          <span>最近会话</span>
          <span className="session-count">{sessions.length}</span>
        </div>

        <nav className="session-list" aria-label="会话列表">
          {loading && sessions.length === 0 && (
            <div className="session-skeleton">
              <span />
              <span />
              <span />
            </div>
          )}
          {!loading && sessions.length === 0 && (
            <div className="session-empty">
              <span className="empty-ring">
                <Icon name="chat" size={20} />
              </span>
              <p>还没有对话</p>
              <span>从一个订单问题开始</span>
            </div>
          )}
          {groups.map((group) => (
            <div className="session-group" key={group.label}>
              <div className="session-group-label">{group.label}</div>
              {group.items.map((session) => (
                <div
                  className={`session-item ${activeId === session.id ? 'active' : ''}`}
                  key={session.id}
                >
                  <button
                    type="button"
                    className="session-main"
                    onClick={() => onOpen(session.id)}
                    title={session.title}
                  >
                    <span className="session-glyph">
                      <Icon name="chat" size={15} />
                    </span>
                    <span className="session-copy">
                      <span className="session-title">{session.title}</span>
                      <span className="session-preview">{session.preview}</span>
                    </span>
                    <span className="session-time">{formatRelative(session.updatedAt)}</span>
                  </button>
                  <button
                    type="button"
                    className="session-delete"
                    aria-label={`删除会话 ${session.title}`}
                    title="删除会话"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDelete(session);
                    }}
                  >
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="runtime-card">
            <div className="runtime-line">
              <span className={`status-dot ${online ? 'online' : agent ? 'danger' : 'pending'}`} />
              <span>{online ? 'Agent 在线' : agent ? '服务降级' : '连接中'}</span>
              <span className="runtime-provider">{providerLabel(provider)}</span>
            </div>
            <div className="runtime-meta">
              <span>{kbChunks ? `${kbChunks} 个知识切片` : '知识库待连接'}</span>
              <span>v0.1</span>
            </div>
          </div>
          <div className="profile">
            <span className="profile-avatar">张</span>
            <span className="profile-copy">
              <strong>售后体验账号</strong>
              <span>单人演示空间</span>
            </span>
            <span className="profile-dot" title="演示数据" />
          </div>
        </div>
      </aside>
    </>
  );
}
