import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';

const RichAssistantMessage = lazy(() => import('../RichAssistantMessage'));
const MarkdownRenderer = lazy(() => import('../MarkdownRenderer'));

function fallbackCopyText(text) {
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    textarea.style.pointerEvents = 'none';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const success = document.execCommand('copy');
    document.body.removeChild(textarea);
    return success;
  } catch {
    return false;
  }
}

function AnimatedPendingText({ text }) {
  const nextText = String(text || '').trim();
  const [renderedText, setRenderedText] = useState(nextText);
  const [isVisible, setIsVisible] = useState(true);
  const timeoutRef = useRef(null);

  useEffect(() => {
    if (nextText === renderedText) return undefined;

    setIsVisible(false);
    timeoutRef.current = window.setTimeout(() => {
      setRenderedText(nextText);
      setIsVisible(true);
      timeoutRef.current = null;
    }, 140);

    return () => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [nextText, renderedText]);

  if (!renderedText) return null;

  return (
    <p
      className={`text-sm leading-6 text-slate-700 transition-all duration-300 ease-out ${
        isVisible ? 'translate-y-0 opacity-100' : '-translate-y-1 opacity-0'
      }`}
    >
      {renderedText}
    </p>
  );
}

function MessageBubble({ msg }) {
  if (msg.status === 'pending') {
    const progressText = String(msg.text || '').trim();
    return (
      <div className="max-w-full rounded-2xl border border-blue-200 bg-white px-4 py-3 shadow-sm md:max-w-[78%]">
        <div className="flex items-center gap-2">
          <div className="inline-flex shrink-0 items-center gap-1.5 self-center">
            <span className="h-2 w-2 rounded-full bg-blue-900 animate-bounce [animation-delay:-0.2s]" />
            <span className="h-2 w-2 rounded-full bg-blue-900 animate-bounce [animation-delay:-0.1s]" />
            <span className="h-2 w-2 rounded-full bg-blue-900 animate-bounce" />
          </div>
          <AnimatedPendingText text={progressText} />
        </div>
      </div>
    );
  }

  const isUser = msg.sender === 'user';
  const isAssistant = msg.sender === 'ai';

  if (isUser) {
    return (
      <div className="ml-auto w-fit max-w-full overflow-hidden rounded-2xl bg-blue-900 text-white shadow-sm md:max-w-[78%]">
        <div className="whitespace-pre-wrap break-words px-4 py-3 text-sm leading-6">
          {msg.text}
        </div>
      </div>
    );
  }

  if (isAssistant) {
    return (
      <div className="max-w-full overflow-hidden rounded-2xl border border-blue-100 bg-white text-slate-800 shadow-sm md:max-w-[78%]">
        <Suspense fallback={<div className="px-4 py-3 text-sm text-slate-500">Rendering response...</div>}>
          <RichAssistantMessage content={msg.text} messageId={msg.id} />
        </Suspense>
      </div>
    );
  }

  return (
    <div className="max-w-full overflow-hidden rounded-2xl border border-red-200 bg-red-50 text-red-700 shadow-sm md:max-w-[78%]">
      <Suspense fallback={<div className="px-4 py-3 text-sm">{msg.text}</div>}>
        <MarkdownRenderer content={msg.text} variant="error" />
      </Suspense>
    </div>
  );
}

export default function MessageList({
  chatLoading,
  messages,
  isInteractionLocked,
  quickPrompts,
  onQuickPromptSelect,
  chatScrollContainerRef,
}) {
  const statusTimeoutsRef = useRef(new Map());
  const [copyStatusById, setCopyStatusById] = useState({});
  const [pdfStatusById, setPdfStatusById] = useState({});
  const bubbleRefs = useRef({});

  useEffect(
    () => () => {
      statusTimeoutsRef.current.forEach((timeoutId) => {
        window.clearTimeout(timeoutId);
      });
      statusTimeoutsRef.current.clear();
    },
    []
  );

  const setTransientCopyStatus = useCallback((messageId, label, timeoutMs = 0) => {
    const normalizedId = String(messageId || '').trim();
    if (!normalizedId) return;

    setCopyStatusById((prev) => ({ ...prev, [normalizedId]: label }));

    const timeoutKey = `copy:${normalizedId}`;
    const existingTimeout = statusTimeoutsRef.current.get(timeoutKey);
    if (existingTimeout) {
      window.clearTimeout(existingTimeout);
      statusTimeoutsRef.current.delete(timeoutKey);
    }

    if (timeoutMs > 0) {
      const timeoutId = window.setTimeout(() => {
        setCopyStatusById((prev) => {
          if (prev[normalizedId] !== label) return prev;
          const next = { ...prev };
          delete next[normalizedId];
          return next;
        });
        statusTimeoutsRef.current.delete(timeoutKey);
      }, timeoutMs);
      statusTimeoutsRef.current.set(timeoutKey, timeoutId);
    }
  }, []);

  const handleCopyAssistantMessage = useCallback(
    async (messageId, text) => {
      const normalizedText = String(text || '');
      if (!normalizedText.trim()) {
        setTransientCopyStatus(messageId, 'Empty', 1600);
        return;
      }

      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(normalizedText);
        } else {
          const copied = fallbackCopyText(normalizedText);
          if (!copied) throw new Error('Clipboard unavailable');
        }
        setTransientCopyStatus(messageId, 'Copied', 1800);
      } catch {
        setTransientCopyStatus(messageId, 'Failed', 2200);
      }
    },
    [setTransientCopyStatus]
  );

  const setTransientPdfStatus = useCallback((messageId, label, timeoutMs = 0) => {
    const normalizedId = String(messageId || '').trim();
    if (!normalizedId) return;

    setPdfStatusById((prev) => ({ ...prev, [normalizedId]: label }));

    const timeoutKey = `pdf:${normalizedId}`;
    const existingTimeout = statusTimeoutsRef.current.get(timeoutKey);
    if (existingTimeout) {
      window.clearTimeout(existingTimeout);
      statusTimeoutsRef.current.delete(timeoutKey);
    }

    if (timeoutMs > 0) {
      const timeoutId = window.setTimeout(() => {
        setPdfStatusById((prev) => {
          if (prev[normalizedId] !== label) return prev;
          const next = { ...prev };
          delete next[normalizedId];
          return next;
        });
        statusTimeoutsRef.current.delete(timeoutKey);
      }, timeoutMs);
      statusTimeoutsRef.current.set(timeoutKey, timeoutId);
    }
  }, []);

  const handleDownloadPdf = useCallback(
    async (messageId) => {
      const normalizedId = String(messageId || '').trim();
      const el = bubbleRefs.current[normalizedId];
      if (!el) return;

      setTransientPdfStatus(normalizedId, '…', 0);
      try {
        // ── 1. Deep-clone the message DOM ──
        const clone = el.cloneNode(true);

        // ── 2. Convert ECharts <canvas> → <img> (canvas content won't
        //       survive serialisation into the print window) ──
        const origCanvases = el.querySelectorAll('canvas');
        const cloneCanvases = clone.querySelectorAll('canvas');
        cloneCanvases.forEach((cc, i) => {
          const oc = origCanvases[i];
          if (!oc) return;
          try {
            const img = document.createElement('img');
            img.src = oc.toDataURL('image/png');
            img.style.cssText = 'width:100%;height:auto;display:block;';
            cc.parentNode.replaceChild(img, cc);
          } catch { /* cross-origin canvas — skip */ }
        });

        // ── 3. Collect every stylesheet from the live page so the print
        //       window inherits all Tailwind, KaTeX, highlight.js, and
        //       app-specific CSS rules ──
        const styleFragments = [];
        document.querySelectorAll('link[rel="stylesheet"], style').forEach((node) => {
          styleFragments.push(node.outerHTML);
        });

        // ── 4. Build the print document ──
        const printHTML = [
          '<!DOCTYPE html><html><head><meta charset="utf-8">',
          '<title>Research Report</title>',
          styleFragments.join('\n'),
          `<style>
            @page { size: A4; margin: 18mm 15mm; }

            *, *::before, *::after {
              -webkit-print-color-adjust: exact !important;
              print-color-adjust: exact !important;
            }

            html, body {
              margin: 0; padding: 0;
              background: #fff; color: #1f2937;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                           Helvetica, Arial, sans-serif;
              font-size: 14px; line-height: 1.65;
            }

            /* ── Strip bubble chrome ── */
            .pdf-root > * {
              max-width: 100% !important;
              border: none !important;
              border-radius: 0 !important;
              box-shadow: none !important;
              overflow: visible !important;
            }

            /* ── Tables: show every column, no scroll ── */
            .markdown-table-wrap,
            .markdown-table-shell {
              overflow: visible !important;
              overflow-x: visible !important;
              max-width: 100% !important;
            }
            table {
              width: 100% !important;
              max-width: 100% !important;
              table-layout: auto !important;
              font-size: 11px !important;
            }
            th, td {
              word-break: break-word !important;
              overflow-wrap: anywhere !important;
              white-space: normal !important;
            }

            /* ── Page-break rules ── */
            pre, .katex-display, table, figure,
            .ra-visual-block, img, svg, blockquote {
              page-break-inside: avoid;
              break-inside: avoid;
            }
            h1,h2,h3,h4,h5,h6 {
              page-break-after: avoid;
              break-after: avoid;
            }
            p, li { orphans: 3; widows: 3; }

            /* ── Visualisations ── */
            .ra-chart-wrap, .ra-mermaid-wrap {
              overflow: visible !important;
            }
            .ra-chart-wrap img, .ra-mermaid-wrap svg {
              width: 100% !important;
              max-width: 100% !important;
              height: auto !important;
            }
            .ra-chart-skeleton, .ra-mermaid-skeleton {
              display: none !important;
            }
            .ra-visual-block {
              overflow: visible !important;
              page-break-inside: avoid;
              break-inside: avoid;
            }

            img, svg {
              max-width: 100% !important;
              height: auto !important;
            }

            /* ── Hide scrollbars ── */
            ::-webkit-scrollbar { display: none !important; }
            * { scrollbar-width: none !important; }

            /* ── Code blocks: wrap instead of scroll ── */
            pre, code {
              white-space: pre-wrap !important;
              word-break: break-all !important;
              overflow: visible !important;
            }
          </style>`,
          '</head><body>',
          '<div class="pdf-root">',
          clone.innerHTML,
          '</div>',
          '</body></html>',
        ].join('\n');

        // ── 5. Use a hidden iframe so the print dialog opens over the
        //       current tab — the user never sees raw text in a new tab. ──
        const iframe = document.createElement('iframe');
        iframe.style.cssText = 'position:fixed;width:0;height:0;border:none;left:-9999px;top:-9999px;';
        document.body.appendChild(iframe);

        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
        iframeDoc.open();
        iframeDoc.write(printHTML);
        iframeDoc.close();

        // Remove the iframe after the print dialog closes.
        iframe.contentWindow.onafterprint = () => {
          document.body.removeChild(iframe);
        };

        // ── 6. Wait for fonts + images, then trigger the print dialog ──
        const triggerPrint = async () => {
          try { await iframe.contentDocument.fonts.ready; } catch { /* ignore */ }
          await new Promise((r) => setTimeout(r, 400));
          iframe.contentWindow.focus();
          iframe.contentWindow.print();
        };

        if (iframeDoc.readyState === 'complete') {
          await triggerPrint();
        } else {
          iframe.addEventListener('load', triggerPrint, { once: true });
        }

        setTransientPdfStatus(normalizedId, 'Done', 2000);
      } catch (err) {
        if (import.meta.env.DEV) console.error('[PDF]', err);
        setTransientPdfStatus(normalizedId, 'Failed', 2200);
      }
    },
    [setTransientPdfStatus]
  );

  return (
    <section
      ref={chatScrollContainerRef}
      className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-4 py-6 md:px-8 md:py-7"
    >
      <div className="mx-auto w-full max-w-5xl">
        {chatLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((item) => (
              <div key={item} className="animate-pulse rounded-2xl border border-blue-100 bg-white/90 p-4 shadow-sm">
                <div className="h-3 w-24 rounded bg-blue-100" />
                <div className="mt-3 h-2.5 w-full rounded bg-blue-50" />
                <div className="mt-2 h-2.5 w-5/6 rounded bg-blue-50" />
              </div>
            ))}
          </div>
        ) : messages.length === 0 ? (
          <div className="rounded-3xl border border-blue-100 bg-white/90 p-6 shadow-sm md:p-8">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-900 text-white">
              <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h8M8 14h5m7 5-4-4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8a4 4 0 0 1-1 2.646Z" />
              </svg>
            </div>

            <h3 className="mt-4 text-2xl font-semibold text-slate-900">What are we researching today?</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              Ask for market scans, comparative analyses, strategy notes, or deep-dive summaries. I will structure the output as a clean research response.
            </p>

            <div className="mt-6 grid gap-2">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => onQuickPromptSelect(prompt)}
                  className="rounded-xl border border-blue-100 bg-blue-50/50 px-4 py-3 text-left text-sm text-slate-700 transition hover:border-blue-200 hover:bg-blue-50"
                  disabled={isInteractionLocked}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex w-full flex-col gap-4">
            {messages.map((msg, index) => {
              const isUser = msg.sender === 'user';
              const isAssistant = msg.sender === 'ai';
              const avatarClass = isUser ? 'bg-slate-900 text-white' : 'bg-blue-900 text-white';
              const avatarText = isUser ? 'You' : 'AI';
              const normalizedMessageId = String(msg.id || '').trim();
              const showAssistantActions =
                isAssistant &&
                msg.status !== 'pending' &&
                Boolean(normalizedMessageId) &&
                Boolean(String(msg.text || '').trim());

              return (
                <div
                  key={msg.id || index}
                  data-message-index={index}
                  data-message-sender={msg.sender}
                  className={`flex items-start gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  {!isUser && (
                    <div className={`mt-1 hidden h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-bold md:flex ${avatarClass}`}>
                      {avatarText}
                    </div>
                  )}
                  {showAssistantActions ? (
                    <div className="flex min-w-0 max-w-full flex-col items-start gap-1.5">
                      <div ref={(el) => { bubbleRefs.current[normalizedMessageId] = el; }} className="min-w-0 max-w-full">
                        <MessageBubble msg={msg} />
                      </div>
                      <div className="flex items-center gap-1.5 pl-1">
                        <button
                          type="button"
                          onClick={() => handleCopyAssistantMessage(normalizedMessageId, msg.text)}
                          className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-blue-200 hover:text-blue-700"
                        >
                          {copyStatusById[normalizedMessageId] || 'Copy'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDownloadPdf(normalizedMessageId)}
                          disabled={pdfStatusById[normalizedMessageId] === '…'}
                          className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-wait disabled:opacity-60"
                        >
                          {pdfStatusById[normalizedMessageId] || 'Save PDF'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <MessageBubble msg={msg} />
                  )}
                  {isUser && (
                    <div className={`mt-1 hidden h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-bold md:flex ${avatarClass}`}>
                      {avatarText}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
