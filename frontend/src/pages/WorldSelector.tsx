import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Globe, Trash2 } from "lucide-react";
import { worlds } from "../api.ts";
import type { World } from "../types.ts";

export default function WorldSelector() {
  const [list, setList] = useState<World[]>([]);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    worlds.list().then(setList).catch(console.error);
  }, []);

  async function handleCreate() {
    if (!name.trim()) return;
    setCreating(true);
    try {
      const w = await worlds.create({ name: name.trim() });
      setList((prev) => [w, ...prev]);
      setName("");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id: string) {
    await worlds.delete(id);
    setList((prev) => prev.filter((w) => w.id !== id));
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-8">
      <div className="w-full max-w-lg space-y-8">
        <div className="text-center">
          <h1 className="text-4xl font-bold tracking-tight">Fable</h1>
          <p className="mt-2 text-text-muted">Choose a world to explore, or create a new one.</p>
        </div>

        {/* Create form */}
        <div className="flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            placeholder="New world name..."
            className="flex-1 rounded-lg border border-border bg-surface px-4 py-2 text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !name.trim()}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            <Plus size={18} /> Create
          </button>
        </div>

        {/* World list */}
        <div className="space-y-2">
          {list.map((w) => (
            <div
              key={w.id}
              className="flex cursor-pointer items-center justify-between rounded-lg border border-border bg-surface p-4 transition hover:bg-surface-hover"
              onClick={() => navigate(`/world/${w.id}`)}
            >
              <div className="flex items-center gap-3">
                <Globe size={20} className="text-accent" />
                <div>
                  <div className="font-medium">{w.name}</div>
                  {w.description && (
                    <div className="text-sm text-text-muted">{w.description}</div>
                  )}
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(w.id);
                }}
                className="rounded p-1 text-text-muted hover:bg-red-900/30 hover:text-red-400"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          {list.length === 0 && (
            <p className="text-center text-text-muted">No worlds yet. Create one above!</p>
          )}
        </div>
      </div>
    </div>
  );
}
