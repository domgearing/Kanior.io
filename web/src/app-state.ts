export const initialApplicationStatus = "Synthetic preview ready";

export type PreviewLocation =
  | { page: "home" }
  | { page: "project"; projectId: string };

export function resolvePreviewLocation(hash: string): PreviewLocation {
  if (hash === "#home" || hash === "") return { page: "home" };
  const projectId = hash.match(/^#projects\/([a-z0-9-]+)$/)?.[1];
  return projectId ? { page: "project", projectId } : { page: "home" };
}
