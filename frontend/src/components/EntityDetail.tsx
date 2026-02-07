import { useState } from "react";
import { Save, Bot, User, Trash2 } from "lucide-react";
import type { Entity, EntityUpdate } from "../types.ts";
import { getNodeColor } from "../types.ts";

interface Props {
  entity: Entity;
  onSave: (data: EntityUpdate) => void;
  onDelete: () => void;
}

export default function EntityDetail({ entity, onSave, onDelete }: Props) {
  const [name, setName] = useState(entity.name);
  const [type, setType] = useState(entity.type);
  const [subtype, setSubtype] = useState(entity.subtype ?? "");
  const [aliases, setAliases] = useState(entity.aliases.join(", "));
  const [summary, setSummary] = useState(entity.summary ?? "");
  const [context, setContext] = useState(entity.context ?? "");
  const [tags, setTags] = useState(entity.tags.join(", "));

  function handleSave() {
    onSave({
      name,
      type,
      subtype: subtype || undefined,
      aliases: aliases.split(",").map((s) => s.trim()).filter(Boolean),
      summary: summary || undefined,
      context: context || undefined,
      tags: tags.split(",").map((s) => s.trim()).filter(Boolean),
    });
  }

  const color = getNodeColor(entity.type);

  return (
    <div className="space-y-4">
      {/* Source badge */}
      <div className="flex items-center gap-2">
        {entity.source === "ai" ? (
          <span className="flex items-center gap-1 rounded-full bg-cyan-900/30 px-2 py-0.5 text-xs text-ai">
            <Bot size={12} /> AI-generated
          </span>
        ) : (
          <span className="flex items-center gap-1 rounded-full bg-purple-900/30 px-2 py-0.5 text-xs text-accent">
            <User size={12} /> User-created
          </span>
        )}
        <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ color, backgroundColor: `${color}20` }}>
          {entity.type}
        </span>
      </div>

      <Field label="Name" value={name} onChange={setName} />
      <Field label="Type" value={type} onChange={setType} />
      <Field label="Subtype" value={subtype} onChange={setSubtype} placeholder="Optional" />
      <Field label="Aliases" value={aliases} onChange={setAliases} placeholder="Comma-separated" />
      <Field label="Summary" value={summary} onChange={setSummary} placeholder="One-liner description" />
      <Field label="Tags" value={tags} onChange={setTags} placeholder="Comma-separated" />

      <label className="block">
        <span className="text-xs font-medium uppercase text-text-muted">Context</span>
        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          rows={5}
          placeholder="Detailed information..."
          className="mt-1 block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
        />
      </label>

      <button
        onClick={handleSave}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent py-2 font-medium text-white hover:bg-accent-hover"
      >
        <Save size={16} /> Save
      </button>
      <button
        onClick={onDelete}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-red-500/60 bg-red-950/20 py-2 font-medium text-red-300 hover:bg-red-950/30"
      >
        <Trash2 size={16} /> Delete Entity
      </button>
    </div>
  );
}

function Field({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase text-text-muted">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
      />
    </label>
  );
}
