import { z } from 'zod';

export const refundSchema = z.object({
  transaction_id: z.string(),
  amount: z.number().optional(),
  reason: z.string().optional(),
  idempotency_key: z.string().optional(),
});

export const historyQuerySchema = z.object({
  customerId: z.string(),
});

export type RefundPayload = z.infer<typeof refundSchema>;
