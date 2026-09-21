import { cp, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const directory = dirname(fileURLToPath(import.meta.url));
const packageDirectory = resolve(directory, "..");
const source = resolve(packageDirectory, "renderer");
const destination = resolve(packageDirectory, "dist", "renderer");

await mkdir(destination, { recursive: true });
await cp(source, destination, { recursive: true });
