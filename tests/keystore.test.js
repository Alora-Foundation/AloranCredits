import assert from 'node:assert';
import { test } from 'node:test';
import { decryptKeystore, encryptKeystore } from '../src/lib/crypto/keystore.js';

const decoder = new TextDecoder();

test('encrypts and decrypts keystore data with matching passphrase', async () => {
  const secret = 'super-secret-data';
  const record = await encryptKeystore(secret, 'correct horse battery staple', 'ed25519');
  const plaintext = await decryptKeystore(record, 'correct horse battery staple');

  assert.strictEqual(decoder.decode(plaintext), secret);
  assert.ok(record.createdAt);
  assert.strictEqual(record.keyType, 'ed25519');
  assert.ok(record.kdfParams.N);
});

test('rejects decryption with an incorrect passphrase', async () => {
  const record = await encryptKeystore('lock-this', 'right-password');

  await assert.rejects(() => decryptKeystore(record, 'wrong-password'));
});

test('detects tampering of ciphertext or iv', async () => {
  const record = await encryptKeystore('immutable', 'lock');
  const ciphertextBytes = Buffer.from(record.ciphertext, 'base64');
  ciphertextBytes[0] = ciphertextBytes[0] ^ 0b00000001;

  const tampered = { ...record, ciphertext: ciphertextBytes.toString('base64') };
  await assert.rejects(() => decryptKeystore(tampered, 'lock'));
});
