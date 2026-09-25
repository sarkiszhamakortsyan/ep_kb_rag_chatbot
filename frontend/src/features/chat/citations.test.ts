import { describe, expect, it } from "vitest";
import { linkCitations } from "./citations";

describe("linkCitations", () => {
  const known = new Set([1, 2, 3]);

  it("turns markers into anchor links", () => {
    expect(linkCitations("Kept 35 days [1].", "m1", known)).toBe("Kept 35 days [1](#cite-m1-1).");
  });

  it("splits grouped and adjacent markers", () => {
    expect(linkCitations("A [1, 3] B [2][3]", "m", known)).toBe(
      "A [1](#cite-m-1)[3](#cite-m-3) B [2](#cite-m-2)[3](#cite-m-3)",
    );
  });

  it("leaves unknown numbers and non-markers alone", () => {
    expect(linkCitations("Invented [9]. Array [x].", "m", known)).toBe("Invented [9]. Array [x].");
  });
});
