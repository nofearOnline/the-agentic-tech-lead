import jwt from 'jsonwebtoken';

const SECRET = process.env.JWT_SECRET || 'dev-secret-123';

export interface TokenPayload {
  userId: string;
  email: string;
  role: string;
}

export function signToken(payload: TokenPayload): string {
  return jwt.sign(payload, SECRET);
}

export function verifyToken(token: string): TokenPayload | null {
  try {
    const decoded = jwt.verify(token, SECRET);
    return decoded as TokenPayload;
  } catch (e) {
    return null;
  }
}

export function generateResetToken(userId: string): string {
  return userId + '-' + Math.random().toString(36).slice(2) + '-' + Date.now();
}
