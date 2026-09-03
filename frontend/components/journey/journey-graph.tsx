import type { ApiGraphEdge, ApiGraphNode, ApiJourney, ApiJourneyGraph } from "@/types/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Deterministic journey graph (Part 3).
 *
 * Renders the reconstruction graph from the backend's own deterministic
 * node positions — no client-side layout, no extra dependencies. The spine
 * is the PRECEDES chain; TRIGGERS / DERIVED_FROM edges are drawn as
 * annotated strokes to the right of the spine; BELONGS_TO and
 * CORRELATES_WITH connect every event to the journey / correlation roots
 * (shown in the legend and edge registry).
 */

const RELATIONSHIP_STYLES: Record<
  ApiGraphEdge["relationship_type"],
  { stroke: string; dash: string; label: string }
> = {
  PRECEDES: { stroke: "#52525b", dash: "", label: "PRECEDES" },
  TRIGGERS: { stroke: "#2563eb", dash: "6 4", label: "TRIGGERS" },
  DERIVED_FROM: { stroke: "#7c3aed", dash: "2 3", label: "DERIVED_FROM" },
  BELONGS_TO: { stroke: "#059669", dash: "", label: "BELONGS_TO" },
  CORRELATES_WITH: { stroke: "#d97706", dash: "", label: "CORRELATES_WITH" },
};

