import { Handle, Position, type NodeProps } from "@xyflow/react";

type EntityNodeData = {
  label: string;
  entityType: string;
  source: "user" | "ai";
  color: string;
  focusState?: "normal" | "active" | "neighbor" | "dim";
};

export default function EntityNode({ data }: NodeProps) {
  const d = data as unknown as EntityNodeData;
  const isAI = d.source === "ai";
  const focus = d.focusState ?? "normal";
  const isActive = focus === "active";
  const isNeighbor = focus === "neighbor";
  const isDim = focus === "dim";

  return (
    <div
      className="flex flex-col items-center"
      style={{ pointerEvents: "all", opacity: isDim ? 0.28 : 1 }}
    >
      <div
        className="relative rounded-full shadow-lg"
        style={{
          width: isActive ? 22 : isNeighbor ? 18 : 16,
          height: isActive ? 22 : isNeighbor ? 18 : 16,
          backgroundColor: d.color,
          border: isAI ? "2px dashed var(--color-ai)" : `2px solid ${d.color}`,
          boxShadow: isActive
            ? `0 0 0 3px var(--color-accent), 0 0 16px ${d.color}a0`
            : isNeighbor
              ? `0 0 12px ${d.color}80`
              : `0 0 8px ${d.color}60`,
        }}
      >
        <Handle
          type="target"
          position={Position.Top}
          className="!opacity-0 !w-0 !h-0 !min-w-0 !min-h-0"
          style={{ top: "50%", left: "50%", transform: "translate(-50%, -50%)" }}
        />
        <Handle
          type="source"
          position={Position.Bottom}
          className="!opacity-0 !w-0 !h-0 !min-w-0 !min-h-0"
          style={{ top: "50%", left: "50%", transform: "translate(-50%, -50%)" }}
        />
      </div>
      <span
        className="mt-1 max-w-24 truncate text-center text-xs"
        style={{
          color: d.color,
          fontWeight: isActive ? 700 : isNeighbor ? 600 : 500,
          opacity: isDim ? 0.65 : 1,
        }}
      >
        {d.label}
      </span>
    </div>
  );
}
