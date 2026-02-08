import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function Signup() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { signup, googleLogin, currentUser } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (currentUser) {
      navigate('/chat');
    }
  }, [currentUser, navigate]);

  const handleGoogleSignup = async () => {
    try {
      setLoading(true);
      setError('');
      googleLogin();
    } catch (err) {
      console.error('Google signup error:', err);
      setError(err.message || 'Failed to sign up with Google');
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (password.length < 6) {
      setError('Password should be at least 6 characters');
      return;
    }

    try {
      setError('');
      setLoading(true);
      await signup(name, email, password);
      navigate('/chat');
    } catch (err) {
      setError(err.message || 'Failed to create an account');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-[calc(100vh-4rem)] overflow-hidden bg-gradient-to-b from-slate-50 via-blue-50/40 to-slate-100 px-4 pb-12 pt-20 sm:px-6">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-14 -top-20 h-72 w-72 rounded-full bg-blue-200/30 blur-3xl" />
        <div className="absolute -bottom-16 right-0 h-64 w-64 rounded-full bg-blue-900/10 blur-3xl" />
      </div>

      <div className="relative mx-auto w-full max-w-6xl">
        <div className="grid gap-6 lg:grid-cols-[1fr_1.05fr]">
          <section className="overflow-hidden rounded-3xl border border-blue-100 bg-white/90 shadow-sm">
            <div className="h-full bg-gradient-to-br from-blue-900 via-blue-800 to-blue-700 p-7 text-white md:p-9">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-100">ResearchAI</p>
              <h1 className="brand-display mt-3 text-3xl font-bold leading-tight md:text-4xl">
                Build your research workspace in minutes
              </h1>
              <p className="mt-4 max-w-lg text-sm leading-7 text-blue-100/90">
                Create an account to start long-form research chats, compare perspectives, and assemble structured outputs faster.
              </p>

              <div className="mt-8 space-y-3">
                {[
                  'Store and resume research sessions',
                  'Generate structured long-form documents',
                  'Collaborate through shareable chat threads',
                ].map((item) => (
                  <div key={item} className="flex items-start gap-3 rounded-xl border border-white/20 bg-white/10 px-3 py-2.5">
                    <span className="mt-1 h-2 w-2 rounded-full bg-blue-200" />
                    <p className="text-sm text-blue-50">{item}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="rounded-3xl border border-blue-100 bg-white p-6 shadow-sm md:p-8">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-700">Create Account</p>
              <h2 className="brand-display mt-2 text-3xl font-bold text-slate-900">Sign up</h2>
              <p className="mt-2 text-sm text-slate-600">Get started with email or continue with Google.</p>
            </div>

            {error && (
              <div className="mt-5 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            <button
              onClick={handleGoogleSignup}
              disabled={loading}
              className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl border border-blue-100 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 488 512">
                <path fill="currentColor" d="M488 261.8C488 403.3 391.1 504 248 504c-137.2 0-248-110.8-248-248S110.8 8 248 8c66.8 0 123 24.5 166.3 64.9l-67.5 64.9C258.5 52.6 94.3 116.6 94.3 256c0 86.5 69.1 156.6 153.7 156.6 98.2 0 135-70.4 140.8-106.9H248v-85.3h236.1c2.3 12.7 3.9 24.9 3.9 41.4z"/>
              </svg>
              Continue with Google
            </button>

            <div className="relative my-5">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-blue-100" />
              </div>
              <div className="relative flex justify-center text-xs font-semibold uppercase tracking-[0.16em]">
                <span className="bg-white px-2 text-slate-400">or sign up with email</span>
              </div>
            </div>

            <form className="space-y-4" onSubmit={handleSubmit}>
              <div>
                <label htmlFor="name" className="mb-1.5 block text-sm font-semibold text-slate-700">
                  Full name
                </label>
                <input
                  id="name"
                  name="name"
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="block w-full rounded-xl border border-blue-100 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                  placeholder="Your name"
                />
              </div>

              <div>
                <label htmlFor="email" className="mb-1.5 block text-sm font-semibold text-slate-700">
                  Email
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full rounded-xl border border-blue-100 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                  placeholder="name@company.com"
                />
              </div>

              <div>
                <label htmlFor="password" className="mb-1.5 block text-sm font-semibold text-slate-700">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="block w-full rounded-xl border border-blue-100 bg-white px-3 py-2.5 pr-11 text-sm text-slate-900 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                    placeholder="At least 6 characters"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    className="absolute inset-y-0 right-2 my-auto inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-blue-50 hover:text-blue-900"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? (
                      <svg className="h-4.5 w-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 3l18 18M10.73 5.08A10.45 10.45 0 0 1 12 5c7 0 10 7 10 7a14.76 14.76 0 0 1-4.11 5.17M6.61 6.61A14.73 14.73 0 0 0 2 12s3 7 10 7a9.77 9.77 0 0 0 5.39-1.61M9.88 9.88a3 3 0 1 0 4.24 4.24" />
                      </svg>
                    ) : (
                      <svg className="h-4.5 w-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
                        <circle cx="12" cy="12" r="3" strokeWidth="2" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              <label htmlFor="terms" className="flex items-start gap-2 rounded-xl border border-blue-100 bg-blue-50/40 px-3 py-2.5 text-sm text-slate-700">
                <input
                  id="terms"
                  name="terms"
                  type="checkbox"
                  required
                  className="mt-0.5 h-4 w-4 rounded border-blue-200 text-blue-900 focus:ring-blue-500"
                />
                <span>I agree to the terms of service and privacy policy.</span>
              </label>

              <button
                type="submit"
                disabled={loading}
                className="mt-2 inline-flex w-full items-center justify-center rounded-xl bg-blue-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? 'Creating account...' : 'Create account'}
              </button>
            </form>

            <p className="mt-5 text-center text-sm text-slate-600">
              Already have an account?{' '}
              <Link to="/login" className="font-semibold text-blue-900 hover:text-blue-700">
                Sign in
              </Link>
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
