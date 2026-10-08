export type LifecycleStep = "recording" | "upload" | "storage" | "transcription" | "review" | "approved" | "published";

export const lifecycleSteps: { id: LifecycleStep; label: string }[] = [
  { id: "recording", label: "Recording / source selected" },
  { id: "upload", label: "Uploading to Recall / Verelo" },
  { id: "storage", label: "Copying audio to Verelo storage" },
  { id: "transcription", label: "Waiting for transcription" },
  { id: "review", label: "Transcript ready for review" },
  { id: "approved", label: "Approved" },
  { id: "published", label: "Published" },
];

export function lifecyclePosition(state: string, stage?: string): number {
  if (state.startsWith("failed")) {
    return ({ upload: 1, quarantine: 2, transcription: 3, cleanup: 4,
      approval: 4, publication: 5 } as Record<string, number>)[stage ?? ""] ?? -1;
  }
  switch (state) {
    case "source_pending": return 1;
    case "quarantined":
    case "source_accepted": return 2;
    case "transcription_queued":
    case "transcription_submitted":
    case "transcription_processing":
    case "raw_transcript_stored": return 3;
    case "draft_ready":
    case "approval_required": return 4;
    case "approved":
    case "publishing": return 5;
    case "published": return 6;
    default: return -1;
  }
}

export function safeProcessingMessage(code: string | null): string | null {
  if (!code) return null;
  return `Processing failed (${code.replaceAll("_", " ")}). ${
    code.includes("transcription") ? "Check the transcription service and retry if offered." :
      code.includes("upload") || code.includes("source") ? "Check the source upload and retry if offered." :
        "Retry if offered, or contact the Verelo administrator with this code."
  }`;
}
