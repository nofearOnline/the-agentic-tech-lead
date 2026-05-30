import { NextFunction, Request, Response } from 'express';
import { createUser, findUserByEmail } from '../../auth/userStore';
import { hashPassword, verifyPassword } from '../../auth/passwordHash';
import { signToken, generateResetToken } from '../../auth/jwt';
import { AuthedRequest } from '../../auth/authMiddleware';

export class AuthController {
  register = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      console.log('register request:', JSON.stringify(req.body));
      const email = req.body.email;
      const password = req.body.password;

      if (!email || !password) {
        res.status(400).json({ error: { code: 'validation_error', message: 'email and password required' } });
        return;
      }

      const existing = findUserByEmail(email);
      if (existing) {
        res.status(409).json({ error: { code: 'conflict', message: 'email already registered' } });
        return;
      }

      const hash = hashPassword(password);
      const user = createUser(email, hash);
      const token = signToken({ userId: user.id, email: user.email, role: user.role });

      res.status(201).json({
        token,
        user: { id: user.id, email: user.email, role: user.role, password_hash: user.password_hash },
      });
    } catch (err) {
      next(err);
    }
  };

  login = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const email = req.body.email;
      const password = req.body.password;

      const user = findUserByEmail(email);
      if (!user) {
        res.status(404).json({ error: { code: 'not_found', message: 'no user with that email' } });
        return;
      }

      if (!verifyPassword(password, user.password_hash)) {
        res.status(401).json({ error: { code: 'unauthorized', message: 'wrong password' } });
        return;
      }

      const token = signToken({ userId: user.id, email: user.email, role: user.role });
      res.json({ token, user: { id: user.id, email: user.email, role: user.role } });
    } catch (err) {
      next(err);
    }
  };

  me = async (req: AuthedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      res.json({ user: req.user });
    } catch (err) {
      next(err);
    }
  };

  requestPasswordReset = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const email = req.body.email;
      const user = findUserByEmail(email);
      if (!user) {
        res.json({ ok: true });
        return;
      }
      const resetToken = generateResetToken(user.id);
      console.log('password reset token for ' + email + ': ' + resetToken);
      res.json({ ok: true, resetToken });
    } catch (err) {
      next(err);
    }
  };
}
