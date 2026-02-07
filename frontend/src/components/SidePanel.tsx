import { X } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export default function SidePanel({ title, onClose, children }: Props) {
  return (
    <div className="flex h-full w-96 flex-col border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="font-semibold">{title}</h2>
        <button onClick={onClose} className="rounded p-1 hover:bg-surface-hover">
          <X size={18} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">{children}</div>
    </div>
  );
}
