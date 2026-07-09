#!/usr/bin/env bash

backend_read_env_value() {
  local key="$1"
  local file="$2"
  if [[ ! -f "${file}" ]]; then
    return 1
  fi

  local line
  line="$(grep -E "^${key}=" "${file}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    return 1
  fi

  printf '%s\n' "${line#*=}" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

backend_is_expected_process() {
  local root_dir="$1"
  local pid="$2"

  if [[ ! "${pid}" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  if ! kill -0 "${pid}" 2>/dev/null; then
    return 1
  fi

  local root_real cwd cmdline
  root_real="$(readlink -f "${root_dir}" 2>/dev/null || true)"
  cwd="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"
  cmdline="$(tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null || true)"

  if [[ -z "${root_real}" || -z "${cwd}" || "${cwd}" != "${root_real}" ]]; then
    return 1
  fi
  if [[ "${cmdline}" != *"main.py"* && "${cmdline}" != *"backend.app.main"* ]]; then
    return 1
  fi

  return 0
}

backend_find_listener_pid() {
  local port="$1"
  if ! command -v ss >/dev/null 2>&1; then
    return 1
  fi
  ss -ltnp "sport = :${port}" 2>/dev/null \
    | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
    | head -n 1
}
