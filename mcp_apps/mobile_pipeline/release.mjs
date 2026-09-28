import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  copyFileSync,
  lstatSync,
  realpathSync,
} from "node:fs";
import { resolve, dirname } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
export const toolkitVersion = "0.1.0";
export function operate(root, command, options = {}) {
  root = realpathSync(root);
  const read = (p) => JSON.parse(readFileSync(resolve(root, p), "utf8"));
  const project = read("infra/mobile/project.json"),
    release = read("infra/mobile/release.json");
  if (
    project.kind !== "nienfos.mobile-project" ||
    project.version !== 1 ||
    project.framework !== "react-native-expo"
  )
    throw new Error("Unsupported project contract");
  if (release.toolkitVersion !== toolkitVersion)
    throw new Error(
      "Toolkit version mismatch: review and promote the consumer before building",
    );
  if (
    !/^[a-z0-9][a-z0-9-]{1,63}$/.test(project.sourceApp) ||
    !/^[\w.-]+\/[\w.-]+$/.test(release.repository) ||
    !/^\d+\.\d+\.\d+$/.test(release.version) ||
    !Number.isSafeInteger(release.androidBuild) ||
    release.androidBuild < 1
  )
    throw new Error("Invalid release identity");
  const profile = release.profile,
    target = project.profiles[profile];
  if (
    !target ||
    !target.apiBaseUrl ||
    !["preview", "staging", "production"].includes(profile)
  )
    throw new Error("A distribution profile with real API is required");
  const api = new URL(target.apiBaseUrl);
  if (
    api.protocol !== "https:" ||
    api.origin !== target.apiBaseUrl ||
    api.username ||
    api.password
  )
    throw new Error("API must be a canonical HTTPS origin");
  const source = resolve(root, project.sourceRoot);
  if (!realpathSync(source).startsWith(root + "/"))
    throw new Error("Source escapes project");
  const run = (cmd, args, cwd = root, env = process.env, capture = false) => {
    const result = spawnSync(cmd, args, {
      cwd,
      env,
      encoding: "utf8",
      stdio: capture ? "pipe" : "inherit",
      maxBuffer: 16 * 1024 * 1024,
    });
    if (result.error || result.status !== 0)
      throw new Error(`Command failed: ${cmd} ${args.slice(0, 2).join(" ")}`);
    return (result.stdout ?? "").trim();
  };
  const git = (...args) => run("git", args, root, process.env, true);
  const tag = `android-${profile}-v${release.version}-build.${release.androidBuild}`;
  const output = resolve(root, `dist/mobile/${tag}`),
    artifact = `${project.sourceApp}.apk`;
  const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");
  const engineHash = sha(fileURLToPath(import.meta.url));
  if (command === "status")
    return {
      sourceApp: project.sourceApp,
      profile,
      tag,
      toolkitVersion,
      toolkitSha256: engineHash,
      repository: release.repository,
      apiOrigin: target.apiBaseUrl,
      receiptExists: existsSync(resolve(output, "release.json")),
      dirty: !!git("status", "--porcelain"),
    };
  if (!["build", "publish"].includes(command))
    throw new Error("Expected status, build or publish");
  if (git("status", "--porcelain"))
    throw new Error("Use a clean committed checkout to build and publish");
  const commit = git("rev-parse", "HEAD");
  if (command === "build") {
    run("npm", ["run", "mobile:check"]);
    run("npm", ["run", "mobile:test"]);
    run("npm", ["run", "typecheck"], source);
    const signingPath =
      options.signingFile ||
      process.env.NIENFOS_MOBILE_SIGNING_FILE ||
      resolve(
        homedir(),
        `.local/state/nienfos-mobile-signing/${project.sourceApp}-${profile}.json`,
      );
    const stat = lstatSync(signingPath);
    if (!stat.isFile() || stat.mode & 0o077)
      throw new Error(
        "Signing credentials require a private regular file (0600)",
      );
    const signing = JSON.parse(readFileSync(signingPath, "utf8"));
    const signingKeys = [
      "ANDROID_KEYSTORE_PATH",
      "ANDROID_STORE_PASSWORD",
      "ANDROID_KEY_PASSWORD",
      "ANDROID_KEY_ALIAS",
    ];
    if (signingKeys.some((k) => typeof signing[k] !== "string" || !signing[k]))
      throw new Error("Signing configuration incomplete");
    const env = {
      ...process.env,
      ...Object.fromEntries(signingKeys.map((k) => [k, signing[k]])),
      MOBILE_PROFILE: profile,
      NODE_ENV: "production",
      EXPO_PUBLIC_API_BASE_URL: target.apiBaseUrl,
      EXPO_PUBLIC_SOURCE_APP: project.sourceApp,
      EXPO_PUBLIC_RUNTIME_PROFILE: profile,
      CI: "1",
    };
    if (!env.ANDROID_HOME || !env.JAVA_HOME)
      throw new Error("Set ANDROID_HOME and JAVA_HOME");
    run(
      "npx",
      ["expo", "prebuild", "--platform", "android", "--no-install"],
      source,
      env,
    );
    run(
      "./gradlew",
      [
        ":app:assembleRelease",
        "-PreactNativeArchitectures=arm64-v8a,x86_64",
        "--max-workers=2",
        "--console=plain",
      ],
      resolve(source, "android"),
      env,
    );
    const apk = resolve(
      source,
      "android/app/build/outputs/apk/release/app-release.apk",
    );
    const tools = resolve(
      env.ANDROID_HOME,
      `build-tools/${release.androidBuildTools}`,
    );
    const certificate = run(
      resolve(tools, "apksigner"),
      ["verify", "--print-certs", apk],
      root,
      env,
      true,
    );
    const fingerprint = certificate.match(
      /certificate SHA-256 digest: ([a-f0-9]+)/,
    )?.[1];
    if (!fingerprint || fingerprint !== release.signingCertificateSha256)
      throw new Error("Signing certificate mismatch");
    const badging = run(
      resolve(tools, "aapt"),
      ["dump", "badging", apk],
      root,
      env,
      true,
    );
    if (
      !badging.includes(`name='${target.androidApplicationId}'`) ||
      !badging.includes(`versionCode='${release.androidBuild}'`) ||
      !badging.includes(`versionName='${release.version}'`)
    )
      throw new Error("APK identity/version mismatch");
    if (git("status", "--porcelain"))
      throw new Error(
        "Build modified tracked input; review and commit before rebuilding",
      );
    mkdirSync(output, { recursive: true });
    copyFileSync(apk, resolve(output, artifact));
    const receipt = {
      schema: "nienfos.mobile-release/v1",
      sourceApp: project.sourceApp,
      profile,
      tag,
      version: release.version,
      build: release.androidBuild,
      packageId: target.androidApplicationId,
      apiOrigin: target.apiBaseUrl,
      gitCommit: commit,
      toolkitVersion,
      toolkitSha256: engineHash,
      sha256: sha(apk),
      signingCertificateSha256: fingerprint,
      artifact,
      createdAt: new Date().toISOString(),
      checks: [
        "mobile:check",
        "mobile:test",
        "native:typecheck",
        "apk-signature",
        "apk-identity",
      ],
      runtimeProfile: profile,
      mockOrDemo: false,
      productionReady: false,
    };
    writeFileSync(
      resolve(output, "release.json"),
      JSON.stringify(receipt, null, 2) + "\n",
    );
    writeFileSync(
      resolve(output, "SHA256SUMS"),
      `${receipt.sha256}  ${artifact}\n`,
    );
    return receipt;
  }
  if (typeof options.approval !== "string" || options.approval.length < 8)
    throw new Error(
      "Publication requires the existing human authorization reference",
    );
  const receipt = JSON.parse(
    readFileSync(resolve(output, "release.json"), "utf8"),
  );
  if (
    receipt.gitCommit !== commit ||
    receipt.tag !== tag ||
    receipt.sha256 !== sha(resolve(output, artifact)) ||
    receipt.toolkitSha256 !== engineHash ||
    receipt.signingCertificateSha256 !== release.signingCertificateSha256
  )
    throw new Error("Build provenance no longer matches");
  if (!existsSync(resolve(output, "validation.json")))
    throw new Error("Runtime verification receipt is required");
  const validation = JSON.parse(
    readFileSync(resolve(output, "validation.json"), "utf8"),
  );
  if (
    validation.apkSha256 !== receipt.sha256 ||
    validation.installLaunch !== true ||
    validation.apiUnauthorizedStatus !== 401
  )
    throw new Error("Runtime verification does not match this APK");
  const remote = git("remote", "get-url", "origin")
    .replace(/^git@github.com:/, "https://github.com/")
    .replace(/\.git$/, "");
  if (remote !== `https://github.com/${release.repository}`)
    throw new Error("GitHub remote mismatch");
  // No tag replacement, no asset clobber, no Actions dispatch.
  run("gh", ["api", `repos/${release.repository}`], root, process.env, true);
  git("push", "origin", `HEAD:refs/heads/${git("branch", "--show-current")}`);
  const existing = spawnSync(
    "git",
    ["rev-parse", "--verify", `refs/tags/${tag}`],
    { cwd: root, encoding: "utf8" },
  );
  if (existing.status === 0) {
    if (git("rev-list", "-n", "1", tag) !== commit)
      throw new Error("Tag points to another commit");
  } else
    git(
      "tag",
      "-a",
      tag,
      "-m",
      `Nienfos ${profile} ${release.version} (${release.androidBuild}) [skip ci]`,
    );
  git("push", "origin", `refs/tags/${tag}`);
  const notes = resolve(output, "release-notes.md");
  writeFileSync(
    notes,
    `React Native ${release.version} (${release.androidBuild}) · ${profile}\n\nReal API: ${target.apiBaseUrl}\n\nCommit: ${commit}\nSHA256: ${receipt.sha256}\n\nLogin, password recovery, device sessions, optional biometrics, pending items and project detail.\n\nValidation: local security tests, signed APK verification and installation/launch. Real-account and biometric checks: ${validation.realAccountLogin === true ? "verified" : "pending device/account verification"}.\n\nBuilt locally without GitHub Actions. Store publication is separate.\n`,
  );
  const assets = [
    artifact,
    "release.json",
    "SHA256SUMS",
    "validation.json",
  ].map((x) => resolve(output, x));
  run("gh", [
    "release",
    "create",
    tag,
    ...assets,
    "--repo",
    release.repository,
    "--verify-tag",
    "--title",
    `${project.sourceApp} ${release.version} (${release.androidBuild}) · ${profile}`,
    "--notes-file",
    notes,
    ...(profile === "production" ? [] : ["--prerelease"]),
  ]);
  return {
    ...receipt,
    published: true,
    releaseUrl: `https://github.com/${release.repository}/releases/tag/${tag}`,
    approval: options.approval,
  };
}
if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    const root = process.argv[2],
      command = process.argv[3] || "status",
      approval = process.argv[4];
    console.log(JSON.stringify(operate(root, command, { approval }), null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
