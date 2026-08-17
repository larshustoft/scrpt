const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("scrptDesktop", {
  toggleFullscreen: () => ipcRenderer.invoke("toggle-fullscreen"),
  isFullscreen: () => ipcRenderer.invoke("is-fullscreen"),
});
