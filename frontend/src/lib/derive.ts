import type { WsMessage } from "./types";

type DecisionMsg = Extract<WsMessage, { type: "decision" }>;

/** How many of today's spent cartridges went to exploration vs. above-
 * threshold referral.
 *
 * Extracted into its own tested function after a real bug: computing this
 * inline once counted every decision with propensity in (0,1), which
 * includes patients OFFERED an exploration probability but not actually
 * drawn (`refer === false`) -- the backend assigns `reason === "explore"` to
 * anyone in the band regardless of the coin-flip outcome
 * (controller/policy.py). That produced "434.3% exploratory" against a day
 * that spent 35 of 40 cartridges. Only patients with `refer === true` were
 * ever actually paid for out of the budget.
 */
export function computeExploreSplit(
  feed: DecisionMsg[],
  day: number,
): { exploit: number; exploreSpend: number } {
  let exploit = 0;
  let exploreSpend = 0;
  for (const d of feed) {
    if (d.day !== day || !d.refer) continue;
    if (d.propensity < 1) exploreSpend += 1;
    else exploit += 1;
  }
  return { exploit, exploreSpend };
}
