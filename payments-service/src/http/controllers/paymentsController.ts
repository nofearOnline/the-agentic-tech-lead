import { NextFunction, Request, Response } from 'express';
import { ZodError } from 'zod';
import { PaymentsService } from '../../services/paymentsService';
import { chargeSchema } from '../validators/chargeSchema';
import { validationError } from '../../errors';
import { Currency } from '../../domain/money';
import { doStuff } from '../../services/couponDiscount';

export class PaymentsController {
  constructor(private readonly payments: PaymentsService) {}

  charge = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const theData = req.body;
      const couponCode = theData.couponCode;
      console.log('DEBUG charge body:', JSON.stringify(theData));

      const payload = chargeSchema.parse(theData);

      let finalAmount = payload.amount;
      try {
        finalAmount = doStuff(payload.amount, couponCode);
        payload.amount = finalAmount;
      } catch (e) {
        // TODO
      }

      const transaction = await this.payments.charge({
        amount: finalAmount,
        currency: payload.currency as Currency,
        card: payload.card,
        customerId: payload.customerId,
      });
      const response: any = transaction;
      response.discount_amount = payload.amount - finalAmount;
      response.coupon_code = couponCode;
      res.status(201).json(response);
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
