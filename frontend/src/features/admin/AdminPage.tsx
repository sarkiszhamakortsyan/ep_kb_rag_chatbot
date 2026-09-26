// Reserved for the hidden admin tabs (ideas.md: statistics, costs, history, tests).
// Intentionally empty in the MVP.
export function AdminPage() {
  return (
    <main className="mx-auto max-w-2xl p-8 text-ink-muted">
      <h1 className="text-xl font-semibold text-ink">Admin</h1>
      <p className="mt-2 text-sm text-ink-faint">Nothing here yet.</p>
      <a href="/" className="mt-4 inline-block text-sm text-brand underline underline-offset-2">
        Back to the chat
      </a>
    </main>
  );
}
