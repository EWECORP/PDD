#!/usr/bin/env bash
# Reusable PDD backend release procedure. Run as root on the target server.
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: bash deploy_backend.sh TEST|PROD VERSION stage|promote|deploy|status

stage   Verify /tmp/pdd-backend-VERSION.zip(.sha256), extract and validate.
promote Stop the worker, preserve backend.prev-TIMESTAMP and activate the stage.
deploy  Update only the Inventory precheck and operational daily deployments.
status  Show installed version, worker and the two deployment names.

Run each phase separately. Promote TEST and validate the daily flow before PROD.
EOF
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  usage
  exit 0
fi
if [[ $# -ne 3 ]]; then usage >&2; exit 2; fi
ENVIRONMENT=$1
VERSION=$2
PHASE=$3
if [[ $EUID -ne 0 ]]; then echo 'Run as root (sudo bash ...)' >&2; exit 1; fi
if [[ ! $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid release version: $VERSION" >&2
  exit 2
fi

BASE=/srv/PDD
NEXT="$BASE/backend.next-$VERSION"
BACKEND="$BASE/backend"
ZIP="/tmp/pdd-backend-$VERSION.zip"
SHA="$ZIP.sha256"
MARKER=.deploy-validated
API_URL=https://orquestador.connexa-cloud.com/api

case $ENVIRONMENT in
  TEST)
    RUN_USER=pdd
    RUN_HOME=/var/lib/pdd
    PYTHON=/srv/PDD/.venv/bin/python
    PREFECT=/srv/PDD/.venv/bin/prefect
    ENV_FILE=/etc/connexa/pdd-test.env
    SERVICE=prefect-worker-pdd-test.service
    PREFECT_FILE=prefect.yaml
    PRECHECK=PDD_INVENTORY_COVERAGE_PRECHECK
    MASTER=PDD_OPERATIONAL_DAILY_MASTER
    ;;
  PROD)
    RUN_USER=root
    RUN_HOME=/root
    PYTHON=/srv/FORECAST/venv/bin/python
    PREFECT=/srv/FORECAST/venv/bin/prefect
    ENV_FILE=/etc/connexa/pdd-prod.env
    SERVICE=prefect-worker-pdd.service
    PREFECT_FILE=prefect.prod.yaml
    PRECHECK=PDD_INVENTORY_COVERAGE_PRECHECK_PROD
    MASTER=PDD_OPERATIONAL_DAILY_MASTER_PROD
    ;;
  *) echo "Unknown environment: $ENVIRONMENT" >&2; exit 2 ;;
esac

run_as_worker() {
  if [[ $RUN_USER == root ]]; then
    env HOME="$RUN_HOME" "$@"
  else
    runuser -u "$RUN_USER" -- env HOME="$RUN_HOME" "$@"
  fi
}

require_runtime() {
  [[ -x $PYTHON && -x $PREFECT && -r $ENV_FILE ]] || {
    echo "Missing Python, Prefect or environment file for $ENVIRONMENT" >&2
    exit 1
  }
  systemctl cat "$SERVICE" >/dev/null
}

check_version() {
  local path=$1
  local found
  found=$(env PYTHONPATH="$path" "$PYTHON" -c \
    'import pdd_backend; print(pdd_backend.__version__)')
  [[ $found == "$VERSION" ]] || {
    echo "Expected $VERSION in $path, got $found" >&2
    exit 1
  }
}

stage() {
  require_runtime
  [[ -f $ZIP && -f $SHA ]] || { echo "Copy $ZIP and $SHA to /tmp" >&2; exit 1; }
  [[ ! -e $NEXT ]] || { echo "$NEXT already exists; inspect it first" >&2; exit 1; }
  (cd /tmp && sha256sum -c "${SHA##*/}")
  "$PYTHON" - "$ZIP" "$VERSION" <<'PY'
import stat
import sys
from pathlib import PurePosixPath
from zipfile import ZipFile
archive, version = sys.argv[1:]
with ZipFile(archive) as package:
    names = set(package.namelist())
    required = {'pyproject.toml', 'prefect.yaml', 'prefect.prod.yaml',
                'tools/deploy_backend.sh', 'pdd_backend/__init__.py'}
    if not required <= names:
        raise SystemExit(f'Missing release files: {sorted(required - names)}')
    for info in package.infolist():
        path = PurePosixPath(info.filename)
        mode = info.external_attr >> 16
        if path.is_absolute() or '..' in path.parts or stat.S_ISLNK(mode):
            raise SystemExit(f'Unsafe ZIP entry: {info.filename}')
    if f'version = "{version}"' not in package.read('pyproject.toml').decode():
        raise SystemExit('ZIP version does not match requested version')
PY
  if [[ $RUN_USER != root ]]; then
    run_as_worker test -r "$ZIP" || {
      echo "User $RUN_USER cannot read $ZIP" >&2
      exit 1
    }
  fi
  install -d -o "$RUN_USER" -g "$RUN_USER" -m 0755 "$NEXT"
  run_as_worker unzip -q "$ZIP" -d "$NEXT"
  find "$NEXT" -type d -exec chmod 0755 {} +
  find "$NEXT" -type f -exec chmod 0644 {} +
  find "$NEXT" -type f -name '*.sh' -exec chmod 0755 {} +
  cd "$NEXT"
  check_version "$NEXT"
  if [[ $ENVIRONMENT == PROD ]]; then
    (
      test_env=$(mktemp /tmp/pdd-prod-test-env.XXXXXX)
      trap 'rm -f "$test_env"' EXIT
      chmod 0600 "$test_env"
      sed '/^PDD_OPERATIONAL_ALLOW_PRODUCTION=/d' "$ENV_FILE" > "$test_env"
      run_as_worker env PDD_ENV_PATH="$test_env" \
        PDD_OPERATIONAL_TARGET_ENV=PROD \
        PDD_OPERATIONAL_ALLOW_PRODUCTION=false PYTHONPATH="$NEXT" \
        "$PYTHON" -m pytest -q -p no:cacheprovider
    )
  else
    run_as_worker env PDD_ENV_PATH="$ENV_FILE" \
      PDD_OPERATIONAL_TARGET_ENV=TEST PYTHONPATH="$NEXT" \
      "$PYTHON" -m pytest -q -p no:cacheprovider
  fi
  run_as_worker env PDD_ENV_PATH="$ENV_FILE" \
    PDD_OPERATIONAL_TARGET_ENV="$ENVIRONMENT" \
    PDD_OPERATIONAL_ALLOW_PRODUCTION=$([[ $ENVIRONMENT == PROD ]] && echo true || echo false) \
    PYTHONPATH="$NEXT" "$PYTHON" tools/validate_sql.py
  run_as_worker env PDD_ENV_PATH="$ENV_FILE" \
    PDD_OPERATIONAL_TARGET_ENV="$ENVIRONMENT" \
    PDD_OPERATIONAL_ALLOW_PRODUCTION=$([[ $ENVIRONMENT == PROD ]] && echo true || echo false) \
    PYTHONPATH="$NEXT" "$PYTHON" tools/validate_operational.py
  printf '%s\n' "environment=$ENVIRONMENT" "version=$VERSION" \
    "sha256=$(sha256sum "$ZIP" | cut -d ' ' -f1)" > "$NEXT/$MARKER"
  chmod 0644 "$NEXT/$MARKER"
  echo "STAGED_OK $ENVIRONMENT $VERSION $NEXT"
}

promote() {
  require_runtime
  [[ -d $NEXT && -f $NEXT/$MARKER && -d $BACKEND ]] || {
    echo "Missing staged release, validation marker or current backend" >&2
    exit 1
  }
  grep -Fxq "environment=$ENVIRONMENT" "$NEXT/$MARKER"
  grep -Fxq "version=$VERSION" "$NEXT/$MARKER"
  check_version "$NEXT"
  systemctl is-active --quiet "$SERVICE" || {
    echo "$SERVICE is not active; investigate before promotion" >&2
    exit 1
  }
  local backup stopped moved_old moved_new
  backup="$BASE/backend.prev-$(date +%Y%m%d-%H%M%S)"
  [[ ! -e $backup ]] || { echo "$backup already exists" >&2; exit 1; }
  stopped=0; moved_old=0; moved_new=0
  rollback_promotion() {
    local rc=$?
    trap - ERR
    if [[ $stopped == 1 ]]; then
      systemctl stop "$SERVICE" || true
      if [[ $moved_new == 1 && -d $BACKEND ]]; then
        mv "$BACKEND" "$BASE/backend.failed-$(date +%Y%m%d-%H%M%S)" || true
      fi
      if [[ $moved_old == 1 && -d $backup ]]; then
        mv "$backup" "$BACKEND" || true
        run_as_worker "$PYTHON" -m pip install --no-deps -e "$BACKEND" || true
      fi
      systemctl start "$SERVICE" || true
    fi
    echo "PROMOTION_FAILED rc=$rc; inspect $SERVICE and $BASE" >&2
    exit "$rc"
  }
  trap rollback_promotion ERR
  systemctl stop "$SERVICE"; stopped=1
  mv "$BACKEND" "$backup"; moved_old=1
  mv "$NEXT" "$BACKEND"; moved_new=1
  run_as_worker "$PYTHON" -m pip install --no-deps -e "$BACKEND"
  check_version "$BACKEND"
  systemctl start "$SERVICE"
  systemctl is-active --quiet "$SERVICE"
  trap - ERR
  echo "PROMOTED_OK $ENVIRONMENT $VERSION backup=$backup"
}

deploy() {
  require_runtime
  [[ -f $BACKEND/$MARKER ]] || {
    echo 'Current backend has no validation marker; run stage/promote first' >&2
    exit 1
  }
  grep -Fxq "environment=$ENVIRONMENT" "$BACKEND/$MARKER"
  grep -Fxq "version=$VERSION" "$BACKEND/$MARKER"
  check_version "$BACKEND"
  cd "$BACKEND"
  run_as_worker env PDD_ENV_PATH="$ENV_FILE" \
    PDD_OPERATIONAL_TARGET_ENV="$ENVIRONMENT" \
    PREFECT_API_URL="$API_URL" \
    "$PREFECT" deploy --prefect-file "$PREFECT_FILE" --name "$PRECHECK"
  run_as_worker env PDD_ENV_PATH="$ENV_FILE" \
    PDD_OPERATIONAL_TARGET_ENV="$ENVIRONMENT" \
    PREFECT_API_URL="$API_URL" \
    "$PREFECT" deploy --prefect-file "$PREFECT_FILE" --name "$MASTER"
  echo "DEPLOYED_OK $ENVIRONMENT $PRECHECK $MASTER"
}

status() {
  require_runtime
  check_version "$BACKEND"
  systemctl status "$SERVICE" --no-pager -l
  run_as_worker env PDD_ENV_PATH="$ENV_FILE" \
    PDD_OPERATIONAL_TARGET_ENV="$ENVIRONMENT" PREFECT_API_URL="$API_URL" \
    "$PREFECT" deployment inspect \
    "PDD - Verificar cobertura Inventory/$PRECHECK"
  run_as_worker env PDD_ENV_PATH="$ENV_FILE" \
    PDD_OPERATIONAL_TARGET_ENV="$ENVIRONMENT" PREFECT_API_URL="$API_URL" \
    "$PREFECT" deployment inspect \
    "PDD - Orquestador diario completo/$MASTER"
}

case $PHASE in
  stage) stage ;;
  promote) promote ;;
  deploy) deploy ;;
  status) status ;;
  *) usage >&2; exit 2 ;;
esac
