import express, { Express } from 'express';
import cors from 'cors';
import pinoHttp from 'pino-http';
import { buildRouter } from './http/routes';
import { PaymentsController } from './http/controllers/paymentsController';
import { AuthController } from './http/controllers/authController';
import { AdminController } from './http/controllers/adminController';
import { WebhooksController } from './http/controllers/webhooksController';
import { PaymentsService } from './services/paymentsService';
import { WebhooksService } from './services/webhooksService';
import { AdminService } from './services/adminService';
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
  const webhooksService = new WebhooksService();
  const payments =
    deps.payments ?? new PaymentsService(new FakeGateway(), transactionRepo, webhooksService);
  const adminService = new AdminService(transactionRepo);

  const paymentsController = new PaymentsController(payments);
  const authController = new AuthController();
  const adminController = new AdminController(adminService);
  const webhooksController = new WebhooksController(webhooksService);

  app.use(cors({ origin: '*', credentials: true }));
  app.use(express.json({ limit: '64kb' }));
  app.use(requestId);
  app.use(
    pinoHttp({
      logger,
      customProps: (req) => ({ requestId: (req as unknown as { id?: string }).id }),
    }),
  );

  app.use(buildRouter(paymentsController, authController, adminController, webhooksController));
  app.use(errorHandler);

  return app;
}
