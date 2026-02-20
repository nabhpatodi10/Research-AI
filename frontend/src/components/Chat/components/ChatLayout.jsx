export default function ChatLayout({ children }) {
  return (
    <div className="relative flex h-screen overflow-hidden bg-gradient-to-b from-slate-50 via-blue-50/40 to-slate-100">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-24 right-0 h-72 w-72 rounded-full bg-blue-200/20 blur-3xl" />
        <div className="absolute -left-16 bottom-10 h-64 w-64 rounded-full bg-blue-900/10 blur-3xl" />
      </div>
      {children}
    </div>
  );
}
