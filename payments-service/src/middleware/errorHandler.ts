import { NextFunction, Request, Response } from 'express';
import { AppError } from '../errors';
import { logger } from '../logger';

export function errorHandler(
  err: Error,
  req: Request,
  res: Response,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _next: NextFunction,
): void {
  const requestId = (req as Request & { id?: string }).id;

  if (err instanceof AppError) {
    logger.warn({ requestId, code: err.code, message: err.message }, 'request_failed');
    res.status(err.statusCode).json({
      error: {
        code: err.code,
        message: err.message,
        details: err.details,
      },
    });
    return;
  }

  logger.error({ requestId, err: { message: err.message, stack: err.stack } }, 'unhandled_error');
  res.status(500).json({
    error: {
      code: 'internal_error',
      message: 'An unexpected error occurred',
    },
  });
}
