import { useState } from "react";
import { Save, Bot, User, ArrowRight } from "lucide-react";
import type { Entity, Relation, RelationUpdate } from "../types.ts";

interface Props {
  relation: Relation;
  sourceEntity: Entity | null;
  targetEntity: Entity | null;
  onSave: (data: RelationUpdate) => void;
}

export default function RelationDetail({
  relation,
  sourceEntity,
  targetEntity,
  onSave,
}: Props) {
  const [type, setType] = useState(relation.type);
  const [weight, setWeight] = useState(String(relation.weight));
  const [context, setContext] = useState(relation.context ?? "");

  function handleSave() {
    const parsedWeight = Number(weight);
    onSave({
      type: type.trim() || relation.type,
      weight: Number.isFinite(parsedWeight) ? parsedWeight : relation.weight,
      context: context.trim() || undefined,
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {relation.source === "ai" ? (
          <span className="flex items-center gap-1 rounded-full bg-cyan-900/30 px-2 py-0.5 text-xs text-ai">
            <Bot size={12} /> AI-generated
          </span>
        ) : (
          <span className="flex items-center gap-1 rounded-full bg-purple-900/30 px-2 py-0.5 text-xs text-accent">
            <User size={12} /> User-created
          </span>
        )}
        <span className="rounded-full bg-surface-hover px-2 py-0.5 text-xs text-text-muted">
          weight {relation.weight}
        </span>
      </div>

      <div className="rounded-lg border border-border bg-bg p-3">
        <div className="text-xs font-medium uppercase text-text-muted">
          Connection
        </div>
        <div className="mt-2 flex items-center gap-2 text-sm">
          <span className="max-w-28 truncate rounded bg-panel px-2 py-1">
            {sourceEntity?.name ?? relation.source_entity_id}
          </span>
          <ArrowRight size={14} className="text-text-muted" />
          <span className="max-w-28 truncate rounded bg-panel px-2 py-1">
            {targetEntity?.name ?? relation.target_entity_id}
          </span>
        </div>
      </div>

      <Field label="Relation Type" value={type} onChange={setType} />
      <Field
        label="Weight"
        value={weight}
        onChange={setWeight}
        placeholder="Numeric weight"
      />

      <label className="block">
        <span className="text-xs font-medium uppercase text-text-muted">
          Context
        </span>
        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          rows={5}
          placeholder="Context for this relation..."
          className="mt-1 block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
        />
      </label>

      <button
        onClick={handleSave}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent py-2 font-medium text-white hover:bg-accent-hover"
      >
        <Save size={16} /> Save
      </button>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase text-text-muted">
        {label}
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
      />
    </label>
  );
}
