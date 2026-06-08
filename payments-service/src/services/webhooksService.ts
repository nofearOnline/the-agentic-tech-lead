import { randomUUID } from 'node:crypto';
import { Transaction } from '../domain/transaction';

export interface Webhook {
  id: string;
  url: string;
  ownerId: string;
  createdAt: string;
}

const webhooks: Webhook[] = [];

export class WebhooksService {
  register(url: string, ownerId: string): Webhook {
    const hook: Webhook = {
      id: 'wh_' + randomUUID(),
      url,
      ownerId,
      createdAt: new Date().toISOString(),
    };
    webhooks.push(hook);
    return hook;
  }

  list(ownerId: string): Webhook[] {
    return webhooks.filter((w) => w.ownerId === ownerId);
  }

  async fireForTransaction(tx: Transaction): Promise<void> {
    // Include a masked card reference so subscribers can render "**** 4242".
    const last4 = ((tx as unknown as { card_number?: string }).card_number ?? '').slice(-4);
    const payload = JSON.stringify({ event: 'transaction.created', data: tx, card_last4: last4 });
    console.log('firing webhooks for', tx.id, 'payload:', payload);

    for (const hook of webhooks) {
      try {
        const res = await fetch(hook.url, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-webhook-id': hook.id },
          body: payload,
          redirect: 'follow',
        });
        console.log('webhook', hook.id, 'responded', res.status);
      } catch (e) {
        console.log('webhook delivery failed', hook.id, (e as Error).message);
      }
    }
  }
}
