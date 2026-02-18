import { useEffect, useMemo, useRef, useState } from 'react';

const UNSAFE_KEYS = new Set(['__proto__', 'prototype', 'constructor']);
const FUNCTION_LIKE_PATTERN = /^\s*(?:function\s*\(|\(?\s*[\w$,\s]+\)?\s*=>)/;
const DEFAULT_CHART_HEIGHT = 320;
const MIN_CHART_HEIGHT = 220;
const MAX_CHART_HEIGHT = 720;

function emitChartTelemetry(eventName, detail) {
  if (import.meta.env.DEV) {
    console.debug(`[chart:${eventName}]`, detail);
  }

  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(`ra:${eventName}`, {
      detail,
    })
  );
}

function isPlainObject(value) {
  return Object.prototype.toString.call(value) === '[object Object]';
}

function hasUnsafeKeysOrValues(input, seen = new WeakSet()) {
  if (input === null || input === undefined) return false;

  if (typeof input === 'string') {
    return FUNCTION_LIKE_PATTERN.test(input);
  }

  if (typeof input !== 'object') {
    return false;
  }

  if (seen.has(input)) {
    return false;
  }
  seen.add(input);

  if (Array.isArray(input)) {
    return input.some((item) => hasUnsafeKeysOrValues(item, seen));
  }

  for (const key of Object.keys(input)) {
    if (UNSAFE_KEYS.has(key)) {
      return true;
    }
    if (hasUnsafeKeysOrValues(input[key], seen)) {
      return true;
    }
  }
  return false;
}

function normalizeChartHeight(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return DEFAULT_CHART_HEIGHT;
  return Math.max(MIN_CHART_HEIGHT, Math.min(MAX_CHART_HEIGHT, numeric));
}

function validateChartPayload(payload) {
  if (!isPlainObject(payload)) {
    return 'Chart payload must be a JSON object.';
  }

  if (hasUnsafeKeysOrValues(payload)) {
    return 'Chart payload contains unsafe keys or function-like values.';
  }

  if (!isPlainObject(payload.option)) {
    return 'Chart payload must include an object field named "option".';
  }

  if (payload.title !== undefined && typeof payload.title !== 'string') {
    return 'Chart "title" must be a string when provided.';
  }

  if (payload.caption !== undefined && typeof payload.caption !== 'string') {
    return 'Chart "caption" must be a string when provided.';
  }

  if (payload.height !== undefined && !Number.isFinite(Number(payload.height))) {
    return 'Chart "height" must be numeric when provided.';
  }

  return '';
}

function parseChartSpec(specSource) {
  const raw = String(specSource ?? '').trim();
  if (!raw) {
    return { raw, error: 'Empty chartjson block.' };
  }

  try {
    const payload = JSON.parse(raw);
    const validationError = validateChartPayload(payload);
    if (validationError) {
      return { raw, error: validationError };
    }
    return { raw, payload };
  } catch {
    return {
      raw,
      error: 'Invalid JSON in chartjson block.',
    };
  }
}

export default function ChartBlock({ specSource, chartId }) {
  const containerRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);
  const [EChartsComponent, setEChartsComponent] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [didEmitSuccess, setDidEmitSuccess] = useState(false);
  const [didEmitValidationError, setDidEmitValidationError] = useState(false);

  const parsed = useMemo(() => parseChartSpec(specSource), [specSource]);

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
    if (!isVisible || !parsed.payload || EChartsComponent || loadError) return;

    let active = true;
    import('echarts-for-react')
      .then((module) => {
        if (!active) return;
        setEChartsComponent(() => module.default);
      })
      .catch((error) => {
        if (!active) return;
        const message = error instanceof Error ? error.message : 'Failed to load chart renderer.';
        setLoadError(message);
        emitChartTelemetry('chart_render_error', {
          chartId,
          stage: 'library_load',
          message,
        });
      });

    return () => {
      active = false;
    };
  }, [isVisible, parsed.payload, EChartsComponent, loadError, chartId]);

  useEffect(() => {
    if (!EChartsComponent || !parsed.payload || didEmitSuccess) return;
    emitChartTelemetry('chart_render_success', {
      chartId,
      title: parsed.payload.title || null,
    });
    setDidEmitSuccess(true);
  }, [EChartsComponent, parsed.payload, chartId, didEmitSuccess]);

  useEffect(() => {
    if (!parsed.error || didEmitValidationError) return;
    emitChartTelemetry('chart_render_error', {
      chartId,
      stage: 'validation',
      message: parsed.error,
    });
    setDidEmitValidationError(true);
  }, [parsed.error, chartId, didEmitValidationError]);

  if (parsed.error) {
    return (
      <div ref={containerRef} className="ra-visual-block ra-visual-error">
        <p className="ra-visual-error-title">Could not render chart.</p>
        <p className="ra-visual-error-message">{parsed.error}</p>
        {parsed.raw && <pre className="ra-visual-fallback-pre">{parsed.raw}</pre>}
      </div>
    );
  }

  const payload = parsed.payload;
  const chartHeight = normalizeChartHeight(payload.height);

  return (
    <div ref={containerRef} className="ra-visual-block">
      {payload.title && <p className="ra-visual-title">{payload.title}</p>}

      {!isVisible || !EChartsComponent ? (
        <div className="ra-chart-skeleton" style={{ height: `${chartHeight}px` }}>
          <span>Chart loads when visible.</span>
        </div>
      ) : loadError ? (
        <div className="ra-visual-error">
          <p className="ra-visual-error-title">Could not render chart.</p>
          <p className="ra-visual-error-message">{loadError}</p>
          {parsed.raw && <pre className="ra-visual-fallback-pre">{parsed.raw}</pre>}
        </div>
      ) : (
        <div className="ra-chart-wrap" style={{ height: `${chartHeight}px` }}>
          <EChartsComponent
            option={payload.option}
            notMerge
            lazyUpdate
            style={{ height: '100%', width: '100%' }}
          />
        </div>
      )}

      {payload.caption && <p className="ra-visual-caption">{payload.caption}</p>}
    </div>
  );
}
