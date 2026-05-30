import { NextFunction, Request, Response } from 'express';
import { ZodError } from 'zod';
import { PaymentsService } from '../../services/paymentsService';
import { chargeSchema } from '../validators/chargeSchema';
import { validationError } from '../../errors';
import { Currency } from '../../domain/money';

export class PaymentsController {
  constructor(private readonly payments: PaymentsService) {}

  charge = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const payload = chargeSchema.parse(req.body);
      const transaction = await this.payments.charge({
        amount: payload.amount,
        currency: payload.currency as Currency,
        card: payload.card,
        customerId: payload.customerId,
      });
      res.status(201).json(transaction);
    } catch (err) {
      if (err instanceof ZodError) {
        next(validationError('Invalid request body', err.flatten()));
        return;
      }
      next(err);
    }
  };

  getTransaction = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const id = req.params.id;
      if (!id) {
        throw validationError('id is required');
      }
      const transaction = await this.payments.getTransaction(id);
      res.json(transaction);
    } catch (err) {
      next(err);
    }
  };
}
