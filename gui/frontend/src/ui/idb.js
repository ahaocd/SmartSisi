function openDb() {
  return new Promise((resolve, reject) => {
    try {
      const req = indexedDB.open("smartsisi_ui", 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains("kv")) db.createObjectStore("kv");
      };
      req.onerror = () => reject(req.error || new Error("indexedDB open failed"));
      req.onsuccess = () => resolve(req.result);
    } catch (e) {
      reject(e);
    }
  });
}

export async function idbGet(key) {
  let db = null;
  try {
    db = await openDb();
    return await new Promise((resolve) => {
      const tx = db.transaction("kv", "readonly");
      const store = tx.objectStore("kv");
      const g = store.get(key);
      g.onerror = () => resolve(null);
      g.onsuccess = () => resolve(g.result ?? null);
      tx.oncomplete = () => resolve(g.result ?? null);
    });
  } catch {
    return null;
  } finally {
    try {
      db?.close?.();
    } catch {}
  }
}

export async function idbSet(key, value) {
  let db = null;
  try {
    db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction("kv", "readwrite");
      const store = tx.objectStore("kv");
      const p = store.put(value, key);
      p.onerror = () => reject(p.error || new Error("indexedDB put failed"));
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error || new Error("indexedDB tx failed"));
    });
    return true;
  } catch {
    return false;
  } finally {
    try {
      db?.close?.();
    } catch {}
  }
}

export async function idbDel(key) {
  let db = null;
  try {
    db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction("kv", "readwrite");
      const store = tx.objectStore("kv");
      const d = store.delete(key);
      d.onerror = () => reject(d.error || new Error("indexedDB delete failed"));
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error || new Error("indexedDB tx failed"));
    });
    return true;
  } catch {
    return false;
  } finally {
    try {
      db?.close?.();
    } catch {}
  }
}

