import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const featureCards = [
  {
    title: 'Focused Discovery',
    description: 'Turn broad topics into clear research directions with guided exploration and organized findings.',
  },
  {
    title: 'Context-Aware Chat',
    description: 'Ask follow-up questions naturally and keep the conversation aligned with your research goal.',
  },
  {
    title: 'Research Workflows',
    description: 'Move from exploration to polished long-form output when you are ready to produce final deliverables.',
  },
  {
    title: 'Live Source Grounding',
    description: 'Get responses shaped around verifiable information and clear supporting references.',
  },
  {
    title: 'Session Collaboration',
    description: 'Rename, share, and organize chats so teams can iterate on the same research direction.',
  },
  {
    title: 'Reliable Experience',
    description: 'A streamlined workspace designed for consistent performance and smooth, uninterrupted research sessions.',
  },
];

const steps = [
  {
    number: '01',
    title: 'Start with a question',
    text: 'Ask a focused prompt or describe a broad topic you want to investigate.',
  },
  {
    number: '02',
    title: 'Collect high-signal context',
    text: 'Build a strong evidence base and shape scattered information into a usable narrative.',
  },
  {
    number: '03',
    title: 'Iterate with follow-ups',
    text: 'Refine scope, compare viewpoints, and pressure-test claims in the same thread.',
  },
  {
    number: '04',
    title: 'Generate deliverables',
    text: 'When needed, hand off to the research graph to produce structured long-form output.',
  },
];

const revealDelays = ['', 'delay-1', 'delay-2', 'delay-3'];

