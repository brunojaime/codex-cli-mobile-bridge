const fs = require('node:fs');
const path = require('node:path');
// Resolve Expo from the consumer rather than requiring a second copy in the shared package.
module.exports = (config, options) => {
  const { withAndroidManifest, withMainApplication, withDangerousMod } = require(
    require.resolve('expo/config-plugins', { paths: [process.cwd()] })
  );
  const enabled = options?.enabled === true;
  if (enabled && options.profile !== 'preview') throw new Error('APK updater is preview-only');
  const origin = new URL(options.bridgeUrl);
  if (
    origin.protocol !== 'https:' ||
    origin.port ||
    origin.pathname !== '/' ||
    origin.username ||
    origin.password ||
    !/^[a-z0-9.-]+$/.test(origin.hostname) ||
    !/^[a-z0-9-]+$/.test(options.sourceApp)
  )
    throw new Error('Invalid updater configuration');
  config = withAndroidManifest(config, (c) => {
    const m = c.modResults.manifest;
    m['uses-permission'] ||= [];
    if (!enabled)
      m['uses-permission'] = m['uses-permission'].filter(
        (p) => p.$['android:name'] !== 'android.permission.REQUEST_INSTALL_PACKAGES'
      );
    if (
      enabled &&
      !m['uses-permission'].some(
        (p) => p.$['android:name'] === 'android.permission.REQUEST_INSTALL_PACKAGES'
      )
    )
      m['uses-permission'].push({
        $: { 'android:name': 'android.permission.REQUEST_INSTALL_PACKAGES' }
      });
    const app = m.application[0];
    app.provider ||= [];
    const authority = '${applicationId}.bridge.updates';
    if (!enabled)
      app.provider = app.provider.filter((p) => p.$['android:authorities'] !== authority);
    if (enabled && !app.provider.some((p) => p.$['android:authorities'] === authority))
      app.provider.push({
        $: {
          'android:name': 'androidx.core.content.FileProvider',
          'android:authorities': authority,
          'android:exported': 'false',
          'android:grantUriPermissions': 'true'
        },
        'meta-data': [
          {
            $: {
              'android:name': 'android.support.FILE_PROVIDER_PATHS',
              'android:resource': '@xml/bridge_update_paths'
            }
          }
        ]
      });
    return c;
  });
  config = withMainApplication(config, (c) => {
    const anchor = 'PackageList(this).packages.apply {';
    if (!enabled) {
      c.modResults.contents = c.modResults.contents.replace(
        /\s*add\(com\.nienfos\.updater\.BridgeUpdaterPackage\(\)\)/g,
        ''
      );
      return c;
    }
    if (!c.modResults.contents.includes('add(com.nienfos.updater.BridgeUpdaterPackage())')) {
      if (!c.modResults.contents.includes(anchor))
        throw new Error('Unsupported MainApplication template');
      c.modResults.contents = c.modResults.contents.replace(
        anchor,
        anchor + '\n          add(com.nienfos.updater.BridgeUpdaterPackage())'
      );
    }
    return c;
  });
  return withDangerousMod(config, [
    'android',
    (c) => {
      const base = path.join(c.modRequest.platformProjectRoot, 'app/src/main');
      const target = path.join(base, 'java/com/nienfos/updater');
      if (!enabled) {
        fs.rmSync(target, { recursive: true, force: true });
        fs.rmSync(path.join(base, 'res/xml/bridge_update_paths.xml'), {
          force: true
        });
        return c;
      }
      fs.mkdirSync(target, { recursive: true });
      const source = fs
        .readFileSync(path.join(__dirname, 'android/BridgeUpdater.kt'), 'utf8')
        .replace('__BRIDGE_HOST__', origin.hostname)
        .replace('__SOURCE_APP__', options.sourceApp);
      fs.writeFileSync(path.join(target, 'BridgeUpdater.kt'), source);
      fs.mkdirSync(path.join(base, 'res/xml'), { recursive: true });
      fs.writeFileSync(
        path.join(base, 'res/xml/bridge_update_paths.xml'),
        '<?xml version="1.0" encoding="utf-8"?><paths><external-files-path name="updates" path="Download/bridge_updates/" /></paths>'
      );
      return c;
    }
  ]);
};
