import pino, { Logger } from 'pino';
import { loadConfig } from './config';

const config = loadConfig();

export const logger: Logger = pino({
  level: config.env === 'test' ? 'silent' : config.logLevel,
  base: { service: 'payments-service' },
  redact: {
    paths: [
      'req.headers.authorization',
      'card.number',
      'card.cvc',
      '*.card.number',
      '*.card.cvc',
    ],
    censor: '[REDACTED]',
  },
});
