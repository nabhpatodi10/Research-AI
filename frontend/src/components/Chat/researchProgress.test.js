import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildPendingResearchView,
  normalizeResearchProgressDetails,
  resolveResearchProgress,
} from './researchProgress.js';

test('normalizes expert progress details and sorts experts by index', () => {
  const details = normalizeResearchProgressDetails({
    kind: 'expert_progress',
    summary_text: '1 of 2 experts actively writing.',
    experts: [
      {
        index: 1,
        name: 'Expert Two',
        status: 'writing',
        status_label: 'Writing',
        section_index: 2,
        section_total: 7,
        section_title: '2. Literature Review',
        display_text: 'Expert 2: Expert Two - Writing 2. Literature Review (Section 2/7)',
      },
      {
        index: 0,
        name: 'Expert One',
        status: 'completed',
        status_label: 'Completed',
        section_index: 7,
        section_total: 7,
        section_title: '7. Conclusion',
        display_text: 'Expert 1: Expert One - Completed all sections (7/7)',
      },
    ],
  });

  assert.deepEqual(details?.experts.map((expert) => expert.name), ['Expert One', 'Expert Two']);
  assert.equal(details?.summaryText, '1 of 2 experts actively writing.');
});

test('resolves progress text from structured details when message is missing', () => {
  const { progressText, progressDetails } = resolveResearchProgress(
    'running',
    'generate_content_for_perspectives',
    '',
    {
      kind: 'expert_progress',
      summary_text: '2 of 3 experts actively writing.',
      experts: [
        {
          index: 0,
          name: 'Expert One',
          status: 'writing',
          status_label: 'Writing',
          section_index: 1,
          section_total: 4,
          section_title: '1. Intro',
          display_text: 'Expert 1: Expert One - Writing 1. Intro (Section 1/4)',
        },
      ],
    }
  );

  assert.equal(progressText, '2 of 3 experts actively writing.');
  assert.equal(progressDetails?.kind, 'expert_progress');
});

test('builds multi-expert pending view from structured progress details', () => {
  const pendingView = buildPendingResearchView('summary fallback', {
    kind: 'expert_progress',
    summaryText: '2 of 2 experts actively writing.',
    experts: [
      {
        index: 0,
        name: 'Expert One',
        status: 'writing',
        statusLabel: 'Writing',
        sectionIndex: 1,
        sectionTotal: 2,
        sectionTitle: '1. Intro',
        displayText: 'Expert 1: Expert One - Writing 1. Intro (Section 1/2)',
      },
      {
        index: 1,
        name: 'Expert Two',
        status: 'writing',
        statusLabel: 'Writing',
        sectionIndex: 2,
        sectionTotal: 2,
        sectionTitle: '2. Review',
        displayText: 'Expert 2: Expert Two - Writing 2. Review (Section 2/2)',
      },
    ],
  });

  assert.deepEqual(pendingView, {
    kind: 'expert_progress',
    summaryText: '2 of 2 experts actively writing.',
    expertLines: [
      'Expert 1: Expert One - Writing 1. Intro (Section 1/2)',
      'Expert 2: Expert Two - Writing 2. Review (Section 2/2)',
    ],
  });
});

test('falls back to plain text for legacy progress payloads', () => {
  const { progressText, progressDetails } = resolveResearchProgress(
    'running',
    'final_section_generation',
    '',
    null
  );
  const pendingView = buildPendingResearchView(progressText, progressDetails);

  assert.equal(progressText, 'Writing your final research document.');
  assert.deepEqual(pendingView, {
    kind: 'text',
    text: 'Writing your final research document.',
  });
});
