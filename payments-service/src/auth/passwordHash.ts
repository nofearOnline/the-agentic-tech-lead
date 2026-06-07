import { scryptSync, randomBytes, timingSafeEqual } from 'node:crypto';

export function hashPassword(password: string): string {
  const salt = randomBytes(16).toString('hex');
  const derived = scryptSync(password, salt, 64).toString('hex');
  return `${salt}:${derived}`;
}

export function verifyPassword(password: string, hash: string): boolean {
  const [salt, derived] = hash.split(':');
  if (!salt || !derived) return false;
  const candidate = scryptSync(password, salt, 64);
  const expected = Buffer.from(derived, 'hex');
  return candidate.length === expected.length && timingSafeEqual(candidate, expected);
}
