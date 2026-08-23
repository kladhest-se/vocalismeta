#!/usr/bin/env bash
set -Eeuo pipefail

repository='https://github.com/kladhest-se/vocalismeta.git'
plex_data_dir="${PLEX_MEDIA_SERVER_DATA_DIR:-/var/lib/plexmediaserver/Library/Application Support/Plex Media Server}"
plugin_root="${VOCALISMETA_PLUGIN_DIRECTORY:-$plex_data_dir/Plug-ins}"
plugin_dir="$plugin_root/VocalisMeta.bundle"
log_file="${VOCALISMETA_LOG_FILE:-$plex_data_dir/Logs/PMS Plugin Logs/com.plexapp.agents.spokenmeta.log}"
service_name="${PLEX_SERVICE_NAME:-plexmediaserver}"
plex_user="${PLEX_USER:-plex}"
plex_group="${PLEX_GROUP:-plex}"

usage() {
  cat >&2 <<'EOF'
Usage:
  sudo bash install-on-plex.sh --release v0.1.0
  sudo bash install-on-plex.sh --developer

Environment overrides:
  VOCALISMETA_PLUGIN_DIRECTORY  Plex Plug-ins directory
  VOCALISMETA_LOG_FILE          VocalisMeta Plex plug-in log
  PLEX_MEDIA_SERVER_DATA_DIR    Plex Media Server data directory
  PLEX_SERVICE_NAME             systemd service name (default: plexmediaserver)
  PLEX_USER / PLEX_GROUP        service ownership (default: plex:plex)
EOF
}

