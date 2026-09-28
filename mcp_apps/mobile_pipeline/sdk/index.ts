/** Provider-neutral native session client. Storage must be OS protected. */
export interface SessionStorage {
  read(): Promise<string | null>;
  write(value: string): Promise<void>;
  clear(): Promise<void>;
}
export interface Actor {
  id: string;
  email: string;
  role: string;
  scopes: string[];
}
export class MobileApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string
  ) {
    super(message);
  }
}
interface Tokens {
  accessToken: string;
  refreshToken: string;
}
/** Grace applies only to a still-running process; cold starts never inherit it. */
export const BACKGROUND_LOCK_MS = 5 * 60_000;
export class BackgroundLockPolicy {
  private leftAt: number | null = null;
  leave(now: number) {
    this.leftAt ??= now;
  }
  due(now: number) {
    return this.leftAt !== null && (now < this.leftAt || now - this.leftAt >= BACKGROUND_LOCK_MS);
  }
  remaining(now: number) {
    return this.leftAt === null
      ? BACKGROUND_LOCK_MS
      : Math.max(0, BACKGROUND_LOCK_MS - (now - this.leftAt));
  }
  resume(now: number) {
    const lock = this.due(now);
    this.leftAt = null;
    return lock;
  }
}
export class MobileClient {
  private access: string | null = null;
  private generation = 0;
  private renewing: Promise<void> | null = null;
  constructor(
    readonly origin: string,
    private storage: SessionStorage,
    private transport: typeof fetch = fetch
  ) {
    const url = new URL(origin);
    if (url.protocol !== 'https:' || url.origin !== origin || url.username || url.password)
      throw new Error('Se requiere un servidor HTTPS válido.');
  }
  lock() {
    this.access = null;
    this.generation++;
  }
  private async send<T>(path: string, init: RequestInit = {}, access?: string | null): Promise<T> {
    if (!/^[a-zA-Z0-9/?=&%._-]+$/.test(path) || path.includes('..'))
      throw new Error('Ruta inválida.');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20_000);
    try {
      const response = await this.transport(`${this.origin}/api/v1/mobile/${path}`, {
        ...init,
        credentials: 'omit',
        redirect: 'error',
        signal: controller.signal,
        headers: {
          accept: 'application/json',
          ...(init.body ? { 'content-type': 'application/json' } : {}),
          ...(access ? { authorization: `Bearer ${access}` } : {})
        }
      });
      let data: { data: T; code?: string; message?: string };
      try {
        data = await response.json();
      } catch {
        throw new MobileApiError(
          response.status,
          'invalid_response',
          'El servidor no respondió como se esperaba.'
        );
      }
      if (!response.ok)
        throw new MobileApiError(
          response.status,
          data.code ?? 'request_failed',
          data.message ?? 'No pudimos completar la solicitud.'
        );
      return data.data;
    } finally {
      clearTimeout(timeout);
    }
  }
  async login(email: string, password: string, platform: string, deviceLabel: string) {
    const generation = ++this.generation;
    const result = await this.send<Tokens>('auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, platform, deviceLabel })
    });
    if (generation !== this.generation) return;
    await this.storage.write(result.refreshToken);
    if (generation === this.generation) this.access = result.accessToken;
    else await this.storage.clear();
  }
  async unlock(): Promise<boolean> {
    if (this.renewing) {
      await this.renewing;
      return !!this.access;
    }
    const generation = this.generation;
    this.renewing = (async () => {
      const refreshToken = await this.storage.read();
      if (!refreshToken || generation !== this.generation) return;
      // A lost rotation response is ambiguous: never replay the consumed token.
      try {
        const result = await this.send<Tokens>('auth/refresh', {
          method: 'POST',
          body: JSON.stringify({ refreshToken })
        });
        if (generation !== this.generation) return;
        await this.storage.write(result.refreshToken);
        if (generation === this.generation) this.access = result.accessToken;
        else await this.storage.clear();
      } catch (error) {
        this.access = null;
        await this.storage.clear();
        throw error;
      }
    })();
    try {
      await this.renewing;
      return !!this.access;
    } finally {
      this.renewing = null;
    }
  }
  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.access) throw new MobileApiError(401, 'locked', 'Desbloqueá tu sesión.');
    const generation = this.generation;
    try {
      const result = await this.send<T>(path, init, this.access);
      if (generation !== this.generation)
        throw new MobileApiError(401, 'locked', 'Desbloqueá tu sesión.');
      return result;
    } catch (error) {
      if (generation !== this.generation) throw error;
      if (!(error instanceof MobileApiError) || error.status !== 401) throw error;
      this.access = null;
      if (!(await this.unlock())) throw error;
      return this.send<T>(path, init, this.access);
    }
  }
  async recovery(email: string) {
    return this.send<{ message: string }>('auth/recovery', {
      method: 'POST',
      body: JSON.stringify({ email })
    });
  }
  async loginWithDevice(credential: string) {
    const generation = ++this.generation;
    const result = await this.send<Tokens>('auth/device', {
      method: 'POST',
      body: JSON.stringify({ credential })
    });
    if (generation !== this.generation) return false;
    await this.storage.write(result.refreshToken);
    if (generation !== this.generation) {
      await this.storage.clear();
      return false;
    }
    this.access = result.accessToken;
    return true;
  }
  async forgetDevice(credential: string) {
    return this.send('auth/device/forget', {
      method: 'POST',
      body: JSON.stringify({ credential })
    });
  }
  async logout() {
    const access = this.access;
    this.lock();
    try {
      if (access) await this.send('auth/logout', { method: 'POST' }, access);
    } finally {
      await this.storage.clear();
    }
  }
}
