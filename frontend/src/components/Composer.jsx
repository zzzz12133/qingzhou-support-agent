import React, { useEffect, useRef } from 'react';
import Icon from './Icons.jsx';

export default function Composer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  disabled,
  placeholder,
}) {
  const textareaRef = useRef(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(164, Math.max(48, textarea.scrollHeight))}px`;
  }, [value]);

  const submit = () => {
    if (streaming || disabled || !value.trim()) return;
    onSend();
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      if (event.nativeEvent.isComposing) return;
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="composer-wrap">
      <div className={`composer ${streaming ? 'is-streaming' : ''}`}>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value.slice(0, 2000))}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          disabled={disabled}
          aria-label="输入消息"
        />
        <div className="composer-toolbar">
          <div className="composer-hints">
            <span className="composer-security">
              <Icon name="shield" size={12} /> 先查工具再回答
            </span>
            <span className="keyboard-hint">
              Enter 发送 <i>·</i> Shift + Enter 换行
            </span>
          </div>
          <div className="composer-actions">
            {value.length > 1100 && <span className="char-count">{value.length}/2000</span>}
            {streaming ? (
              <button
                type="button"
                className="stop-button"
                onClick={onStop}
                title="停止生成，并通知后端取消"
                aria-label="停止生成"
              >
                <Icon name="stop" size={15} />
              </button>
            ) : (
              <button
                type="button"
                className="send-button"
                onClick={submit}
                disabled={disabled || !value.trim()}
                title="发送"
                aria-label="发送消息"
              >
                <Icon name="send" size={17} strokeWidth={1.9} />
              </button>
            )}
          </div>
        </div>
      </div>
      <p className="composer-footnote">
        晴舟可能会犯错。涉及退款金额、赔付与法律争议时，请以人工核验为准。
      </p>
    </div>
  );
}
