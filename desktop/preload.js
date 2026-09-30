// Narrow, validated bridge. No filesystem, shell or Node primitives are exposed.
"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hvsDesktop", {
  token: () => ipcRenderer.invoke("hvs:token"),
  revealExport: (fileName) => (typeof fileName === "string" ? ipcRenderer.invoke("hvs:reveal-export", fileName) : Promise.resolve(false)),
  platform: process.platform,
});
