import { NextFunction, Request, Response } from 'express';
import { ZodError } from 'zod';
import { RefundsService } from '../../services/refundsService';
import { refundSchema } from '../validators/refundSchema';
import { validationError } from '../../errors';

export class RefundsController {
  constructor(private readonly refunds: RefundsService) {}

  create = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const payload = refundSchema.parse(req.body);

      const result = await this.refunds.refund(
        payload.transaction_id,
        payload.amount,
        payload.reason,
        payload.idempotency_key,
      );

      if (result == null) {
        // transaction didn't exist - just return empty body
        res.status(200).json({});
        return;
      }

      res.status(201).json({
        refund_id: result.refundId,
        transaction_id: result.transactionId,
        amount: result.amount,
        status: result.status,
        created_at: result.createdAt,
      });
    } catch (err) {
      if (err instanceof ZodError) {
        next(validationError('Invalid request body', err.flatten()));
        return;
      }
      next(err);
    }
  };
}
