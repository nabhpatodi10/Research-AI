export default function PrivacyPolicy() {
  return (
    <div className="relative min-h-[calc(100vh-4rem)] overflow-hidden bg-gradient-to-b from-slate-50 via-blue-50/30 to-slate-100 px-4 pb-14 pt-20 sm:px-6">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-20 -top-14 h-72 w-72 rounded-full bg-blue-200/30 blur-3xl" />
        <div className="absolute -bottom-10 right-0 h-72 w-72 rounded-full bg-blue-900/10 blur-3xl" />
      </div>

      <article className="relative mx-auto w-full max-w-4xl rounded-3xl border border-blue-100 bg-white/95 p-6 shadow-sm md:p-10">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-700">Legal</p>
        <h1 className="brand-display mt-2 text-3xl font-bold text-slate-900 md:text-4xl">
          Privacy Policy
        </h1>
        <p className="mt-3 text-sm text-slate-600">
          Last updated: February 16, 2026
        </p>

        <div className="mt-8 space-y-7 text-[15px] leading-7 text-slate-700">
          <section>
            <h2 className="text-xl font-bold text-slate-900">1. Overview</h2>
            <p className="mt-2">
              This Privacy Policy explains how ResearchAI collects, uses, stores, and shares information when you use the app.
              By using ResearchAI, you agree to the practices described here.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">2. Information We Collect</h2>
            <div className="mt-2 space-y-3">
              <p>
                <span className="font-semibold text-slate-900">Account information:</span> name, email address, provider, and account ID when you sign up or log in.
              </p>
              <p>
                <span className="font-semibold text-slate-900">Session and authentication data:</span> a secure session cookie used to keep you signed in.
              </p>
              <p>
                <span className="font-semibold text-slate-900">Research and chat data:</span> chat messages, research prompts, generated responses, session titles, and metadata.
              </p>
              <p>
                <span className="font-semibold text-slate-900">Retrieved content:</span> source content collected from web search and URL retrieval tools to answer your requests.
              </p>
              <p>
                <span className="font-semibold text-slate-900">Feedback data:</span> information you submit through the feedback form.
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">3. How We Use Information</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>Provide, operate, and improve ResearchAI.</li>
              <li>Authenticate users and secure sessions.</li>
              <li>Process chat and research requests.</li>
              <li>Store session history and enable sharing/collaboration features.</li>
              <li>Respond to support or feedback submissions.</li>
              <li>Detect abuse, fraud, or misuse of the service.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">4. Third-Party Processing</h2>
            <p className="mt-2">
              ResearchAI uses third-party infrastructure and model providers to deliver core functionality.
              Depending on your usage, your prompts or related content may be processed by services such as authentication providers,
              database/storage providers, model APIs, and search/retrieval providers.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">5. Cookies</h2>
            <p className="mt-2">
              ResearchAI uses an HTTP-only authentication cookie to maintain your logged-in session.
              This cookie is required for account and chat features to function.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">6. Data Sharing</h2>
            <p className="mt-2">
              We do not sell your personal information.
              We may share information only as needed to operate the service, comply with legal obligations, protect rights/safety, or when you explicitly use sharing features.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">7. Data Retention</h2>
            <p className="mt-2">
              We retain account and research data for as long as needed to provide the service and maintain account history,
              unless a longer period is required for legal, security, or operational reasons.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">8. Security</h2>
            <p className="mt-2">
              We apply reasonable technical and organizational safeguards to protect your data.
              No system is completely secure, so we cannot guarantee absolute security.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">9. Your Choices</h2>
            <p className="mt-2">
              You can manage your account usage, stop using the service at any time, and request removal of your data through project maintainers where applicable.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">10. Children&rsquo;s Privacy</h2>
            <p className="mt-2">
              ResearchAI is not intended for children under 13, and we do not knowingly collect personal information from children under 13.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">11. Changes to This Policy</h2>
            <p className="mt-2">
              We may update this Privacy Policy from time to time.
              Material updates will be reflected by revising the &ldquo;Last updated&rdquo; date on this page.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900">12. Contact</h2>
            <p className="mt-2">
              For privacy-related questions, contact the project maintainers through the official repository or support channel associated with this deployment.
            </p>
          </section>
        </div>
      </article>
    </div>
  );
}
