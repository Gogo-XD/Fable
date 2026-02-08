import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type SyntheticEvent,
} from "react";
import type { TimelineMarker } from "../types.ts";

type TimelineOption = {
  id: string;
  label: string;
  sortKey: number;
  globalRatio: number;
};

type MarkerCluster = {
  key: string;
  markerIds: string[];
  labels: string[];
  leftPct: number;
  active: boolean;
  count: number;
};

const ZOOM_LEVELS = [1, 1.5, 2, 3, 4, 6, 8, 12];

function sortedPlacedMarkers(markers: TimelineMarker[]): TimelineMarker[] {
  return markers
    .filter((marker) => marker.placement_status === "placed")
    .sort(
      (a, b) =>
        a.sort_key - b.sort_key ||
        a.created_at.localeCompare(b.created_at) ||
        a.id.localeCompare(b.id),
    );
}

function markerLabel(marker: TimelineMarker): string {
  return marker.date_label ? `${marker.date_label} - ${marker.title}` : marker.title;
}

function absorbEvent(event: SyntheticEvent) {
  event.stopPropagation();
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function shortenLabel(label: string, maxLength = 18): string {
  if (label.length <= maxLength) return label;
  return `${label.slice(0, maxLength - 1)}...`;
}

function nextZoomLevel(current: number, direction: 1 | -1): number {
  const sorted = [...ZOOM_LEVELS].sort((a, b) => a - b);
  if (direction > 0) {
    return sorted.find((value) => value > current) ?? sorted[sorted.length - 1];
  }
  const reversed = [...sorted].reverse();
  return reversed.find((value) => value < current) ?? sorted[0];
}

export default function TimelineStrip({
  markers,
  activeMarkerId,
  onSelectMarker,
  onOpenActiveMarkerOps,
  onRepositionMarker,
}: {
  markers: TimelineMarker[];
  activeMarkerId: string;
  onSelectMarker: (markerId: string) => void;
  onOpenActiveMarkerOps?: (markerId: string) => void;
  onRepositionMarker?: (
    markerId: string,
    newSortKey: number,
    placementStatus?: "placed" | "unplaced",
  ) => Promise<void> | void;
}) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const liveSelectedMarkerIdRef = useRef(activeMarkerId);
  const dragStartRatioRef = useRef<number | null>(null);
  const markerDragMovedRef = useRef(false);
  const ignoreClickAfterDragRef = useRef<string | null>(null);
  const [dragRatio, setDragRatio] = useState<number | null>(null);
  const [isSliding, setIsSliding] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [draggingMarkerId, setDraggingMarkerId] = useState<string | null>(null);
  const [draggingMarkerRatio, setDraggingMarkerRatio] = useState<number | null>(null);
  const [isRepositioning, setIsRepositioning] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [viewCenterRatio, setViewCenterRatio] = useState(0.5);
  const [trackWidth, setTrackWidth] = useState(0);

  const placedMarkers = useMemo(
    () => sortedPlacedMarkers(markers),
    [markers],
  );
  const unplacedMarkers = useMemo(
    () => markers.filter((marker) => marker.placement_status !== "placed"),
    [markers],
  );
  const activeMarker = useMemo(
    () => markers.find((marker) => marker.id === activeMarkerId) ?? null,
    [markers, activeMarkerId],
  );
  const markerById = useMemo(
    () => new Map(markers.map((marker) => [marker.id, marker])),
    [markers],
  );

  const globalRatioById = useMemo(() => {
    const map = new Map<string, number>();
    if (placedMarkers.length <= 0) return map;

    const minSortKey = placedMarkers[0].sort_key;
    const maxSortKey = placedMarkers[placedMarkers.length - 1].sort_key;
    const span = maxSortKey - minSortKey;

    placedMarkers.forEach((marker, index) => {
      const ratio =
        span > 0
          ? (marker.sort_key - minSortKey) / span
          : placedMarkers.length <= 1
            ? 0.5
            : index / Math.max(placedMarkers.length - 1, 1);
      map.set(marker.id, clamp(ratio, 0, 1));
    });
    return map;
  }, [placedMarkers]);

  const sliderOptions = useMemo<TimelineOption[]>(
    () =>
      placedMarkers.map((marker) => ({
        id: marker.id,
        label: markerLabel(marker),
        sortKey: marker.sort_key,
        globalRatio: globalRatioById.get(marker.id) ?? 0,
      })),
    [globalRatioById, placedMarkers],
  );

  const optionById = useMemo(
    () => new Map(sliderOptions.map((option) => [option.id, option])),
    [sliderOptions],
  );

  const activeIndex = useMemo(() => {
    const foundIndex = sliderOptions.findIndex((option) => option.id === activeMarkerId);
    return foundIndex >= 0 ? foundIndex : sliderOptions.length > 0 ? 0 : -1;
  }, [sliderOptions, activeMarkerId]);

  const indexCount = sliderOptions.length;
  const maxIndex = Math.max(indexCount - 1, 0);

  const activePlacedMarkerGlobalRatio = useMemo(() => {
    if (!activeMarker || activeMarker.placement_status !== "placed") return null;
    return globalRatioById.get(activeMarker.id) ?? null;
  }, [activeMarker, globalRatioById]);

  const viewWidthRatio = 1 / zoomLevel;
  const maxViewStart = Math.max(1 - viewWidthRatio, 0);
  const viewStartRatio = clamp(viewCenterRatio - viewWidthRatio / 2, 0, maxViewStart);

  const displayToGlobalRatio = useCallback(
    (displayRatio: number) =>
      clamp(viewStartRatio + clamp(displayRatio, 0, 1) * viewWidthRatio, 0, 1),
    [viewStartRatio, viewWidthRatio],
  );

  const globalToDisplayRatio = useCallback(
    (globalRatio: number) => {
      if (viewWidthRatio >= 1) return clamp(globalRatio, 0, 1);
      return clamp((globalRatio - viewStartRatio) / viewWidthRatio, 0, 1);
    },
    [viewStartRatio, viewWidthRatio],
  );

  const nearestMarkerIdForDisplayRatio = useCallback(
    (displayRatio: number): string | null => {
      if (sliderOptions.length <= 0) return null;
      const targetGlobalRatio = displayToGlobalRatio(displayRatio);
      let best = sliderOptions[0];
      let bestDistance = Math.abs(best.globalRatio - targetGlobalRatio);

      for (let i = 1; i < sliderOptions.length; i += 1) {
        const candidate = sliderOptions[i];
        const distance = Math.abs(candidate.globalRatio - targetGlobalRatio);
        if (
          distance < bestDistance ||
          (distance === bestDistance && candidate.sortKey < best.sortKey)
        ) {
          best = candidate;
          bestDistance = distance;
        }
      }

      return best.id;
    },
    [displayToGlobalRatio, sliderOptions],
  );

  const activeDisplayRatio =
    activePlacedMarkerGlobalRatio === null ? 0 : globalToDisplayRatio(activePlacedMarkerGlobalRatio);
  const clampedDragRatio =
    dragRatio === null ? activeDisplayRatio : Math.min(Math.max(dragRatio, 0), 1);
  const nearestMarkerId = nearestMarkerIdForDisplayRatio(clampedDragRatio);
  const nearestIndex = nearestMarkerId
    ? sliderOptions.findIndex((option) => option.id === nearestMarkerId)
    : 0;
  const sliderSelection =
    (nearestMarkerId ? optionById.get(nearestMarkerId) : null) ?? sliderOptions[0] ?? null;

  const selectedLabel =
    activeMarker && activeMarker.placement_status !== "placed" && !isSliding
      ? markerLabel(activeMarker)
      : sliderSelection?.label ?? (placedMarkers.length > 0 ? "Select marker" : "No placed markers");

  const draggingMarker = useMemo(
    () => (draggingMarkerId ? markerById.get(draggingMarkerId) ?? null : null),
    [draggingMarkerId, markerById],
  );

  const draggingUnplacedOnTrack = Boolean(
    isEditMode &&
      draggingMarker &&
      draggingMarker.placement_status !== "placed" &&
      draggingMarkerRatio !== null,
  );

  const dragPreview = useMemo(() => {
    if (!isEditMode || draggingMarkerRatio === null || !draggingMarkerId) return null;
    const placedIds = sliderOptions.map((option) => option.id);
    const dragMarker = markerById.get(draggingMarkerId);
    if (!dragMarker) return null;

    const isPlacedDrag = dragMarker.placement_status === "placed";
    if (isPlacedDrag) {
      const remaining = placedIds.filter((id) => id !== draggingMarkerId);
      const insertionIndex = clamp(
        Math.round(draggingMarkerRatio * remaining.length),
        0,
        remaining.length,
      );
      const previewOrder = [
        ...remaining.slice(0, insertionIndex),
        draggingMarkerId,
        ...remaining.slice(insertionIndex),
      ];
      const indexById = new Map(previewOrder.map((id, index) => [id, index]));
      return {
        indexById,
        maxIndex: Math.max(previewOrder.length - 1, 0),
        isPlacedDrag: true,
      };
    }

    const insertionIndex = clamp(
      Math.round(draggingMarkerRatio * placedIds.length),
      0,
      placedIds.length,
    );
    const indexById = new Map<string, number>();
    placedIds.forEach((id, index) => {
      indexById.set(id, index < insertionIndex ? index : index + 1);
    });
    return {
      indexById,
      maxIndex: placedIds.length,
      isPlacedDrag: false,
    };
  }, [draggingMarkerId, draggingMarkerRatio, isEditMode, markerById, sliderOptions]);

  const markerClusters = useMemo<MarkerCluster[]>(() => {
    if (isEditMode || sliderOptions.length <= 0) return [];

    type VisibleOption = TimelineOption & { displayRatio: number };

    const visible: VisibleOption[] = sliderOptions
      .filter((option) => {
        if (viewWidthRatio >= 1) return true;
        return (
          option.globalRatio >= viewStartRatio - 0.000001 &&
          option.globalRatio <= viewStartRatio + viewWidthRatio + 0.000001
        );
      })
      .map((option) => ({
        ...option,
        displayRatio: globalToDisplayRatio(option.globalRatio),
      }))
      .sort(
        (a, b) =>
          a.displayRatio - b.displayRatio || a.sortKey - b.sortKey || a.id.localeCompare(b.id),
      );

    if (visible.length <= 0) return [];

    const minimumSeparationPx = 20;
    const minimumGapRatio = trackWidth > 0 ? minimumSeparationPx / trackWidth : 0.03;

    const groups: VisibleOption[][] = [];
    for (const option of visible) {
      const lastGroup = groups[groups.length - 1];
      if (!lastGroup) {
        groups.push([option]);
        continue;
      }
      const lastInGroup = lastGroup[lastGroup.length - 1];
      if (option.displayRatio - lastInGroup.displayRatio <= minimumGapRatio) {
        lastGroup.push(option);
      } else {
        groups.push([option]);
      }
    }

    return groups.map((group, index) => {
      const markerIds = group.map((item) => item.id);
      const labels = group.map((item) => item.label);
      const averageDisplayRatio =
        group.reduce((sum, item) => sum + item.displayRatio, 0) / Math.max(group.length, 1);
      return {
        key: `${group[0].id}-${group[group.length - 1].id}-${group.length}-${index}`,
        markerIds,
        labels,
        leftPct: clamp(averageDisplayRatio, 0, 1) * 100,
        active: markerIds.includes(activeMarkerId),
        count: markerIds.length,
      };
    });
  }, [
    activeMarkerId,
    globalToDisplayRatio,
    isEditMode,
    sliderOptions,
    trackWidth,
    viewStartRatio,
    viewWidthRatio,
  ]);

  useEffect(() => {
    if (!isSliding) {
      liveSelectedMarkerIdRef.current = activeMarkerId;
    }
  }, [activeMarkerId, isSliding]);

  useEffect(() => {
    if (isEditMode || isSliding) return;
    if (activePlacedMarkerGlobalRatio !== null) {
      setViewCenterRatio(activePlacedMarkerGlobalRatio);
    }
  }, [activePlacedMarkerGlobalRatio, isEditMode, isSliding]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    const updateTrackWidth = () => {
      setTrackWidth(track.getBoundingClientRect().width);
    };

    updateTrackWidth();

    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(() => {
        updateTrackWidth();
      });
      observer.observe(track);
      return () => observer.disconnect();
    }

    window.addEventListener("resize", updateTrackWidth);
    return () => window.removeEventListener("resize", updateTrackWidth);
  }, []);

  const commitMarkerId = useCallback(
    (markerId: string | null) => {
      if (!markerId) return;
      if (markerId === liveSelectedMarkerIdRef.current) return;
      liveSelectedMarkerIdRef.current = markerId;
      onSelectMarker(markerId);
    },
    [onSelectMarker],
  );

  const commitIndex = useCallback(
    (index: number) => {
      const option = sliderOptions[index] ?? sliderOptions[0];
      commitMarkerId(option?.id ?? null);
    },
    [commitMarkerId, sliderOptions],
  );

  const commitNearestAtRatio = useCallback(
    (ratio: number) => {
      commitMarkerId(nearestMarkerIdForDisplayRatio(ratio));
    },
    [commitMarkerId, nearestMarkerIdForDisplayRatio],
  );

  const updateRatioFromClientX = useCallback((clientX: number): number | null => {
    const track = trackRef.current;
    if (!track) return null;
    const rect = track.getBoundingClientRect();
    if (rect.width <= 0) return null;
    const ratio = (clientX - rect.left) / rect.width;
    const clampedRatio = Math.min(Math.max(ratio, 0), 1);
    setDragRatio(clampedRatio);
    return clampedRatio;
  }, []);

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    absorbEvent(event);
    if (isEditMode) return;
    if (indexCount <= 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setIsSliding(true);
    const ratio = updateRatioFromClientX(event.clientX);
    if (ratio !== null) {
      commitNearestAtRatio(ratio);
    }
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    absorbEvent(event);
    if (isEditMode) return;
    if (!isSliding) return;
    const ratio = updateRatioFromClientX(event.clientX);
    if (ratio !== null) {
      commitNearestAtRatio(ratio);
    }
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    absorbEvent(event);
    if (isEditMode) return;
    if (!isSliding) return;
    const ratio = updateRatioFromClientX(event.clientX);
    if (ratio !== null) {
      commitNearestAtRatio(ratio);
    } else {
      commitIndex(Math.max(nearestIndex, 0));
    }
    setIsSliding(false);
    setDragRatio(null);
  };

  const handlePointerCancel = (event: ReactPointerEvent<HTMLDivElement>) => {
    absorbEvent(event);
    if (isEditMode) return;
    setIsSliding(false);
    setDragRatio(null);
  };

  const handleTrackKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    absorbEvent(event);
    if (maxIndex <= 0) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      commitIndex(Math.max(activeIndex - 1, 0));
      return;
    }
    if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      commitIndex(Math.min(activeIndex + 1, maxIndex));
      return;
    }
    if (event.key === "Home") {
      commitIndex(0);
      return;
    }
    if (event.key === "End") {
      commitIndex(maxIndex);
    }
  };

  const markerSortKeyForDrop = useCallback(
    (markerId: string, dropRatio: number): number | null => {
      const remaining = placedMarkers.filter((marker) => marker.id !== markerId);
      const insertionIndex = clamp(
        Math.round(dropRatio * remaining.length),
        0,
        remaining.length,
      );
      const prev = insertionIndex > 0 ? remaining[insertionIndex - 1] : null;
      const next = insertionIndex < remaining.length ? remaining[insertionIndex] : null;
      if (prev && next) return (prev.sort_key + next.sort_key) / 2;
      if (prev) return prev.sort_key + 1;
      if (next) return next.sort_key - 1;
      return 0;
    },
    [placedMarkers],
  );

  const handleMarkerPointerDown = (event: ReactPointerEvent<HTMLButtonElement>, markerId: string) => {
    if (!isEditMode || !onRepositionMarker || isRepositioning) return;
    absorbEvent(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    const ratio = updateRatioFromClientX(event.clientX);
    dragStartRatioRef.current = ratio;
    markerDragMovedRef.current = false;
    setDraggingMarkerId(markerId);
    setDraggingMarkerRatio(ratio);
  };

  const handleMarkerPointerMove = (event: ReactPointerEvent<HTMLButtonElement>, markerId: string) => {
    if (!isEditMode || draggingMarkerId !== markerId) return;
    absorbEvent(event);
    const ratio = updateRatioFromClientX(event.clientX);
    if (ratio === null) return;
    setDraggingMarkerRatio(ratio);
    const start = dragStartRatioRef.current;
    if (start !== null && Math.abs(ratio - start) > 0.01) {
      markerDragMovedRef.current = true;
    }
  };

  const finishMarkerDrag = useCallback(
    async (clientX: number | null) => {
      if (!isEditMode || !onRepositionMarker || !draggingMarkerId) return;

      let dropRatio = draggingMarkerRatio;
      if (clientX !== null) {
        dropRatio = updateRatioFromClientX(clientX);
      }
      const resolvedDropRatio = clamp(dropRatio ?? 0, 0, 1);
      const draggedMarkerId = draggingMarkerId;
      const moved = markerDragMovedRef.current;

      setDraggingMarkerId(null);
      setDraggingMarkerRatio(null);
      dragStartRatioRef.current = null;
      markerDragMovedRef.current = false;

      if (!moved) {
        onSelectMarker(draggedMarkerId);
        return;
      }

      const newSortKey = markerSortKeyForDrop(draggedMarkerId, resolvedDropRatio);
      if (newSortKey === null) return;
      ignoreClickAfterDragRef.current = draggedMarkerId;

      setIsRepositioning(true);
      try {
        await onRepositionMarker(draggedMarkerId, newSortKey, "placed");
      } finally {
        setIsRepositioning(false);
      }
    },
    [
      draggingMarkerId,
      draggingMarkerRatio,
      isEditMode,
      markerSortKeyForDrop,
      onRepositionMarker,
      onSelectMarker,
      updateRatioFromClientX,
    ],
  );

  const handleMarkerPointerUp = (
    event: ReactPointerEvent<HTMLButtonElement>,
    markerId: string,
  ) => {
    if (!isEditMode || draggingMarkerId !== markerId) return;
    absorbEvent(event);
    void finishMarkerDrag(event.clientX);
  };

  const handleMarkerPointerCancel = (
    event: ReactPointerEvent<HTMLButtonElement>,
    markerId: string,
  ) => {
    if (!isEditMode || draggingMarkerId !== markerId) return;
    absorbEvent(event);
    void finishMarkerDrag(null);
  };

  const handleClusterClick = useCallback(
    (cluster: MarkerCluster) => {
      if (cluster.markerIds.length <= 0) return;
      const activeClusterIndex = cluster.markerIds.indexOf(activeMarkerId);
      const nextMarkerId =
        activeClusterIndex >= 0
          ? cluster.markerIds[(activeClusterIndex + 1) % cluster.markerIds.length]
          : cluster.markerIds[0];
      commitMarkerId(nextMarkerId);
    },
    [activeMarkerId, commitMarkerId],
  );

  const showTicks = sliderOptions.length > 1;
  const indexToLeftPct = useCallback(
    (index: number) => (maxIndex <= 0 ? 50 : (index / maxIndex) * 100),
    [maxIndex],
  );

  const previewIndexToLeftPct = useCallback(
    (index: number, previewMaxIndex: number) =>
      previewMaxIndex <= 0 ? 50 : (index / previewMaxIndex) * 100,
    [],
  );

  const canZoomIn = !isEditMode && zoomLevel < ZOOM_LEVELS[ZOOM_LEVELS.length - 1];
  const canZoomOut = !isEditMode && zoomLevel > ZOOM_LEVELS[0];

  return (
    <div
      className="pointer-events-auto rounded-xl bg-transparent px-3 py-2 text-text [text-shadow:0_1px_1px_rgba(0,0,0,0.8)]"
      onMouseDown={absorbEvent}
      onPointerDown={absorbEvent}
    >
      <div className="mb-1 flex items-center justify-between gap-3 text-[11px]">
        <span className="font-medium truncate">
          {isEditMode
            ? isRepositioning
              ? "Updating timeline order..."
              : draggingMarkerId
                ? "Drag marker to reorder"
                : "Edit Timeline mode"
            : isSliding
              ? `Scrubbing: ${selectedLabel}`
              : selectedLabel}
        </span>
        <div className="flex shrink-0 items-center gap-2">
          {!isEditMode && (
            <>
              <button
                onMouseDown={absorbEvent}
                onPointerDown={absorbEvent}
                onClick={(event) => {
                  absorbEvent(event);
                  setZoomLevel((prev) => nextZoomLevel(prev, -1));
                }}
                disabled={!canZoomOut}
                className="rounded border border-[#6d54a2] bg-[#251c40] px-2 py-0.5 text-text hover:bg-[#332655] disabled:cursor-not-allowed disabled:opacity-50"
                title="Zoom out"
              >
                -
              </button>
              <button
                onMouseDown={absorbEvent}
                onPointerDown={absorbEvent}
                onClick={(event) => {
                  absorbEvent(event);
                  setZoomLevel(1);
                  if (activePlacedMarkerGlobalRatio !== null) {
                    setViewCenterRatio(activePlacedMarkerGlobalRatio);
                  }
                }}
                className="rounded border border-[#6d54a2] bg-[#251c40] px-2 py-0.5 text-text hover:bg-[#332655]"
                title="Reset zoom"
              >
                {zoomLevel.toFixed(1)}x
              </button>
              <button
                onMouseDown={absorbEvent}
                onPointerDown={absorbEvent}
                onClick={(event) => {
                  absorbEvent(event);
                  setZoomLevel((prev) => nextZoomLevel(prev, 1));
                }}
                disabled={!canZoomIn}
                className="rounded border border-[#6d54a2] bg-[#251c40] px-2 py-0.5 text-text hover:bg-[#332655] disabled:cursor-not-allowed disabled:opacity-50"
                title="Zoom in"
              >
                +
              </button>
            </>
          )}
          <button
            onMouseDown={absorbEvent}
            onPointerDown={absorbEvent}
            onClick={(event) => {
              absorbEvent(event);
              setIsEditMode((prev) => {
                const next = !prev;
                if (next) {
                  setZoomLevel(1);
                }
                return next;
              });
              setDraggingMarkerId(null);
              setDraggingMarkerRatio(null);
              setIsSliding(false);
              setDragRatio(null);
            }}
            className={`rounded border px-2 py-0.5 ${
              isEditMode
                ? "border-accent bg-[#2b1f49] text-accent"
                : "border-[#6d54a2] bg-[#251c40] text-text hover:bg-[#332655]"
            }`}
            title="Toggle timeline edit mode"
          >
            {isEditMode ? "Done" : "Edit Timeline"}
          </button>
          <span className="text-text-muted">
            Timeline: {placedMarkers.length} placed
            {unplacedMarkers.length > 0 ? `, ${unplacedMarkers.length} unplaced` : ""}
          </span>
          {activeMarkerId && onOpenActiveMarkerOps && (
            <button
              onMouseDown={absorbEvent}
              onPointerDown={absorbEvent}
              onClick={(event) => {
                absorbEvent(event);
                onOpenActiveMarkerOps(activeMarkerId);
              }}
              className="rounded border border-[#6d54a2] bg-[#251c40] px-2 py-0.5 text-text hover:bg-[#332655]"
              title="Edit timeline marker operations"
            >
              Operations
            </button>
          )}
        </div>
      </div>

      <div
        ref={trackRef}
        role="slider"
        tabIndex={0}
        aria-label="Timeline selector"
        aria-valuemin={0}
        aria-valuemax={maxIndex}
        aria-valuenow={isSliding ? Math.max(nearestIndex, 0) : Math.max(activeIndex, 0)}
        className={`relative select-none touch-none outline-none ${
          isEditMode ? "h-12" : "h-7"
        } ${
          isEditMode ? "cursor-default" : "cursor-ew-resize"
        }`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onKeyDown={handleTrackKeyDown}
      >
        <div className="absolute left-0 right-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-[#55407f]" />

        {isEditMode &&
          (showTicks || isEditMode) &&
          sliderOptions.map((option, index) => {
            let leftPct = indexToLeftPct(index);
            if (dragPreview) {
              if (
                dragPreview.isPlacedDrag &&
                draggingMarkerId === option.id &&
                draggingMarkerRatio !== null
              ) {
                leftPct = draggingMarkerRatio * 100;
              } else {
                const previewIndex = dragPreview.indexById.get(option.id);
                if (previewIndex !== undefined) {
                  leftPct = previewIndexToLeftPct(previewIndex, dragPreview.maxIndex);
                }
              }
            }
            const active = option.id === activeMarkerId;
            return (
              <button
                key={`tick-${option.id}`}
                type="button"
                className={`absolute top-1/2 block h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border ${
                  active ? "border-accent bg-accent" : "border-[#6d54a2] bg-[#2b1f49]"
                } cursor-grab pointer-events-auto`}
                style={{ left: `${leftPct}%` }}
                title={option.label}
                aria-label={`Timeline marker ${option.label}`}
                onPointerDown={(event) => handleMarkerPointerDown(event, option.id)}
                onPointerMove={(event) => handleMarkerPointerMove(event, option.id)}
                onPointerUp={(event) => handleMarkerPointerUp(event, option.id)}
                onPointerCancel={(event) => handleMarkerPointerCancel(event, option.id)}
              />
            );
          })}

        {!isEditMode &&
          markerClusters.map((cluster) => {
            const clusterTitle =
              cluster.count <= 1
                ? cluster.labels[0]
                : `${cluster.count} markers\n${cluster.labels.slice(0, 4).join("\n")}${
                    cluster.count > 4 ? `\n+${cluster.count - 4} more` : ""
                  }`;

            return (
              <button
                key={`cluster-${cluster.key}`}
                type="button"
                onMouseDown={absorbEvent}
                onPointerDown={absorbEvent}
                onClick={(event) => {
                  absorbEvent(event);
                  handleClusterClick(cluster);
                }}
                className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border transition ${
                  cluster.active
                    ? "border-accent bg-accent"
                    : "border-[#6d54a2] bg-[#2b1f49] hover:bg-[#3a2a62]"
                } ${cluster.count > 1 ? "h-3 w-3" : "h-2 w-2"}`}
                style={{ left: `${cluster.leftPct}%` }}
                title={clusterTitle}
                aria-label={
                  cluster.count > 1
                    ? `${cluster.count} timeline markers`
                    : `Timeline marker ${cluster.labels[0] ?? ""}`
                }
              >
                {cluster.count > 1 && (
                  <span className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-[7px] font-semibold text-white">
                    {cluster.count}
                  </span>
                )}
              </button>
            );
          })}

        {isEditMode &&
          sliderOptions.length > 0 &&
          sliderOptions.map((option, index) => {
            let leftPct = indexToLeftPct(index);
            if (dragPreview) {
              if (
                dragPreview.isPlacedDrag &&
                draggingMarkerId === option.id &&
                draggingMarkerRatio !== null
              ) {
                leftPct = draggingMarkerRatio * 100;
              } else {
                const previewIndex = dragPreview.indexById.get(option.id);
                if (previewIndex !== undefined) {
                  leftPct = previewIndexToLeftPct(previewIndex, dragPreview.maxIndex);
                }
              }
            }
            return (
              <span
                key={`tick-label-${option.id}`}
                className="pointer-events-none absolute top-[calc(50%+11px)] max-w-24 -translate-x-1/2 truncate text-[9px] text-text-muted"
                style={{ left: `${leftPct}%` }}
                title={option.label}
              >
                {shortenLabel(option.label)}
              </span>
            );
          })}

        {draggingUnplacedOnTrack && draggingMarker && (
          <>
            <span
              className="pointer-events-none absolute top-1/2 block h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-accent bg-accent"
              style={{ left: `${(draggingMarkerRatio ?? 0) * 100}%` }}
            />
            {isEditMode && (
              <span
                className="pointer-events-none absolute top-[calc(50%+11px)] max-w-24 -translate-x-1/2 truncate text-[9px] text-accent"
                style={{ left: `${(draggingMarkerRatio ?? 0) * 100}%` }}
                title={markerLabel(draggingMarker)}
              >
                {shortenLabel(markerLabel(draggingMarker))}
              </span>
            )}
          </>
        )}

        {!isEditMode && sliderOptions.length > 0 && (
          <span
            className="pointer-events-none absolute top-1/2 block h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border border-accent bg-[#e0d5ff] shadow-[0_0_0_2px_rgba(86,44,149,0.4)]"
            style={{ left: `${clampedDragRatio * 100}%` }}
          />
        )}
      </div>

      {unplacedMarkers.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {unplacedMarkers.map((marker) => (
            <button
              key={marker.id}
              onMouseDown={absorbEvent}
              onPointerDown={(event) => {
                if (!isEditMode) {
                  absorbEvent(event);
                  return;
                }
                handleMarkerPointerDown(event, marker.id);
              }}
              onPointerMove={(event) => {
                if (!isEditMode) return;
                handleMarkerPointerMove(event, marker.id);
              }}
              onPointerUp={(event) => {
                if (!isEditMode) return;
                handleMarkerPointerUp(event, marker.id);
              }}
              onPointerCancel={(event) => {
                if (!isEditMode) return;
                handleMarkerPointerCancel(event, marker.id);
              }}
              onClick={(event) => {
                absorbEvent(event);
                if (ignoreClickAfterDragRef.current === marker.id) {
                  ignoreClickAfterDragRef.current = null;
                  return;
                }
                onSelectMarker(marker.id);
              }}
              className={`rounded border px-2 py-0.5 text-[10px] ${
                marker.id === activeMarkerId
                  ? "border-accent bg-[#2b1f49] text-accent"
                  : "border-[#6d54a2] bg-[#251c40] text-text hover:bg-[#332655]"
              } ${isEditMode ? "cursor-grab" : ""}`}
              title={marker.summary ?? marker.title}
            >
              {marker.title}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
