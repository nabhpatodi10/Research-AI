import { useState } from 'react';
import { useAuth } from '../context/useAuth';
import { Link } from 'react-router-dom';
import { apiRequest } from '../lib/api';

const FEEDBACK_TYPES = ['General Feedback', 'Bug Report', 'Feature Request'];
const SATISFACTION_OPTIONS = [
  {
    value: 'Very Satisfied',
    label: 'Very Satisfied',
    description: 'The product is working great for me.',
  },
  {
    value: 'Satisfied',
    label: 'Satisfied',
    description: 'Mostly good with a few improvements needed.',
  },
  {
    value: 'Neutral',
    label: 'Neutral',
    description: 'It works, but the experience feels average.',
  },
  {
    value: 'Unsatisfied',
    label: 'Unsatisfied',
    description: 'I am facing clear issues or friction.',
  },
];

export default function Feedback() {
  const [feedbackType, setFeedbackType] = useState('General Feedback');
  const [satisfaction, setSatisfaction] = useState('');
  const [comments, setComments] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { currentUser } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!currentUser) {
      setError('You must be logged in to submit feedback');
      return;
    }

    const trimmedComments = comments.trim();
    if (!satisfaction || !trimmedComments) {
      setError('Please fill all required fields');
      return;
    }

    setLoading(true);
    try {
      await apiRequest('/feedback', {
        method: 'POST',
        body: JSON.stringify({
          feedbackType,
          satisfaction,
          comments: trimmedComments,
        }),
      });
      setSubmitted(true);
      setError('');
    } catch (err) {
      console.error('Error submitting feedback:', err);
      setError('Failed to submit feedback. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFeedbackType('General Feedback');
    setSatisfaction('');
    setComments('');
    setError('');
  };

  if (!currentUser) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-b from-slate-50 via-blue-50/40 to-slate-100 pt-16">
        <div className="mx-auto max-w-md px-4 py-12">
          <div className="rounded-2xl border border-blue-100 bg-white p-6 shadow-sm">
            <h2 className="brand-display text-2xl font-bold text-slate-900">Authentication Required</h2>
            <p className="mt-2 text-sm text-slate-600">Please log in to submit feedback.</p>
            <Link
              to="/login"
              className="mt-5 inline-flex rounded-lg bg-blue-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-800"
            >
              Go to Login
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-b from-slate-50 via-blue-50/40 to-slate-100 pt-16">
        <div className="mx-auto max-w-xl px-4 py-12">
          <div className="overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-sm">
            <div className="border-b border-blue-100 bg-blue-50/60 px-6 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-700">Feedback Received</p>
              <h2 className="brand-display mt-1 text-2xl font-bold text-slate-900">Thank You</h2>
            </div>
            <div className="px-6 py-6">
              <p className="text-sm leading-6 text-slate-700">
                Your feedback has been submitted successfully. It helps us prioritize what to improve next.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <Link
                  to="/chat"
                  className="rounded-lg bg-blue-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-800"
                >
                  Back to Chat
                </Link>
                <button
                  type="button"
                  onClick={() => {
                    setSubmitted(false);
                    resetForm();
                  }}
                  className="rounded-lg border border-blue-100 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-blue-50"
                >
                  Submit Another
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-[calc(100vh-4rem)] overflow-hidden bg-gradient-to-b from-slate-50 via-blue-50/40 to-slate-100 pt-16">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-20 right-0 h-72 w-72 rounded-full bg-blue-200/20 blur-3xl" />
        <div className="absolute -left-20 bottom-8 h-64 w-64 rounded-full bg-blue-900/10 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-6xl px-4 py-10 md:py-14">
        <div className="grid gap-6 lg:grid-cols-[0.95fr_1.25fr]">
          <section className="rounded-3xl border border-blue-100 bg-white/90 p-6 shadow-sm md:p-7">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-700">Help Us Improve</p>
            <h1 className="brand-display mt-2 text-3xl font-bold text-slate-900">Share Your Feedback</h1>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Tell us what is working, where friction appears, and what would make your research workflow better.
            </p>

            <div className="mt-6 space-y-3">
              <div className="rounded-xl border border-blue-100 bg-blue-50/60 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-700">Signed In</p>
                <p className="mt-1 text-sm text-slate-700">{currentUser.email || currentUser.name || 'Active account'}</p>
              </div>

              <div className="rounded-xl border border-blue-100 bg-white p-3">
                <p className="text-sm font-semibold text-slate-800">Tips for useful feedback</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
                  <li>Mention the page or action where the issue happened.</li>
                  <li>Include expected behavior and actual behavior.</li>
                  <li>For feature requests, explain the outcome you want.</li>
                </ul>
              </div>
            </div>
          </section>

          <section className="rounded-3xl border border-blue-100 bg-white p-6 shadow-sm md:p-7">
            {error && (
              <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label htmlFor="feedbackType" className="block text-sm font-semibold text-slate-800">
                  Feedback Type
                </label>
                <select
                  id="feedbackType"
                  value={feedbackType}
                  onChange={(e) => setFeedbackType(e.target.value)}
                  className="mt-2 block w-full rounded-xl border border-blue-100 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                >
                  {FEEDBACK_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </div>

              <fieldset>
                <legend className="block text-sm font-semibold text-slate-800">
                  Satisfaction <span className="text-red-500">*</span>
                </legend>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {SATISFACTION_OPTIONS.map((option) => {
                    const checked = satisfaction === option.value;
                    return (
                      <label
                        key={option.value}
                        className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition ${
                          checked
                            ? 'border-blue-300 bg-blue-50'
                            : 'border-blue-100 bg-white hover:border-blue-200 hover:bg-blue-50/40'
                        }`}
                      >
                        <input
                          type="radio"
                          name="satisfaction"
                          value={option.value}
                          checked={checked}
                          onChange={() => setSatisfaction(option.value)}
                          className="mt-0.5"
                          required
                        />
                        <span>
                          <span className="block text-sm font-semibold text-slate-800">{option.label}</span>
                          <span className="mt-0.5 block text-xs text-slate-600">{option.description}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <div>
                <label htmlFor="comments" className="block text-sm font-semibold text-slate-800">
                  Comments <span className="text-red-500">*</span>
                </label>
                <textarea
                  id="comments"
                  value={comments}
                  onChange={(e) => setComments(e.target.value)}
                  placeholder="Describe your experience, suggestions, or issues..."
                  className="mt-2 h-36 w-full resize-y rounded-xl border border-blue-100 bg-white px-3 py-2.5 text-sm leading-6 text-slate-800 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                  required
                />
                <div className="mt-1 text-right text-[11px] text-slate-500">{comments.length} characters</div>
              </div>

              <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded-lg border border-blue-100 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-blue-50"
                  disabled={loading}
                >
                  Reset
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-blue-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:opacity-50"
                  disabled={loading}
                >
                  {loading ? 'Submitting...' : 'Submit Feedback'}
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
