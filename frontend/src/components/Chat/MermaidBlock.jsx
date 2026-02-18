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
    mermaidPromise = import('mermaid').then((mod) => mod.default || mod);
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

export default function MermaidBlock({ definition, diagramId }) {
  const containerRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);
  const [svgContent, setSvgContent] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [isRendering, setIsRendering] = useState(false);
  const [didEmitSuccess, setDidEmitSuccess] = useState(false);
  const [didEmitValidationError, setDidEmitValidationError] = useState(false);
  const normalizedDefinition = useMemo(() => String(definition ?? '').trim(), [definition]);
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
    return () => observer.disconnect();
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
            deterministicIds: true,
            deterministicIDSeed: 'research-ai-chat',
          });
          isMermaidInitialized = true;
        }

        const renderId = `${diagramId}-${hashString(normalizedDefinition)}`;
        const result = await mermaid.render(renderId, normalizedDefinition);
        if (!active) return;

        setSvgContent(String(result?.svg || ''));
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
    return (
      <div ref={containerRef} className="ra-visual-block ra-visual-error">
        <p className="ra-visual-error-title">Could not render diagram.</p>
        <p className="ra-visual-error-message">{validationError}</p>
        {normalizedDefinition && (
          <pre className="ra-visual-fallback-pre">{normalizedDefinition}</pre>
        )}
      </div>
    );
  }

  return (
    <div ref={containerRef} className="ra-visual-block">
      <p className="ra-visual-title">Diagram</p>

      {!isVisible || isRendering ? (
        <div className="ra-mermaid-skeleton">
          <span>Diagram loads when visible.</span>
        </div>
      ) : errorMessage ? (
        <div className="ra-visual-error">
          <p className="ra-visual-error-title">Could not render diagram.</p>
          <p className="ra-visual-error-message">{errorMessage}</p>
          {normalizedDefinition && (
            <pre className="ra-visual-fallback-pre">{normalizedDefinition}</pre>
          )}
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
