import React from 'react';

const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`|\[\d{1,2}\]|https?:\/\/[^\s<]+)/g;

function Inline({ text, onCitationClick }) {
  const parts = String(text || '').split(INLINE_PATTERN);
  return parts.map((part, index) => {
    if (!part) return null;
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    if (/^\[\d{1,2}\]$/.test(part)) {
      const number = Number(part.slice(1, -1));
      return (
        <button
          key={index}
          type="button"
          className="cite-ref"
          onClick={() => onCitationClick?.(number)}
          title={`查看第 ${number} 条依据`}
        >
          {number}
        </button>
      );
    }
    if (/^https?:\/\//.test(part)) {
      return (
        <a key={index} href={part} target="_blank" rel="noreferrer noopener">
          {part}
        </a>
      );
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

function Paragraph({ lines, onCitationClick }) {
  return (
    <p>
      {lines.map((line, index) => (
        <React.Fragment key={index}>
          {index > 0 && <br />}
          <Inline text={line} onCitationClick={onCitationClick} />
        </React.Fragment>
      ))}
    </p>
  );
}

export default function Markdown({ text = '', onCitationClick }) {
  const lines = String(text || '').split('\n');
  const blocks = [];
  let paragraph = [];
  let list = null;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push(<Paragraph key={`p-${blocks.length}`} lines={paragraph} onCitationClick={onCitationClick} />);
      paragraph = [];
    }
  };

  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? 'ol' : 'ul';
    blocks.push(
      <Tag key={`list-${blocks.length}`} className="md-list">
        {list.items.map((item, index) => (
          <li key={index}>
            <Inline text={item} onCitationClick={onCitationClick} />
          </li>
        ))}
      </Tag>
    );
    list = null;
  };

  const flushAll = () => {
    flushParagraph();
    flushList();
  };

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, '');
    const trimmed = line.trim();

    if (!trimmed) {
      flushAll();
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushAll();
      const level = heading[1].length;
      const Tag = level <= 2 ? 'h3' : 'h4';
      blocks.push(
        <Tag key={`h-${blocks.length}`} className="md-heading">
          <Inline text={heading[2]} onCitationClick={onCitationClick} />
        </Tag>
      );
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      flushAll();
      blocks.push(<hr key={`hr-${blocks.length}`} className="md-rule" />);
      continue;
    }

    const bullet = trimmed.match(/^[-*•]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push(bullet[1]);
      continue;
    }

    const ordered = trimmed.match(/^\d+[.)、]\s*(.+)$/);
    if (ordered) {
      flushParagraph();
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(ordered[1]);
      continue;
    }

    const quote = trimmed.match(/^>\s?(.*)$/);
    if (quote) {
      flushAll();
      const quoteLines = [quote[1]];
      blocks.push(
        <blockquote key={`q-${blocks.length}`} className="md-quote">
          <Inline text={quoteLines.join(' ')} onCitationClick={onCitationClick} />
        </blockquote>
      );
      continue;
    }

    flushList();
    paragraph.push(trimmed);
  }

  flushAll();
  return <div className="markdown">{blocks}</div>;
}
