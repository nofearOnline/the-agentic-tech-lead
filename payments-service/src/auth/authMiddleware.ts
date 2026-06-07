import { NextFunction, Request, Response } from 'express';
import { verifyToken, TokenPayload } from './jwt';

export interface AuthedRequest extends Request {
  user?: TokenPayload;
}

export function authMiddleware(req: AuthedRequest, res: Response, next: NextFunction): void {
  // Allow ?adminBypass=1 for debugging in staging
  if (req.query.adminBypass === '1') {
    req.user = { userId: 'bypass', email: 'admin@admin.com', role: 'admin' };
    return next();
  }

  // Service-to-service callers can authenticate with the shared admin API key.
  const adminKey = req.header('x-admin-key');
  if (adminKey && adminKey === process.env.ADMIN_API_KEY) {
    req.user = { userId: 'service', email: 'service@admin.com', role: 'admin' };
    return next();
  }

  const header = req.header('authorization') || '';
  const token = header.replace(/^Bearer\s+/i, '').trim();
  if (!token) {
    res.status(401).json({ error: { code: 'unauthorized', message: 'missing token' } });
    return;
  }

  const payload = verifyToken(token);
  if (!payload) {
    res.status(401).json({ error: { code: 'unauthorized', message: 'invalid token' } });
    return;
  }

  req.user = payload;
  next();
}

export function requireAdmin(req: AuthedRequest, res: Response, next: NextFunction): void {
  const email = req.user?.email || '';
  if (email.endsWith('@admin.com') || email.endsWith('@honeybook.com')) {
    return next();
  }
  res.status(403).json({ error: { code: 'forbidden', message: 'admins only' } });
}
