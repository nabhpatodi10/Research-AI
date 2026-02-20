import ChatHistory from '../ChatHistory';

export default function SidebarContent({
  sessions,
  sessionsLoading,
  sessionsError,
  activeSessionId,
  searchTerm,
  setSearchTerm,
  handleNewChat,
  handleDeleteChat,
  handleRenameChat,
  handleShareChat,
  loadChat,
  taskBySession,
}) {
  return (
    <>
      <div className="border-b border-blue-100 px-4 pb-4 pt-3">
        <div className="rounded-2xl border border-blue-100/80 bg-gradient-to-br from-blue-50 via-white to-slate-50 p-4 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-700">Workspace</p>
          <h1 className="brand-display mt-1 text-xl font-bold text-blue-900">ResearchAI Chat</h1>
          <p className="mt-2 text-xs text-slate-500">{sessions.length} sessions available</p>

          <button
            onClick={handleNewChat}
            className="mt-4 w-full rounded-xl bg-blue-900 px-3 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800"
          >
            + New chat
          </button>
        </div>

        <div className="mt-3 relative">
          <svg
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m21 21-4.35-4.35M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />
          </svg>
          <input
            type="text"
            placeholder="Search sessions"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => event.stopPropagation()}
            className="w-full rounded-xl border border-blue-100 bg-white px-9 py-2.5 text-sm text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto no-scrollbar px-3 pb-6 pt-3">
        <ChatHistory
          sessions={sessions}
          loading={sessionsLoading}
          error={sessionsError}
          activeSessionId={activeSessionId}
          onChatSelect={loadChat}
          onDeleteChat={handleDeleteChat}
          onRenameChat={handleRenameChat}
          onShareChat={handleShareChat}
          searchTerm={searchTerm}
          taskBySession={taskBySession}
        />
      </div>
    </>
  );
}
