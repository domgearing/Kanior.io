import { useEffect, useState } from "react";
import { lifecyclePosition, lifecycleSteps, safeProcessingMessage } from "./ingestion-lifecycle";

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

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
  if (!response.ok) throw new Error(`Verelo API returned HTTP ${response.status}. Please check your connection or ask an administrator if it persists.`);
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
        <div className="brand">
          <span>K</span>Verelo
        </div>
        <button
          className={page === "home" ? "active" : ""}
          onClick={() => setPage("home")}
        >
          Home
        </button>
        <button
          className={page === "profile" ? "active" : ""}
          onClick={() => setPage("profile")}
        >
          My profile
        </button>
        <label>YOUR PROJECTS</label>
        {projects.map((project) => (
          <button
            key={project.project_id}
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
          <small>PERSONAL WORKSPACE</small>
          <h1>Welcome, {me.display_name.split(" ")[0]}</h1>
          <p>Only projects assigned to this account appear here.</p>
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
            <p>You will become its project owner.</p>
          </div>
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Project name"
          />
          <button className="button primary">Create project</button>
        </form>
      )}
      <section className="connected-list">
        <h2>Your projects</h2>
        {projects.length === 0 ? (
          <p>No project memberships have been assigned yet.</p>
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
        <small>ACCOUNT</small>
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
          Your permissions are enforced by the API and PostgreSQL membership
          policies.
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
              placeholder="Meeting or interview title"
            />
            <button className="button primary">Create meeting</button>
          </form>
        )}
        {documents.length === 0 ? (
          <p>No documents are visible in this project yet.</p>
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
            <button className="button primary">Grant access</button>
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
  const [correction, setCorrection] = useState("");
  const [status, setStatus] = useState("");
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
    void refresh();
    // The document identifier is the intended refresh boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document.document_id]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void request<{ items: Ingestion[] }>(
        `/api/v1/documents/${document.document_id}/ingestions`,
      ).then(async (page) => {
        setIngestions(page.items);
        const current = page.items.find(
          (item) => item.ingestion_id === selected?.ingestion_id,
        );
        if (!current) return;
        setSelected(current);
        if (current.draft_sha256 && current.draft_sha256 !== draft?.content_sha256) {
          const value = await request<Draft>(
            `/api/v1/ingestions/${current.ingestion_id}/draft`,
          );
          setDraft(value);
          setCorrection(value.canonical_text);
        }
      }).catch(() => setStatus("Could not refresh processing status. Check the API connection."));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [document.document_id, selected?.ingestion_id, draft?.content_sha256]);

  const openIngestion = async (item: Ingestion) => {
    setSelected(item);
    if (item.draft_sha256) {
      const value = await request<Draft>(
        `/api/v1/ingestions/${item.ingestion_id}/draft`,
      );
      setDraft(value);
      setCorrection(value.canonical_text);
    } else setDraft(null);
  };
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
      { method: "POST", headers, body: JSON.stringify({ operation_key: `web-retry-${crypto.randomUUID()}` }) },
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
    setStatus("Published. TXT, Markdown, and JSON downloads are ready.");
    await refresh();
  };
  const download = async (format: "txt" | "md" | "json") => {
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

  return (
    <section className="ingestion-workspace">
      <header>
        <div>
          <small>TRANSCRIPT WORKSPACE</small>
          <h2>{document.title}</h2>
        </div>
        <button onClick={close}>Close</button>
      </header>
      {role !== "reader" && (
        <form className="source-upload" onSubmit={(event) => void upload(event).catch((error: unknown) =>
          setStatus(error instanceof Error ? error.message : "Upload failed. Please try again."))}>
          <input
            name="source"
            type="file"
            required
            accept=".wav,.mp3,.m4a,.webm,.txt,.vtt,.srt,.json"
          />
          <button className="button primary">Upload and process</button>
        </form>
      )}
      {status && <p className="access-notice">{status}</p>}
      <div className="workflow-grid">
        <nav>
          {ingestions.map((item) => (
            <button
              key={item.ingestion_id}
              onClick={() => void openIngestion(item)}
            >
              <strong>
                {item.source_kind === "audio" ? "Audio" : "Transcript"}
              </strong>
              <small>{item.state.replaceAll("_", " ")}</small>
              <small>{new Date(item.created_at).toLocaleString()}</small>
            </button>
          ))}
          {ingestions.length === 0 && <p>No sources uploaded yet.</p>}
        </nav>
        <article className="draft-view">
          {selected && (
            <div className="processing-status" role="status">
              <strong>{selected.state.replaceAll("_", " ")}</strong>
              <span>Stage: {selected.stage.replaceAll("_", " ")}</span>
              {selected.state === "source_pending" && (
                <span>{Math.floor(100 * selected.uploaded_bytes / selected.expected_bytes)}% uploaded</span>
              )}
              {selected.safe_error_code && <span>{safeProcessingMessage(selected.safe_error_code)}</span>}
              <ol className="lifecycle-steps" aria-label="Recording and transcript progress">
                {lifecycleSteps.map((step, index) => (
                  <li key={step.id} className={
                    selected.state === "aborted" ? "pending"
                      : index < lifecyclePosition(selected.state, selected.stage) ? "complete"
                        : index === lifecyclePosition(selected.state, selected.stage) ? "current" : "pending"
                  }>{selected.source_kind === "transcript" && step.id === "upload"
                    ? "Uploading transcript"
                    : selected.source_kind === "transcript" && step.id === "storage"
                      ? "Storing transcript in Verelo"
                      : step.label}</li>
                ))}
              </ol>
              {selected.can_retry && role !== "reader" && (
                <button className="button" onClick={() => void retry().catch((error: unknown) =>
                  setStatus(error instanceof Error ? error.message : "Retry failed."))}>Retry processing</button>
              )}
            </div>
          )}
          {!draft ? (
            <p>{selected?.safe_error_code
              ? "Processing stopped. Review the issue above and retry if available."
              : selected
                ? "Transcript processing is underway. This view refreshes automatically."
                : "Select a source to review its transcript."}</p>
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
              {draft.segments.some(
                (segment) => segment.speaker_label || segment.start_ms !== null,
              ) && (
                <div className="organized-transcript" aria-label="Speaker-organized transcript">
                  {draft.segments.map((segment, index) => (
                    <section key={`${segment.start_ms ?? "untimed"}-${index}`}>
                      <div className="speaker-line">
                        <strong>{speakerName(segment.speaker_label)}</strong>
                        {transcriptTime(segment.start_ms) && (
                          <time>{transcriptTime(segment.start_ms)}</time>
                        )}
                      </div>
                      <p>{segment.text}</p>
                    </section>
                  ))}
                </div>
              )}
              {role === "project_owner" && selected?.state !== "published" ? (
                <textarea
                  className="draft-editor"
                  value={correction}
                  onChange={(event) => setCorrection(event.target.value)}
                  aria-label="Transcript correction editor"
                />
              ) : !draft.segments.some(
                  (segment) => segment.speaker_label || segment.start_ms !== null,
                ) ? (
                <pre>{draft.canonical_text}</pre>
              ) : null}
              {role === "project_owner" &&
                selected?.state !== "published" &&
                correction !== draft.canonical_text && (
                  <button
                    className="button"
                    onClick={() => void saveCorrection()}
                  >
                    Save immutable correction
                  </button>
                )}
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
                  <button onClick={() => void download("md")}>Markdown</button>
                  <button onClick={() => void download("json")}>JSON</button>
                </div>
              )}
            </>
          )}
        </article>
      </div>
    </section>
  );
}
