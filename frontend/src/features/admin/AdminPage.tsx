// Reserved for the hidden admin tabs (ideas.md: statistics, costs, history, tests).
// Intentionally empty in the MVP.
export function AdminPage() {
  return (
    <main className="mx-auto max-w-2xl p-8 text-slate-700">
      <h1 className="text-xl font-semibold">Admin</h1>
      <p className="mt-2 text-sm text-slate-500">Nothing here yet.</p>
      <a href="/" className="mt-4 inline-block text-sm text-indigo-700 underline">
        Back to the chat
      </a>
    </main>
  );
}
