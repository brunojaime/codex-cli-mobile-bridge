import { loadQueue } from './core.js';

// IndexedDB avoids localStorage's small string quota. Each transaction commits
// the complete queue atomically; failed writes leave the previous queue intact.
export function createQueueStore(key, database = indexedDB, legacy = localStorage) {
  const db = new Promise((resolve, reject) => {
    const request = database.open('codex-developer-feedback', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('queues');
    request.onsuccess = () => { request.result.onversionchange = () => request.result.close(); resolve(request.result); };
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('Cerrá otras pestañas de la app y recargá para abrir la cola.'));
  });
  const transaction = async (mode, value) => {
    const connection = await db;
    return new Promise((resolve, reject) => {
      const tx = connection.transaction('queues', mode);
      const store = tx.objectStore('queues');
      const request = mode === 'readonly' ? store.get(key) : store.put(value, key);
      tx.oncomplete = () => resolve(request.result);
      tx.onabort = () => reject(tx.error || new Error('No se pudo guardar la cola.'));
      tx.onerror = () => {}; // onabort reports the transaction's final outcome.
    });
  };
  return {
    async load() {
      const existing = await transaction('readonly');
      if (existing !== undefined) return existing;
      const items = loadQueue(legacy, key);
      await transaction('readwrite', items);
      // Retain the legacy copy if removal is forbidden; IndexedDB is canonical.
      try { legacy.removeItem(key); } catch {}
      return items;
    },
    async save(items) {
      try { await transaction('readwrite', items); }
      catch (error) {
        if (error.name === 'QuotaExceededError') throw new Error('No queda espacio en este dispositivo. El recorrido sigue abierto: liberá espacio o enviá los pendientes antes de reintentar.');
        throw error;
      }
    },
    async close() { try { (await db).close(); } catch {} },
  };
}
