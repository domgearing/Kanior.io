import { Brand } from "./Brand";
import { useEffect, useMemo, useRef, useState } from "react";
import { activeTimedIndex, wordParts, type TimedWord } from "./audio-timeline";
import { WaveformScrubber } from "./WaveformScrubber";
import { togglePlaybackAt } from "./waveform";
import {
  lifecyclePosition,
  lifecycleSteps,
  safeProcessingMessage,
} from "./ingestion-lifecycle";

const apiBase =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : window.location.origin);

type Role = "reader" | "contributor" | "project_owner";
type Me = {
  user_id: string;
  display_name: string;
  email: string;
  csrf_token: string;
  capabilities: string[];
};
type Project = {
  project_id: string;
  name: string;
  my_role: Role;
  owner_user_id: string;
};
type Document = {
  document_id: string;
  title: string;
  meeting_date: string;
  language: string;
};
type Member = {
  user_id: string;
  display_name: string;
  email: string;
  role: Role;
  enabled: boolean;
  revision: number;
};
type Ingestion = {
  ingestion_id: string;
  document_id: string;
  source_asset_id: string | null;
  source_kind: "audio" | "transcript";
  state: string;
  stage: string;
  safe_error_code: string | null;
  can_retry: boolean;
  uploaded_bytes: number;
  expected_bytes: number;
  created_at: string;
  updated_at: string;
  draft_revision: number | null;
  draft_sha256: string | null;
  can_approve: boolean;
  can_publish: boolean;
};
type Draft = {
  ingestion_id: string;
  draft_id: string;
  revision: number;
  content_sha256: string;
  canonical_text: string;
  segments: Array<{
    text: string;
    speaker_label: string | null;
    start_ms: number | null;
    end_ms: number | null;
  }>;
  cleanup_status: string;
  approval: { method: string } | null;
};
type WordAlignment = {
  draft_id: string;
  available: boolean;
  matches_current_draft: boolean;
  source_segments: Draft["segments"];
  segments: Array<{ index: number; words: TimedWord[] }>;
};

type RecorderDevice = {
  device_id: string;
  online: boolean;
  state: string;
  document_id: string | null;
  capture_session_id: string | null;
};
type RecorderCommand = {
  command_id: string;
  device_id: string;
  action: "start" | "pause" | "resume" | "stop";
  document_id: string | null;
  status: "pending" | "running" | "completed" | "failed" | "expired";
  safe_error_code: string | null;
};

function speakerName(label: string | null) {
  const match = label?.trim().match(/^speaker[-_ ]?(\d+)$/i);
  return match ? `Speaker ${Number(match[1])}` : label?.trim() || "Speaker";
}

function transcriptTime(milliseconds: number | null) {
  if (milliseconds === null) return null;
  const total = Math.floor(milliseconds / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const short = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours ? `${String(hours).padStart(2, "0")}:${short}` : short;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!response.ok)
    throw new Error(
      `Verelo API returned HTTP ${response.status}. Please check your connection or ask an administrator if it persists.`,
    );
  return (await response.json()) as T;
}

