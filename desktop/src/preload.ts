import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("kaniorDesktop", {
  platform: process.platform,
});
