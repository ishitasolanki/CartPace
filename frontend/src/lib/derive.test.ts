import { describe, expect, it } from "vitest";
import { computeExploreSplit } from "./derive";
import type { WsMessage } from "./types";

type DecisionMsg = Extract<WsMessage, { type: "decision" }>;

function decision(overrides: Partial<DecisionMsg>): DecisionMsg {
  return {
    type: "decision",
    day: 0,
    seq: 0,
    refer: true,
    propensity: 1,
    s_tilde: 0.5,
    reason: "above_threshold",
    stratum: 0,
    ...overrides,
  };
}

describe("computeExploreSplit", () => {
  it("counts only referred patients, never patients merely offered exploration", () => {
    // The exact shape of the regression: a day that spent 35 cartridges,
    // where far more than 35 patients were offered a sub-threshold
    // propensity but only some of them were actually drawn. Before the fix,
    // filtering by propensity range alone (ignoring `refer`) produced
    // "434.3% exploratory" against a 35-cartridge day.
    const feed: DecisionMsg[] = [
      ...Array.from({ length: 33 }, () =>
        decision({ refer: true, propensity: 1, reason: "above_threshold" }),
      ),
      ...Array.from({ length: 2 }, () =>
        decision({ refer: true, propensity: 0.02, reason: "explore" }),
      ),
      // Offered exploration, coin flip did not draw them -- not referred,
      // must not count as spent.
      ...Array.from({ length: 150 }, () =>
        decision({ refer: false, propensity: 0.02, reason: "explore" }),
      ),
    ];

    const { exploit, exploreSpend } = computeExploreSplit(feed, 0);
    expect(exploit).toBe(33);
    expect(exploreSpend).toBe(2);
    expect(exploit + exploreSpend).toBe(35); // matches actual cartridges spent
  });

  it("ignores decisions from other days", () => {
    const feed: DecisionMsg[] = [
      decision({ day: 0, refer: true, propensity: 1 }),
      decision({ day: 1, refer: true, propensity: 0.02 }),
    ];
    expect(computeExploreSplit(feed, 0)).toEqual({ exploit: 1, exploreSpend: 0 });
    expect(computeExploreSplit(feed, 1)).toEqual({ exploit: 0, exploreSpend: 1 });
  });

  it("ignores non-referred decisions entirely, including budget_exhausted", () => {
    const feed: DecisionMsg[] = [
      decision({ refer: false, propensity: 0, reason: "budget_exhausted" }),
      decision({ refer: false, propensity: 0.004, reason: "below_floor" }),
    ];
    expect(computeExploreSplit(feed, 0)).toEqual({ exploit: 0, exploreSpend: 0 });
  });

  it("returns zero for an empty feed", () => {
    expect(computeExploreSplit([], 0)).toEqual({ exploit: 0, exploreSpend: 0 });
  });

  it("treats propensity exactly 1 as exploit, never explore", () => {
    const feed = [decision({ refer: true, propensity: 1 })];
    expect(computeExploreSplit(feed, 0)).toEqual({ exploit: 1, exploreSpend: 0 });
  });
});
