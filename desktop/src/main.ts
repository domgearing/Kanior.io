import { app, BrowserWindow } from "electron";
import path from "node:path";

import { desktopApplicationName } from "./app-info";

const createWindow = () => {
  const window = new BrowserWindow({
    width: 960,
    height: 720,
    minWidth: 720,
    minHeight: 540,
    title: desktopApplicationName,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  void window.loadFile(path.join(__dirname, "renderer", "index.html"));
};

app.whenReady().then(() => {
  app.setName(desktopApplicationName);
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
