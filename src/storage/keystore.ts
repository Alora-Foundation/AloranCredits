import type { KeystoreRecord } from '../lib/crypto/keystore.js';

const KEYSTORE_KEY = 'aloran.keystore';
let inMemoryFallback: KeystoreRecord | null = null;

type StorageLike = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

function resolveStorage(): StorageLike | null {
  if (typeof globalThis !== 'undefined' && 'localStorage' in globalThis) {
    return (globalThis as unknown as { localStorage: StorageLike }).localStorage;
  }
  return null;
}

export function saveKeystore(record: KeystoreRecord): void {
  const { ciphertext, salt, iv } = record;
  if (!ciphertext || !salt || !iv) {
    throw new Error('Keystore record must include ciphertext, salt, and iv');
  }

  const payload = JSON.stringify(record);
  const storage = resolveStorage();
  if (storage) {
    storage.setItem(KEYSTORE_KEY, payload);
  } else {
    inMemoryFallback = record;
  }
}

export function loadKeystore(): KeystoreRecord | null {
  const storage = resolveStorage();
  const storedValue = storage ? storage.getItem(KEYSTORE_KEY) : null;

  if (storedValue) {
    return JSON.parse(storedValue) as KeystoreRecord;
  }
  return inMemoryFallback;
}

export function clearKeystore(): void {
  const storage = resolveStorage();
  if (storage) {
    storage.removeItem(KEYSTORE_KEY);
  }
  inMemoryFallback = null;
}
