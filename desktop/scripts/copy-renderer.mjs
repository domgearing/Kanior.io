import { cp, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const directory = dirname(fileURLToPath(import.meta.url));
const packageDirectory = resolve(directory, "..");
const source = resolve(packageDirectory, "renderer");
const destination = resolve(packageDirectory, "dist", "renderer");

await mkdir(destination, { recursive: true });
await cp(source, destination, { recursive: true });
// Ship the same local fonts, logos and tokens as the web app, including licenses.
await cp(
  resolve(packageDirectory, "../verelo-design-system"),
  resolve(destination, "design-system"),
  { recursive: true },
);
await cp(
  resolve(packageDirectory, "../web/src/controls.css"),
  resolve(destination, "controls.css"),
);