const NODE_HEIGHT = 44;
const SPINE_X = 28;
const LABEL_X = 56;
const ARCS_X = 420;

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 10)}…` : id;
}

export function JourneyGraph({
  graph,
  journey,
}: {
  graph: ApiJourneyGraph;
  journey: ApiJourney;
}) {
  const flagsByEventId = new Map(
    journey.events.map((event) => [event.id, event])
  );
  const eventNodes = graph.nodes
    .filter((node) => node.kind === "event")
    .sort((a, b) => a.position.y - b.position.y);
  const rootNodes = graph.nodes.filter((node) => node.kind !== "event");

  const nodeCenterY = (node: ApiGraphNode) => node.position.y + NODE_HEIGHT / 2;
  const maxY = Math.max(0, ...graph.nodes.map((node) => node.position.y + NODE_HEIGHT));
  const spineEdges = graph.edges.filter((edge) => edge.relationship_type === "PRECEDES");
  const triggerEdges = graph.edges.filter(
    (edge) => edge.relationship_type === "TRIGGERS"
  );
  const derivedEdges = graph.edges.filter(
    (edge) => edge.relationship_type === "DERIVED_FROM"
  );

  // Unique (type, rule_id) combinations for the edge registry.
  const registry = new Map<string, { ruleId: string; reason: string; count: number }>();
  for (const edge of graph.edges) {
    const key = `${edge.relationship_type}:${edge.rule_id}`;
    const existing = registry.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      registry.set(key, {
        ruleId: edge.rule_id,
        reason: edge.reason,
        count: 1,
      });
    }
  }

  return (
    <div className="space-y-4">
      {/* Legend */}
      <div className="flex flex-wrap gap-2">
        {(Object.keys(RELATIONSHIP_STYLES) as ApiGraphEdge["relationship_type"][]).map(
          (type) => (
            <span
              key={type}
              className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
            >
              <span
                aria-hidden
                className="h-0.5 w-4 rounded"
                style={{
                  backgroundColor: RELATIONSHIP_STYLES[type].stroke,
                  backgroundImage:
                    type === "TRIGGERS" || type === "DERIVED_FROM"
                      ? `repeating-linear-gradient(90deg, ${RELATIONSHIP_STYLES[type].stroke} 0 4px, transparent 4px 7px)`
                      : undefined,
                }}
              />
              {RELATIONSHIP_STYLES[type].label}
            </span>
          )
        )}
      </div>

      {/* SVG diagram — nodes at the backend's deterministic positions */}
      <div className="overflow-x-auto">
        <svg
          width="780"
          height={maxY + 24}
          viewBox={`0 0 780 ${maxY + 24}`}
          className="block max-w-full"
          role="img"
          aria-label="Deterministic journey graph"
        >
          {/* PRECEDES spine */}
          {spineEdges.map((edge) => {
            const source = graph.nodes.find((node) => node.id === edge.source);
            const target = graph.nodes.find((node) => node.id === edge.target);
            if (!source || !target) return null;
            return (
              <line
                key={`${edge.relationship_type}:${edge.source}:${edge.target}`}
                x1={SPINE_X}
                y1={nodeCenterY(source)}
                x2={SPINE_X}
                y2={nodeCenterY(target)}
                stroke={RELATIONSHIP_STYLES.PRECEDES.stroke}
                strokeWidth={1.5}
              >
                <title>{`${source.label} PRECEDES ${target.label} — ${edge.reason}`}</title>
              </line>
            );
          })}

          {/* TRIGGERS arcs */}
          {triggerEdges.map((edge) => {
            const source = graph.nodes.find((node) => node.id === edge.source);
            const target = graph.nodes.find((node) => node.id === edge.target);
            if (!source || !target) return null;
            return (
              <path
                key={`${edge.relationship_type}:${edge.source}:${edge.target}`}
                d={`M ${SPINE_X + 10} ${nodeCenterY(source)} C ${ARCS_X} ${nodeCenterY(
                  source
                )}, ${ARCS_X} ${nodeCenterY(target)}, ${SPINE_X + 10} ${nodeCenterY(
                  target
                )}`}
                fill="none"
                stroke={RELATIONSHIP_STYLES.TRIGGERS.stroke}
                strokeWidth={1}
                strokeDasharray={RELATIONSHIP_STYLES.TRIGGERS.dash}
                opacity={0.55}
              >
                <title>{`${source.label} TRIGGERS ${target.label} — ${edge.reason} (${edge.rule_id})`}</title>
              </path>
            );
          })}

          {/* DERIVED_FROM arcs */}
          {derivedEdges.map((edge) => {
            const source = graph.nodes.find((node) => node.id === edge.source);
            const target = graph.nodes.find((node) => node.id === edge.target);
            if (!source || !target) return null;
            return (
              <path
                key={`${edge.relationship_type}:${edge.source}:${edge.target}`}
                d={`M ${SPINE_X + 10} ${nodeCenterY(source)} C ${ARCS_X + 120} ${nodeCenterY(
                  source
                )}, ${ARCS_X + 120} ${nodeCenterY(target)}, ${SPINE_X + 10} ${nodeCenterY(
                  target
                )}`}
                fill="none"
                stroke={RELATIONSHIP_STYLES.DERIVED_FROM.stroke}
                strokeWidth={1}
                strokeDasharray={RELATIONSHIP_STYLES.DERIVED_FROM.dash}
                opacity={0.55}
              >
                <title>{`${source.label} DERIVED_FROM ${target.label} — ${edge.reason} (${edge.rule_id})`}</title>
              </path>
            );
          })}

          {/* Node boxes */}
          {[...rootNodes, ...eventNodes].map((node) => {
            const flags = flagsByEventId.get(node.id);
            const isRoot = node.kind !== "event";
            return (
              <g key={node.id}>
                <rect
                  x={SPINE_X - 7}
                  y={node.position.y + 4}
                  width={13}
                  height={13}
                  rx={6.5}
                  fill={
                    isRoot
                      ? node.kind === "journey_root"
                        ? "#3f3f46"
                        : "#7c3aed"
                      : "#0284c7"
                  }
                />
                <text
                  x={LABEL_X}
                  y={node.position.y + NODE_HEIGHT / 2 + 4}
                  fontSize={11}
                  fontFamily="ui-monospace, monospace"
                  fill={isRoot ? "#a1a1aa" : "#e4e4e7"}
                >
                  {isRoot
                    ? node.label
                    : `${node.event_type}  ·  ${node.source}`}
                </text>
                {!isRoot && flags ? (
                  <text
                    x={LABEL_X + 20}
                    y={node.position.y + NODE_HEIGHT / 2 + 17}
                    fontSize={9}
                    fontFamily="ui-monospace, monospace"
                    fill={
                      flags.is_duplicate
                        ? "#f59e0b"
                        : flags.is_orphan
                          ? "#a855f7"
                          : flags.is_unknown
                            ? "#ef4444"
                            : "#71717a"
                    }
                  >
                    {[
                      flags.is_duplicate ? "DUPLICATE" : null,
                      flags.is_orphan ? "ORPHAN" : null,
                      flags.is_unknown ? "UNKNOWN" : null,
                    ]
                      .filter(Boolean)
                      .join(" · ") || shortId(node.id)}
                  </text>
                ) : (
                  <text
                    x={LABEL_X + 20}
                    y={node.position.y + NODE_HEIGHT / 2 + 17}
                    fontSize={9}
                    fontFamily="ui-monospace, monospace"
                    fill="#52525b"
                  >
                    {node.timestamp ? formatDateTime(node.timestamp) : "—"}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Edge registry — every deterministic rule that produced edges */}
      <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
        {[...registry.entries()].map(([key, item]) => {
          const type = key.split(":")[0] as ApiGraphEdge["relationship_type"];
          return (
            <div
              key={key}
              className={cn(
                "rounded-md border bg-muted/30 p-2 text-[11px] leading-relaxed"
              )}
            >
              <p className="font-mono font-medium text-foreground">
                <span style={{ color: RELATIONSHIP_STYLES[type].stroke }}>
                  {type}
                </span>
                {" · "}
                {item.ruleId}
                <span className="ml-1 text-muted-foreground">
                  ×{item.count}
                </span>
              </p>
              <p className="mt-0.5 text-muted-foreground">{item.reason}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}