export function ConnectedApp({ onSignedOut }: { onSignedOut: () => void }) {
  const [me, setMe] = useState<Me | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Project | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [page, setPage] = useState<"home" | "project" | "profile">("home");
  const [notice, setNotice] = useState("");

  const refreshProjects = async () => {
    const data = await request<{ items: Project[] }>("/api/v1/projects");
    setProjects(data.items);
    return data.items;
  };
  useEffect(() => {
    void Promise.all([
      request<Me>("/api/v1/me"),
      request<{ items: Project[] }>("/api/v1/projects"),
    ])
      .then(([identity, projectPage]) => {
        setMe(identity);
        setProjects(projectPage.items);
      })
      .catch(() => onSignedOut());
  }, [onSignedOut]);

  const openProject = async (project: Project) => {
    setSelected(project);
    setPage("project");
    setNotice("");
    const data = await request<{ items: Document[] }>(
      `/api/v1/projects/${project.project_id}/documents`,
    );
    setDocuments(data.items);
    if (project.my_role === "project_owner") {
      const people = await request<{ items: Member[] }>(
        `/api/v1/projects/${project.project_id}/members`,
      );
      setMembers(people.items);
    } else setMembers([]);
  };
  const signOut = async () => {
    if (me) {
      await fetch(`${apiBase}/api/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": me.csrf_token },
      });
    }
    onSignedOut();
  };
  if (!me) return <div className="auth-loading">Loading your workspace…</div>;

  return (
    <div className="connected-shell">
      <aside className="connected-sidebar">
        <Brand />
        <button
          aria-current={page === "home" ? "page" : undefined}
          className={page === "home" ? "active" : ""}
          onClick={() => setPage("home")}
        >
          Home
        </button>
        <button
          aria-current={page === "profile" ? "page" : undefined}
          className={page === "profile" ? "active" : ""}
          onClick={() => setPage("profile")}
        >
          My profile
        </button>
        <label>Your projects</label>
        {projects.map((project) => (
          <button
            key={project.project_id}
            aria-current={
              selected?.project_id === project.project_id && page === "project"
                ? "page"
                : undefined
            }
            className={
              selected?.project_id === project.project_id && page === "project"
                ? "active"
                : ""
            }
            onClick={() => void openProject(project)}
          >
            <span className="project-dot" />
            {project.name}
          </button>
        ))}
        <div className="connected-account">
          <span>
            {me.display_name
              .split(/\s+/)
              .map((part) => part[0])
              .join("")
              .slice(0, 2)
              .toUpperCase()}
          </span>
          <div>
            <strong>{me.display_name}</strong>
            <small>{me.email}</small>
          </div>
          <button onClick={() => void signOut()}>Sign out</button>
        </div>
      </aside>

      {page === "home" && (
        <AccountHome
          me={me}
          projects={projects}
          refresh={refreshProjects}
          openProject={openProject}
        />
      )}
      {page === "profile" && <ProfilePage me={me} setMe={setMe} />}
      {page === "project" && selected && (
        <ProjectPage
          project={selected}
          documents={documents}
          members={members}
          csrf={me.csrf_token}
          refresh={() => openProject(selected)}
          notice={notice}
          setNotice={setNotice}
        />
      )}
    </div>
  );
}

function AccountHome({
  me,
  projects,
  refresh,
  openProject,
}: {
  me: Me;
  projects: Project[];
  refresh: () => Promise<Project[]>;
  openProject: (project: Project) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    const project = await request<Project>("/api/v1/projects", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": me.csrf_token,
      },
      body: JSON.stringify({ name }),
    });
    setName("");
    await refresh();
    await openProject(project);
  };
  return (
    <main className="connected-main">
      <header>
        <div>
          <small>Your workspace</small>
          <h1>Welcome, {me.display_name.split(" ")[0]}</h1>
          <p>Your interviews, transcripts, and team research in one place.</p>
        </div>
      </header>
      <section className="account-stats">
        <article>
          <strong>{projects.length}</strong>
          <span>Accessible projects</span>
        </article>
        <article>
          <strong>
            {projects.filter((p) => p.my_role === "project_owner").length}
          </strong>
          <span>Owned projects</span>
        </article>
        <article>
          <strong>
            {projects.filter((p) => p.my_role === "reader").length}
          </strong>
          <span>Read-only projects</span>
        </article>
      </section>
      {me.capabilities.includes("projects:create") && (
        <form className="create-project" onSubmit={create}>
          <div>
            <h2>Create a project</h2>
            <p>
              Give your research a home. Add interviews and invite your team.
            </p>
          </div>
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            aria-label="Project name"
            placeholder="Project name"
          />
          <button className="button primary">Create project</button>
        </form>
      )}
      <section className="connected-list">
        <h2>Your projects</h2>
        {projects.length === 0 ? (
          <p>
            No projects yet. Create a project above, or ask a project owner to
            invite you.
          </p>
        ) : (
          projects.map((project) => (
            <button
              key={project.project_id}
              onClick={() => void openProject(project)}
            >
              <div>
                <strong>{project.name}</strong>
                <small>{project.my_role.replaceAll("_", " ")}</small>
              </div>
              <b>→</b>
            </button>
          ))
        )}
      </section>
    </main>
  );
}

function ProfilePage({ me, setMe }: { me: Me; setMe: (me: Me) => void }) {
  const [name, setName] = useState(me.display_name);
  const [saved, setSaved] = useState(false);
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const updated = await request<Me>("/api/v1/me", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": me.csrf_token,
      },
      body: JSON.stringify({ display_name: name }),
    });
    setMe(updated);
    setSaved(true);
  };
  return (
    <main className="connected-main profile-page">
      <header>
        <small>Account</small>
        <h1>My profile</h1>
        <p>This identity is unique to your internal Verelo user ID.</p>
      </header>
      <section>
        <div className="profile-avatar">{name.slice(0, 1).toUpperCase()}</div>
        <form onSubmit={save}>
          <label>
            Display name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </label>
          <label>
            Login email
            <input value={me.email} disabled />
          </label>
          <small>
            Email changes require an administrator so project access cannot be
            transferred accidentally.
          </small>
          <button className="button primary">Save profile</button>
          {saved && <b className="saved">Saved</b>}
        </form>
      </section>
    </main>
  );
}

function ProjectPage({
  project,
  documents,
  members,
  csrf,
  refresh,
  notice,
  setNotice,
}: {
  project: Project;
  documents: Document[];
  members: Member[];
  csrf: string;
  refresh: () => Promise<void>;
  notice: string;
  setNotice: (message: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("reader");
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(
    null,
  );
  const [documentTitle, setDocumentTitle] = useState("");
  const assign = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await request(`/api/v1/projects/${project.project_id}/members/by-email`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({
          email,
          role,
          enabled: true,
          expected_revision: 0,
        }),
      });
      setEmail("");
      setNotice("Access granted.");
      await refresh();
    } catch {
      setNotice(
        "That enabled employee is unavailable or already has a membership. Update existing roles below.",
      );
    }
  };
  const update = async (
    member: Member,
    nextRole: Role,
    enabled = member.enabled,
  ) => {
    await request(
      `/api/v1/projects/${project.project_id}/members/${member.user_id}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({
          role: nextRole,
          enabled,
          expected_revision: member.revision,
        }),
      },
    );
    await refresh();
  };
  const createDocument = async (event: React.FormEvent) => {
    event.preventDefault();
    const created = await request<Document>(
      `/api/v1/projects/${project.project_id}/documents`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({
          title: documentTitle,
          meeting_date: new Date().toISOString(),
          language: "en-US",
          consent_acknowledged: true,
          consent_policy_version: "synthetic-consent-v1",
        }),
      },
    );
    setDocumentTitle("");
    setSelectedDocument(created);
    await refresh();
  };
  return (
    <main className="connected-main">
      <header>
        <small>{project.my_role.replaceAll("_", " ")}</small>
        <h1>{project.name}</h1>
        <p>
          Record an interview or upload a source, then review and publish your
          transcript.
        </p>
      </header>
      <section className="connected-list">
        <h2>Meetings and transcripts</h2>
        {project.my_role !== "reader" && (
          <form className="inline-create" onSubmit={createDocument}>
            <input
              required
              value={documentTitle}
              onChange={(event) => setDocumentTitle(event.target.value)}
              aria-label="Meeting or interview title"
              placeholder="Meeting or interview title"
            />
            <button
              className={`button ${selectedDocument ? "secondary" : "primary"}`}
            >
              Create meeting
            </button>
          </form>
        )}
        {documents.length === 0 ? (
          <p>
            No meetings yet. Create a meeting to record a call or upload a
            transcript.
          </p>
        ) : (
          documents.map((document) => (
            <button
              className="document-row"
              key={document.document_id}
              onClick={() => setSelectedDocument(document)}
            >
              <div>
                <strong>{document.title}</strong>
                <small>
                  {new Date(document.meeting_date).toLocaleDateString()} ·{" "}
                  {document.language}
                </small>
              </div>
              <b>Open →</b>
            </button>
          ))
        )}
      </section>
      {selectedDocument && (
        <IngestionWorkspace
          document={selectedDocument}
          role={project.my_role}
          csrf={csrf}
          close={() => setSelectedDocument(null)}
        />
      )}
      {project.my_role === "project_owner" && (
        <section className="member-panel">
          <h2>Project access</h2>
          <form onSubmit={assign}>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="Allowlisted employee email"
            />
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
            >
              <option value="reader">Reader</option>
              <option value="contributor">Contributor</option>
              <option value="project_owner">Project owner</option>
            </select>
            <button className="button secondary">Grant access</button>
          </form>
          {notice && <p className="access-notice">{notice}</p>}
          <div className="member-list">
            {members.map((member) => (
              <article key={member.user_id}>
                <div>
                  <strong>{member.display_name}</strong>
                  <small>{member.email}</small>
                </div>
                <select
                  value={member.role}
                  disabled={member.user_id === project.owner_user_id}
                  onChange={(event) =>
                    void update(member, event.target.value as Role)
                  }
                >
                  <option value="reader">Reader</option>
                  <option value="contributor">Contributor</option>
                  <option value="project_owner">Project owner</option>
                </select>
                <button
                  disabled={member.user_id === project.owner_user_id}
                  onClick={() => void update(member, member.role, false)}
                >
                  Remove
                </button>
              </article>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

function IngestionWorkspace({
  document,
  role,
  csrf,
  close,
}: {
  document: Document;
  role: Role;
  csrf: string;
  close: () => void;
}) {
  const [ingestions, setIngestions] = useState<Ingestion[]>([]);
  const [selected, setSelected] = useState<Ingestion | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [alignment, setAlignment] = useState<WordAlignment | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioMediaType, setAudioMediaType] = useState("");
  const [audioStatus, setAudioStatus] = useState("");
  const [waveform, setWaveform] = useState<{
    duration_ms: number;
    peaks: number[];
  } | null>(null);
  const [waveformStatus, setWaveformStatus] = useState("");
  const [playbackMs, setPlaybackMs] = useState(0);
  const [panelOpen, setPanelOpen] = useState(true);
  const [editing, setEditing] = useState(false);
  const [correction, setCorrection] = useState("");
  const [status, setStatus] = useState("");
  const transcriptRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const headers = { "Content-Type": "application/json", "X-CSRF-Token": csrf };

  const refresh = async () => {
    const page = await request<{ items: Ingestion[] }>(
      `/api/v1/documents/${document.document_id}/ingestions`,
    );
    setIngestions(page.items);
    if (selected) {
      const current = page.items.find(
        (item) => item.ingestion_id === selected.ingestion_id,
      );
      if (current) setSelected(current);
    }
  };
  useEffect(() => {
    setSelected(null);
    setDraft(null);
    setAlignment(null);
    setEditing(false);
    void refresh();
    // The document identifier is the intended refresh boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document.document_id]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void request<{ items: Ingestion[] }>(
        `/api/v1/documents/${document.document_id}/ingestions`,
      )
        .then(async (page) => {
          setIngestions(page.items);
          const current = page.items.find(
            (item) => item.ingestion_id === selected?.ingestion_id,
          );
          if (!current) return;
          setSelected(current);
          if (
            current.draft_sha256 &&
            current.draft_sha256 !== draft?.content_sha256
          ) {
            const value = await request<Draft>(
              `/api/v1/ingestions/${current.ingestion_id}/draft`,
            );
            setDraft(value);
            setCorrection(value.canonical_text);
            const wordTiming = await request<WordAlignment>(
              `/api/v1/ingestions/${current.ingestion_id}/word-alignment`,
            );
            setAlignment(wordTiming);
          }
        })
        .catch(() =>
          setStatus(
            "Could not refresh processing status. Check the API connection.",
          ),
        );
    }, 5000);
    return () => window.clearInterval(timer);
  }, [document.document_id, selected?.ingestion_id, draft?.content_sha256]);

  const openIngestion = async (item: Ingestion) => {
    setSelected(item);
    setPanelOpen(true);
    setEditing(false);
    setPlaybackMs(0);
    if (item.draft_sha256) {
      const [value, wordTiming] = await Promise.all([
        request<Draft>(`/api/v1/ingestions/${item.ingestion_id}/draft`),
        request<WordAlignment>(
          `/api/v1/ingestions/${item.ingestion_id}/word-alignment`,
        ),
      ]);
      setDraft(value);
      setAlignment(wordTiming);
      setCorrection(value.canonical_text);
    } else {
      setDraft(null);
      setAlignment(null);
    }
  };

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setAudioUrl(null);
    setAudioMediaType("");
    setAudioStatus("");
    if (selected?.source_kind === "audio" && selected.source_asset_id) {
      setAudioStatus("Loading original audio…");
      void request<{ content_base64: string; media_type: string }>(
        `/api/v1/source-assets/${selected.source_asset_id}/content`,
      )
        .then((payload) => {
          const bytes = Uint8Array.from(
            atob(payload.content_base64),
            (character) => character.charCodeAt(0),
          );
          const blob = new Blob([bytes], { type: payload.media_type });
          objectUrl = URL.createObjectURL(blob);
          if (cancelled) {
            URL.revokeObjectURL(objectUrl);
            return;
          }
          setAudioMediaType(payload.media_type);
          setAudioUrl(objectUrl);
          setAudioStatus("");
        })
        .catch(() => {
          if (!cancelled) setAudioStatus("Original audio could not be loaded.");
        });
    }
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selected?.source_asset_id, selected?.source_kind]);

  useEffect(() => {
    let cancelled = false;
    setWaveform(null);
    setWaveformStatus("");
    if (selected?.source_kind === "audio" && selected.source_asset_id) {
      setWaveformStatus("Preparing waveform…");
      void request<{ duration_ms: number; peaks: number[] }>(
        `/api/v1/source-assets/${selected.source_asset_id}/waveform`,
      )
        .then((value) => {
          if (!cancelled) {
            setWaveform(value);
            setWaveformStatus("");
          }
        })
        .catch(() => {
          if (!cancelled)
            setWaveformStatus(
              "Waveform unavailable. Use the audio player to seek.",
            );
        });
    }
    return () => {
      cancelled = true;
    };
  }, [selected?.source_asset_id, selected?.source_kind]);

  const alignedSegments = useMemo(
    () =>
      alignment && draft && alignment.draft_id === draft.draft_id
        ? alignment.segments
        : [],
    [alignment, draft],
  );
  const playbackSegments =
    alignment &&
    draft &&
    alignment.draft_id === draft.draft_id &&
    alignment.source_segments.length
      ? alignment.source_segments
      : draft?.segments || [];
  const playbackMatchesCanonical =
    !!draft &&
    playbackSegments.map((segment) => segment.text).join("\n") ===
      draft.canonical_text;
  const activeSegment =
    draft && playbackSegments.length
      ? activeTimedIndex(playbackSegments, playbackMs)
      : -1;

  useEffect(() => {
    if (activeSegment < 0 || !panelOpen || editing) return;
    const word = alignedSegments.find(
      (item) => item.index === activeSegment,
    )?.words;
    const activeWord = word ? activeTimedIndex(word, playbackMs) : -1;
    const selector =
      activeWord >= 0
        ? `[data-word-key="${activeSegment}-${activeWord}"]`
        : `[data-segment-index="${activeSegment}"]`;
    transcriptRef.current
      ?.querySelector(selector)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeSegment, alignedSegments, editing, panelOpen, playbackMs]);
  const upload = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem(
      "source",
    ) as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    setStatus("Hashing source…");
    const bytes = new Uint8Array(await file.arrayBuffer());
    const digest = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    )
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("");
    const extension = file.name.split(".").pop()?.toLowerCase();
    const mediaTypes: Record<string, string> = {
      wav: "audio/wav",
      mp3: "audio/mpeg",
      m4a: "audio/mp4",
      webm: "audio/webm",
      txt: "text/plain",
      vtt: "text/vtt",
      srt: "application/x-subrip",
      json: "application/json",
    };
    const mediaType = mediaTypes[extension ?? ""];
    if (!mediaType) {
      setStatus(
        "Unsupported file. Use WAV, MP3, M4A, WebM, TXT, VTT, SRT, or JSON.",
      );
      return;
    }
    const operation = crypto.randomUUID();
    const created = await request<Ingestion>(
      `/api/v1/documents/${document.document_id}/ingestions`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          source_kind: mediaType.startsWith("audio/") ? "audio" : "transcript",
          filename: file.name,
          declared_media_type: mediaType,
          byte_length: bytes.byteLength,
          sha256: digest,
          operation_key: `web-create-${operation}`,
        }),
      },
    );
    const chunkSize = 5 * 1024 * 1024;
    for (
      let offset = 0, sequence = 1;
      offset < bytes.length;
      offset += chunkSize, sequence += 1
    ) {
      setStatus(`Uploading chunk ${sequence}…`);
      const chunk = bytes.slice(
        offset,
        Math.min(offset + chunkSize, bytes.length),
      );
      const chunkDigest = Array.from(
        new Uint8Array(await crypto.subtle.digest("SHA-256", chunk)),
      )
        .map((value) => value.toString(16).padStart(2, "0"))
        .join("");
      let binary = "";
      for (const value of chunk) binary += String.fromCharCode(value);
      await request(
        `/api/v1/ingestions/${created.ingestion_id}/chunks/${sequence}`,
        {
          method: "PUT",
          headers,
          body: JSON.stringify({
            sequence,
            content_base64: btoa(binary),
            sha256: chunkDigest,
          }),
        },
      );
    }
    setStatus("Validating and preparing transcript…");
    const finalized = await request<Ingestion>(
      `/api/v1/ingestions/${created.ingestion_id}/finalize`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          operation_key: `web-finalize-${operation}`,
          expected_byte_length: bytes.byteLength,
          expected_sha256: digest,
        }),
      },
    );
    setStatus(
      finalized.draft_sha256
        ? "Source accepted. Review the transcript below."
        : "Source accepted. AssemblyAI transcription is queued; refresh shortly to review it.",
    );
    input.value = "";
    await refresh();
    await openIngestion(finalized);
  };
  const approve = async () => {
    if (!selected || !draft) return;
    const updated = await request<Draft>(
      `/api/v1/ingestions/${selected.ingestion_id}/approvals`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          content_sha256: draft.content_sha256,
          expected_revision: draft.revision,
          reason_code: "reviewed_transcript",
        }),
      },
    );
    setDraft(updated);
    await refresh();
  };
  const retry = async () => {
    if (!selected?.can_retry) return;
    const updated = await request<Ingestion>(
      `/api/v1/ingestions/${selected.ingestion_id}/retry`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          operation_key: `web-retry-${crypto.randomUUID()}`,
        }),
      },
    );
    setSelected(updated);
    setStatus("Retry requested. Processing status will update automatically.");
    await refresh();
  };
  const saveCorrection = async () => {
    if (!selected || !draft || correction === draft.canonical_text) return;
    const updated = await request<Draft>(
      `/api/v1/ingestions/${selected.ingestion_id}/draft`,
      {
        method: "PUT",
        headers,
        body: JSON.stringify({
          canonical_text: correction,
          expected_revision: draft.revision,
          expected_content_sha256: draft.content_sha256,
          reason_code: "transcription_correction",
        }),
      },
    );
    setDraft(updated);
    setCorrection(updated.canonical_text);
    setAlignment(null);
    setEditing(false);
    await refresh();
  };
  const publish = async () => {
    if (!selected || !draft) return;
    let activeVersion: string | null = null;
    try {
      const active = await request<{ transcript_version_id: string }>(
        `/api/v1/documents/${document.document_id}/transcript-publication`,
      );
      activeVersion = active.transcript_version_id;
    } catch {
      activeVersion = null;
    }
    await request(`/api/v1/ingestions/${selected.ingestion_id}/publication`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        approved_content_sha256: draft.content_sha256,
        expected_draft_revision: draft.revision,
        expected_active_transcript_version_id: activeVersion,
        operation_key: `web-publish-${crypto.randomUUID()}`,
      }),
    });
    setStatus("Published. TXT, Markdown, JSON, and PDF downloads are ready.");
    await refresh();
  };
  const download = async (format: "txt" | "md" | "json" | "pdf") => {
    const payload = await request<{
      filename: string;
      media_type: string;
      content_base64: string;
    }>(
      `/api/v1/documents/${document.document_id}/transcript-downloads/${format}`,
    );
    const binary = atob(payload.content_base64);
    const bytes = Uint8Array.from(binary, (character) =>
      character.charCodeAt(0),
    );
    const url = URL.createObjectURL(
      new Blob([bytes], { type: payload.media_type }),
    );
    const anchor = window.document.createElement("a");
    anchor.href = url;
    anchor.download = payload.filename;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const downloadRawAudio = () => {
    if (!audioUrl || !selected?.source_asset_id) return;
    const extension =
      (
        {
          "audio/wav": "wav",
          "audio/mpeg": "mp3",
          "audio/mp4": "m4a",
          "audio/webm": "webm",
        } as Record<string, string>
      )[audioMediaType] || "bin";
    const anchor = window.document.createElement("a");
    anchor.href = audioUrl;
    anchor.download = `recording-${selected.source_asset_id}.${extension}`;
    anchor.click();
  };

  return (
    <section className="ingestion-workspace">
      <header>
        <div>
          <small>Transcript workspace</small>
          <h2>{document.title}</h2>
        </div>
        <button onClick={close}>Close</button>
      </header>
      {role !== "reader" && (
        <RecorderControls
          key={document.document_id}
          document={document}
          csrf={csrf}
        />
      )}
      {role !== "reader" && (
        <form
          className="source-upload"
          onSubmit={(event) =>
            void upload(event).catch((error: unknown) =>
              setStatus(
                error instanceof Error
                  ? error.message
                  : "Upload failed. Please try again.",
              ),
            )
          }
        >
          <input
            name="source"
            aria-label="Audio or transcript file"
            type="file"
            required
            accept=".wav,.mp3,.m4a,.webm,.txt,.vtt,.srt,.json"
          />
          <button className={`button ${selected ? "secondary" : "primary"}`}>
            Upload and process
          </button>
        </form>
      )}
      {status && <p className="access-notice">{status}</p>}
      <div className={`workflow-grid ${panelOpen ? "with-transcript" : ""}`}>
        <div className="workflow-side">
          <nav aria-label="Sources">
            {ingestions.map((item) => (
              <button
                key={item.ingestion_id}
                aria-pressed={selected?.ingestion_id === item.ingestion_id}
                onClick={() => void openIngestion(item)}
              >
                <strong>
                  {item.source_kind === "audio" ? "Audio" : "Transcript"}
                </strong>
                <small>{item.state.replaceAll("_", " ")}</small>
                <small>{new Date(item.created_at).toLocaleString()}</small>
              </button>
            ))}
            {ingestions.length === 0 && (
              <p>
                No sources yet. Record this meeting or choose a file above to
                get started.
              </p>
            )}
          </nav>
          <article className="draft-view">
            <h3>Processing</h3>
            {!panelOpen && selected && (
              <button onClick={() => setPanelOpen(true)}>
                Open transcript panel
              </button>
            )}
            {selected && (
              <div className="processing-status" role="status">
                <strong>{selected.state.replaceAll("_", " ")}</strong>
                <span>Stage: {selected.stage.replaceAll("_", " ")}</span>
                {selected.state === "source_pending" && (
                  <span>
                    {Math.floor(
                      (100 * selected.uploaded_bytes) / selected.expected_bytes,
                    )}
                    % uploaded
                  </span>
                )}
                {selected.safe_error_code && (
                  <span>{safeProcessingMessage(selected.safe_error_code)}</span>
                )}
                <ol
                  className="lifecycle-steps"
                  aria-label="Recording and transcript progress"
                >
                  {lifecycleSteps.map((step, index) => (
                    <li
                      key={step.id}
                      className={
                        selected.state === "aborted"
                          ? "pending"
                          : index <
                              lifecyclePosition(selected.state, selected.stage)
                            ? "complete"
                            : index ===
                                lifecyclePosition(
                                  selected.state,
                                  selected.stage,
                                )
                              ? "current"
                              : "pending"
                      }
                    >
                      {selected.source_kind === "transcript" &&
                      step.id === "upload"
                        ? "Uploading transcript"
                        : selected.source_kind === "transcript" &&
                            step.id === "storage"
                          ? "Storing transcript in Verelo"
                          : step.label}
                    </li>
                  ))}
                </ol>
                {selected.can_retry && role !== "reader" && (
                  <button
                    className="button"
                    onClick={() =>
                      void retry().catch((error: unknown) =>
                        setStatus(
                          error instanceof Error
                            ? error.message
                            : "Retry failed.",
                        ),
                      )
                    }
                  >
                    Retry processing
                  </button>
                )}
              </div>
            )}
            {!draft ? (
              <p>
                {selected?.safe_error_code
                  ? "Processing stopped. Review the issue above and retry if available."
                  : selected
                    ? "Transcript processing is underway. This view refreshes automatically."
                    : "Select a source to review its transcript."}
              </p>
            ) : (
              <>
                <p>Review the recording and transcript before approval.</p>
                {role === "project_owner" && selected?.can_approve && (
                  <button className="button" onClick={() => void approve()}>
                    Approve exact draft
                  </button>
                )}
                {role === "project_owner" && selected?.can_publish && (
                  <button
                    className="button primary"
                    onClick={() => void publish()}
                  >
                    Publish transcript
                  </button>
                )}
                {selected?.state === "published" && (
                  <div className="download-row">
                    <button onClick={() => void download("txt")}>TXT</button>
                    <button onClick={() => void download("md")}>
                      Markdown
                    </button>
                    <button onClick={() => void download("json")}>JSON</button>
                    <button onClick={() => void download("pdf")}>PDF</button>
                  </div>
                )}
              </>
            )}
          </article>
        </div>
        {panelOpen && (
          <aside
            className="transcript-panel"
            aria-label="Recording and transcript review"
          >
            <header>
              <h3>
                {selected?.source_kind === "audio"
                  ? "Recording and transcript"
                  : "Transcript"}
              </h3>
              <button
                onClick={() => setPanelOpen(false)}
                aria-label="Close transcript panel"
              >
                Close
              </button>
            </header>
            {selected?.source_kind === "audio" && (
              <div className="audio-review">
                <h3>Original recording</h3>
                {audioUrl ? (
                  <>
                    <audio
                      ref={audioRef}
                      controls
                      preload="metadata"
                      src={audioUrl}
                      onTimeUpdate={(event) =>
                        setPlaybackMs(event.currentTarget.currentTime * 1000)
                      }
                      onSeeked={(event) =>
                        setPlaybackMs(event.currentTarget.currentTime * 1000)
                      }
                    >
                      Your browser cannot play this audio format.
                    </audio>
                    {waveform ? (
                      <WaveformScrubber
                        waveform={waveform}
                        positionMs={playbackMs}
                        audioRef={audioRef}
                        onSeek={(milliseconds) => {
                          if (audioRef.current) {
                            audioRef.current.currentTime = milliseconds / 1000;
                            setPlaybackMs(milliseconds);
                          }
                        }}
                        onToggleAt={(milliseconds) => {
                          if (!audioRef.current) return;
                          void togglePlaybackAt(
                            audioRef.current,
                            milliseconds,
                          ).catch(() =>
                            setAudioStatus(
                              "Playback could not start. Use the audio controls to try again.",
                            ),
                          );
                          setPlaybackMs(milliseconds);
                        }}
                      />
                    ) : (
                      <p className="alignment-note" role="status">
                        {waveformStatus ||
                          "Waveform will appear after audio loads."}
                      </p>
                    )}
                    {audioStatus && <p role="status">{audioStatus}</p>}
                    <button onClick={downloadRawAudio}>
                      Download raw audio
                    </button>
                  </>
                ) : (
                  <p role="status">
                    {audioStatus || "Audio is not stored yet."}
                  </p>
                )}
              </div>
            )}
            {!draft ? (
              <p>Select a processed recording to view its transcript.</p>
            ) : (
              <>
                <div className="draft-meta">
                  <span>{draft.cleanup_status.replaceAll("_", " ")}</span>
                  <span>
                    {draft.approval
                      ? `Approved: ${draft.approval.method}`
                      : "Not approved"}
                  </span>
                </div>
                {editing ? (
                  <>
                    <textarea
                      className="draft-editor"
                      value={correction}
                      onChange={(event) => setCorrection(event.target.value)}
                      aria-label="Transcript correction editor"
                    />
                    <div className="transcript-actions">
                      <button
                        onClick={() => {
                          setCorrection(draft.canonical_text);
                          setEditing(false);
                        }}
                      >
                        Cancel
                      </button>
                      <button
                        className="button primary"
                        disabled={correction === draft.canonical_text}
                        onClick={() =>
                          void saveCorrection().catch((error: unknown) =>
                            setStatus(
                              error instanceof Error
                                ? error.message
                                : "Correction failed.",
                            ),
                          )
                        }
                      >
                        Save immutable correction
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    {role === "project_owner" &&
                      selected?.state !== "published" && (
                        <button onClick={() => setEditing(true)}>
                          Edit transcript
                        </button>
                      )}
                    {!playbackMatchesCanonical && (
                      <p className="alignment-note">
                        Original audio-aligned transcription is shown below. The
                        reviewed transcript differs; open it separately or use
                        Edit transcript to correct it.
                      </p>
                    )}
                    {selected?.source_kind === "audio" &&
                      !alignment?.available && (
                        <p className="alignment-note">
                          Exact word timing is unavailable. The app will not
                          guess where words occur in the audio.
                        </p>
                      )}
                    <div
                      className="organized-transcript"
                      ref={transcriptRef}
                      aria-label="Speaker-organized transcript"
                    >
                      {playbackSegments.some(
                        (segment) =>
                          segment.speaker_label || segment.start_ms !== null,
                      ) ? (
                        playbackSegments.map((segment, index) => {
                          const words =
                            alignedSegments.find((item) => item.index === index)
                              ?.words || [];
                          const activeWord =
                            activeSegment === index
                              ? activeTimedIndex(words, playbackMs)
                              : -1;
                          return (
                            <section
                              key={`${segment.start_ms ?? "untimed"}-${index}`}
                              data-segment-index={index}
                              className={
                                activeSegment === index ? "active-segment" : ""
                              }
                            >
                              <div className="speaker-line">
                                <strong>
                                  {speakerName(segment.speaker_label)}
                                </strong>
                                {transcriptTime(segment.start_ms) && (
                                  <button
                                    className="time-seek"
                                    onClick={() => {
                                      if (
                                        audioRef.current &&
                                        segment.start_ms !== null
                                      ) {
                                        audioRef.current.currentTime =
                                          segment.start_ms / 1000;
                                      }
                                    }}
                                  >
                                    {transcriptTime(segment.start_ms)}
                                  </button>
                                )}
                              </div>
                              <p>
                                {words.length
                                  ? wordParts(segment.text, words).map(
                                      (part, partIndex) =>
                                        part.wordIndex === null ? (
                                          part.text
                                        ) : (
                                          <span
                                            key={partIndex}
                                            data-word-key={`${index}-${part.wordIndex}`}
                                            className={
                                              part.wordIndex === activeWord
                                                ? "active-word"
                                                : ""
                                            }
                                          >
                                            {part.text}
                                          </span>
                                        ),
                                    )
                                  : segment.text}
                              </p>
                            </section>
                          );
                        })
                      ) : (
                        <pre>{draft.canonical_text}</pre>
                      )}
                    </div>
                    {!playbackMatchesCanonical && (
                      <details className="reviewed-transcript">
                        <summary>Reviewed transcript text</summary>
                        <pre>{draft.canonical_text}</pre>
                      </details>
                    )}
                  </>
                )}
              </>
            )}
          </aside>
        )}
      </div>
    </section>
  );
}

