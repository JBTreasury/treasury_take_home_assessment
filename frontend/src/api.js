
const API_BASE = (import.meta.env.VITE_API_BASE || "/api").replace(/\/$/, "");

export const apiUrl = (path) => `${API_BASE}${path}`;
