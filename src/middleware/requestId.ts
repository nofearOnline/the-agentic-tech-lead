import { randomUUID } from 'node:crypto';
import { NextFunction, Request, Response } from 'express';

export function requestId(req: Request, res: Response, next: NextFunction): void {
  const headerId = req.header('x-request-id');
  const id = headerId && headerId.length <= 128 ? headerId : randomUUID();
  res.setHeader('x-request-id', id);
  (req as Request & { id: string }).id = id;
  next();
}
