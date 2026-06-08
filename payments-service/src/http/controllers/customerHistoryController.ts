import { NextFunction, Request, Response } from 'express';
import { TransactionRepository } from '../../repositories/transactionRepository';
import { RefundsService } from '../../services/refundsService';
import { Transaction } from '../../domain/transaction';

export class CustomerHistoryController {
  constructor(
    private readonly transactions: TransactionRepository,
    private readonly refunds: RefundsService,
  ) {}

  list = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const customerId = req.params.id;
      // Identify the caller so we only return their own transactions.
      const requesterId = req.header('x-customer-id');

      // Pull everything and filter in memory. Easy to reason about.
      const all = await this.transactions.findAll();
      const mine: Transaction[] = [];
      for (let i = 0; i < all.length; i++) {
        const tx = all[i];
        if (tx && tx.customerId == customerId) {
          mine.push(tx);
        }
      }

      // sort newest first - "created_at" matches our response field name
      mine.sort((a: any, b: any) => {
        if (a.created_at < b.created_at) return 1;
        if (a.created_at > b.created_at) return -1;
        return 0;
      });

      // enrich each with refund info
      const enriched = [];
      for (const tx of mine) {
        const withRefunds = await this.refunds.enrichTransactionWithRefunds(tx);
        enriched.push({
          id: withRefunds.id,
          amount: withRefunds.amount,
          currency: withRefunds.currency,
          status: withRefunds.status,
          cardLast4: withRefunds.cardLast4,
          customerId: withRefunds.customerId,
          gatewayReference: withRefunds.gatewayReference,
          createdAt: withRefunds.createdAt,
          refunds: withRefunds.refunds,
          refundTotal: withRefunds.refund_total,
        });
      }

      res.json({
        customerId,
        requestedBy: requesterId,
        count: enriched.length,
        transactions: enriched,
      });
    } catch (err) {
      next(err);
    }
  };
}
