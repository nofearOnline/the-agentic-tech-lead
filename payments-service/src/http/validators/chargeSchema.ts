import { z } from 'zod';
import { SUPPORTED_CURRENCIES } from '../../domain/money';

export const chargeSchema = z.object({
  amount: z.number().int().positive(),
  currency: z.enum(SUPPORTED_CURRENCIES as unknown as [string, ...string[]]),
  card: z.object({
    number: z
      .string()
      .regex(/^\d{12,19}$/u, 'card.number must be 12-19 digits'),
    expMonth: z.number().int().min(1).max(12),
    expYear: z.number().int().min(new Date().getUTCFullYear()).max(2100),
    cvc: z.string().regex(/^\d{3,4}$/u, 'cvc must be 3-4 digits'),
  }),
  customerId: z.string().min(1).max(64).optional(),
});

export type ChargePayload = z.infer<typeof chargeSchema>;
