import { useMemo, useCallback, useEffect, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  MarkerType,
  EdgeLabelRenderer,
  type Node,
  type Edge,
  type EdgeProps,
  type NodeMouseHandler,
} from "@xyflow/react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceX,
  forceY,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import type { Entity, Relation } from "../types.ts";
import { getNodeColor } from "../types.ts";
import EntityNode from "./EntityNode.tsx";

// Custom straight edge that shortens both ends so the arrow isn't hidden behind nodes
const NODE_RADIUS = 10; // dot radius (8) + small gap

function DirectedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  markerEnd,
  style,
  data,
}: EdgeProps) {
  const [hovered, setHovered] = useState(false);
  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return null;

  // Shorten both ends by node radius
  const ux = dx / len;
  const uy = dy / len;
  const x1 = sourceX + ux * NODE_RADIUS;
  const y1 = sourceY + uy * NODE_RADIUS;
  const x2 = targetX - ux * NODE_RADIUS;
  const y2 = targetY - uy * NODE_RADIUS;
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  const edgeData = data as { label?: string; labelColor?: string } | undefined;
  const labelColor = edgeData?.labelColor ?? "var(--color-text)";

  return (
    <>
      <path
        d={`M ${x1} ${y1} L ${x2} ${y2}`}
        fill="none"
        stroke="transparent"
        strokeWidth={14}
        className="react-flow__edge-interaction"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      <path
        id={id}
        d={`M ${x1} ${y1} L ${x2} ${y2}`}
        style={style}
        markerEnd={markerEnd as string}
        fill="none"
        className="react-flow__edge-path"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      {hovered && edgeData?.label && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan absolute rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] text-text shadow"
            style={{
              transform: `translate(-50%, -50%) translate(${midX}px, ${midY}px)`,
              color: labelColor,
              pointerEvents: "none",
              whiteSpace: "nowrap",
              zIndex: 9999,
            }}
          >
            {edgeData.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const nodeTypes = { entity: EntityNode };
const edgeTypes = { directed: DirectedEdge };

interface Props {
  entities: Entity[];
  relations: Relation[];
  activeEntityId?: string;
  onSelectEntity: (id: string) => void;
  onSelectRelation: (id: string) => void;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
}

function buildEdges(
  relations: Relation[],
  entities: Entity[],
  activeEntityId?: string,
): Edge[] {
  const entityNameById = new Map(entities.map((e) => [e.id, e.name]));
  const edges = relations.map((r) => {
    const baseColor =
      r.source === "ai" ? "var(--color-ai)" : "var(--color-text-muted)";
    const isConnected = Boolean(
      activeEntityId &&
      (r.source_entity_id === activeEntityId ||
        r.target_entity_id === activeEntityId),
    );
    const isDimmed = Boolean(activeEntityId) && !isConnected;
    const color = isConnected ? "var(--color-accent)" : baseColor;
    const sourceName = entityNameById.get(r.source_entity_id) ?? "Unknown";
    const targetName = entityNameById.get(r.target_entity_id) ?? "Unknown";
    return {
      id: r.id,
      source: r.source_entity_id,
      target: r.target_entity_id,
      style: {
        stroke: color,
        strokeWidth: isConnected ? 2.5 : 1,
        opacity: isDimmed ? 0.15 : 1,
      },
      zIndex: isConnected ? 2 : 1,
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
      type: "directed",
      data: {
        label: `${sourceName} ${r.type} ${targetName}`,
        labelColor: color,
      },
    };
  });
  if (!activeEntityId) return edges;
  // Keep active-connected edges at the end so they're rendered above dimmed ones.
  return edges.sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
}

function ForceGraph({
  entities,
  relations,
  activeEntityId,
  onSelectEntity,
  onSelectRelation,
}: Props) {
  const { fitView, setCenter } = useReactFlow();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const simulationRef = useRef<ReturnType<
    typeof forceSimulation<SimNode>
  > | null>(null);
  const simNodeMapRef = useRef<Map<string, SimNode>>(new Map());
  const rafRef = useRef<number | null>(null);
  const draggedNodeRef = useRef<string | null>(null);

  // Build edges from relations
  const builtEdges = useMemo(
    () => buildEdges(relations, entities, activeEntityId),
    [relations, entities, activeEntityId],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(builtEdges);

  // Sync edges when relations change
  useEffect(() => {
    setEdges(builtEdges);
  }, [builtEdges, setEdges]);

  // Structural key: only changes when entity IDs or relation connections change
  const structureKey = useMemo(() => {
    const eIds = entities
      .map((e) => e.id)
      .sort()
      .join(",");
    const rKeys = relations
      .map((r) => `${r.source_entity_id}-${r.target_entity_id}`)
      .sort()
      .join(",");
    return `${eIds}|${rKeys}`;
  }, [entities, relations]);

  // Run force simulation only when graph STRUCTURE changes (new/removed nodes or edges)
  useEffect(() => {
    if (simulationRef.current) simulationRef.current.stop();
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }

    if (entities.length === 0) {
      setNodes([]);
      return;
    }

    const entityDataMap = new Map(
      entities.map((e) => [
        e.id,
        {
          label: e.name,
          entityType: e.type,
          source: e.source,
          color: getNodeColor(e.type),
        },
      ]),
    );

    const simNodes: SimNode[] = entities.map((e) => ({
      id: e.id,
      x: Math.random() * 400 - 200,
      y: Math.random() * 400 - 200,
    }));

    const simNodeMap = new Map(simNodes.map((n) => [n.id, n]));
    simNodeMapRef.current = simNodeMap;

    const simLinks: SimulationLinkDatum<SimNode>[] = relations
      .filter(
        (r) =>
          simNodeMap.has(r.source_entity_id) &&
          simNodeMap.has(r.target_entity_id),
      )
      .map((r) => ({
        source: r.source_entity_id,
        target: r.target_entity_id,
      }));

    const sim = forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        forceLink<SimNode, SimulationLinkDatum<SimNode>>(simLinks)
          .id((d) => d.id)
          .distance(120)
          .strength(0.4),
      )
      .force("charge", forceManyBody().strength(-200))
      .force("x", forceX(0).strength(0.1))
      .force("y", forceY(0).strength(0.1))
      .force("collide", forceCollide(50))
      .stop();

    for (let i = 0; i < 300; i++) sim.tick();

    setNodes(
      simNodes.map((sn) => ({
        id: sn.id,
        type: "entity" as const,
        position: { x: sn.x ?? 0, y: sn.y ?? 0 },
        data: entityDataMap.get(sn.id)!,
      })),
    );

    simulationRef.current = sim;
    requestAnimationFrame(() => fitView({ duration: 300 }));

    return () => {
      sim.stop();
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structureKey, setNodes, fitView]);

  // Update node DATA (labels, colors) in place when entity metadata changes without re-layout
  useEffect(() => {
    const connectedIds = new Set<string>();
    if (activeEntityId) {
      for (const rel of relations) {
        if (rel.source_entity_id === activeEntityId)
          connectedIds.add(rel.target_entity_id);
        if (rel.target_entity_id === activeEntityId)
          connectedIds.add(rel.source_entity_id);
      }
    }
    const dataMap = new Map(
      entities.map((e) => [
        e.id,
        {
          label: e.name,
          entityType: e.type,
          source: e.source,
          color: getNodeColor(e.type),
          focusState: !activeEntityId
            ? "normal"
            : e.id === activeEntityId
              ? "active"
              : connectedIds.has(e.id)
                ? "neighbor"
                : "dim",
        },
      ]),
    );
    setNodes((prev) =>
      prev.map((node) => {
        const newData = dataMap.get(node.id);
        if (!newData) return node;
        return { ...node, data: newData };
      }),
    );
  }, [entities, relations, activeEntityId, setNodes]);

  const centerActiveNode = useCallback(
    (duration = 350) => {
      if (!activeEntityId) return;
      const activeNode = nodes.find((n) => n.id === activeEntityId);
      if (!activeNode) return;
      setCenter(activeNode.position.x, activeNode.position.y, {
        zoom: 1.25,
        duration,
      });
    },
    [activeEntityId, nodes, setCenter],
  );

  useEffect(() => {
    centerActiveNode(350);
  }, [centerActiveNode]);

  useEffect(() => {
    if (!activeEntityId) return;
    const el = containerRef.current;
    if (!el) return;

    let rafA: number | null = null;
    let rafB: number | null = null;
    const recenterAfterResize = () => {
      if (rafA !== null) cancelAnimationFrame(rafA);
      if (rafB !== null) cancelAnimationFrame(rafB);
      // Wait two frames so React Flow settles after container size changes.
      rafA = requestAnimationFrame(() => {
        rafB = requestAnimationFrame(() => centerActiveNode(200));
      });
    };

    const observer = new ResizeObserver(recenterAfterResize);
    observer.observe(el);

    return () => {
      observer.disconnect();
      if (rafA !== null) cancelAnimationFrame(rafA);
      if (rafB !== null) cancelAnimationFrame(rafB);
    };
  }, [activeEntityId, centerActiveNode]);

  useEffect(() => {
    if (!activeEntityId) return;
    const onResize = () => centerActiveNode(0);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [activeEntityId, centerActiveNode]);

  // RAF loop: sync simulation positions → React Flow (only while sim is active)
  // Uses functional setNodes to update positions in-place, skipping the dragged node
  const startSyncLoop = useCallback(() => {
    const tick = () => {
      const sim = simulationRef.current;
      if (!sim || sim.alpha() < 0.01) {
        sim?.stop();
        rafRef.current = null;
        return;
      }
      const map = simNodeMapRef.current;
      const dragId = draggedNodeRef.current;
      setNodes((prev) =>
        prev.map((node) => {
          if (node.id === dragId) return node; // Don't touch the dragged node
          const sn = map.get(node.id);
          if (!sn) return node;
          const x = sn.x ?? 0;
          const y = sn.y ?? 0;
          // Skip update if position hasn't meaningfully changed
          if (
            Math.abs(node.position.x - x) < 0.5 &&
            Math.abs(node.position.y - y) < 0.5
          )
            return node;
          return { ...node, position: { x, y } };
        }),
      );
      rafRef.current = requestAnimationFrame(tick);
    };
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(tick);
    }
  }, [setNodes]);

  // On drag: pin the node in the simulation and reheat
  const handleNodeDragStart = useCallback(
    (_: React.MouseEvent, node: Node) => {
      draggedNodeRef.current = node.id;
      const sn = simNodeMapRef.current.get(node.id);
      if (sn) {
        sn.fx = node.position.x;
        sn.fy = node.position.y;
      }
      const sim = simulationRef.current;
      if (sim) {
        // Explicitly reheat alpha so the first drag after page load updates neighbors.
        sim.alpha(0.3).alphaTarget(0.3).restart();
        startSyncLoop();
      }
    },
    [startSyncLoop],
  );

  const handleNodeDrag = useCallback((_: React.MouseEvent, node: Node) => {
    const sn = simNodeMapRef.current.get(node.id);
    if (sn) {
      sn.fx = node.position.x;
      sn.fy = node.position.y;
    }
  }, []);

  const handleNodeDragStop = useCallback((_: React.MouseEvent, node: Node) => {
    draggedNodeRef.current = null;
    const sn = simNodeMapRef.current.get(node.id);
    if (sn) {
      sn.fx = null;
      sn.fy = null;
    }
    simulationRef.current?.alphaTarget(0);
  }, []);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => onSelectEntity(node.id),
    [onSelectEntity],
  );

  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => onSelectRelation(edge.id),
    [onSelectRelation],
  );

  return (
    <div ref={containerRef} className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onNodeDragStart={handleNodeDragStart}
        onNodeDrag={handleNodeDrag}
        onNodeDragStop={handleNodeDragStop}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        minZoom={0.1}
        maxZoom={3}
      >
        <Background color="var(--color-border)" gap={24} />
        <Controls />
        <MiniMap
          nodeComponent={({ x, y, color }) => (
            <circle cx={x} cy={y} r={8} fill={color} />
          )}
          nodeColor={(n) =>
            (n.data as { color?: string }).color ?? "var(--color-node-default)"
          }
          maskColor="transparent"
          maskStrokeColor="transparent"
          maskStrokeWidth={0}
          style={{ backgroundColor: "var(--color-surface)" }}
        />
      </ReactFlow>
    </div>
  );
}

// Wrap with ReactFlowProvider so useReactFlow() works
export default function WorldGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <ForceGraph {...props} />
    </ReactFlowProvider>
  );
}
