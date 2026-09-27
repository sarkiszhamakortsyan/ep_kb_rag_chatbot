// Tests for the Tests tab: the run list, confirmation before a paid Claude run, and the run
// details.

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EvalRun } from "../../api/admin";
import { jsonResponse } from "../../test/fixtures";
import { TestsTab } from "./TestsTab";

const run = (overrides: Partial<EvalRun>): EvalRun => ({
  id: "r1",
  kind: "answers",
  provider: "anthropic",
  model: "claude-opus-5",
  status: "done",
  started_at: "2026-09-26T12:00:00.000+00:00",
  finished_at: "2026-09-26T12:01:30.000+00:00",
  total: 18,
  done: 18,
  summary: { passed: 18, questions: 18 },
  results: [],
  error: null,
  ...overrides,
});

const providers = {
  default: "ollama",
  providers: [
    {
      name: "ollama",
      model: "ministral-3:3b",
      default: true,
      available: true,
      detail: null,
    },
    {
      name: "anthropic",
      model: "claude-opus-5",
      default: false,
      available: true,
      detail: null,
    },
  ],
};

function mockApi(runs: EvalRun[], started: EvalRun) {
  let running: EvalRun | null = null;
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/providers"))
      return Promise.resolve(jsonResponse(providers));
    if (url.endsWith("/admin/eval") && init?.method === "POST") {
      running = started;
      return Promise.resolve(jsonResponse(started, 202));
    }
    if (url.endsWith("/admin/eval")) {
      return Promise.resolve(
        jsonResponse({
          runs: running ? [running, ...runs] : runs,
          running: running?.id ?? null,
        }),
      );
    }
    if (running && url.endsWith(`/admin/eval/${running.id}`))
      return Promise.resolve(jsonResponse(running));
    if (url.includes("/admin/eval/r1")) {
      return Promise.resolve(
        jsonResponse(
          run({
            results: [
              {
                id: "q01",
                question: "Which plans support SCIM?",
                answerable: true,
                passed: true,
                refused: false,
                cited: ["kb-001"],
                key_facts: ["Enterprise"],
                facts_found: ["Enterprise"],
                answer: "Only **Enterprise** [1].",
                total_ms: 3000,
              },
              {
                id: "q11",
                question: "Salesforce sync?",
                answerable: true,
                passed: false,
                refused: false,
                cited: ["kb-004"],
                key_facts: ["200", "temporary"],
                facts_found: ["temporary"],
                answer: "It counts.",
                total_ms: 4000,
              },
            ],
          }),
        ),
      );
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("TestsTab", () => {
  it("lists runs with the change against the previous run", async () => {
    mockApi(
      [run({}), run({ id: "r0", summary: { passed: 17, questions: 18 } })],
      run({}),
    );
    render(<TestsTab token="t" onUnauthorized={vi.fn()} />);

    const table = await screen.findByRole("table");
    expect(within(table).getAllByText("18 / 18 passed")).toHaveLength(1);
    expect(within(table).getByText("+1 vs previous")).toBeInTheDocument();
    expect(within(table).getAllByText("90 s")).toHaveLength(2);
  });

  it("asks for confirmation before a paid Claude run, then shows progress", async () => {
    const fetchMock = mockApi(
      [],
      run({ id: "r2", status: "running", done: 3, summary: null }),
    );
    const user = userEvent.setup();
    render(<TestsTab token="t" onUnauthorized={vi.fn()} />);

    await user.click(await screen.findByRole("radio", { name: /Answers/ }));
    await user.selectOptions(screen.getByLabelText("Model"), "anthropic");
    expect(screen.getByText(/Costs about \$0\.20/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run benchmark" }));
    await user.click(
      screen.getByRole("button", { name: "Yes, run it (about $0.20)" }),
    );

    const bar = await screen.findByRole("progressbar", {
      name: "Benchmark progress",
    });
    expect(bar).toHaveAttribute("aria-valuenow", "3");
    const post = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "POST",
    )!;
    expect(JSON.parse(post[1]!.body as string)).toEqual({
      kind: "answers",
      provider: "anthropic",
    });
  });

  it("opens a run with failures first", async () => {
    mockApi([run({})], run({}));
    const user = userEvent.setup();
    render(<TestsTab token="t" onUnauthorized={vi.fn()} />);
    await user.click(
      await screen.findByRole("button", { name: /Answers · Claude Opus/ }),
    );

    const panel = await screen.findByRole("dialog", { name: "Benchmark run" });
    const items = await within(panel).findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Salesforce sync?");
    expect(items[0]).toHaveTextContent("facts 1/2");
    expect(within(items[0]).getByLabelText("failed")).toBeInTheDocument();
  });
});
