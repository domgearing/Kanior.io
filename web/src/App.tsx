import { Brand } from "./Brand";
import { useCallback, useEffect, useState } from "react";

import { resolvePreviewLocation } from "./app-state";
import { ConnectedApp } from "./ConnectedApp";

const apiBase =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : window.location.origin);

type View = "transcript" | "cleanup" | "source";
type Page = "home" | "project";
const northstarMeetings = [
  ["Expert interview — retail operations", "Sep 18", "Published", "42 min"],
  ["Customer discovery — onboarding", "Sep 16", "Review", "31 min"],
  ["Market landscape working session", "Sep 12", "Processing", "58 min"],
  ["Project kickoff", "Sep 8", "Published", "47 min"],
];
const projects = [
  {
    id: "northstar",
    name: "Northstar research",
    color: "blue",
    description: "Retail operations and multi-location workflow research",
    updated: "Today",
    meetings: northstarMeetings,
  },
  {
    id: "dovetail",
    name: "Dovetail study",
    color: "amber",
    description: "Fictional onboarding and adoption interviews",
    updated: "Sep 17",
    meetings: [
      ["Admin onboarding interview", "Sep 17", "Published", "36 min"],
      ["New user activation review", "Sep 14", "Review", "28 min"],
      ["Implementation partner call", "Sep 9", "Published", "51 min"],
    ],
  },
  {
    id: "market",
    name: "Market landscape",
    color: "green",
    description: "Competitive landscape and category development",
    updated: "Sep 15",
    meetings: [
      ["Category expert interview", "Sep 15", "Processing", "44 min"],
      ["Analyst landscape review", "Sep 11", "Published", "39 min"],
    ],
  },
];
const segments = [
  [
    "Maya Chen",
    "MC",
    "00:00",
    "Thanks for joining. I’d like to understand where operational complexity shows up most often as retail teams scale.",
  ],
  [
    "Alex Morgan",
    "AM",
    "00:14",
    "The biggest shift happens around the fifteenth location. Before that, the regional manager can usually keep the exceptions in their head.",
  ],
  [
    "Alex Morgan",
    "AM",
    "00:29",
    "After fifteen locations, inventory transfers and staffing approvals become much harder to coordinate. It is not just more volume; there are more dependencies between stores.",
  ],
  [
    "Maya Chen",
    "MC",
    "00:48",
    "What does that look like during a normal week?",
  ],
  [
    "Alex Morgan",
    "AM",
    "00:53",
    "Monday starts with a spreadsheet review. By Wednesday, the spreadsheet is already behind because managers have resolved urgent issues in email and chat.",
  ],
  [
    "Alex Morgan",
    "AM",
    "01:11",
    "The important point is that the process does not fail all at once. Confidence erodes gradually, and teams build their own parallel tracking systems.",
  ],
];

function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    home: (
      <>
        <path d="M3 11.5 12 4l9 7.5" />
        <path d="M5 10v10h14V10" />
      </>
    ),
    folder: <path d="M3 6h7l2 2h9v11H3z" />,
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V4m0 0L7 9m5-5 5 5" />
        <path d="M4 15v5h16v-5" />
      </>
    ),
    mic: (
      <>
        <rect x="9" y="3" width="6" height="12" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      </>
    ),
    dots: (
      <>
        <circle cx="5" cy="12" r="1" fill="currentColor" />
        <circle cx="12" cy="12" r="1" fill="currentColor" />
        <circle cx="19" cy="12" r="1" fill="currentColor" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    shield: <path d="M12 3 5 6v5c0 4.5 2.9 8.1 7 10 4.1-1.9 7-5.5 7-10V6z" />,
    play: <path d="m9 7 8 5-8 5z" fill="currentColor" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
  };
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

export function App() {
  return <AuthenticatedApp />;
}

