import { NextFunction, Response } from 'express';
import { WebhooksService } from '../../services/webhooksService';
import { AuthedRequest } from '../../auth/authMiddleware';

export class WebhooksController {
  constructor(private readonly webhooks: WebhooksService) {}

  register = async (req: AuthedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const url = req.body.url;
      if (!url || typeof url !== 'string') {
        res.status(400).json({ error: { code: 'validation_error', message: 'url required' } });
        return;
      }
      const owner = req.user?.userId || 'anonymous';
      const hook = this.webhooks.register(url, owner);
      res.status(201).json(hook);
    } catch (err) {
      next(err);
    }
  };

  list = async (req: AuthedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const owner = req.user?.userId || 'anonymous';
      res.json({ webhooks: this.webhooks.list(owner) });
    } catch (err) {
      next(err);
    }
  };
}
