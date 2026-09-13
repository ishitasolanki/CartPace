import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BaselineTable } from "./BaselineTable";
import type { CompareOut } from "../lib/types";

const data: CompareOut = {
  policies: [
    { policy: "CartPace", caught: 616, spent: 1394, recall: 0.631, per_cartridge: 0.44, explore_share: 0.017 },
    { policy: "ClockPacer (ablation)", caught: 609, spent: 1387, recall: 0.623, per_cartridge: 0.44, explore_share: 0 },
    { policy: "Fixed", caught: 538, spent: 1013, recall: 0.551, per_cartridge: 0.53, explore_share: 0 },
  ],
  oracle: { policy: "TopB oracle (model score)", caught: 681, spent: 1600 },
};

describe("BaselineTable", () => {
  it("marks the ablation, per project.md section 13 -- it must never be an unlabelled row", () => {
    render(<BaselineTable data={data} />);
    expect(screen.getByText("ablation")).toBeInTheDocument();
  });

  it("always includes the oracle, labelled as an offline upper bound", () => {
    render(<BaselineTable data={data} />);
    expect(screen.getByText(/TopB oracle/)).toBeInTheDocument();
    expect(screen.getByText(/upper bound, offline/i)).toBeInTheDocument();
  });

  it("ranks by cases caught, not cases per cartridge", () => {
    render(<BaselineTable data={data} />);
    const rows = screen.getAllByRole("row").slice(1); // skip the header row
    // CartPace (616) must be listed before Fixed (538) despite Fixed having
    // the higher per-cartridge figure in this fixture.
    const text = rows.map((r) => r.textContent ?? "").join("|");
    expect(text.indexOf("CartPace")).toBeLessThan(text.indexOf("Fixed"));
  });
});