function AuthenticatedApp() {
  const [authMode, setAuthMode] = useState<
    "dev_password" | "magic_link" | "entra" | null
  >(null);
  const [status, setStatus] = useState<"checking" | "signed-out" | "signed-in">(
    "checking",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const handleSignedOut = useCallback(() => setStatus("signed-out"), []);

  useEffect(() => {
    const token = window.location.hash.startsWith("#token=")
      ? decodeURIComponent(window.location.hash.slice(7))
      : null;
    const finish = async () => {
      const modeResponse = await fetch(`${apiBase}/api/v1/auth/mode`);
      if (!modeResponse.ok) throw new Error("auth_mode_unavailable");
      const mode = (await modeResponse.json()) as {
        provider: "dev_password" | "magic_link" | "entra";
      };
      setAuthMode(mode.provider);
      if (window.location.search.includes("sign_in_error=1")) {
        window.history.replaceState(null, "", window.location.pathname);
        setMessage(
          "Microsoft sign-in was not accepted. Check that your employee account is assigned to Verelo.",
        );
      }
      if (token) {
        const response = await fetch(
          `${apiBase}/api/v1/auth/magic-link/consume`,
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token }),
          },
        );
        window.history.replaceState(null, "", "#home");
        if (!response.ok) {
          setMessage("That sign-in link is invalid or has expired.");
          setStatus("signed-out");
          return;
        }
      }
      const response = await fetch(`${apiBase}/api/v1/me`, {
        credentials: "include",
      });
      setStatus(response.ok ? "signed-in" : "signed-out");
    };
    void finish().catch(() => {
      setMessage("The Verelo API is unavailable.");
      setStatus("signed-out");
    });
  }, []);

  if (status === "checking") {
    return <div className="auth-loading">Checking your Verelo session…</div>;
  }
  if (status === "signed-in") {
    return <ConnectedApp onSignedOut={handleSignedOut} />;
  }

  const requestLink = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage("");
    try {
      const response = await fetch(
        `${apiBase}/api/v1/auth/magic-link/request`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        },
      );
      setMessage(
        response.ok
          ? "If this employee account is enabled, a sign-in link is now in the local development mailbox."
          : "The sign-in request could not be accepted.",
      );
    } catch {
      setMessage("The Verelo API is unavailable.");
    }
  };
  const requestPassword = async (
    event: React.MouseEvent<HTMLButtonElement>,
  ) => {
    if (
      !event.currentTarget.form
        ?.querySelector<HTMLInputElement>("#employee-email")
        ?.reportValidity()
    )
      return;
    setMessage("");
    setPassword("");
    try {
      const response = await fetch(
        `${apiBase}/api/v1/auth/dev-password/request`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        },
      );
      setMessage(
        response.ok
          ? "If this employee account is enabled, a one-time password is in the local development mailbox."
          : "The password request could not be accepted.",
      );
    } catch {
      setMessage("The Verelo API is unavailable.");
    }
  };
  const signInWithPassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage("");
    try {
      const response = await fetch(
        `${apiBase}/api/v1/auth/dev-password/consume`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        },
      );
      if (!response.ok) {
        setMessage(
          "That email or one-time password is invalid or has expired.",
        );
        return;
      }
      setPassword("");
      setStatus("signed-in");
    } catch {
      setMessage("The Verelo API is unavailable.");
    }
  };
  return (
    <main className="auth-page">
      <aside className="auth-story" aria-label="About Verelo">
        <span className="auth-eyebrow">Your research, in focus</span>
        <h2>
          Every conversation.
          <br />A clearer perspective.
        </h2>
        <p>
          Bring your interviews together. Review transcripts, keep the source in
          sight, and build on what was actually said.
        </p>
        <ol className="auth-steps">
          <li>
            <span>01</span>
            <div>
              <strong>Capture the conversation</strong>
              <p>Record a call or import a transcript.</p>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <strong>Review with context</strong>
              <p>Read, listen, and prepare your transcript.</p>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <strong>Keep your research organized</strong>
              <p>One shared workspace for each project.</p>
            </div>
          </li>
        </ol>
        <small>Verelo · Transcript intelligence</small>
      </aside>
      <section className="auth-card">
        <Brand />
        <small>Employee access</small>
        <h1>Sign in to your workspace</h1>
        {authMode === "entra" ? (
          <>
            <p>Sign in with your assigned company Microsoft account.</p>
            <button
              className="button primary"
              onClick={() =>
                window.location.assign(`${apiBase}/api/v1/auth/entra/start`)
              }
            >
              Sign in with Microsoft
            </button>
          </>
        ) : authMode === "dev_password" ? (
          <>
            <p>
              Use an approved employee email. Request a one-time password, then
              copy it from the local development mailbox. It expires after 10
              minutes.
            </p>
            <form onSubmit={(event) => void signInWithPassword(event)}>
              <label htmlFor="employee-email">Work email</label>
              <input
                id="employee-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="employee@example.com"
              />
              <label htmlFor="employee-password">One-time password</label>
              <input
                id="employee-password"
                type="password"
                required
                autoComplete="one-time-code"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button className="button primary" type="submit">
                Sign in
              </button>
              <button
                className="button secondary"
                type="button"
                onClick={(event) => void requestPassword(event)}
              >
                Get one-time password
              </button>
            </form>
          </>
        ) : (
          <>
            <p>
              Enter an email address that an administrator has explicitly
              approved.
            </p>
            <form onSubmit={requestLink}>
              <label htmlFor="employee-email">Work email</label>
              <input
                id="employee-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="employee@example.com"
              />
              <button className="button primary" type="submit">
                Send sign-in link
              </button>
            </form>
          </>
        )}
        {message && (
          <div className="auth-message" role="status">
            {message}
          </div>
        )}
        <footer>
          {authMode === "entra"
            ? "Company employee access"
            : authMode === "dev_password"
              ? "Local development only · No public signup"
              : "Development magic link · No public signup"}
        </footer>
      </section>
    </main>
  );
}

