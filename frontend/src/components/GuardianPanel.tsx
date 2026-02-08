import { Loader2, ShieldCheck, Sparkles } from "lucide-react";
import type { GuardianRunDetail, MechanicRunDetail } from "../types.ts";

interface GuardianPanelProps {
  run: GuardianRunDetail | null;
  running: boolean;
  error: string | null;
  expandedFindingIds: Set<string>;
  dismissingFindingId: string | null;
  runningMechanicFindingId: string | null;
  runningMechanicOptionId: string | null;
  mechanicRunsByFinding: Record<string, MechanicRunDetail>;
  mechanicErrorByFinding: Record<string, string>;
  onRunGuardian: () => Promise<void>;
  onToggleFinding: (findingId: string) => void;
  onDismissFinding: (findingId: string) => Promise<void>;
  onRunMechanic: (findingId: string) => Promise<void>;
  onRunMechanicOption: (findingId: string, optionId: string) => Promise<void>;
}

export default function GuardianPanel({
  run,
  running,
  error,
  expandedFindingIds,
  dismissingFindingId,
  runningMechanicFindingId,
  runningMechanicOptionId,
  mechanicRunsByFinding,
  mechanicErrorByFinding,
  onRunGuardian,
  onToggleFinding,
  onDismissFinding,
  onRunMechanic,
  onRunMechanicOption,
}: GuardianPanelProps) {
  const visibleFindings = run?.findings.filter((finding) => finding.resolution_status !== "applied") ?? [];

  return (
    <div className="space-y-4">
      <button
        onClick={() => void onRunGuardian()}
        disabled={running}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-amber-600 bg-amber-900/30 py-2 text-sm font-medium text-amber-300 hover:bg-amber-900/40 disabled:opacity-50"
      >
        {running ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
        {running ? "Running Guardian..." : "Run Guardian Scan"}
      </button>

      {!run && !running && !error && (
        <div className="rounded-lg border border-border bg-surface p-3 text-sm text-text-muted">
          Run a world-wide guardian scan to check for canon inconsistencies.
        </div>
      )}

      {run && (
        <div className="rounded-lg border border-amber-800 bg-amber-900/20 p-3 text-sm">
          <div className="font-medium text-amber-300">Guardian run</div>
          <div className="mt-1 text-text-muted">
            Run: {run.id} ({run.status})
          </div>
          <div className="mt-1 text-text-muted">
            Findings: {visibleFindings.length} | Actions: {run.actions.length}
          </div>
        </div>
      )}

      {run && visibleFindings.length === 0 && run.status !== "failed" && (
        <div className="rounded-lg border border-green-800 bg-green-900/20 p-3 text-sm">
          <div className="flex items-center gap-2 font-medium text-green-400">
            <ShieldCheck size={15} />
            No findings
          </div>
          <div className="mt-1 text-text-muted">
            The guardian did not detect canon issues in this world.
          </div>
        </div>
      )}

      {run && visibleFindings.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Guardian Findings
          </div>
          {visibleFindings.map((finding) => {
            const expanded = expandedFindingIds.has(finding.id);
            const mechanicRun = mechanicRunsByFinding[finding.id];
            const mechanicOptions = mechanicRun?.options.filter(
              (option) => option.finding_id === finding.id,
            ) ?? [];
            const mechanicError = mechanicErrorByFinding[finding.id];
            const isDismissing = dismissingFindingId === finding.id;
            const isRunningMechanic = runningMechanicFindingId === finding.id;
            return (
              <div key={finding.id} className="rounded-lg border border-border bg-surface p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{finding.title}</div>
                    <div className="text-xs text-text-muted">
                      {finding.severity} | {finding.resolution_status} | confidence {finding.confidence.toFixed(2)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => onToggleFinding(finding.id)}
                      className="rounded border border-border px-2 py-1 text-xs text-text-muted hover:bg-surface-hover"
                    >
                      {expanded ? "Collapse" : "Expand"}
                    </button>
                    <button
                      onClick={() => void onRunMechanic(finding.id)}
                      disabled={isRunningMechanic || finding.resolution_status === "dismissed"}
                      className="rounded border border-cyan-700 px-2 py-1 text-xs text-cyan-300 hover:bg-cyan-900/20 disabled:opacity-50"
                    >
                      {isRunningMechanic ? "Running..." : "Use Mechanic"}
                    </button>
                    <button
                      onClick={() => void onDismissFinding(finding.id)}
                      disabled={isDismissing || finding.resolution_status === "dismissed"}
                      className="rounded border border-red-800 px-2 py-1 text-xs text-red-300 hover:bg-red-900/20 disabled:opacity-50"
                    >
                      {isDismissing ? "Discarding..." : "Discard"}
                    </button>
                  </div>
                </div>
                {expanded && (
                  <div className="mt-2 space-y-2 text-xs text-text-muted">
                    <div>{finding.detail}</div>
                    {finding.evidence.length > 0 && (
                      <div>
                        Evidence:{" "}
                        {finding.evidence.map((ev) => `${ev.kind}:${ev.id}`).join(", ")}
                      </div>
                    )}
                    {mechanicRun && (
                      <div className="rounded border border-cyan-800 bg-cyan-900/15 p-2">
                        <div className="font-medium text-cyan-300">
                          Mechanic options ({mechanicOptions.length}) - run {mechanicRun.id}
                        </div>
                        {mechanicOptions.length === 0 ? (
                          <div className="mt-1 text-text-muted">No mechanic options returned for this finding.</div>
                        ) : (
                          <div className="mt-1 space-y-1">
                            {mechanicOptions.map((option) => (
                              <div key={option.id} className="rounded border border-border bg-panel p-2">
                                <div className="text-text">
                                  {option.action_type}
                                  {option.op_type ? ` / ${option.op_type}` : ""}
                                  {option.target_kind ? ` / ${option.target_kind}` : ""}
                                </div>
                                {option.rationale && <div className="text-text-muted">{option.rationale}</div>}
                                {option.expected_outcome && <div className="text-text-muted">Outcome: {option.expected_outcome}</div>}
                                <div className="text-text-muted">
                                  Risk: {option.risk_level} | confidence {option.confidence.toFixed(2)}
                                </div>
                                <div className="mt-2 flex items-center justify-between">
                                  <div className="text-text-muted">Status: {option.status}</div>
                                  <button
                                    onClick={() => void onRunMechanicOption(finding.id, option.id)}
                                    disabled={
                                      runningMechanicOptionId === option.id ||
                                      (option.status !== "proposed" && option.status !== "accepted")
                                    }
                                    className="rounded border border-cyan-700 px-2 py-1 text-xs text-cyan-300 hover:bg-cyan-900/20 disabled:opacity-50"
                                  >
                                    {runningMechanicOptionId === option.id ? "Running..." : "Run Now"}
                                  </button>
                                </div>
                                {option.error && (
                                  <div className="mt-1 rounded border border-red-800 bg-red-900/20 p-1 text-red-300">
                                    {option.error}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                    {mechanicError && (
                      <div className="rounded border border-red-800 bg-red-900/20 p-2 text-red-300">
                        {mechanicError}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-900/20 p-3 text-sm">
          <div className="font-medium text-red-400">Guardian error</div>
          <div className="mt-1 text-text-muted">{error}</div>
        </div>
      )}
    </div>
  );
}
