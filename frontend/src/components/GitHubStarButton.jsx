import { useEffect, useState } from 'react';

const REPO_URL = 'https://github.com/nabhpatodi10/Research-AI';
const REPO_API_URL = 'https://api.github.com/repos/nabhpatodi10/Research-AI';
const CACHE_KEY = 'researchai_github_repo_stars_v1';
const CACHE_TTL_MS = 60 * 60 * 1000;

let cachedStarCount = null;
let cachedFetchedAt = 0;
let pendingStarRequest = null;

function isFresh(timestamp) {
  return Number.isFinite(timestamp) && (Date.now() - timestamp) < CACHE_TTL_MS;
}

function formatStarCount(value) {
  if (!Number.isFinite(value)) {
    return null;
  }
  return new Intl.NumberFormat('en', {
    notation: value >= 1000 ? 'compact' : 'standard',
    maximumFractionDigits: value >= 1000 ? 1 : 0,
  }).format(value);
}

function readStoredStarCount() {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw);
    if (!Number.isFinite(parsed?.count) || !Number.isFinite(parsed?.fetchedAt)) {
      return null;
    }

    return parsed;
  } catch {
    return null;
  }
}

function persistStarCount(count) {
  const payload = {
    count,
    fetchedAt: Date.now(),
  };
  cachedStarCount = payload.count;
  cachedFetchedAt = payload.fetchedAt;

  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Ignore storage failures and keep the in-memory cache only.
  }
}

async function loadStarCount() {
  if (Number.isFinite(cachedStarCount) && isFresh(cachedFetchedAt)) {
    return cachedStarCount;
  }

  const stored = readStoredStarCount();
  if (stored && isFresh(stored.fetchedAt)) {
    cachedStarCount = stored.count;
    cachedFetchedAt = stored.fetchedAt;
    return stored.count;
  }

  if (!pendingStarRequest) {
    pendingStarRequest = fetch(REPO_API_URL, {
      headers: {
        Accept: 'application/vnd.github+json',
      },
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`GitHub repo stats request failed with ${response.status}`);
        }

        const payload = await response.json();
        if (!Number.isFinite(payload?.stargazers_count)) {
          throw new Error('GitHub repo stats response was missing stargazers_count.');
        }

        persistStarCount(payload.stargazers_count);
        return payload.stargazers_count;
      })
      .finally(() => {
        pendingStarRequest = null;
      });
  }

  return pendingStarRequest;
}

export default function GitHubStarButton({ variant = 'hero' }) {
  const [starCount, setStarCount] = useState(() => {
    if (Number.isFinite(cachedStarCount)) {
      return cachedStarCount;
    }
    const stored = readStoredStarCount();
    if (stored) {
      cachedStarCount = stored.count;
      cachedFetchedAt = stored.fetchedAt;
      return stored.count;
    }
    return null;
  });

  useEffect(() => {
    let isActive = true;
    const stored = readStoredStarCount();
    const hasFreshStoredCount = stored && isFresh(stored.fetchedAt);

    if (hasFreshStoredCount && !Number.isFinite(cachedStarCount)) {
      cachedStarCount = stored.count;
      cachedFetchedAt = stored.fetchedAt;
    }

    loadStarCount()
      .then((count) => {
        if (isActive) {
          setStarCount(count);
        }
      })
      .catch(() => {
        // Keep the button usable even if GitHub rate limits or the network is unavailable.
      });

    return () => {
      isActive = false;
    };
  }, []);

  const formattedCount = formatStarCount(starCount);
  const isNavbar = variant === 'navbar';

  return (
    <a
      href={REPO_URL}
      target="_blank"
      rel="noreferrer"
      className={
        isNavbar
          ? 'group inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-900'
          : 'group inline-flex w-full items-center justify-center gap-3 rounded-xl border border-white/40 bg-white/10 px-5 py-3 text-white transition hover:bg-white/18 sm:w-auto'
      }
      aria-label="Open the ResearchAI GitHub repository and star it on GitHub"
    >
      <span
        className={
          isNavbar
            ? 'inline-flex h-7 w-7 items-center justify-center rounded-full bg-slate-900 text-white transition group-hover:bg-blue-900'
            : 'inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/25 bg-slate-950/25 text-white transition group-hover:border-white/40 group-hover:bg-slate-950/40'
        }
      >
        <svg className={isNavbar ? 'h-3.5 w-3.5' : 'h-4.5 w-4.5'} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.086 3.344a1 1 0 0 0 .95.69h3.517c.969 0 1.371 1.24.588 1.81l-2.845 2.067a1 1 0 0 0-.364 1.118l1.087 3.344c.299.921-.755 1.688-1.539 1.118l-2.845-2.067a1 1 0 0 0-1.176 0l-2.845 2.067c-.783.57-1.838-.197-1.539-1.118l1.087-3.344a1 1 0 0 0-.364-1.118L2.91 8.771c-.783-.57-.38-1.81.588-1.81h3.517a1 1 0 0 0 .95-.69l1.086-3.344Z" />
        </svg>
      </span>
      {isNavbar ? (
        <>
          <span>GitHub</span>
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[11px] font-bold text-blue-900">
            {formattedCount ?? 'Star'}
          </span>
        </>
      ) : (
        <>
          <span className="flex flex-col items-start text-left leading-none">
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-blue-100/80">
              Open Source
            </span>
            <span className="mt-1 text-sm font-semibold text-white sm:text-[15px]">
              Star on GitHub
            </span>
          </span>
          <span className="rounded-full bg-white px-3 py-1 text-xs font-bold text-blue-900">
            {formattedCount ?? 'Star'}
          </span>
        </>
      )}
    </a>
  );
}
