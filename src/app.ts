import express, { Express } from 'express';
import pinoHttp from 'pino-http';
import { buildRouter } from './http/routes';
import { PaymentsController } from './http/controllers/paymentsController';
import { PaymentsService } from './services/paymentsService';
import { InMemoryTransactionRepository } from './repositories/transactionRepository';
import { FakeGateway } from './gateway/fakeGateway';
import { errorHandler } from './middleware/errorHandler';
import { requestId } from './middleware/requestId';
import { logger } from './logger';

export interface AppDeps {
  payments?: PaymentsService;
}

export function createApp(deps: AppDeps = {}): Express {
  const app = express();

  const payments =
    deps.payments ?? new PaymentsService(new FakeGateway(), new InMemoryTransactionRepository());
  const controller = new PaymentsController(payments);

  app.use(express.json({ limit: '64kb' }));
  app.use(requestId);
  app.use(
    pinoHttp({
      logger,
      customProps: (req) => ({ requestId: (req as unknown as { id?: string }).id }),
    }),
  );

  app.use(buildRouter(controller));
  app.use(errorHandler);

  return app;
}
