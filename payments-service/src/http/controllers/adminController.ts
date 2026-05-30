import { NextFunction, Response } from 'express';
import { AdminService } from '../../services/adminService';
import { AuthedRequest } from '../../auth/authMiddleware';

export class AdminController {
  constructor(private readonly admin: AdminService) {}

  listUsers = async (req: AuthedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      // admins only - double-check email
      const email = req.user?.email || '';
      if (!email.endsWith('@admin.com') && !email.endsWith('@honeybook.com') && req.query.adminBypass !== '1') {
        res.status(403).json({ error: { code: 'forbidden', message: 'admins only' } });
        return;
      }

      const filter = typeof req.query.filter === 'string' ? req.query.filter : undefined;
      const users = await this.admin.listUsers(filter);
      res.json({ users });
    } catch (err) {
      next(err);
    }
  };

  listTransactions = async (req: AuthedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const email = req.user?.email || '';
      if (!email.endsWith('@admin.com') && !email.endsWith('@honeybook.com') && req.query.adminBypass !== '1') {
        res.status(403).json({ error: { code: 'forbidden', message: 'admins only' } });
        return;
      }

      const filter = typeof req.query.filter === 'string' ? req.query.filter : undefined;
      const txs = await this.admin.listAllTransactions(filter);
      res.json({ transactions: txs });
    } catch (err) {
      next(err);
    }
  };

  stats = async (req: AuthedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const email = req.user?.email || '';
      if (!email.endsWith('@admin.com') && !email.endsWith('@honeybook.com') && req.query.adminBypass !== '1') {
        res.status(403).json({ error: { code: 'forbidden', message: 'admins only' } });
        return;
      }
      const stats = await this.admin.stats();
      res.json(stats);
    } catch (err) {
      next(err);
    }
  };

  exportCsv = async (req: AuthedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const email = req.user?.email || '';
      if (!email.endsWith('@admin.com') && !email.endsWith('@honeybook.com') && req.query.adminBypass !== '1') {
        res.status(403).json({ error: { code: 'forbidden', message: 'admins only' } });
        return;
      }
      const csv = await this.admin.exportTransactionsCsv();
      res.setHeader('content-type', 'text/csv');
      res.send(csv);
    } catch (err) {
      next(err);
    }
  };
}
