import { Router } from 'express';
import { PaymentsController } from './controllers/paymentsController';

export function buildRouter(payments: PaymentsController): Router {
  const router = Router();

  router.get('/health', (_req, res) => {
    res.json({ status: 'ok' });
  });

  router.post('/charge', payments.charge);
  router.get('/transactions/:id', payments.getTransaction);

  return router;
}