mode=''
release_version=''
while (( $# > 0 )); do
  case "$1" in
    --release)
      [[ -z "$mode" && $# -ge 2 ]] || { usage; exit 2; }
      mode='release'
      release_version="$2"
      shift 2
      ;;
    --developer)
      [[ -z "$mode" ]] || { usage; exit 2; }
      mode='developer'
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ -n "$mode" ]] || { usage; exit 2; }
if [[ "$mode" == 'release' && ! "$release_version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid release tag: $release_version" >&2
  exit 2
fi
if (( EUID != 0 )); then
  echo 'Run this installer as root (for example, pipe it to sudo bash).' >&2
  exit 1
fi

for command_name in awk chown date git grep id mktemp mv python3 sleep systemctl tail; do
  command -v "$command_name" >/dev/null || {
    echo "$command_name is required" >&2
    exit 1
  }
done
id "$plex_user" >/dev/null 2>&1 || {
  echo "Plex service user does not exist: $plex_user" >&2
  exit 1
}

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/vocalismeta-install.XXXXXXXX")"
clone_dir="$work_dir/repository"
bundle_source="$clone_dir/VocalisMeta.bundle"
startup_log="$work_dir/vocalismeta-startup.log"
backup_dir=''
backup_restore_target=''
rollback_needed=false
service_stopped=false
old_install_moved=false
new_install_moved=false

restore_previous_install() {
  rollback_needed=false
  echo 'VocalisMeta startup validation failed; restoring the previous installation.' >&2
  if [[ "$new_install_moved" == true ]]; then
    systemctl stop "$service_name" >/dev/null 2>&1 || true
  fi
  if [[ "$new_install_moved" == true && -e "$plugin_dir" ]]; then
    mv -- "$plugin_dir" "$work_dir/failed-VocalisMeta.bundle"
    new_install_moved=false
  fi
  if [[ "$old_install_moved" == true && -e "$backup_dir" ]]; then
    mv -- "$backup_dir" "$backup_restore_target"
    chown -R "$plex_user:$plex_group" "$backup_restore_target"
    old_install_moved=false
  fi
  if [[ "$service_stopped" == true ]]; then
    systemctl start "$service_name" >/dev/null 2>&1 || true
    service_stopped=false
  fi
}

cleanup() {
  status=$?
  if [[ "$rollback_needed" == true ]]; then
    restore_previous_install
  fi
  rm -rf -- "$work_dir"
  trap - EXIT
  exit "$status"
}
trap cleanup EXIT

if [[ "$mode" == 'release' ]]; then
  echo "Downloading VocalisMeta release $release_version"
  mkdir -p -- "$clone_dir"
  git -C "$clone_dir" init --quiet
  git -C "$clone_dir" remote add origin "$repository"
  git -C "$clone_dir" fetch --quiet --depth 1 origin \
    "refs/tags/$release_version:refs/tags/$release_version"
  git -C "$clone_dir" checkout --quiet --detach "$release_version^{commit}"
  actual_tag="$(git -C "$clone_dir" describe --tags --exact-match)"
  [[ "$actual_tag" == "$release_version" ]] || {
    echo "Downloaded revision is not exact tag $release_version" >&2
    exit 1
  }
  install_channel="stable ($release_version)"
else
  echo 'Downloading the latest VocalisMeta developer build from main'
  git clone --quiet --depth 1 --single-branch --branch main \
    "$repository" "$clone_dir"
  install_channel='development (main)'
fi
source_revision="$(git -C "$clone_dir" rev-parse --short HEAD)"

[[ -f "$bundle_source/Contents/Info.plist" ]] || {
  echo 'Downloaded repository has no VocalisMeta bundle.' >&2
  exit 1
}
[[ -f "$bundle_source/Contents/Code/__init__.py" ]] || {
  echo 'Downloaded repository has no VocalisMeta agent entry point.' >&2
  exit 1
}

bundle_version="$(python3 - "$bundle_source/Contents/Info.plist" <<'PY'
import plistlib
import sys

with open(sys.argv[1], 'rb') as handle:
    info = plistlib.load(handle)
version = info.get('CFBundleShortVersionString') or info.get('CFBundleVersion')
if not isinstance(version, str) or not version.strip():
    raise SystemExit('VocalisMeta bundle has no valid version.')
print(version.strip())
PY
)"

echo 'Running installer-owned Plex compatibility checks'
python3 - "$bundle_source/Contents/Code" <<'PY'
import ast
import os
import sys

code_dir = sys.argv[1]
invalid = []
unsupported_names = set([
    'bytes', 'bytearray', 'memoryview',
    'getattr', 'setattr', 'hasattr', 'delattr', 'open',
    'any', 'all', 'sum', 'iter', 'frozenset', 'slice',
    'file', 'execfile', 'input', 'raw_input', 'compile', 'eval',
    'globals', 'locals', 'vars', 'dir', 'super', 'type',
    'intern', 'reload', 'buffer', 'coerce',
])
generator_nodes = (ast.GeneratorExp, ast.Yield)
if hasattr(ast, 'YieldFrom'):
    generator_nodes += (ast.YieldFrom,)

for filename in sorted(os.listdir(code_dir)):
    if not filename.endswith('.py'):
        continue
    path = os.path.join(code_dir, filename)
    with open(path, 'r', encoding='utf-8') as handle:
        tree = ast.parse(handle.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, generator_nodes):
            invalid.append('%s:%d:generator' % (filename, node.lineno))
        if isinstance(node, ast.AugAssign):
            if isinstance(node.target, (ast.Attribute, ast.Subscript)):
                invalid.append('%s:%d:augmented complex target' % (
                    filename, node.lineno,
                ))
            elif not isinstance(node.op, ast.Add):
                invalid.append('%s:%d:unsupported augmented operator' % (
                    filename, node.lineno,
                ))
        if isinstance(node, ast.Name) and node.id in unsupported_names:
            invalid.append('%s:%d:missing builtin %s' % (
                filename, node.lineno, node.id,
            ))

if invalid:
    for problem in invalid:
        print('Plex compatibility failure: %s' % problem, file=sys.stderr)
    raise SystemExit(1)
PY

mkdir -p -- "$plugin_root"
if [[ -e "$plugin_dir" ]]; then
  backup_restore_target="$plugin_dir"
fi
if [[ -n "$backup_restore_target" ]]; then
  backup_dir="$(mktemp -d "$plugin_root/.vocalismeta-backup.XXXXXXXX")"
  rmdir -- "$backup_dir"
fi

chown -R "$plex_user:$plex_group" "$bundle_source"
systemctl stop "$service_name"
service_stopped=true
rollback_needed=true

if [[ -n "$backup_dir" ]]; then
  mv -- "$backup_restore_target" "$backup_dir"
  old_install_moved=true
fi
mv -- "$bundle_source" "$plugin_dir"
new_install_moved=true

started_at="$(date '+%Y-%m-%d %H:%M:%S')"
systemctl start "$service_name"

service_active=false
for unused in {1..30}; do
  if systemctl is-active --quiet "$service_name"; then
    service_active=true
    break
  fi
  sleep 1
done
[[ "$service_active" == true ]] || {
  echo 'Plex did not become active within 30 seconds.' >&2
  exit 1
}

startup_seen=false
for unused in {1..30}; do
  if [[ -f "$log_file" ]]; then
    awk -v started="$started_at" '
      /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ {
        include = (substr($0, 1, 19) >= started)
      }
      include { print }
    ' "$log_file" > "$startup_log"
    if grep -Eq \
      "Exception starting plug-in|Exception when calling function 'Start'|SECURITY ERROR|SyntaxError:|NameError:|ImportError:|AttributeError:" \
      "$startup_log"; then
      break
    fi
    if grep -q 'Creating new agent class called VocalisMetaAlbum' "$startup_log" && \
       grep -q 'Started plug-in' "$startup_log"; then
      startup_seen=true
      break
    fi
  fi
  sleep 1
done

if [[ -s "$startup_log" ]] && grep -Eq \
  "Exception starting plug-in|Exception when calling function 'Start'|SECURITY ERROR|SyntaxError:|NameError:|ImportError:|AttributeError:" \
  "$startup_log"; then
  echo 'A fatal VocalisMeta startup error was detected:' >&2
  tail -n 100 "$startup_log" >&2
  exit 1
fi
if [[ "$startup_seen" != true ]]; then
  echo 'VocalisMeta did not complete registration within 30 seconds.' >&2
  [[ -s "$startup_log" ]] && tail -n 100 "$startup_log" >&2
  exit 1
fi

rollback_needed=false
echo "VocalisMeta $bundle_version installed successfully."
echo "Install channel: $install_channel"
echo "Source revision: $source_revision"
echo 'Plex is active and no fatal VocalisMeta startup errors were detected.'
if grep -q 'resourceHashes' "$startup_log"; then
  echo "Ignored Plex's known non-fatal resourceHashes 404 during validation."
fi
if [[ -n "$backup_dir" ]]; then
  echo "Previous installation retained at: $backup_dir"
fi