export function ProductApp({ onSignedOut }: { onSignedOut: () => void }) {
  const initialLocation = resolvePreviewLocation(window.location.hash);
  const initialProject =
    initialLocation.page === "project" ? initialLocation.projectId : undefined;
  const [page, setPage] = useState<Page>(initialLocation.page);
  const [projectId, setProjectId] = useState(
    projects.some((item) => item.id === initialProject)
      ? initialProject!
      : "northstar",
  );
  const [view, setView] = useState<View>("transcript");
  const [modal, setModal] = useState<"record" | "import" | null>(null);
  const [published, setPublished] = useState(false);
  const [selected, setSelected] = useState(1);
  const project = projects.find((item) => item.id === projectId) ?? projects[0];
  const meetings = project.meetings;
  const showProject = (id: string, updateHistory = true) => {
    setProjectId(id);
    setSelected(0);
    setView("transcript");
    setPublished(false);
    setPage("project");
    if (updateHistory) window.history.pushState(null, "", `#projects/${id}`);
  };
  const openProject = (id: string) => showProject(id);
  const showHome = (updateHistory = true) => {
    setPage("home");
    if (updateHistory) window.history.pushState(null, "", "#home");
  };
  const openHome = () => showHome();
  const signOut = async () => {
    const me = await fetch(`${apiBase}/api/v1/me`, { credentials: "include" });
    if (me.ok) {
      const current = (await me.json()) as { csrf_token: string };
      await fetch(`${apiBase}/api/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": current.csrf_token },
      });
    }
    onSignedOut();
  };
  useEffect(() => {
    const restoreLocation = () => {
      const location = resolvePreviewLocation(window.location.hash);
      const id = location.page === "project" ? location.projectId : undefined;
      if (id && projects.some((item) => item.id === id)) {
        setProjectId(id);
        setSelected(0);
        setView("transcript");
        setPage("project");
      } else {
        setPage("home");
      }
    };
    window.addEventListener("popstate", restoreLocation);
    return () => window.removeEventListener("popstate", restoreLocation);
  }, []);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <nav>
          <button
            className={page === "home" ? "active" : ""}
            onClick={openHome}
          >
            <Icon name="home" />
            Home
          </button>
          <button
            className={page === "project" ? "active" : ""}
            onClick={() => openProject(projectId)}
          >
            <Icon name="folder" />
            Projects
          </button>
          <button title="Available in Phase 3" disabled>
            <Icon name="search" />
            Evidence search
          </button>
        </nav>
        <div className="project-nav">
          <label>
            Projects <b title="Project creation uses the authorized API">+</b>
          </label>
          {projects.map((item) => (
            <button
              className={
                page === "project" && projectId === item.id ? "active" : ""
              }
              onClick={() => openProject(item.id)}
              key={item.id}
            >
              <i className={item.color} />
              {item.name}
            </button>
          ))}
        </div>
        <div className="sidebar-foot">
          <div className="preview">
            <i />
            Synthetic preview
          </div>
          <div className="profile">
            <span>DG</span>
            <div>
              <strong>Dominic Gearing</strong>
              <small>Project owner</small>
            </div>
            <Icon name="dots" />
          </div>
          <button className="signout" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      </aside>
      {page === "home" ? (
        <Home
          projects={projects}
          onOpenProject={openProject}
          onImport={() => setModal("import")}
          onRecord={() => setModal("record")}
        />
      ) : (
        <main className="workspace">
          <header className="topbar">
            <div>
              <p>
                <button className="crumb" onClick={openHome}>
                  Projects
                </button>{" "}
                <b>/</b> {project.name}
              </p>
              <h1>{project.name}</h1>
            </div>
            <div>
              <button
                className="button secondary"
                onClick={() => setModal("import")}
              >
                <Icon name="upload" />
                Import
              </button>
              <button
                className="button primary"
                onClick={() => setModal("record")}
              >
                <Icon name="mic" />
                Record meeting
              </button>
            </div>
          </header>
          <div className="grid">
            <section className="meetings">
              <header>
                <div>
                  <h2>Meetings</h2>
                  <p>{meetings.length} recordings · Synthetic workspace</p>
                </div>
                <Icon name="dots" />
              </header>
              <label className="search">
                <Icon name="search" />
                <input placeholder="Search meetings" />
              </label>
              {meetings.map((m, i) => (
                <button
                  className={`meeting ${selected === i ? "selected" : ""}`}
                  onClick={() => setSelected(i)}
                  key={m[0]}
                >
                  <time>
                    <strong>{m[1].split(" ")[1]}</strong>
                    <small>{m[1].split(" ")[0]}</small>
                  </time>
                  <div>
                    <strong>{m[0]}</strong>
                    <p>
                      <i className={m[2].toLowerCase()} />
                      {m[2]} · {m[3]}
                    </p>
                  </div>
                </button>
              ))}
            </section>
            <section className="document">
              <header className="doc-header">
                <div>
                  <p className="kicker">
                    <i />
                    Ready for review
                  </p>
                  <h2>{meetings[selected][0]}</h2>
                  <small>September 16, 2026 · 10:04 AM · English (US)</small>
                </div>
                <Icon name="dots" />
              </header>
              <div className="tabs">
                {(["transcript", "cleanup", "source"] as View[]).map((t) => (
                  <button
                    className={view === t ? "active" : ""}
                    onClick={() => setView(t)}
                    key={t}
                  >
                    {t === "cleanup"
                      ? "Cleanup review"
                      : t[0].toUpperCase() + t.slice(1)}
                    {t === "cleanup" && <b>3</b>}
                  </button>
                ))}
              </div>
              {view === "transcript" && (
                <div className="scroll">
                  <div className="audio">
                    <button>
                      <Icon name="play" />
                    </button>
                    <small>00:00</small>
                    <div>
                      {Array.from({ length: 48 }, (_, i) => (
                        <i
                          style={{ height: `${7 + ((i * 11) % 20)}px` }}
                          key={i}
                        />
                      ))}
                    </div>
                    <small>31:24</small>
                    <b>1×</b>
                  </div>
                  <div className="meta">
                    617 words <i /> 2 speakers <i /> Version 1 draft{" "}
                    <button>Find in transcript ⌘F</button>
                  </div>
                  <div className="segments">
                    {segments.map((s, i) => (
                      <article key={i}>
                        <span className={s[1] === "AM" ? "orange" : "blue-bg"}>
                          {s[1]}
                        </span>
                        <div>
                          <header>
                            <strong>{s[0]}</strong>
                            <button>{s[2]}</button>
                          </header>
                          <p>{s[3]}</p>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              )}
              {view === "cleanup" && (
                <div className="scroll cleanup">
                  <div className="policy">
                    <Icon name="shield" />
                    <div>
                      <strong>Controlled cleanup policy v2</strong>
                      <p>
                        3 changes passed deterministic validation. Names,
                        numbers, negation, modality and punctuation are
                        protected.
                      </p>
                    </div>
                  </div>
                  <Change
                    rule="Filler removal"
                    text={
                      <>
                        <del>Um </del>Monday starts with a spreadsheet review.
                      </>
                    }
                    note="Allowed token ‘um’ removed · 00:53"
                  />
                  <Change
                    rule="Stutter deduplication"
                    text={
                      <>
                        The important point is <del>that </del>that the process
                        does not fail all at once.
                      </>
                    }
                    note="Adjacent allowlisted token deduplicated · 01:11"
                  />
                  <Change
                    rule="Formatting"
                    text={<>Normalized line endings and trailing whitespace.</>}
                    note="No source characters changed"
                  />
                </div>
              )}
              {view === "source" && (
                <div className="scroll source">
                  <h3>Source provenance</h3>
                  <dl>
                    <Row a="Import type" b="Transcript JSON" />
                    <Row
                      a="Original asset"
                      b="customer-discovery.synthetic.json"
                    />
                    <Row a="SHA-256" b="6a938f…e124" />
                    <Row a="Parser" b="verelo-transcript-v1" />
                    <Row
                      a="Audio provenance"
                      b="Unavailable — transcript import"
                    />
                  </dl>
                  <div className="verified">
                    <Icon name="check" />
                    <div>
                      <strong>Integrity verified</strong>
                      <p>
                        Canonical text can be reproduced from immutable internal
                        records.
                      </p>
                    </div>
                  </div>
                </div>
              )}
              <footer className="review">
                <div>
                  <strong>
                    {published
                      ? "Published as version 1"
                      : "All automated changes validated"}
                  </strong>
                  <small>
                    {published
                      ? "Canonical transcript is immutable"
                      : "Ready for controlled-policy approval"}
                  </small>
                </div>
                <button className="button secondary">Request changes</button>
                <button
                  className="button primary"
                  disabled={published}
                  onClick={() => setPublished(true)}
                >
                  <Icon name="check" />
                  {published ? "Published" : "Approve & publish"}
                </button>
              </footer>
            </section>
            <aside className="details">
              <section>
                <h3>Processing</h3>
                {[
                  "Source preserved",
                  "Transcript parsed",
                  "Cleanup validated",
                ].map((x) => (
                  <div className="step done" key={x}>
                    <span>
                      <Icon name="check" />
                    </span>
                    <p>
                      <strong>{x}</strong>
                      <small>Complete</small>
                    </p>
                  </div>
                ))}
                <div className="step current">
                  <span>4</span>
                  <p>
                    <strong>Approval</strong>
                    <small>{published ? "Complete" : "Awaiting review"}</small>
                  </p>
                </div>
                <div className="step">
                  <span>5</span>
                  <p>
                    <strong>Indexing</strong>
                    <small>{published ? "Queued" : "After publication"}</small>
                  </p>
                </div>
              </section>
              <section>
                <h3>Integrity</h3>
                <div className="integrity">
                  <Icon name="shield" />
                  <strong>Source protected</strong>
                  <p>
                    Raw import and canonical draft are immutable, hash-verified
                    artifacts.
                  </p>
                </div>
              </section>
              <section>
                <h3>Participants</h3>
                <Person initials="MC" name="Maya Chen" role="Interviewer" />
                <Person
                  initials="AM"
                  name="Alex Morgan"
                  role="Anonymous speaker A"
                />
              </section>
            </aside>
          </div>
        </main>
      )}
      {modal && (
        <div className="backdrop" onMouseDown={() => setModal(null)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <button className="x" onClick={() => setModal(null)}>
              <Icon name="close" />
            </button>
            <div className="modal-icon">
              <Icon name={modal === "record" ? "mic" : "upload"} />
            </div>
            <small>Synthetic workflow</small>
            <h2>
              {modal === "record" ? "Record a meeting" : "Import a source"}
            </h2>
            <p>
              {modal === "record"
                ? "Preview the complete recorder flow without connecting Recall. Interruptions and upload acknowledgements behave like the production adapter."
                : "Use a fictional TXT, VTT, SRT, JSON, WAV, MP3, M4A or WebM file. It stays in your local development environment."}
            </p>
            {modal === "record" ? (
              <div className="device">
                <i />
                <div>
                  <strong>Synthetic mixed audio</strong>
                  <small>Local and remote channels · Ready</small>
                </div>
                <b>▂▅▇▄▆</b>
              </div>
            ) : (
              <label className="drop">
                <Icon name="upload" />
                <strong>Choose a fictional file</strong>
                <small>or drag it here · Maximum 20 MB transcript</small>
                <input type="file" />
              </label>
            )}
            <footer>
              <button
                className="button secondary"
                onClick={() => setModal(null)}
              >
                Cancel
              </button>
              <button className="button primary" onClick={() => setModal(null)}>
                {modal === "record"
                  ? "Start synthetic recording"
                  : "Import source"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}

function Home({
  projects: items,
  onOpenProject,
  onImport,
  onRecord,
}: {
  projects: typeof projects;
  onOpenProject: (id: string) => void;
  onImport: () => void;
  onRecord: () => void;
}) {
  const totalMeetings = items.reduce(
    (total, item) => total + item.meetings.length,
    0,
  );
  return (
    <main className="workspace home-page">
      <header className="topbar home-topbar">
        <div>
          <p>Workspace overview</p>
          <h1>Good afternoon, Dominic</h1>
        </div>
        <div>
          <button className="button secondary" onClick={onImport}>
            <Icon name="upload" />
            Import
          </button>
          <button className="button primary" onClick={onRecord}>
            <Icon name="mic" />
            Record meeting
          </button>
        </div>
      </header>
      <div className="home-content">
        <section className="overview-cards" aria-label="Workspace totals">
          <article>
            <small>Active projects</small>
            <strong>{items.length}</strong>
            <p>All synthetic and locally isolated</p>
          </article>
          <article>
            <small>Meetings</small>
            <strong>{totalMeetings}</strong>
            <p>Across your permitted projects</p>
          </article>
          <article>
            <small>Awaiting review</small>
            <strong>2</strong>
            <p>Meaning-preserving cleanup validated</p>
          </article>
          <article>
            <small>Published versions</small>
            <strong>5</strong>
            <p>Immutable and ready for indexing</p>
          </article>
        </section>
        <section className="home-projects">
          <header>
            <div>
              <h2>Your projects</h2>
              <p>
                Open a project to review its recordings and transcript versions.
              </p>
            </div>
            <small>Synthetic data</small>
          </header>
          <div className="project-cards">
            {items.map((item) => (
              <button onClick={() => onOpenProject(item.id)} key={item.id}>
                <span className={`project-mark ${item.color}`} />
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.description}</p>
                  <small>
                    {item.meetings.length} meetings · Updated {item.updated}
                  </small>
                </div>
                <b aria-hidden="true">→</b>
              </button>
            ))}
          </div>
        </section>
        <section className="recent-work">
          <header>
            <div>
              <h2>Recent activity</h2>
              <p>
                Processing and publication activity across permitted projects.
              </p>
            </div>
          </header>
          <button onClick={() => onOpenProject("northstar")}>
            <span className="activity-icon">
              <Icon name="check" />
            </span>
            <div>
              <strong>Expert interview — retail operations</strong>
              <small>Published in Northstar research · Today</small>
            </div>
            <em>Published</em>
          </button>
          <button onClick={() => onOpenProject("dovetail")}>
            <span className="activity-icon review">
              <Icon name="shield" />
            </span>
            <div>
              <strong>New user activation review</strong>
              <small>Cleanup validated in Dovetail study · Sep 14</small>
            </div>
            <em className="review">Review</em>
          </button>
        </section>
      </div>
    </main>
  );
}

function Change({
  rule,
  text,
  note,
}: {
  rule: string;
  text: React.ReactNode;
  note: string;
}) {
  return (
    <div className="change">
      <header>
        <b>{rule}</b>
        <small>Validated change</small>
      </header>
      <p>{text}</p>
      <small>{note}</small>
    </div>
  );
}
function Row({ a, b }: { a: string; b: string }) {
  return (
    <div>
      <dt>{a}</dt>
      <dd>{b}</dd>
    </div>
  );
}
function Person({
  initials,
  name,
  role,
}: {
  initials: string;
  name: string;
  role: string;
}) {
  return (
    <div className="person">
      <span className={initials === "AM" ? "orange" : "blue-bg"}>
        {initials}
      </span>
      <p>
        <strong>{name}</strong>
        <small>{role}</small>
      </p>
    </div>
  );
}
