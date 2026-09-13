import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExploreSplit } from "./ExploreSplit";

describe("ExploreSplit", () => {
  it("labels a resumed view as not tracked, rather than showing a stale zero", () => {
    // Regression guard for the follow-on to the 434% bug: resuming a
    // finished run with an empty feed must not present 0/0 as if it were a
    // real measurement sitting next to a non-zero cartridge count.
    render(<ExploreSplit spent={35} exploreSpend={0} stale />);
    expect(screen.getByText(/not tracked for a resumed view/i)).toBeInTheDocument();
    expect(screen.queryByText(/exploit \(/)).not.toBeInTheDocument();
  });

  it("shows a sane percentage for a real live split", () => {
    render(<ExploreSplit spent={35} exploreSpend={2} />);
    expect(screen.getByText(/5\.7% exploratory/)).toBeInTheDocument();
    expect(screen.getByText(/exploit \(33\)/)).toBeInTheDocument();
    expect(screen.getByText(/explore \(2\)/)).toBeInTheDocument();
  });
});
