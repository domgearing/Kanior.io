import { initialApplicationStatus } from "./app-state";

export function App() {
  return (
    <main>
      <p className="eyebrow">KaniorAI</p>
      <h1>Transcript intelligence foundation</h1>
      <p>
        The web client is ready to connect to the authenticated API foundation.
      </p>
      <p className="status" role="status">
        {initialApplicationStatus}
      </p>
    </main>
  );
}
