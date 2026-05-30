import { randomUUID } from 'node:crypto';
import { Currency } from '../domain/money';

export interface ChargeRequest {
  amount: number;
  currency: Currency;
  card: {
    number: string;
    expMonth: number;
    expYear: number;
    cvc: string;
  };
}

export interface ChargeResult {
  approved: boolean;
  gatewayReference: string;
  declineReason?: string;
}

export interface PaymentGateway {
  charge(request: ChargeRequest): Promise<ChargeResult>;
}

const DECLINE_SUFFIX = '0002';

/**
 * A deterministic fake gateway used by tests and local dev.
 *
 * Cards ending in 0002 are declined; everything else is approved.
 * No real network calls are made.
 */
export class FakeGateway implements PaymentGateway {
  async charge(request: ChargeRequest): Promise<ChargeResult> {
    const last4 = request.card.number.slice(-4);
    if (last4 === DECLINE_SUFFIX) {
      return {
        approved: false,
        gatewayReference: `decline_${randomUUID()}`,
        declineReason: 'insufficient_funds',
      };
    }
    return {
      approved: true,
      gatewayReference: `auth_${randomUUID()}`,
    };
  }
}
