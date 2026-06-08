import { Router } from 'express';
import { PaymentsController } from './controllers/paymentsController';
import { AuthController } from './controllers/authController';
import { AdminController } from './controllers/adminController';
import { WebhooksController } from './controllers/webhooksController';
import { authMiddleware } from '../auth/authMiddleware';

export function buildRouter(
  payments: PaymentsController,
  auth: AuthController,
  admin: AdminController,
  webhooks: WebhooksController,
): Router {
  const router = Router();

  router.get('/health', (_req, res) => {
    res.json({ status: 'ok' });
  });

  router.post('/charge', payments.charge);
  router.get('/transactions/:id', payments.getTransaction);

  router.post('/auth/register', auth.register);
  router.post('/auth/login', auth.login);
  router.post('/auth/password-reset', auth.requestPasswordReset);
  router.get('/auth/me', authMiddleware, auth.me);

  router.get('/admin/users', authMiddleware, admin.listUsers);
  router.get('/admin/transactions', authMiddleware, admin.listTransactions);
  router.get('/admin/stats', authMiddleware, admin.stats);
  router.get('/admin/export.csv', authMiddleware, admin.exportCsv);

  router.post('/webhooks', authMiddleware, webhooks.register);
  router.get('/webhooks', authMiddleware, webhooks.list);

  return router;
}
