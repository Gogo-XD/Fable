import { useState } from "react";
import { Plus, FileText, Sparkles, Save, Loader2 } from "lucide-react";
import type {
  Note,
  NoteCreate,
  NoteUpdate,
  AnalysisResult,
  AnalyzeAllResult,
} from "../types.ts";

interface Props {
  notes: Note[];
  onCreateNote: (data: NoteCreate) => void;
  onUpdateNote: (id: string, data: NoteUpdate) => void;
  onAnalyzeNote: (id: string) => Promise<AnalysisResult>;
  onAnalyzeAllNotes: () => Promise<AnalyzeAllResult>;
}

export default function NotePanel({
  notes,
  onCreateNote,
  onUpdateNote,
  onAnalyzeNote,
  onAnalyzeAllNotes,
}: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [analyzingAll, setAnalyzingAll] = useState(false);
  const [allResult, setAllResult] = useState<AnalyzeAllResult | null>(null);

  const selected = notes.find((n) => n.id === selectedId);
  const pendingAnalyzeCount = notes.filter((n) => n.status !== "analyzed").length;

  async function handleAnalyzeAll() {
    setAnalyzingAll(true);
    setAllResult(null);
    try {
      const result = await onAnalyzeAllNotes();
      setAllResult(result);
    } finally {
      setAnalyzingAll(false);
    }
  }

  if (creating) {
    return (
      <NoteEditor
        onSave={(data) => {
          onCreateNote(data);
          setCreating(false);
        }}
        onCancel={() => setCreating(false)}
      />
    );
  }

  if (selected) {
    return (
      <NoteView
        note={selected}
        onUpdate={(data) => onUpdateNote(selected.id, data)}
        onAnalyze={() => onAnalyzeNote(selected.id)}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  return (
    <div className="space-y-2">
      <button
        onClick={() => setCreating(true)}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border py-3 text-sm text-text-muted hover:border-accent hover:text-accent"
      >
        <Plus size={16} /> New Note
      </button>
      <button
        onClick={handleAnalyzeAll}
        disabled={analyzingAll || pendingAnalyzeCount === 0}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-700 py-2 text-sm font-medium text-white hover:bg-cyan-600 disabled:opacity-50"
      >
        {analyzingAll ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
        {analyzingAll
          ? "Analyzing All..."
          : `Analyze All (${pendingAnalyzeCount} pending)`}
      </button>
      {allResult && (
        <div className="rounded-lg border border-green-800 bg-green-900/20 p-3 text-sm">
          <div className="font-medium text-green-400">Bulk analysis complete</div>
          <div className="mt-1 text-text-muted">
            {allResult.notes_analyzed} analyzed, {allResult.notes_skipped} skipped,{" "}
            {allResult.notes_failed} failed
          </div>
          <div className="mt-1 text-text-muted">
            {allResult.entities_created} entities created, {allResult.entities_updated} updated,{" "}
            {allResult.relations_created} relations created,{" "}
            {allResult.timeline_markers_created} timeline markers added
          </div>
        </div>
      )}
      {notes.map((n) => (
        <div
          key={n.id}
          onClick={() => setSelectedId(n.id)}
          className="flex cursor-pointer items-center gap-3 rounded-lg border border-border bg-surface p-3 hover:bg-surface-hover"
        >
          <FileText size={16} className="shrink-0 text-text-muted" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{n.title || "Untitled"}</div>
            <div className="truncate text-xs text-text-muted">{n.content.slice(0, 80)}</div>
          </div>
          <StatusBadge status={n.status} />
        </div>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: Note["status"] }) {
  const styles = {
    draft: "bg-yellow-900/30 text-yellow-400",
    saved: "bg-blue-900/30 text-blue-400",
    analyzed: "bg-green-900/30 text-green-400",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs ${styles[status]}`}>
      {status}
    </span>
  );
}

function NoteEditor({ initial, onSave, onCancel }: {
  initial?: { title: string; content: string };
  onSave: (data: NoteCreate) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [content, setContent] = useState(initial?.content ?? "");

  return (
    <div className="space-y-3">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Note title..."
        className="block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
      />
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={12}
        placeholder="Write your worldbuilding notes here..."
        className="block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
      />
      <div className="flex gap-2">
        <button
          onClick={() => onSave({ title: title || undefined, content })}
          disabled={!content.trim()}
          className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
        >
          <Save size={14} /> Save
        </button>
        <button
          onClick={onCancel}
          className="rounded-lg border border-border px-4 py-2 text-sm text-text-muted hover:bg-surface-hover"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function NoteView({ note, onUpdate, onAnalyze, onBack }: {
  note: Note;
  onUpdate: (data: NoteUpdate) => void;
  onAnalyze: () => Promise<AnalysisResult>;
  onBack: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(note.title ?? "");
  const [content, setContent] = useState(note.content);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  async function handleAnalyze() {
    setAnalyzing(true);
    setResult(null);
    try {
      const r = await onAnalyze();
      setResult(r);
    } finally {
      setAnalyzing(false);
    }
  }

  if (editing) {
    return (
      <div className="space-y-3">
        <button onClick={onBack} className="text-xs text-text-muted hover:text-text">&larr; Back</button>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Note title..."
          className="block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={12}
          className="block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
        />
        <div className="flex gap-2">
          <button
            onClick={() => { onUpdate({ title: title || undefined, content }); setEditing(false); }}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover"
          >
            <Save size={14} /> Save
          </button>
          <button onClick={() => setEditing(false)} className="rounded-lg border border-border px-4 py-2 text-sm text-text-muted hover:bg-surface-hover">
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-xs text-text-muted hover:text-text">&larr; Back</button>
      <div className="flex items-start justify-between">
        <h3 className="text-lg font-semibold">{note.title || "Untitled"}</h3>
        <StatusBadge status={note.status} />
      </div>
      <p className="whitespace-pre-wrap text-sm text-text-muted">{note.content}</p>
      <div className="flex gap-2">
        <button
          onClick={() => setEditing(true)}
          className="rounded-lg border border-border px-4 py-2 text-sm text-text-muted hover:bg-surface-hover"
        >
          Edit
        </button>
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-cyan-700 py-2 text-sm font-medium text-white hover:bg-cyan-600 disabled:opacity-50"
        >
          {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          {analyzing ? "Analyzing..." : "Analyze"}
        </button>
      </div>
      {result && (
        <div className="rounded-lg border border-green-800 bg-green-900/20 p-3 text-sm">
          <div className="font-medium text-green-400">Analysis complete</div>
          <div className="mt-1 text-text-muted">
            {result.entities_created} entities created, {result.entities_updated} updated, {result.relations_created} relations created, {result.timeline_markers_created} timeline markers added
          </div>
        </div>
      )}
    </div>
  );
}
