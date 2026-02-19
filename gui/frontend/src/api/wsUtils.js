export function collectUnknownKeys(payload, knownKeys = []) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return [];
  const known = new Set(knownKeys || []);
  return Object.keys(payload).filter((k) => !known.has(k));
}
