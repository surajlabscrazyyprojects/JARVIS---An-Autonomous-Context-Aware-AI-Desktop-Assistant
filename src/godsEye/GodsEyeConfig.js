/**
 * GodsEyeConfig — single source of truth for God's Eye endpoint
 * - Resolves from VITE_GODS_EYE_URL env, then default http://localhost:4173/
 * - Centralizes host/port/url/origin so no file hard-codes 4173 randomly
 */

export const GODS_EYE_DEFAULT_URL = 'http://localhost:4173/';
export const GODS_EYE_DEFAULT_PORT = 4173;
export const GODS_EYE_DEFAULT_HOST = 'localhost';

function envUrl() {
  try {
    if (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_GODS_EYE_URL) {
      return import.meta.env.VITE_GODS_EYE_URL;
    }
  } catch (_) {}
  return null;
}

export function resolveGodsEyeEndpoint() {
  const fromEnv = envUrl();
  const raw = fromEnv || GODS_EYE_DEFAULT_URL;
  try {
    const u = new URL(raw);
    const port = u.port ? parseInt(u.port, 10) : GODS_EYE_DEFAULT_PORT;
    const host = u.hostname || GODS_EYE_DEFAULT_HOST;
    const url = u.origin + '/';
    return { url, origin: u.origin, host, port, raw };
  } catch (_) {
    return { url: GODS_EYE_DEFAULT_URL, origin: 'http://localhost:4173', host: 'localhost', port: 4173, raw };
  }
}

export const GodsEyeConfig = resolveGodsEyeEndpoint();
export const GODS_EYE_URL = GodsEyeConfig.url;
export const GODS_EYE_ORIGIN = GodsEyeConfig.origin;
export const GODS_EYE_PORT = GodsEyeConfig.port;
export const GODS_EYE_HOST = GodsEyeConfig.host;
