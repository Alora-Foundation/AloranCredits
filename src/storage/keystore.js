const KEYSTORE_KEY = 'aloran.keystore';
let inMemoryFallback = null;

function resolveStorage() {
  if (typeof globalThis !== 'undefined' && 'localStorage' in globalThis) {
    return globalThis.localStorage;
  }
  return null;
}

export function saveKeystore(record) {
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

export function loadKeystore() {
  const storage = resolveStorage();
  const storedValue = storage ? storage.getItem(KEYSTORE_KEY) : null;

  if (storedValue) {
    return JSON.parse(storedValue);
  }
  return inMemoryFallback;
}

export function clearKeystore() {
  const storage = resolveStorage();
  if (storage) {
    storage.removeItem(KEYSTORE_KEY);
  }
  inMemoryFallback = null;
}
