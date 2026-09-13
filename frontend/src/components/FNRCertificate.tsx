import type { CertificateOut } from "../lib/types";

/** The false-negative certificate, reported honestly rather than enforced.
 *
 * `identifiable === false` is not "no data yet" -- it also covers the
 * specific failure this project is built around: with zero exploration the
 * estimator cannot observe a miss and would report exactly 0%, which reads
 * as perfect performance while the controller is actually blind. This panel
 * must never render that as a green number. */
export function FNRCertificate({ cert }: { cert: CertificateOut | null }) {
  if (!cert || !cert.identifiable) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">
          False-negative certificate
        </div>
        <div className="text-sm text-slate-400">
          {cert === null
            ? "No labels have landed yet."
            : "Not identifiable yet — no sub-threshold patient has been " +
              "explored, so a miss cannot be observed. This is not the same " +
              "as a good result."}
        </div>
      </div>
    );
  }

  const pct = (cert.fnr_hat ?? 0) * 100;
  const half = (cert.halfwidth ?? 0) * 100;
  const risky = pct > 20;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          False-negative certificate
        </span>
        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
          identifiable
        </span>
      </div>
      <div className={`text-2xl font-semibold tabular-nums ${risky ? "text-warn" : "text-ink"}`}>
        {pct.toFixed(1)}%{" "}
        <span className="text-sm font-normal text-slate-400">
          ± {half.toFixed(1)} pts
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Estimated share of true cases never referred. A delta-method
        approximation, not a distribution-free bound — see docs/p2-findings.md.
      </p>
    </div>
  );
}
