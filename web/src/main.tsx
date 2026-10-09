import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "../../verelo-design-system/tokens/tokens.css";
import "./controls.css";
import "./styles.css";
import "./polish.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Application root is missing.");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
