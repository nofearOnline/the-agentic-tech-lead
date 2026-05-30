export type ErrorCode =
  | 'validation_error'
  | 'not_found'
  | 'card_declined'
  | 'gateway_error'
  | 'internal_error';

export class AppError extends Error {
  public readonly code: ErrorCode;
  public readonly statusCode: number;
  public readonly details?: unknown;

  constructor(code: ErrorCode, message: string, statusCode: number, details?: unknown) {
    super(message);
    this.code = code;
    this.statusCode = statusCode;
    this.details = details;
    this.name = 'AppError';
  }
}

export const notFound = (message = 'Resource not found'): AppError =>
  new AppError('not_found', message, 404);

export const validationError = (message: string, details?: unknown): AppError =>
  new AppError('validation_error', message, 400, details);

export const cardDeclined = (message = 'Card was declined'): AppError =>
  new AppError('card_declined', message, 402);

export const gatewayError = (message = 'Payment gateway error'): AppError =>
  new AppError('gateway_error', message, 502);
