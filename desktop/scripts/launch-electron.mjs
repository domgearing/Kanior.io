import { spawn } from "node:child_process";

import electronPath from "electron";

const { ELECTRON_RUN_AS_NODE: _electronRunAsNode, ...environment } =
  process.env;
const child = spawn(electronPath, [process.cwd()], {
  env: environment,
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error(`Unable to start Electron: ${error.message}`);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exitCode = code ?? 1;
});
