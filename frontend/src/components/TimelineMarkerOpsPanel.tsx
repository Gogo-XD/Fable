import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Plus, Save, Trash2 } from "lucide-react";
import { timeline as timelineApi } from "../api.ts";
import type {
  TimelineMarker,
  TimelineOperation,
  TimelineOperationCreate,
  TimelineOperationUpdate,
  TimelineTargetKind,
} from "../types.ts";

const TARGET_KINDS: TimelineTargetKind[] = ["entity", "relation", "world"];

function parsePayloadJson(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Payload must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

interface Props {
  worldId: string;
  markerId: string;
  onChanged: () => Promise<void> | void;
}

export default function TimelineMarkerOpsPanel({ worldId, markerId, onChanged }: Props) {
  const [marker, setMarker] = useState<TimelineMarker | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshMarker = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const detailed = await timelineApi.getMarker(worldId, markerId, { include_operations: true });
      setMarker(detailed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load marker operations.");
    } finally {
      setLoading(false);
    }
  }, [worldId, markerId]);

  useEffect(() => {
    void refreshMarker();
  }, [refreshMarker]);

  const operations = useMemo(
    () => [...(marker?.operations ?? [])].sort((a, b) => a.order_index - b.order_index),
    [marker],
  );

  const handleCreateOperation = useCallback(
    async (input: TimelineOperationCreate) => {
      setBusy(true);
      setError(null);
      try {
        await timelineApi.createOperation(worldId, markerId, input);
        await refreshMarker();
        await onChanged();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create operation.");
      } finally {
        setBusy(false);
      }
    },
    [worldId, markerId, onChanged, refreshMarker],
  );

  const handleUpdateOperation = useCallback(
    async (operationId: string, input: TimelineOperationUpdate) => {
      setBusy(true);
      setError(null);
      try {
        await timelineApi.updateOperation(worldId, markerId, operationId, input);
        await refreshMarker();
        await onChanged();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update operation.");
      } finally {
        setBusy(false);
      }
    },
    [worldId, markerId, onChanged, refreshMarker],
  );

  const handleDeleteOperation = useCallback(
    async (operationId: string) => {
      const ok = window.confirm("Delete this timeline operation?");
      if (!ok) return;
      setBusy(true);
      setError(null);
      try {
        await timelineApi.deleteOperation(worldId, markerId, operationId);
        await refreshMarker();
        await onChanged();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete operation.");
      } finally {
        setBusy(false);
      }
    },
    [worldId, markerId, onChanged, refreshMarker],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-text-muted">
        <Loader2 size={16} className="mr-2 animate-spin" />
        Loading marker operations...
      </div>
    );
  }

  if (!marker) {
    return <div className="text-sm text-red-400">Marker not found.</div>;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-bg p-3">
        <div className="text-xs uppercase tracking-wide text-text-muted">Active Marker</div>
        <div className="mt-1 text-sm font-semibold">{marker.title}</div>
        {marker.date_label && (
          <div className="mt-1 text-xs text-text-muted">{marker.date_label}</div>
        )}
        {marker.summary && (
          <div className="mt-2 text-xs text-text-muted">{marker.summary}</div>
        )}
      </div>

      <CreateOperationForm
        disabled={busy}
        defaultOrderIndex={operations.length}
        onCreate={handleCreateOperation}
      />

      {error && (
        <div className="rounded border border-red-900 bg-red-900/20 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="space-y-3">
        <div className="text-xs uppercase tracking-wide text-text-muted">
          Operations ({operations.length})
        </div>
        {operations.length === 0 && (
          <div className="rounded border border-border bg-bg px-3 py-2 text-sm text-text-muted">
            No operations yet.
          </div>
        )}
        {operations.map((operation) => (
          <OperationEditor
            key={`${operation.id}:${operation.updated_at}`}
            operation={operation}
            disabled={busy}
            onSave={(input) => handleUpdateOperation(operation.id, input)}
            onDelete={() => handleDeleteOperation(operation.id)}
          />
        ))}
      </div>
    </div>
  );
}

function CreateOperationForm({
  disabled,
  defaultOrderIndex,
  onCreate,
}: {
  disabled: boolean;
  defaultOrderIndex: number;
  onCreate: (input: TimelineOperationCreate) => Promise<void>;
}) {
  const [opType, setOpType] = useState("entity_patch");
  const [targetKind, setTargetKind] = useState<TimelineTargetKind>("entity");
  const [targetId, setTargetId] = useState("");
  const [orderIndex, setOrderIndex] = useState(String(defaultOrderIndex));
  const [payloadText, setPayloadText] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    setError(null);
    const parsedOrder = Number(orderIndex);
    if (!Number.isFinite(parsedOrder) || parsedOrder < 0) {
      setError("Order index must be a number >= 0.");
      return;
    }

    let payload: Record<string, unknown>;
    try {
      payload = parsePayloadJson(payloadText);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid payload JSON.");
      return;
    }

    await onCreate({
      op_type: opType.trim() || "entity_patch",
      target_kind: targetKind,
      target_id: targetId.trim() || undefined,
      order_index: Math.floor(parsedOrder),
      payload,
    });
    setTargetId("");
    setPayloadText("{}");
  }

  return (
    <div className="space-y-2 rounded-lg border border-border bg-bg p-3">
      <div className="text-xs uppercase tracking-wide text-text-muted">Add Operation</div>
      <OpFields
        opType={opType}
        targetKind={targetKind}
        targetId={targetId}
        orderIndex={orderIndex}
        payloadText={payloadText}
        onOpTypeChange={setOpType}
        onTargetKindChange={setTargetKind}
        onTargetIdChange={setTargetId}
        onOrderIndexChange={setOrderIndex}
        onPayloadTextChange={setPayloadText}
      />
      {error && <div className="text-xs text-red-300">{error}</div>}
      <button
        disabled={disabled}
        onClick={() => void handleCreate()}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
      >
        <Plus size={14} /> Add Operation
      </button>
    </div>
  );
}