export default function Home() {
  const { currentUser } = useAuth();
  const primaryHref = currentUser ? '/chat' : '/signup';
  const primaryLabel = currentUser ? 'Open Chat Workspace' : 'Create Free Account';

  return (
    <div className="pt-16 overflow-x-hidden">
      <section id="home" className="relative isolate">
        <div className="absolute inset-0 -z-10 bg-gradient-to-br from-blue-950 via-blue-900 to-blue-800" />
        <div className="absolute -left-24 top-16 -z-10 h-72 w-72 rounded-full bg-blue-400/30 blur-3xl float-slow" />
        <div className="absolute -right-12 bottom-8 -z-10 h-64 w-64 rounded-full bg-indigo-200/20 blur-3xl float-slow" />

        <div className="max-w-6xl mx-auto px-4 py-18 md:py-24">
          <div className="grid gap-12 lg:grid-cols-[1.1fr_0.9fr] items-center">
            <div className="text-white">
              <p className="reveal-up inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-4 py-1.5 text-xs font-semibold tracking-wide uppercase">
                AI Research Platform
              </p>
              <h1 className="reveal-up delay-1 mt-5 text-4xl md:text-6xl font-bold leading-tight">
                Build stronger research outputs with a chat-native workflow.
              </h1>
              <p className="reveal-up delay-2 mt-5 text-blue-100 text-lg max-w-2xl">
                ResearchAI helps you go from first question to publication-grade output in one focused workspace.
              </p>
              <div className="reveal-up delay-3 mt-8 flex flex-wrap items-center gap-3">
                <Link
                  to={primaryHref}
                  className="rounded-xl bg-white px-6 py-3 font-semibold text-blue-900 hover:bg-blue-50 transition"
                >
                  {primaryLabel}
                </Link>
                <a
                  href="#workflow"
                  className="rounded-xl border border-white/40 bg-white/10 px-6 py-3 font-semibold text-white hover:bg-white/20 transition"
                >
                  See Workflow
                </a>
              </div>
            </div>

            <div className="reveal-up delay-2">
              <div className="glass-panel rounded-2xl p-6 shadow-2xl">
                <div className="rounded-xl border border-blue-100 bg-white p-5">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">Research AI</p>
                    <span className="inline-flex rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-semibold text-blue-700">
                      Live Workflow
                    </span>
                  </div>

                  <h2 className="mt-3 text-xl font-bold text-slate-900">
                    Plan, run, and refine in one workspace
                  </h2>

                  <div className="mt-4 grid gap-2">
                    {[
                      'Keep every idea, note, and iteration in one place.',
                      'Transform rough questions into structured, decision-ready insights.',
                      'Produce shareable outputs that are easy for teams to review and build on.',
                    ].map((item) => (
                      <div key={item} className="flex items-start gap-2 rounded-lg border border-blue-100 bg-blue-50/40 px-3 py-2">
                        <span className="mt-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-blue-900 text-[10px] font-bold text-white">
                          ✓
                        </span>
                        <p className="text-sm text-slate-700">{item}</p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 grid grid-cols-3 gap-2">
                    <div className="rounded-lg bg-blue-50 px-3 py-2">
                      <p className="text-[11px] text-blue-900/80">Output Quality</p>
                      <p className="text-base font-bold text-blue-900">Structured & Grounded</p>
                    </div>
                    <div className="rounded-lg bg-blue-50 px-3 py-2">
                      <p className="text-[11px] text-blue-900/80">Workspace</p>
                      <p className="text-base font-bold text-blue-900">Individual or Collaborative</p>
                    </div>
                    <div className="rounded-lg bg-blue-50 px-3 py-2">
                      <p className="text-[11px] text-blue-900/80">Research Speed</p>
                      <p className="text-base font-bold text-blue-900">Quick Iteration</p>
                    </div>
                  </div>
                </div>
                <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
                  Start simple, iterate quickly, and publish with confidence when your scope is stable.
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-white">
        <div className="max-w-6xl mx-auto px-4 py-10">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="reveal-up rounded-xl border border-blue-100 bg-blue-50/60 px-5 py-4">
              <p className="text-xs uppercase tracking-wide font-semibold text-blue-700">Built for Depth</p>
              <p className="mt-2 text-2xl font-bold text-blue-900">Structured, Long-form research documents</p>
            </div>
            <div className="reveal-up delay-1 rounded-xl border border-blue-100 bg-blue-50/60 px-5 py-4">
              <p className="text-xs uppercase tracking-wide font-semibold text-blue-700">Grounded Answers</p>
              <p className="mt-2 text-2xl font-bold text-blue-900">Evidence-driven research workflow</p>
            </div>
            <div className="reveal-up delay-2 rounded-xl border border-blue-100 bg-blue-50/60 px-5 py-4">
              <p className="text-xs uppercase tracking-wide font-semibold text-blue-700">Team Ready</p>
              <p className="mt-2 text-2xl font-bold text-blue-900">Shareable and collaborative chat sessions</p>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="bg-slate-50">
        <div className="max-w-6xl mx-auto px-4 py-18">
          <p className="reveal-up text-sm uppercase tracking-[0.2em] font-semibold text-blue-700">Capabilities</p>
          <h2 className="reveal-up delay-1 mt-3 text-3xl md:text-4xl font-bold text-slate-900">
            Everything you need for modern research execution
          </h2>
          <p className="reveal-up delay-2 mt-4 max-w-3xl text-slate-600">
            Same palette, stronger structure: purpose-built blocks for discovery, synthesis, and production output.
          </p>

          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {featureCards.map((feature, index) => (
              <div
                key={feature.title}
                className={`reveal-up ${revealDelays[index % revealDelays.length]} rounded-2xl border border-blue-100 bg-white p-6 shadow-sm hover:shadow-md transition`}
              >
                <h3 className="text-xl font-bold text-blue-900">{feature.title}</h3>
                <p className="mt-3 text-sm leading-6 text-slate-600">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="workflow" className="bg-white">
        <div className="max-w-6xl mx-auto px-4 py-18">
          <p className="reveal-up text-sm uppercase tracking-[0.2em] font-semibold text-blue-700">Workflow</p>
          <h2 className="reveal-up delay-1 mt-3 text-3xl md:text-4xl font-bold text-slate-900">
            A clear path from idea to final document
          </h2>

          <div className="mt-10 grid gap-4 md:grid-cols-2">
            {steps.map((step, index) => (
              <div
                key={step.number}
                className={`reveal-up ${revealDelays[index % revealDelays.length]} rounded-2xl border border-blue-100 p-6 bg-gradient-to-br from-white to-blue-50/40`}
              >
                <div className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-blue-900 text-white text-sm font-bold">
                  {step.number}
                </div>
                <h3 className="mt-4 text-xl font-bold text-blue-900">{step.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{step.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="relative isolate overflow-hidden bg-blue-900 text-white">
        <div className="absolute -right-24 -top-16 -z-10 h-80 w-80 rounded-full bg-blue-400/30 blur-3xl" />
        <div className="max-w-5xl mx-auto px-4 py-18 text-center">
          <h2 className="reveal-up text-3xl md:text-5xl font-bold">Ready to upgrade your research workflow?</h2>
          <p className="reveal-up delay-1 mt-4 text-blue-100 max-w-2xl mx-auto">
            Move from fragmented research tools to one coherent workspace for discovery, synthesis, and reporting.
          </p>
          <div className="reveal-up delay-2 mt-8 flex flex-wrap justify-center gap-3">
            <Link
              to={primaryHref}
              className="rounded-xl bg-white px-7 py-3 font-semibold text-blue-900 hover:bg-blue-50 transition"
            >
              {primaryLabel}
            </Link>
            <Link
              to="/feedback"
              className="rounded-xl border border-white/35 bg-white/10 px-7 py-3 font-semibold text-white hover:bg-white/20 transition"
            >
              Share Feedback
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
