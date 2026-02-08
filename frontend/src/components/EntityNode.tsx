import { Handle, Position, type NodeProps } from "@xyflow/react";

type EntityNodeData = {
  label: string;
  entityType: string;
  source: "user" | "ai";
  color: string;
  status?: string;
  existsAtMarker?: boolean;
  focusState?: "normal" | "active" | "neighbor" | "dim";
};

export default function EntityNode({ data }: NodeProps) {
  const d = data as unknown as EntityNodeData;
  const isAI = d.source === "ai";
  const focus = d.focusState ?? "normal";
  const isActive = focus === "active";
  const isNeighbor = focus === "neighbor";
  const isDim = focus === "dim";
  const existsAtMarker = d.existsAtMarker !== false;
  const nodeColor = existsAtMarker ? d.color : "var(--color-text-muted)";
  const borderColor = existsAtMarker ? d.color : "var(--color-border)";

  return (
    <div
      className="flex flex-col items-center"
      style={{
        pointerEvents: "all",
        opacity: !existsAtMarker ? 0.42 : isDim ? 0.28 : 1,
        transition: "opacity 220ms ease",
      }}
    >
      <div
        className="relative rounded-full shadow-lg"
        style={{
          width: isActive ? 22 : isNeighbor ? 18 : 16,
          height: isActive ? 22 : isNeighbor ? 18 : 16,
          backgroundColor: nodeColor,
          border: !existsAtMarker
            ? `2px solid ${borderColor}`
            : isAI
              ? "2px dashed var(--color-ai)"
              : `2px solid ${borderColor}`,
          boxShadow: !existsAtMarker
            ? `0 0 8px ${borderColor}66`
            : isActive
              ? `0 0 0 3px var(--color-accent), 0 0 16px ${nodeColor}a0`
              : isNeighbor
                ? `0 0 12px ${nodeColor}80`
                : `0 0 8px ${nodeColor}60`,
          transition:
            "width 180ms ease, height 180ms ease, background-color 220ms ease, border-color 220ms ease, box-shadow 220ms ease",
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
          color: nodeColor,
          fontWeight: isActive ? 700 : isNeighbor ? 600 : 500,
          opacity: !existsAtMarker ? 0.7 : isDim ? 0.65 : 1,
          transition: "color 220ms ease, opacity 220ms ease",
        }}
      >
        {d.label}
      </span>
    </div>
  );
}
