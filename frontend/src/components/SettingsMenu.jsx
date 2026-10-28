import React, { useEffect, useRef, useState } from 'react';
import Icon from './Icons.jsx';

const THEME_OPTIONS = [
  { value: 'warm', label: '暖阳', description: '奶油日光与琥珀高光' },
  { value: 'dusk', label: '暮色', description: '暖棕玻璃与金色余晖' },
  { value: 'system', label: '跟随系统', description: '自动匹配设备外观' },
];

const FONT_OPTIONS = [
  { value: 'sm', label: '小' },
  { value: 'md', label: '标准' },
  { value: 'lg', label: '大' },
  { value: 'xl', label: '特大' },
];

export default function SettingsMenu({
  theme,
  onThemeChange,
  fontSize,
  onFontSizeChange,
  density,
  onDensityChange,
  motion,
  onMotionChange,
  onReset,
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className="theme-switcher" ref={rootRef}>
      <button
        type="button"
        className={`icon-button theme-trigger ${open ? 'is-open' : ''}`}
        aria-label="打开设置"
        aria-haspopup="menu"
        aria-expanded={open}
        title="设置"
        onClick={() => setOpen((current) => !current)}
      >
        <Icon name="settings" size={17} />
        <span className="settings-trigger-label">设置</span>
      </button>

      {open && (
        <div className="theme-menu settings-menu" role="menu" aria-label="设置">
          <div className="theme-menu-head">
            <span>设置</span>
            <em>SETTINGS</em>
          </div>

          <div className="settings-section">
            <div className="settings-label">
              <span>界面色调</span>
              <em>APPEARANCE</em>
            </div>
            {THEME_OPTIONS.map((option) => {
              const selected = option.value === theme;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="menuitemradio"
                  aria-checked={selected}
                  className={`theme-option ${selected ? 'active' : ''}`}
                  onClick={() => onThemeChange(option.value)}
                >
                  <span className={`theme-preview ${option.value}`}>
                    <i />
                    <i />
                  </span>
                  <span className="theme-option-copy">
                    <strong>{option.label}</strong>
                    <small>{option.description}</small>
                  </span>
                  {selected && (
                    <span className="theme-check">
                      <Icon name="check" size={13} strokeWidth={2.2} />
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className="settings-divider" />

          <div className="settings-section">
            <div className="settings-label">
              <span>字体大小</span>
              <em>TEXT SIZE</em>
            </div>
            <div className="font-options" role="radiogroup" aria-label="字体大小">
              {FONT_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={fontSize === option.value}
                  className={`font-option ${fontSize === option.value ? 'active' : ''}`}
                  onClick={() => onFontSizeChange(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="font-preview">
              <span>Aa</span>
              晴舟，把问题说清楚
            </div>
          </div>

          <div className="settings-divider" />

          <div className="settings-section">
            <div className="settings-label">
              <span>界面</span>
              <em>INTERFACE</em>
            </div>
            <div className="settings-row">
              <span>消息密度</span>
              <div className="pref-options" role="radiogroup" aria-label="消息密度">
                <button
                  type="button"
                  role="radio"
                  aria-checked={density === 'comfortable'}
                  className={density === 'comfortable' ? 'active' : ''}
                  onClick={() => onDensityChange('comfortable')}
                >
                  舒适
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={density === 'compact'}
                  className={density === 'compact' ? 'active' : ''}
                  onClick={() => onDensityChange('compact')}
                >
                  紧凑
                </button>
              </div>
            </div>
            <div className="settings-row">
              <span>界面动效</span>
              <div className="pref-options" role="radiogroup" aria-label="界面动效">
                <button
                  type="button"
                  role="radio"
                  aria-checked={motion === 'full'}
                  className={motion === 'full' ? 'active' : ''}
                  onClick={() => onMotionChange('full')}
                >
                  标准
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={motion === 'reduced'}
                  className={motion === 'reduced' ? 'active' : ''}
                  onClick={() => onMotionChange('reduced')}
                >
                  减弱
                </button>
              </div>
            </div>
          </div>

          <button type="button" className="settings-reset" onClick={onReset}>
            恢复默认设置
          </button>
        </div>
      )}
    </div>
  );
}
