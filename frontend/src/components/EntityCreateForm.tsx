import { useState } from "react";
import { Plus } from "lucide-react";
import type { EntityCreate } from "../types.ts";

interface Props {
  onSubmit: (data: EntityCreate) => void;
}

export default function EntityCreateForm({ onSubmit }: Props) {
  const [name, setName] = useState("");
  const [type, setType] = useState("character");
  const [subtype, setSubtype] = useState("");
  const [aliases, setAliases] = useState("");
  const [summary, setSummary] = useState("");
  const [tags, setTags] = useState("");

  function handleSubmit() {
    if (!name.trim()) return;
    onSubmit({
      name: name.trim(),
      type,
      subtype: subtype || undefined,
      aliases: aliases
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      summary: summary || undefined,
      tags: tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    });
    setName("");
    setSubtype("");
    setAliases("");
    setSummary("");
    setTags("");
  }

  return (
    <div className="space-y-3">
      <Field label="Name" value={name} onChange={setName} />
      <Field label="Type" value={type} onChange={setType} />
      <Field
        label="Subtype"
        value={subtype}
        onChange={setSubtype}
        placeholder="Optional"
      />
      <Field
        label="Aliases"
        value={aliases}
        onChange={setAliases}
        placeholder="Comma-separated"
      />
      <Field
        label="Summary"
        value={summary}
        onChange={setSummary}
        placeholder="One-liner"
      />
      <Field
        label="Tags"
        value={tags}
        onChange={setTags}
        placeholder="Comma-separated"
      />

      <button
        onClick={handleSubmit}
        disabled={!name.trim()}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent py-2 font-medium text-white hover:bg-accent-hover disabled:opacity-50"
      >
        <Plus size={16} /> Create Entity
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
