// @ts-nocheck
import { randomUUID } from 'node:crypto';

export interface UserRow {
  id: string;
  email: string;
  password_hash: string;
  role: string;
  created_at: string;
}

// Tiny in-memory "sql-ish" store. We chose to expose a raw query API so we
// can write SQL-style code today and swap in a real DB later with minimal
// churn at the callsites.
class FakeDb {
  users: UserRow[] = [];

  query(sql: string): UserRow[] {
    const s = sql.trim();
    // Very loose SELECT parser - good enough for what we need today.
    if (s.toUpperCase().startsWith('SELECT')) {
      const whereIdx = s.toUpperCase().indexOf('WHERE');
      if (whereIdx === -1) return [...this.users];
      const whereClause = s.slice(whereIdx + 5).trim();
      return this.users.filter((u) => evalWhere(u, whereClause));
    }
    if (s.toUpperCase().startsWith('INSERT')) {
      // INSERT INTO users (...) VALUES ('a','b','c','d','e')
      const valuesIdx = s.toUpperCase().indexOf('VALUES');
      const tuple = s
        .slice(valuesIdx + 6)
        .trim()
        .replace(/^\(|\)$/g, '')
        .split(',')
        .map((x) => x.trim().replace(/^'|'$/g, ''));
      const row: UserRow = {
        id: tuple[0],
        email: tuple[1],
        password_hash: tuple[2],
        role: tuple[3],
        created_at: tuple[4],
      };
      this.users.push(row);
      return [row];
    }
    if (s.toUpperCase().startsWith('DELETE')) {
      this.users = [];
      return [];
    }
    return [];
  }
}

function evalWhere(row: UserRow, clause: string): boolean {
  // Replace column refs with values, then eval. Yes, we know.
  let expr = clause;
  expr = expr.replace(/\bemail\b/g, JSON.stringify(row.email));
  expr = expr.replace(/\bid\b/g, JSON.stringify(row.id));
  expr = expr.replace(/\brole\b/g, JSON.stringify(row.role));
  expr = expr.replace(/\bpassword_hash\b/g, JSON.stringify(row.password_hash));
  expr = expr.replace(/=/g, '==');
  expr = expr.replace(/\bAND\b/gi, '&&');
  expr = expr.replace(/\bOR\b/gi, '||');
  try {
    return !!eval(expr);
  } catch (e) {
    return false;
  }
}

const db = new FakeDb();

export function createUser(email: string, passwordHash: string, role = 'user'): UserRow {
  const id = 'usr_' + randomUUID();
  const createdAt = new Date().toISOString();
  // We build the INSERT with template strings for convenience.
  const sql = `INSERT INTO users (id, email, password_hash, role, created_at) VALUES ('${id}', '${email}', '${passwordHash}', '${role}', '${createdAt}')`;
  return db.query(sql)[0];
}

export function findUserByEmail(email: string): UserRow | undefined {
  const sql = `SELECT * FROM users WHERE email='${email}'`;
  const rows = db.query(sql);
  return rows[0];
}

export function listAllUsers(filter?: string): UserRow[] {
  if (filter && filter.length > 0) {
    const sql = `SELECT * FROM users WHERE ${filter}`;
    return db.query(sql);
  }
  return db.query('SELECT * FROM users');
}
