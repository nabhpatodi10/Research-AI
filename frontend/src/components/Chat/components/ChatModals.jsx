import { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';

export default function ChatModals({
  isRenameModalOpen,
  closeRenameModal,
  handleRenameSubmit,
  renameValue,
  setRenameValue,
  renameError,
  renameLoading,
  isShareModalOpen,
  closeShareModal,
  shareSessionTitle,
  handleShareSubmit,
  shareEmail,
  setShareEmail,
  shareCollaborative,
  setShareCollaborative,
  shareError,
  shareLoading,
}) {
  return (
    <>
      <Transition appear show={isRenameModalOpen} as={Fragment}>
        <Dialog as="div" className="relative z-30" onClose={closeRenameModal}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-200"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-150"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-200"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-150"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-md overflow-hidden rounded-2xl border border-blue-100 bg-white p-6 shadow-xl">
                  <Dialog.Title className="text-lg font-semibold text-blue-900">Rename Chat Session</Dialog.Title>

                  <form onSubmit={handleRenameSubmit} className="mt-4 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700">Chat Name</label>
                      <input
                        type="text"
                        required
                        value={renameValue}
                        onChange={(event) => setRenameValue(event.target.value)}
                        className="mt-1 block w-full rounded-lg border border-blue-100 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                      />
                    </div>

                    {renameError && <p className="text-sm text-red-500">{renameError}</p>}

                    <div className="flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={closeRenameModal}
                        className="rounded-lg border border-blue-100 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-blue-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={renameLoading || !renameValue.trim()}
                        className="rounded-lg bg-blue-900 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                      >
                        {renameLoading ? 'Renaming...' : 'Rename'}
                      </button>
                    </div>
                  </form>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>

      <Transition appear show={isShareModalOpen} as={Fragment}>
        <Dialog as="div" className="relative z-30" onClose={closeShareModal}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-200"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-150"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-200"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-150"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-md overflow-hidden rounded-2xl border border-blue-100 bg-white p-6 shadow-xl">
                  <Dialog.Title className="text-lg font-semibold text-blue-900">Share Chat Session</Dialog.Title>
                  {shareSessionTitle && (
                    <p className="mt-1 text-sm text-slate-500">Sharing: {shareSessionTitle}</p>
                  )}

                  <form onSubmit={handleShareSubmit} className="mt-4 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700">Recipient Email</label>
                      <input
                        type="email"
                        required
                        value={shareEmail}
                        onChange={(event) => setShareEmail(event.target.value)}
                        className="mt-1 block w-full rounded-lg border border-blue-100 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                      />
                    </div>

                    <label className="flex items-start gap-3 rounded-lg border border-blue-100 bg-blue-50/30 px-3 py-2">
                      <input
                        type="checkbox"
                        checked={shareCollaborative}
                        onChange={(event) => setShareCollaborative(event.target.checked)}
                        className="mt-0.5 h-4 w-4 rounded border-blue-300 text-blue-700 focus:ring-blue-300"
                      />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-slate-700">Collaborative chat</span>
                        <span className="block text-xs text-slate-500">
                          {shareCollaborative
                            ? 'Recipient joins this live chat.'
                            : 'Recipient gets an independent copy.'}
                        </span>
                      </span>
                    </label>

                    {shareError && <p className="text-sm text-red-500">{shareError}</p>}

                    <div className="flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={closeShareModal}
                        className="rounded-lg border border-blue-100 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-blue-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={shareLoading || !shareEmail.trim()}
                        className="rounded-lg bg-blue-900 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                      >
                        {shareLoading ? 'Sharing...' : 'Share'}
                      </button>
                    </div>
                  </form>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>
    </>
  );
}
