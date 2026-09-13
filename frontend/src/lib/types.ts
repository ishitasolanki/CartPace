/** Mirrors backend/schemas.py. Kept as a single file so a schema change on
 * one side is easy to notice on the other -- there is no codegen step yet. */

export type Role = "health_worker" | "supervisor";

export interface Me {
  id: number;
  username: string;
  role: Role;
}

export interface RunOut {
  id: number;
  scenario: string;
  seed: number;
  n_days: number;
  status: "pending" | "running" | "done" | "error";
}

export interface DecisionOut {
  day: number;
  seq: number;
  refer: boolean;
  propensity: number;
  s_tilde: number;
  tau: number;
  reason: "above_threshold" | "explore" | "below_floor" | "budget_exhausted";
  stratum: number;
  true_label: number;
}

export interface CertificateOut {
  fnr_hat: number | null;
  halfwidth: number | null;
  identifiable: boolean;
}

export interface StratumOffset {
  stratum: number;
  offset: number;
  ess: number;
}

export interface StratumHistoryPoint {
  day: number;
  stratum: number;
  offset: number;
  ess: number;
}

export interface DayStatOut {
  day: number;
  budget: number;
  spent: number;
  caught: number;
  cases: number;
  explore_spend: number;
}

export interface PolicySummary {
  policy: string;
  caught: number;
  spent: number;
  recall: number;
  per_cartridge: number;
  explore_share: number;
}

export interface CompareOut {
  policies: PolicySummary[];
  oracle: { policy: string; caught: number; spent: number };
}

export interface ScenarioInfo {
  budget: number;
  shortage_budget: number;
  shortage_prob: number;
  delay: number;
  rank_drift_stratum: number;
}

/** WebSocket frames, from backend/engine.py's manager.broadcast() calls. */
export type WsMessage =
  | {
      type: "decision";
      day: number;
      seq: number;
      refer: boolean;
      propensity: number;
      s_tilde: number;
      reason: string;
      stratum: number;
    }
  | {
      type: "day_end";
      day: number;
      budget: number;
      spent: number;
      offsets: number[];
      fnr_hat: number | null;
      fnr_halfwidth: number | null;
      identifiable: boolean;
    }
  | { type: "run_complete" }
  | { type: "error"; detail: string };
