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

function normalizeLegacyChartPayload(payload) {
  if (!isPlainObject(payload)) {
    return payload;
  }

  const titleField = payload.title;
  const hasLegacyTitleObject =
    isPlainObject(titleField) && typeof titleField.text === 'string';

  if (!hasLegacyTitleObject) {
    return payload;
  }

  const normalized = {
    ...payload,
    title: String(titleField.text),
  };

  // Backward compatibility: allow raw ECharts config at top-level when title is an object.
  if (!isPlainObject(payload.option)) {
    const option = {};
    for (const [key, value] of Object.entries(payload)) {
      if (key === 'title' || key === 'caption' || key === 'height') continue;
      option[key] = value;
    }
    if (Object.keys(option).length > 0) {
      normalized.option = option;
    }
  }

  return normalized;
}

function decodeEscapedChartSpec(rawValue) {
  const raw = String(rawValue ?? '').trim();
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
    const parsedPayload = JSON.parse(raw);
    const payload = normalizeLegacyChartPayload(parsedPayload);
    const validationError = validateChartPayload(payload);
    if (validationError) {
      return { raw, error: validationError };
    }
    return { raw, payload };
  } catch {
    const normalizedRaw = decodeEscapedChartSpec(raw);
    if (normalizedRaw && normalizedRaw !== raw) {
      try {
        const parsedPayload = JSON.parse(normalizedRaw);
        const payload = normalizeLegacyChartPayload(parsedPayload);
        const validationError = validateChartPayload(payload);
        if (validationError) {
          return { raw: normalizedRaw, error: validationError };
        }
        return { raw: normalizedRaw, payload };
      } catch {
        // Fall through to the standard error payload below.
      }
    }

    return { raw, error: 'Invalid JSON in chartjson block.' };
  }
}

function renderChartError(message, rawContent) {
  return (
    <div className="ra-visual-block ra-visual-error" role="alert">
      <p className="ra-visual-error-title">Chart could not be rendered</p>
      <p className="ra-visual-error-message">{message}</p>
      {rawContent ? <pre className="ra-visual-fallback-pre">{rawContent}</pre> : null}
    </div>
  );
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
    return renderChartError(parsed.error, parsed.raw || String(specSource ?? '').trim());
  }
  if (loadError) {
    return renderChartError(loadError, parsed.raw || String(specSource ?? '').trim());
  }

  const payload = parsed.payload;
  const chartHeight = normalizeChartHeight(payload.height);

  return (
    <div ref={containerRef} className="ra-visual-block">
      {payload.title && <p className="ra-visual-title">{payload.title}</p>}

      {!isVisible || !EChartsComponent ? (
        <div className="ra-chart-skeleton" style={{ height: `${chartHeight}px` }} />
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
