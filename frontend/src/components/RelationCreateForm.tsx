import { useState } from "react";
import { Plus } from "lucide-react";
import type { Entity, RelationCreate } from "../types.ts";

interface Props {
  entities: Entity[];
  onSubmit: (data: RelationCreate) => void;
}

export default function RelationCreateForm({ entities, onSubmit }: Props) {
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [type, setType] = useState("related_to");
  const [context, setContext] = useState("");

  function handleSubmit() {
    if (!sourceId || !targetId || !type.trim()) return;
    onSubmit({
      source_entity_id: sourceId,
      target_entity_id: targetId,
      type: type.trim(),
      context: context || undefined,
    });
    setContext("");
    setType("related_to");
  }

  return (
    <div className="space-y-3">
      <label className="block">
        <span className="text-xs font-medium uppercase text-text-muted">Source Entity</span>
        <select
          value={sourceId}
          onChange={(e) => setSourceId(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
        >
          <option value="">Select...</option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>{e.name} [{e.type}]</option>
          ))}
        </select>
      </label>

      <label className="block">
        <span className="text-xs font-medium uppercase text-text-muted">Target Entity</span>
        <select
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
        >
          <option value="">Select...</option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>{e.name} [{e.type}]</option>
          ))}
        </select>
      </label>

      <label className="block">
        <span className="text-xs font-medium uppercase text-text-muted">Relation Type</span>
        <input
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="mt-1 block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
        />
      </label>

      <label className="block">
        <span className="text-xs font-medium uppercase text-text-muted">Context</span>
        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          rows={3}
          placeholder="Describe this relation..."
          className="mt-1 block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
        />
      </label>

      <button
        onClick={handleSubmit}
        disabled={!sourceId || !targetId || !type.trim()}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent py-2 font-medium text-white hover:bg-accent-hover disabled:opacity-50"
      >
        <Plus size={16} /> Create Relation
      </button>
    </div>
  );
}
