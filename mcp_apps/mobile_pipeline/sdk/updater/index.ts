/** Shared Bridge APK update contract. No API-session credentials cross into Bridge. */
export type UpdateConfig = {
  bridgeUrl: string;
  sourceApp: string;
  packageId: string;
  version: string;
  build: number;
};
export type Update = {
  version: string;
  build: number;
  url: string;
  sha256: string;
  size: number;
};
export const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;
export function updateEndpoint(c: UpdateConfig): string {
  const base = new URL(c.bridgeUrl);
  if (base.protocol !== 'https:' || base.username || base.password || base.pathname !== '/')
    throw new Error('Invalid Bridge origin');
  return `${base.origin}/app-updates/${encodeURIComponent(c.sourceApp)}?platform=android&channel=prerelease&currentVersion=${encodeURIComponent(c.version)}&currentBuild=${c.build}`;
}
export function parseUpdate(value: unknown, c: UpdateConfig): Update | null {
  if (!value || typeof value !== 'object') throw new Error('Invalid update response');
  const r = value as Record<string, unknown>;
  if (
    r.kind !== 'codex.appUpdate' ||
    r.version !== 1 ||
    r.sourceApp !== c.sourceApp ||
    r.platform !== 'android' ||
    typeof r.available !== 'boolean'
  )
    throw new Error('Wrong update identity');
  if (!r.available) return null;
  if (
    r.packageId !== c.packageId ||
    !Number.isSafeInteger(r.latestBuild) ||
    (r.latestBuild as number) <= c.build ||
    typeof r.latestVersion !== 'string' ||
    !/^\d+\.\d+\.\d+$/.test(r.latestVersion) ||
    typeof r.sha256 !== 'string' ||
    !/^[a-f0-9]{64}$/.test(r.sha256) ||
    !Number.isSafeInteger(r.sizeBytes) ||
    (r.sizeBytes as number) <= 0 ||
    (r.sizeBytes as number) > 500_000_000 ||
    typeof r.apkUrl !== 'string'
  )
    throw new Error('Unsafe update metadata');
  const url = new URL(r.apkUrl),
    origin = new URL(c.bridgeUrl);
  if (
    url.protocol !== 'https:' ||
    url.origin !== origin.origin ||
    url.username ||
    url.password ||
    !url.pathname.startsWith(`/app-updates/${c.sourceApp}/apk/`)
  )
    throw new Error('Untrusted download URL');
  return {
    version: r.latestVersion,
    build: r.latestBuild as number,
    url: url.href,
    sha256: r.sha256,
    size: r.sizeBytes as number
  };
}
export async function checkUpdate(
  c: UpdateConfig,
  fetcher: typeof fetch = fetch
): Promise<Update | null> {
  const controller = new AbortController(),
    timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetcher(updateEndpoint(c), {
      signal: controller.signal,
      credentials: 'omit',
      headers: { Accept: 'application/json' }
    });
    if (!response.ok) throw new Error('Bridge unavailable');
    return parseUpdate(await response.json(), c);
  } finally {
    clearTimeout(timeout);
  }
}
