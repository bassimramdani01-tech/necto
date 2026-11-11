import type { GraphNode, GraphResponse } from "./types";

/** Nodes inferred from a ref (a handoff target, say) have no payload name yet. */
export function nodeLabel(node: GraphNode): string {
  if (node.name) return node.name;
  const parts = node.id.split(":");
  return parts.length > 1 ? (parts[parts.length - 1] as string) : node.id;
}

/** Label a node id, falling back to the ref's last segment. */
export function labelFor(graph: GraphResponse | undefined, id: string): string {
  const node = graph?.nodes.find((candidate) => candidate.id === id);
  if (node) return nodeLabel(node);
  const parts = id.split(":");
  return parts.length > 1 ? (parts[parts.length - 1] as string) : id;
}
