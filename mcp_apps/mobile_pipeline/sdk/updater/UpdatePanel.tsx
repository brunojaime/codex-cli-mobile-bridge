import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, NativeModules, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { CHECK_INTERVAL_MS, checkUpdate, type Update, type UpdateConfig } from './index';
type NativeUpdater = {
  version: string;
  build: number;
  packageId: string;
  download(url: string, hash: string, size: number): Promise<string>;
  install(hash: string, size: number): Promise<'permission' | 'installer'>;
};
const native = NativeModules.BridgeUpdater as NativeUpdater | undefined;
export function UpdatePanel({
  enabled,
  bridgeUrl,
  sourceApp
}: {
  enabled: boolean;
  bridgeUrl: string;
  sourceApp: string;
}) {
  enabled = enabled && Platform.OS === 'android' && Number(Platform.Version) >= 28;
  const [update, setUpdate] = useState<Update | null>(null),
    [status, setStatus] = useState(''),
    [busy, setBusy] = useState(false),
    [hidden, setHidden] = useState(false);
  const lastCheck = useRef(0),
    running = useRef(false),
    alive = useRef(true);
  const check = useCallback(
    async (manual = false) => {
      if (
        !enabled ||
        !native ||
        running.current ||
        (!manual && Date.now() - lastCheck.current < CHECK_INTERVAL_MS)
      )
        return;
      running.current = true;
      lastCheck.current = Date.now();
      setBusy(true);
      if (manual) setStatus('Buscando actualizaciones…');
      try {
        const config: UpdateConfig = {
          bridgeUrl,
          sourceApp,
          packageId: native.packageId,
          version: native.version,
          build: native.build
        };
        const next = await checkUpdate(config);
        if (alive.current) {
          setUpdate(next);
          setStatus(next ? '' : manual ? 'Tenés la última versión.' : '');
        }
      } catch {
        if (alive.current && manual)
          setStatus(
            'No pudimos consultar Bridge. Revisá tu conexión y Tailscale, e intentá nuevamente.'
          );
      } finally {
        running.current = false;
        if (alive.current) setBusy(false);
      }
    },
    [enabled, bridgeUrl, sourceApp]
  );
  useEffect(() => {
    alive.current = true;
    if (enabled && native && Platform.OS === 'android') void check();
    const sub = AppState.addEventListener('change', (state) => {
      setHidden(state !== 'active');
      if (state === 'active') void check();
    });
    return () => {
      alive.current = false;
      sub.remove();
    };
  }, [check, enabled]);
  async function install() {
    if (!native || !update || running.current) return;
    running.current = true;
    setBusy(true);
    setStatus('Descargando y verificando… Podés volver más tarde.');
    try {
      await native.download(update.url, update.sha256, update.size);
      if (AppState.currentState !== 'active') {
        setStatus('Descarga lista. Tocá Actualizar para instalar.');
        return;
      }
      const result = await native.install(update.sha256, update.size);
      if (alive.current)
        setStatus(
          result === 'permission'
            ? 'Permití instalar desde esta app. Al volver, tocá Actualizar.'
            : 'Confirmá la instalación en Android. Si la cancelaste, podés reintentar.'
        );
    } catch {
      if (alive.current)
        setStatus(
          'No se pudo completar una actualización segura. Revisá tu conexión y volvé a intentar.'
        );
    } finally {
      running.current = false;
      if (alive.current) setBusy(false);
    }
  }
  if (!enabled || Platform.OS !== 'android' || !native || hidden) return null;
  return (
    <View style={styles.panel}>
      <View style={styles.row}>
        <Text style={styles.label}>
          {update
            ? `Nueva versión ${update.version} (${update.build})`
            : `Versión ${native.version} (${native.build})`}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: busy }}
          disabled={busy}
          onPress={() => void (update ? install() : check(true))}
          style={styles.button}
        >
          <Text style={styles.action}>
            {busy ? 'Un momento…' : update ? 'Actualizar' : 'Buscar actualizaciones'}
          </Text>
        </Pressable>
      </View>
      {!!status && (
        <Text accessibilityLiveRegion="polite" style={styles.status}>
          {status}
        </Text>
      )}
    </View>
  );
}
const styles = StyleSheet.create({
  panel: {
    backgroundColor: '#eaf1ed',
    borderBottomWidth: 1,
    borderBottomColor: '#d5e1db',
    paddingHorizontal: 16,
    paddingVertical: 6
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: 4
  },
  label: { fontSize: 12, color: '#375c55', fontWeight: '600', flexShrink: 1 },
  button: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 8 },
  action: { color: '#1b5042', fontWeight: '700', fontSize: 13 },
  status: { color: '#375c55', fontSize: 12, lineHeight: 18, paddingBottom: 8 }
});
