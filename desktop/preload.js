const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("scrptDesktop", {
  toggleFullscreen: () => ipcRenderer.invoke("toggle-fullscreen"),
  isFullscreen: () => ipcRenderer.invoke("is-fullscreen"),

  // the big screen: an external monitor becomes SCRPT's cinema
  cinemaAvailable: () => ipcRenderer.invoke("cinema-available"),
  cinemaPlay: (src, time) => ipcRenderer.invoke("cinema-play", { src, time }),
  cinemaPause: () => ipcRenderer.invoke("cinema-pause"),
  cinemaSeek: (time) => ipcRenderer.invoke("cinema-seek", { time }),
  cinemaVolume: (volume, muted) => ipcRenderer.invoke("cinema-volume", { volume, muted }),
  cinemaStop: () => ipcRenderer.invoke("cinema-stop"),
  onCinemaAvailability: (cb) => {
    const h = (_e, available) => cb(Boolean(available));
    ipcRenderer.on("cinema:availability", h);
    return () => ipcRenderer.removeListener("cinema:availability", h);
  },
});