function RecorderControls({
  document,
  csrf,
}: {
  document: Document;
  csrf: string;
}) {
  const [devices, setDevices] = useState<RecorderDevice[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [command, setCommand] = useState<RecorderCommand | null>(null);
  const [consent, setConsent] = useState(false);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const page = await request<{ items: RecorderDevice[] }>(
          "/api/v1/recorder-devices",
        );
        if (!active) return;
        setDevices(page.items);
        setDeviceId((current) =>
          page.items.some((item) => item.device_id === current)
            ? current
            : (page.items.find((item) => item.online)?.device_id ?? ""),
        );
      } catch {
        if (active)
          setMessage(
            "Could not reach recorder status. Check the API connection.",
          );
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const commandId = command?.command_id;
  const commandStatus = command?.status;
  useEffect(() => {
    if (
      !commandId ||
      !commandStatus ||
      !["pending", "running"].includes(commandStatus)
    )
      return;
    let active = true;
    const refresh = async () => {
      try {
        const result = await request<RecorderCommand>(
          `/api/v1/recorder-commands/${commandId}`,
        );
        if (!active) return;
        setCommand(result);
        if (result.status === "completed") {
          setMessage(`${result.action} completed on the desktop recorder.`);
        } else if (result.status === "failed") {
          setMessage(
            result.safe_error_code === "permission_revoked"
              ? "Recording access changed. This command was not sent to the desktop."
              : "The desktop recorder could not complete this action. Check its window before retrying.",
          );
        } else if (result.status === "expired") {
          setMessage(
            "The command expired. Check the desktop recorder's actual state before retrying.",
          );
        }
      } catch {
        if (active)
          setMessage(
            "Could not confirm the recorder action. Check the desktop window.",
          );
      }
    };
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [commandId, commandStatus]);

  const device = devices.find((item) => item.device_id === deviceId);
  const thisMeeting = device?.document_id === document.document_id;
  const pending = command && ["pending", "running"].includes(command.status);
  const available = Boolean(device?.online && !pending && !submitting);
  const startable =
    available &&
    [
      "idle",
      "finalizing",
      "uploading",
      "complete",
      "failed",
      "aborted",
    ].includes(device?.state ?? "") &&
    consent;
  const send = async (action: RecorderCommand["action"]) => {
    if (!device || !available) return;
    setSubmitting(true);
    setMessage("");
    try {
      const result = await request<RecorderCommand>(
        `/api/v1/recorder-devices/${device.device_id}/commands`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({
            action,
            document_id: action === "start" ? document.document_id : null,
            operation_key: crypto.randomUUID(),
          }),
        },
      );
      setCommand(result);
      setMessage(`${action} requested. Waiting for the desktop recorder…`);
      if (action === "start") setConsent(false);
    } catch {
      setMessage(
        "Action was not accepted. Check that this recorder is online, idle, and permitted for this meeting.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const recordingHere = Boolean(
    thisMeeting &&
    ["recording", "paused", "interrupted"].includes(device?.state ?? ""),
  );
  const startHint = !device
    ? "Choose a desktop recorder to continue."
    : !device.online
      ? "Open Verelo on the recording computer to bring it online."
      : pending || submitting
        ? "Waiting for the desktop recorder to confirm your request."
        : !consent
          ? "Confirm recording consent to enable Start recording."
          : !startable
            ? "The recorder is busy. Check its current meeting before starting."
            : "Ready to record. Audio will be saved to this meeting.";

  return (
    <section className="recorder-panel" aria-label="Desktop recording controls">
      <header className="recorder-heading">
        <div>
          <h3>Record this meeting</h3>
          <p>Capture the conversation, then review the transcript.</p>
        </div>
        <span
          className="recorder-status"
          data-online={Boolean(device?.online)}
          role="status"
        >
          <span aria-hidden="true" />
          {device
            ? device.online
              ? "Recorder online"
              : "Recorder offline"
            : "No recorder selected"}
        </span>
      </header>
      <div className="recorder-steps">
        <section
          className="recorder-setup-card"
          aria-label="Connect a recorder"
        >
          <header className="recorder-step-heading">
            <span aria-hidden="true">01</span>
            <div>
              <h4>Connect a recorder</h4>
              <p>Use Verelo on the computer capturing audio.</p>
            </div>
          </header>
          {devices.length > 0 ? (
            <label className="recorder-device-field">
              <span>Desktop recorder</span>
              <select
                value={deviceId}
                onChange={(event) => setDeviceId(event.target.value)}
              >
                <option value="">Choose a recorder</option>
                {devices.map((item) => (
                  <option key={item.device_id} value={item.device_id}>
                    {`Recorder ${item.device_id.slice(0, 8)} · ${item.online ? item.state.replaceAll("_", " ") : "offline"}`}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p className="recorder-empty">
              Open the desktop app and sign in with this account. Your recorder
              will appear here.
            </p>
          )}
          {device && (
            <p className="recorder-device-note">
              {device.online
                ? `Status: ${device.state.replaceAll("_", " ")}`
                : "This recorder is offline."}
              {device.online && device.document_id && !thisMeeting
                ? " · Another meeting is selected."
                : ""}
            </p>
          )}
          <a className="button secondary" href="verelo-recorder://open">
            Open desktop recorder
          </a>
          <details className="recorder-help">
            <summary>Having trouble connecting?</summary>
            <p>
              Keep the desktop app open and signed in. The button opens it on
              this Windows computer; your browser may ask for confirmation. If
              nothing opens, check that the local desktop link is installed for
              your Windows account.
            </p>
          </details>
        </section>
        <section
          className="recorder-session-card"
          aria-label="Record your meeting"
        >
          <header className="recorder-step-heading">
            <span aria-hidden="true">02</span>
            <div>
              <h4>Record your meeting</h4>
              <p className="recorder-meeting-name">{document.title}</p>
            </div>
          </header>
          {recordingHere ? (
            <div
              className="recorder-live-state"
              role="status"
              data-recording={device?.online && device.state === "recording"}
            >
              <strong>
                <span aria-hidden="true" />
                {!device?.online
                  ? "Recorder offline"
                  : device.state === "recording"
                    ? "Recording in progress"
                    : device?.state === "paused"
                      ? "Recording paused"
                      : "Recording interrupted"}
              </strong>
              <p>
                {!device?.online
                  ? "Open the desktop recorder to check the recording. Its current status cannot be confirmed while offline."
                  : device.state === "interrupted"
                    ? "Check the desktop recorder to recover, or stop and process the captured audio."
                    : "Stop and process when you’re ready to prepare the transcript."}
              </p>
            </div>
          ) : (
            <label className="recorder-consent">
              <input
                type="checkbox"
                checked={consent}
                onChange={(event) => setConsent(event.target.checked)}
              />
              <span>
                <strong>Confirm recording consent</strong>
                <span>
                  I confirm the required recording consent for this meeting.
                </span>
              </span>
            </label>
          )}
          <div className="recorder-session-footer">
            {!recordingHere && (
              <p className="recorder-start-hint">{startHint}</p>
            )}
            <div className="recorder-actions">
              {!recordingHere && (
                <button
                  className="button primary"
                  disabled={!startable}
                  onClick={() => void send("start")}
                >
                  Start recording
                </button>
              )}
              {recordingHere && device?.state === "recording" && (
                <button
                  className="button secondary"
                  disabled={
                    !available || !thisMeeting || device?.state !== "recording"
                  }
                  onClick={() => void send("pause")}
                >
                  Pause
                </button>
              )}
              {recordingHere && device?.state === "paused" && (
                <button
                  className="button secondary"
                  disabled={
                    !available || !thisMeeting || device?.state !== "paused"
                  }
                  onClick={() => void send("resume")}
                >
                  Resume
                </button>
              )}
              {recordingHere && (
                <button
                  className="button primary"
                  disabled={
                    !available ||
                    !thisMeeting ||
                    !["recording", "paused", "interrupted"].includes(
                      device?.state ?? "",
                    )
                  }
                  onClick={() => void send("stop")}
                >
                  Stop and process
                </button>
              )}
            </div>
          </div>
        </section>
      </div>
      {message && (
        <p className="recorder-message" role="status">
          {message}
        </p>
      )}
    </section>
  );
}
