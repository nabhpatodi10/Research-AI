const NODE_PROGRESS_FALLBACK = {
  queued: 'Research queued. Waiting to start.',
  preparing: 'Preparing your research workflow.',
  generate_document_outline: 'Analyzing your request, gathering context, and drafting an outline.',
  generate_perspectives: 'Ensuring all important angles of your idea are covered.',
  generate_content_for_perspectives: 'Performing deep, well-rounded research to collect information.',
  final_section_generation: 'Writing your final research document.',
  completed: 'Research completed.',
  failed: 'Research could not be completed.',
};

function normalizeText(value) {
  const normalized = String(value || '').trim();
  return normalized || null;
}

function normalizeCount(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  const rounded = Math.trunc(number);
  return rounded > 0 ? rounded : null;
}

export function resolveProgressMessage(status, currentNode, rawMessage, progressDetails = null) {
  const message = String(rawMessage || '').trim();
  if (message) return message;
  if (progressDetails?.summaryText) return progressDetails.summaryText;
  if (currentNode && NODE_PROGRESS_FALLBACK[currentNode]) {
    return NODE_PROGRESS_FALLBACK[currentNode];
  }
  if (status === 'queued') return NODE_PROGRESS_FALLBACK.queued;
  if (status === 'running') return 'Research is in progress.';
  if (status === 'completed') return NODE_PROGRESS_FALLBACK.completed;
  if (status === 'failed') return NODE_PROGRESS_FALLBACK.failed;
  return '';
}

export function normalizeResearchProgressDetails(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const kind = normalizeText(raw.kind);
  if (kind !== 'expert_progress') return null;

  const experts = Array.isArray(raw.experts)
    ? raw.experts
        .map((entry) => {
          if (!entry || typeof entry !== 'object') return null;
          const index = Number(entry.index);
          if (!Number.isFinite(index)) return null;
          const name = normalizeText(entry.name);
          const status = normalizeText(entry.status);
          const statusLabel = normalizeText(entry.status_label);
          const displayText = normalizeText(entry.display_text);
          if (!name || !status || !statusLabel || !displayText) return null;
          return {
            index: Math.trunc(index),
            name,
            status,
            statusLabel,
            sectionIndex: normalizeCount(entry.section_index),
            sectionTotal: normalizeCount(entry.section_total),
            sectionTitle: normalizeText(entry.section_title),
            displayText,
          };
        })
        .filter(Boolean)
        .sort((left, right) => left.index - right.index)
    : [];

  return {
    kind,
    summaryText: normalizeText(raw.summary_text) || '',
    experts,
  };
}

export function resolveResearchProgress(status, currentNode, rawMessage, rawDetails) {
  const progressDetails = normalizeResearchProgressDetails(rawDetails);
  const progressText = resolveProgressMessage(status, currentNode, rawMessage, progressDetails);
  return {
    progressText,
    progressDetails,
  };
}

export function buildPendingResearchView(progressText, progressDetails) {
  if (progressDetails?.kind === 'expert_progress' && progressDetails.experts.length > 0) {
    return {
      kind: 'expert_progress',
      summaryText: progressDetails.summaryText || String(progressText || '').trim(),
      expertLines: progressDetails.experts.map((expert) => expert.displayText),
    };
  }

  return {
    kind: 'text',
    text: String(progressText || '').trim(),
  };
}
