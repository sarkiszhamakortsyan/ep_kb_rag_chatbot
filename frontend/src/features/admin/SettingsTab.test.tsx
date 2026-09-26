import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { jsonResponse } from "../../test/fixtures";
import { SettingsTab } from "./SettingsTab";

const settings = {
  providers: [
    { name: "ollama", model: "ministral-3:3b", enabled: true, default: true },
    { name: "anthropic", model: "claude-opus-5", enabled: true, default: false },
  ],
  embedding_provider: "ollama",
  embedding_model: "embeddinggemma",
};

describe("SettingsTab", () => {
  it("validates, then saves the enabled models and the default", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return Promise.resolve(
          jsonResponse({
            ...settings,
            providers: [
              { ...settings.providers[0], enabled: false, default: false },
              { ...settings.providers[1], default: true },
            ],
          }),
        );
      }
      return Promise.resolve(jsonResponse(settings));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<SettingsTab token="t" onUnauthorized={vi.fn()} />);

    const save = await screen.findByRole("button", { name: "Save" });
    expect(save).toBeDisabled(); // nothing changed yet

    await user.click(screen.getByRole("switch", { name: "Enable Ministral 3B" }));
    expect(screen.getByText("The default model must be enabled.")).toBeInTheDocument();
    expect(save).toBeDisabled();

    await user.click(screen.getAllByRole("radio", { name: "Default" })[1]);
    expect(save).toBeEnabled();
    await user.click(save);

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(put[1]!.body as string)).toEqual({
      enabled_providers: ["anthropic"],
      default_provider: "anthropic",
    });
    expect(screen.getByRole("switch", { name: "Enable Ministral 3B" })).not.toBeChecked();
  });
});
