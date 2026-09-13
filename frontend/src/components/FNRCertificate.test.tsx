import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FNRCertificate } from "./FNRCertificate";

describe("FNRCertificate", () => {
  it("never renders a number when the estimate is not identifiable", () => {
    // The core failure mode this project exists to prevent: with zero
    // exploration the estimator returns exactly 0%, which reads as perfect
    // performance while the controller is actually blind. This component
    // must not render that as a green number under any circumstance.
    render(
      <FNRCertificate cert={{ fnr_hat: 0, halfwidth: 0, identifiable: false }} />,
    );
    expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
    expect(screen.getByText(/not identifiable/i)).toBeInTheDocument();
  });

  it("shows a placeholder before any labels have landed", () => {
    render(<FNRCertificate cert={null} />);
    expect(screen.getByText(/no labels have landed/i)).toBeInTheDocument();
  });

  it("renders the estimate and halfwidth when identifiable", () => {
    render(
      <FNRCertificate cert={{ fnr_hat: 0.383, halfwidth: 0.094, identifiable: true }} />,
    );
    expect(screen.getByText(/38\.3%/)).toBeInTheDocument();
    expect(screen.getByText(/± 9\.4 pts/)).toBeInTheDocument();
  });
});
