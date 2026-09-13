import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BudgetGauge } from "./BudgetGauge";

describe("BudgetGauge", () => {
  it("warns when the budget is exhausted", () => {
    render(<BudgetGauge spent={40} budget={40} />);
    expect(screen.getByText(/exhausted/i)).toBeInTheDocument();
  });

  it("does not warn while budget remains", () => {
    render(<BudgetGauge spent={20} budget={40} />);
    expect(screen.queryByText(/exhausted/i)).not.toBeInTheDocument();
  });

  it("does not divide by zero when the budget is zero", () => {
    render(<BudgetGauge spent={0} budget={0} />);
    expect(screen.getByText("0 / 0")).toBeInTheDocument();
  });
});
