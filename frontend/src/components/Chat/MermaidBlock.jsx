import { useEffect, useMemo, useRef, useState } from 'react';

let mermaidPromise = null;
let isMermaidInitialized = false;

const UNSAFE_MERMAID_PATTERN = /<script|onerror\s*=|onload\s*=|javascript:/i;

function emitMermaidTelemetry(eventName, detail) {
  if (import.meta.env.DEV) {
    console.debug(`[mermaid:${eventName}]`, detail);
  }

  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(`ra:${eventName}`, {
      detail,
    })
  );
}

function hashString(value) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
}

async function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid')
      .then((module) => {
        const mermaid = module?.default || module;
        if (
          !mermaid ||
          typeof mermaid.initialize !== 'function' ||
          typeof mermaid.render !== 'function'
        ) {
          throw new Error('Mermaid renderer loaded with an invalid interface.');
        }
        return mermaid;
      })
      .catch((error) => {
        mermaidPromise = null;
        throw error;
      });
  }
  return mermaidPromise;
}

function validateMermaidSource(definition) {
  const source = String(definition ?? '').trim();
  if (!source) return 'Empty mermaid block.';
  if (UNSAFE_MERMAID_PATTERN.test(source)) {
    return 'Mermaid block contains disallowed content.';
  }
  return '';
}

function normalizeEscapedDefinition(value) {
  const raw = String(value ?? '').trim();
  const escapedNewlineMatches = raw.match(/\\r\\n|\\n|\\r/g) || [];
  const realNewlineMatches = raw.match(/\r\n|\n|\r/g) || [];
  const escapedNewlineCount = escapedNewlineMatches.length;
  const realNewlineCount = realNewlineMatches.length;

  if (escapedNewlineCount < 2 || escapedNewlineCount <= realNewlineCount) {
    return raw;
  }

  return raw
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\n')
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\')
    .trim();
}

/**
 * Replace literal newlines that appear inside double-quoted label strings with
 * mermaid's <br/> marker.  A real newline in a quoted label terminates the
 * lexer token and causes a parse error; <br/> is the correct multiline syntax.
 */
function repairLabelNewlines(source) {
  const raw = String(source ?? '');
  if (!raw.includes('\n') && !raw.includes('\r')) return raw;

  let result = '';
  let inDoubleQuote = false;
  let escaped = false;

  for (let index = 0; index < raw.length; index += 1) {
    const ch = raw[index];

    if (escaped) {
      escaped = false;
      result += ch;
      continue;
    }

    if (ch === '\\') {
      escaped = true;
      result += ch;
      continue;
    }

    if (ch === '"') {
      inDoubleQuote = !inDoubleQuote;
      result += ch;
      continue;
    }

    if (inDoubleQuote && (ch === '\n' || ch === '\r')) {
      // Absorb the \n in a \r\n pair so we only emit one <br/>.
      if (ch === '\r' && raw[index + 1] === '\n') continue;
      result += '<br/>';
      continue;
    }

    result += ch;
  }

  return result;
}

function renderMermaidError(message, rawContent) {
  return (
    <div className="ra-visual-block ra-visual-error" role="alert">
      <p className="ra-visual-error-title">Diagram could not be rendered</p>
      <p className="ra-visual-error-message">{message}</p>
      {rawContent ? <pre className="ra-visual-fallback-pre">{rawContent}</pre> : null}
    </div>
  );
}

function extractRenderedSvg(result) {
  if (!result) return '';
  if (typeof result === 'string') return result.trim();
  if (typeof result.svg === 'string') return result.svg.trim();
  return '';
}

export default function MermaidBlock({ definition, diagramId }) {
  const containerRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);
  const [svgContent, setSvgContent] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [isRendering, setIsRendering] = useState(false);
  const [didEmitSuccess, setDidEmitSuccess] = useState(false);
  const [didEmitValidationError, setDidEmitValidationError] = useState(false);
  const normalizedDefinition = useMemo(
    () => repairLabelNewlines(normalizeEscapedDefinition(definition)),
    [definition]
  );
  const validationError = useMemo(
    () => validateMermaidSource(normalizedDefinition),
    [normalizedDefinition]
  );

  useEffect(() => {
    setSvgContent('');
    setErrorMessage('');
    setIsRendering(false);
    setDidEmitSuccess(false);
    setDidEmitValidationError(false);
  }, [diagramId, normalizedDefinition]);

  useEffect(() => {
    const node = containerRef.current;
    if (!node || isVisible) return;

    if (typeof IntersectionObserver === 'undefined') {
      setIsVisible(true);
      return;
    }

    let fallbackTimer = null;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setIsVisible(true);
            observer.disconnect();
          }
        });
      },
      { rootMargin: '120px 0px' }
    );

    observer.observe(node);
    fallbackTimer = window.setTimeout(() => {
      setIsVisible(true);
    }, 350);
    return () => {
      if (fallbackTimer) window.clearTimeout(fallbackTimer);
      observer.disconnect();
    };
  }, [isVisible]);

  useEffect(() => {
    if (!isVisible || validationError || svgContent || errorMessage) return;

    let active = true;
    setIsRendering(true);

    loadMermaid()
      .then(async (mermaid) => {
        if (!active) return;

        if (!isMermaidInitialized) {
          mermaid.initialize({
            startOnLoad: false,
            securityLevel: 'strict',
            theme: 'neutral',
            suppressErrorRendering: true,
          });
          isMermaidInitialized = true;
        }

        const renderId = `${diagramId}-${hashString(normalizedDefinition)}`;
        const result = await mermaid.render(renderId, normalizedDefinition);
        if (!active) return;

        const nextSvg = extractRenderedSvg(result);
        if (!nextSvg || !nextSvg.includes('<svg')) {
          throw new Error('Mermaid renderer returned blank output. Diagram syntax may be invalid.');
        }

        setSvgContent(nextSvg);
        setErrorMessage('');
      })
      .catch((error) => {
        if (!active) return;
        const message =
          error instanceof Error
            ? error.message
            : 'Could not render this mermaid diagram.';
        setErrorMessage(message);
        emitMermaidTelemetry('mermaid_render_error', {
          diagramId,
          stage: 'render',
          message,
        });
      })
      .finally(() => {
        if (!active) return;
        setIsRendering(false);
      });

    return () => {
      active = false;
    };
  }, [isVisible, validationError, svgContent, errorMessage, diagramId, normalizedDefinition]);

  useEffect(() => {
    if (!svgContent || didEmitSuccess) return;
    emitMermaidTelemetry('mermaid_render_success', {
      diagramId,
    });
    setDidEmitSuccess(true);
  }, [svgContent, didEmitSuccess, diagramId]);

  useEffect(() => {
    if (!validationError || didEmitValidationError) return;
    emitMermaidTelemetry('mermaid_render_error', {
      diagramId,
      stage: 'validation',
      message: validationError,
    });
    setDidEmitValidationError(true);
  }, [validationError, didEmitValidationError, diagramId]);

  if (validationError) {
    return renderMermaidError(validationError, normalizedDefinition);
  }
  if (errorMessage) {
    return renderMermaidError(errorMessage, normalizedDefinition);
  }

  return (
    <div ref={containerRef} className="ra-visual-block">
      <p className="ra-visual-title">Diagram</p>

      {!isVisible || isRendering ? (
        <div className="ra-mermaid-skeleton">
          <span>Rendering diagram...</span>
        </div>
      ) : (
        <div
          className="ra-mermaid-wrap"
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />
      )}
    </div>
  );
}