function OperationEditor({
  operation,
  disabled,
  onSave,
  onDelete,
}: {
  operation: TimelineOperation;
  disabled: boolean;
  onSave: (input: TimelineOperationUpdate) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [opType, setOpType] = useState(operation.op_type);
  const [targetKind, setTargetKind] = useState<TimelineTargetKind>(operation.target_kind);
  const [targetId, setTargetId] = useState(operation.target_id ?? "");
  const [orderIndex, setOrderIndex] = useState(String(operation.order_index));
  const [payloadText, setPayloadText] = useState(
    JSON.stringify(operation.payload ?? {}, null, 2),
  );
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setError(null);
    const parsedOrder = Number(orderIndex);
    if (!Number.isFinite(parsedOrder) || parsedOrder < 0) {
      setError("Order index must be a number >= 0.");
      return;
    }

    let payload: Record<string, unknown>;
    try {
      payload = parsePayloadJson(payloadText);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid payload JSON.");
      return;
    }

    await onSave({
      op_type: opType.trim() || operation.op_type,
      target_kind: targetKind,
      target_id: targetId.trim() || undefined,
      order_index: Math.floor(parsedOrder),
      payload,
    });
  }

  return (
    <div className="space-y-2 rounded-lg border border-border bg-bg p-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-text-muted">Operation {operation.id.slice(0, 8)}</div>
        <button
          disabled={disabled}
          onClick={() => void onDelete()}
          className="rounded border border-red-800 bg-red-900/20 px-2 py-1 text-xs text-red-300 hover:bg-red-900/30 disabled:opacity-50"
        >
          <span className="inline-flex items-center gap-1">
            <Trash2 size={12} /> Delete
          </span>
        </button>
      </div>

      <OpFields
        opType={opType}
        targetKind={targetKind}
        targetId={targetId}
        orderIndex={orderIndex}
        payloadText={payloadText}
        onOpTypeChange={setOpType}
        onTargetKindChange={setTargetKind}
        onTargetIdChange={setTargetId}
        onOrderIndexChange={setOrderIndex}
        onPayloadTextChange={setPayloadText}
      />

      {error && <div className="text-xs text-red-300">{error}</div>}

      <button
        disabled={disabled}
        onClick={() => void handleSave()}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-border py-2 text-sm text-text hover:bg-surface-hover disabled:opacity-50"
      >
        <Save size={14} /> Save Operation
      </button>
    </div>
  );
}

function OpFields({
  opType,
  targetKind,
  targetId,
  orderIndex,
  payloadText,
  onOpTypeChange,
  onTargetKindChange,
  onTargetIdChange,
  onOrderIndexChange,
  onPayloadTextChange,
}: {
  opType: string;
  targetKind: TimelineTargetKind;
  targetId: string;
  orderIndex: string;
  payloadText: string;
  onOpTypeChange: (v: string) => void;
  onTargetKindChange: (v: TimelineTargetKind) => void;
  onTargetIdChange: (v: string) => void;
  onOrderIndexChange: (v: string) => void;
  onPayloadTextChange: (v: string) => void;
}) {
  return (
    <div className="space-y-2">
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-text-muted">Operation Type</span>
        <input
          value={opType}
          onChange={(event) => onOpTypeChange(event.target.value)}
          className="mt-1 block w-full rounded border border-border bg-panel px-2 py-1.5 text-sm text-text focus:border-accent focus:outline-none"
          placeholder="entity_patch"
        />
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-xs uppercase tracking-wide text-text-muted">Target Kind</span>
          <select
            value={targetKind}
            onChange={(event) => onTargetKindChange(event.target.value as TimelineTargetKind)}
            className="mt-1 block w-full rounded border border-border bg-panel px-2 py-1.5 text-sm text-text focus:border-accent focus:outline-none"
          >
            {TARGET_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-wide text-text-muted">Order Index</span>
          <input
            value={orderIndex}
            onChange={(event) => onOrderIndexChange(event.target.value)}
            className="mt-1 block w-full rounded border border-border bg-panel px-2 py-1.5 text-sm text-text focus:border-accent focus:outline-none"
            placeholder="0"
          />
        </label>
      </div>

      <label className="block">
        <span className="text-xs uppercase tracking-wide text-text-muted">Target ID</span>
        <input
          value={targetId}
          onChange={(event) => onTargetIdChange(event.target.value)}
          className="mt-1 block w-full rounded border border-border bg-panel px-2 py-1.5 text-sm text-text focus:border-accent focus:outline-none"
          placeholder="entity/relation id"
        />
      </label>

      <label className="block">
        <span className="text-xs uppercase tracking-wide text-text-muted">Payload JSON</span>
        <textarea
          value={payloadText}
          onChange={(event) => onPayloadTextChange(event.target.value)}
          rows={6}
          className="mt-1 block w-full rounded border border-border bg-panel px-2 py-1.5 font-mono text-xs text-text focus:border-accent focus:outline-none"
          placeholder='{"name":"New value"}'
        />
      </label>
    </div>
  );
}
