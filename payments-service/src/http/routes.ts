import { Router } from 'express';
import { PaymentsController } from './controllers/paymentsController';
import { RefundsController } from './controllers/refundsController';
import { CustomerHistoryController } from './controllers/customerHistoryController';

export function buildRouter(
  payments: PaymentsController,
  refunds: RefundsController,
  history: CustomerHistoryController,
): Router {
  const router = Router();

  router.get('/health', (_req, res) => {
    res.json({ status: 'ok' });
  });

  router.post('/charge', payments.charge);
  router.get('/transactions/:id', payments.getTransaction);

  router.post('/refunds', refunds.create);
  router.get('/customers/:id/transactions', history.list);

  return router;
}
