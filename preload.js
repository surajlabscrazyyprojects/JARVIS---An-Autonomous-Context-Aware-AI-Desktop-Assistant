/**
 * JARVIS preload — isolated bridge for Spidey Tracker WebContentsView
 * - nodeIntegration: false, contextIsolation: true, sandbox: true
 * - exposes only spideyTracker IPC, no Node APIs
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node
  },
  spideyTracker: {
    create: () => ipcRenderer.invoke('spidey:create'),
    show: (bounds) => ipcRenderer.invoke('spidey:show', bounds),
    hide: () => ipcRenderer.invoke('spidey:hide'),
    setBounds: (bounds) => ipcRenderer.invoke('spidey:setBounds', bounds),
    load: (url) => ipcRenderer.invoke('spidey:load', url),
    reload: () => ipcRenderer.invoke('spidey:reload'),
    destroy: () => ipcRenderer.invoke('spidey:destroy'),
    getState: () => ipcRenderer.invoke('spidey:getState'),
    onEvent: (callback) => {
      const handler = (_e, data) => {
        try { callback(data); } catch (err) { console.error('[preload] spidey event callback error', err); }
      };
      ipcRenderer.on('spidey:event', handler);
      return () => ipcRenderer.removeListener('spidey:event', handler);
    },
    getWindowBounds: () => ipcRenderer.invoke('spidey:getWindowBounds')
  },
  godsEye: {
    create: () => ipcRenderer.invoke('godsEye:create'),
    show: (bounds) => ipcRenderer.invoke('godsEye:show', bounds),
    hide: () => ipcRenderer.invoke('godsEye:hide'),
    setBounds: (bounds) => ipcRenderer.invoke('godsEye:setBounds', bounds),
    load: (url) => ipcRenderer.invoke('godsEye:load', url),
    reload: () => ipcRenderer.invoke('godsEye:reload'),
    destroy: () => ipcRenderer.invoke('godsEye:destroy'),
    getState: () => ipcRenderer.invoke('godsEye:getState'),
    getRuntime: () => ipcRenderer.invoke('godsEye:getRuntime'),
    healthCheck: () => ipcRenderer.invoke('godsEye:healthCheck'),
    ensureStarted: (opts) => ipcRenderer.invoke('godsEye:ensureStarted', opts),
    startServer: () => ipcRenderer.invoke('godsEye:startServer'),
    stop: () => ipcRenderer.invoke('godsEye:stop'),
    openExternal: (url) => ipcRenderer.invoke('godsEye:openExternal', url),
    onEvent: (callback) => {
      const handler = (_e, data) => {
        try { callback(data); } catch (err) { console.error('[preload] godsEye event error', err); }
      };
      ipcRenderer.on('godsEye:event', handler);
      return () => ipcRenderer.removeListener('godsEye:event', handler);
    }
  }
});

// Also expose a minimal isElectron flag without needing preload race
// Keep legacy detection compatible
try {
  window.addEventListener('DOMContentLoaded', () => {
    document.documentElement.setAttribute('data-electron', 'true');
  });
} catch (_) {}
