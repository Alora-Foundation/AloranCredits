import { webcrypto, scrypt as nodeScrypt, randomBytes as nodeRandomBytes } from 'crypto';
import { promisify } from 'util';

const cryptoApi = webcrypto;
const scryptAsync = promisify(nodeScrypt);

export const defaultKdfParams = {
  N: 2 ** 15,
  r: 8,
  p: 1,
  dkLen: 32,
};

function encodeBase64(bytes) {
  return Buffer.from(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)).toString('base64');
}

function toUint8(data) {
  if (typeof data === 'string') {
    return new TextEncoder().encode(data);
  }
  return data;
}

async function deriveAesMaterial(passphrase, salt, kdfParams) {
  const keyBuffer = await scryptAsync(passphrase, salt, kdfParams.dkLen, {
    cost: kdfParams.N,
    blockSize: kdfParams.r,
    parallelization: kdfParams.p,
    maxmem: 64 * 1024 * 1024,
  });
  return new Uint8Array(keyBuffer);
}

export async function deriveKey(passphrase, salt, kdfParams = defaultKdfParams) {
  const saltBytes = typeof salt === 'string' ? Buffer.from(salt, 'base64') : salt;
  const keyMaterial = await deriveAesMaterial(passphrase, saltBytes, kdfParams);
  return cryptoApi.subtle.importKey('raw', keyMaterial, 'AES-GCM', false, ['encrypt', 'decrypt']);
}

export async function encryptKeystore(data, passphrase, keyType) {
  const salt = nodeRandomBytes(16);
  const iv = cryptoApi.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(passphrase, salt, defaultKdfParams);
  const plaintext = toUint8(data);
  const ciphertextBuffer = await cryptoApi.subtle.encrypt({ name: 'AES-GCM', iv }, key, plaintext);

  return {
    ciphertext: encodeBase64(ciphertextBuffer),
    salt: encodeBase64(salt),
    iv: encodeBase64(iv),
    kdfParams: { ...defaultKdfParams },
    createdAt: new Date().toISOString(),
    keyType,
  };
}

export async function decryptKeystore(record, passphrase) {
  const key = await deriveKey(passphrase, Buffer.from(record.salt, 'base64'), record.kdfParams);
  const iv = Buffer.from(record.iv, 'base64');
  const ciphertext = Buffer.from(record.ciphertext, 'base64');
  const plaintext = await cryptoApi.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
  return new Uint8Array(plaintext);
}

export const keystoreShapeDocumentation = `{
  ciphertext: string; // base64 AES-GCM ciphertext
  salt: string;       // base64 salt for scrypt
  iv: string;         // base64 AES-GCM IV
  kdfParams: { N: number; r: number; p: number; dkLen: number };
  createdAt: string;  // ISO timestamp
  keyType?: string;   // optional descriptor of key material
}`;
