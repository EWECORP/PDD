#!/usr/bin/env bash
# Ayuda interactiva para TEST. No ejecutar como root ni usar este archivo como
# unidad systemd. El servicio real carga las mismas rutas desde
# prefect-worker-pdd-test.service.

set -euo pipefail

cd /srv/PDD/backend
export HOME=/var/lib/pdd
export PDD_ENV_PATH=/etc/connexa/pdd-test.env
export PDD_OPERATIONAL_TARGET_ENV=TEST
export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
export PATH=/srv/PDD/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

/srv/PDD/.venv/bin/python3 -m pip show diarco-pdd-backend prefect
/srv/PDD/.venv/bin/python3 tools/validate_sql.py
/srv/PDD/.venv/bin/python3 tools/validate_operational.py
/srv/PDD/.venv/bin/pdd-etl runtime-config show --environment TEST
/srv/PDD/.venv/bin/prefect config view | grep PREFECT_API_URL

echo "Entorno PDD TEST validado. Scope/modelo se administran con runtime-config; no edite UUID en el archivo de secretos."
