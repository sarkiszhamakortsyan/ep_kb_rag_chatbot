import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { jsonResponse } from "../../test/fixtures";
import { AdminPage } from "./AdminPage";

const TOKEN = "secret-token-123";
const session = { history_enabled: true, history_retention_days: 90 };
const turn = {
  created_at: "2026-09-26T12:00:00.000+00:00",
  conversation_id: "conv1",
  message_id: "m1",
  question: "How long are backups kept?",
  refused: false,
  refusal_reason: null,
  provider: "anthropic",
  model: "claude-opus-5",
  sources: 1,
  total_ms: 3800,
};
const detail = {
  ...turn,
  answer: "Backups are kept for **35 days** [1].",
  citations: [
    { number: 1, chunk_id: "kb-003#001", doc_id: "kb-003", title: "Data policy", section: "Backups", snippet: "…", score: 0.63 },
  ],
  language: null,
  stop_reason: "end_turn",
  top_score: 0.63,
  sources_used: 6,
  input_tokens: 1300,
  output_tokens: 90,
  cache_read_tokens: 500,
  cache_creation_tokens: 0,
  embed_ms: 50,
  search_ms: 1,
  ttft_ms: 1400,
  generation_ms: 2000,
};

const stats = {
  date_from: "2026-08-28",
  date_to: "2026-09-26",
  questions: 4,
  answered: 3,
  refused: 1,
  conversations: 2,
  refused_by_reason: { low_score: 1 },
  p50_ms: 3800,
  per_day: [
    { day: "2026-09-25", answered: 1, refused: 0 },
    { day: "2026-09-26", answered: 2, refused: 1 },
  ],
  per_model: [
    { provider: "anthropic", model: "claude-opus-5", questions: 3, refused: 0, p50_ms: 3800, p95_ms: 5200, ttft_p50_ms: 1400 },
    { provider: null, model: null, questions: 1, refused: 1, p50_ms: 60, p95_ms: 60, ttft_p50_ms: null },
  ],
  top_documents: [{ doc_id: "kb-003", title: "Data policy", section: null, citations: 3 }],
  top_sections: [{ doc_id: "kb-003", title: "Data policy", section: "Backups", citations: 2 }],
  recent_refused: [
    { created_at: "2026-09-26T12:00:00.000+00:00", message_id: "m1", question: "What does Enterprise cost?", reason: "low_score" },
  ],
};

function mockAdminApi() {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const auth = new Headers(init?.headers).get("Authorization");
    if (auth !== `Bearer ${TOKEN}`) {
      return Promise.resolve(jsonResponse({ error: { code: "unauthorized", message: "no" } }, 401));
    }
    if (url.endsWith("/session")) return Promise.resolve(jsonResponse(session));
    if (url.includes("/stats")) return Promise.resolve(jsonResponse(stats));
    if (url.includes("/history/m1")) return Promise.resolve(jsonResponse(detail));
    if (url.includes("/history")) {
      return Promise.resolve(jsonResponse({ items: [turn], total: 1, limit: 25, offset: 0 }));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  sessionStorage.clear();
  window.history.pushState(null, "", "/");
});

describe("AdminPage", () => {
  it("rejects a wrong token", async () => {
    mockAdminApi();
    const user = userEvent.setup();
    render(<AdminPage />);
    await user.type(screen.getByLabelText("Admin token"), "wrong{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("not valid");
  });

  it("explains when the admin area is switched off", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ error: { code: "admin_disabled", message: "off" } }, 404))),
    );
    const user = userEvent.setup();
    render(<AdminPage />);
    await user.type(screen.getByLabelText("Admin token"), "anything{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Set ADMIN_TOKEN");
  });

  it("signs in, lists the history and opens a turn", async () => {
    const fetchMock = mockAdminApi();
    const user = userEvent.setup();
    render(<AdminPage />);
    await user.type(screen.getByLabelText("Admin token"), `${TOKEN}{Enter}`);

    // Statistics is the first tab.
    expect(await screen.findByRole("heading", { name: "Usage statistics" })).toBeInTheDocument();
    expect(await screen.findByText("75%")).toBeInTheDocument(); // answered share
    expect(screen.getByText("What does Enterprise cost?")).toBeInTheDocument();
    expect(screen.getByText("No model (refused early)")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Questions per day: 4 in 2 days" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "History" }));
    expect(window.location.pathname).toBe("/admin/history");
    expect(await screen.findByRole("heading", { name: "Response history" })).toBeInTheDocument();
    expect(screen.getByText("Kept for 90 days.", { exact: false })).toBeInTheDocument();
    const row = await screen.findByRole("button", { name: "How long are backups kept?" });
    const table = screen.getByRole("table");
    expect(within(table).getByText("Claude Opus")).toBeInTheDocument();
    expect(within(table).getByText("Answered")).toBeInTheDocument();
    expect(sessionStorage.getItem("omnicorp-admin-token")).toBe(TOKEN);

    await user.click(row);
    const panel = await screen.findByRole("dialog", { name: "Answer details" });
    expect(await within(panel).findByText("35 days")).toBeInTheDocument();
    expect(within(panel).getByText("Data policy")).toBeInTheDocument();
    expect(within(panel).getByText("1,300")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Status"), "refused");
    const lastCall = fetchMock.mock.calls.at(-1)![0];
    expect(lastCall).toContain("refused=true");
  });

  it("returns to sign-in on sign-out", async () => {
    mockAdminApi();
    sessionStorage.setItem("omnicorp-admin-token", TOKEN);
    const user = userEvent.setup();
    render(<AdminPage />);
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(screen.getByLabelText("Admin token")).toBeInTheDocument();
    expect(sessionStorage.getItem("omnicorp-admin-token")).toBeNull();
  });
});
