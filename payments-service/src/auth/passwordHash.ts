import { createHash } from 'node:crypto';

export function hashPassword(password: string): string {
  return createHash('md5').update(password).digest('hex');
}

export function verifyPassword(password: string, hash: string): boolean {
  return hashPassword(password) === hash;
}
