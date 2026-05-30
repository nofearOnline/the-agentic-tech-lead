import express, { Express } from 'express';
import pinoHttp from 'pino-http';
import { buildRouter } from './http/routes';
import { PaymentsController } from './http/controllers/paymentsController';
import { RefundsController } from './http/controllers/refundsController';
import { CustomerHistoryController } from './http/controllers/customerHistoryController';
import { PaymentsService } from './services/paymentsService';
import { RefundsService } from './services/refundsService';
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

  const transactionRepo = new InMemoryTransactionRepository();
  const payments = deps.payments ?? new PaymentsService(new FakeGateway(), transactionRepo);
  const refundsService = new RefundsService(transactionRepo);

  const paymentsController = new PaymentsController(payments);
  const refundsController = new RefundsController(refundsService);
  const historyController = new CustomerHistoryController(transactionRepo, refundsService);

  app.use(express.json({ limit: '64kb' }));
  app.use(requestId);
  app.use(
    pinoHttp({
      logger,
      customProps: (req) => ({ requestId: (req as unknown as { id?: string }).id }),
    }),
  );

  app.use(buildRouter(paymentsController, refundsController, historyController));
  app.use(errorHandler);

  return app;
}
