# Iniciar entorno virtual
source /srv/FORECAST/venv/bin/activate

# Configurar variables de entorno
echo $PREFECT_API_URL
export PREFECT_API_URL="https://orquestador.connexa-cloud.com/api"
prefect config view | grep PREFECT_API_URL

# Iniciar el despliegue de Prefect
cd /srv/PDD/backend
prefect deploy --all

# Iniciar el entorno de PDD
cd /srv/PDD/backend
export PDD_ENV_PATH=/srv/PDD/backend/.env

pdd-etl --help
python -m pip show diarco-pdd-backend prefect
python tools/validate_sql.py


### INICIAR EL ENTORNO
cd /srv/PDD/backend
source /srv/FORECAST/venv/bin/activate
export PDD_ENV_PATH=/srv/PDD/backend/.env
export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api

prefect config view | grep PREFECT_API_URL

# Instalar dependencias del proyecto
python -m pip install -e .

### Actualizá el modelo en .env:
sed -i \
  's/^PDD_MODEL_VERSION_UUID=.*/PDD_MODEL_VERSION_UUID=a0a35b25-628d-43f1-b651-82c97207fc60/' \
  /srv/PDD/backend/.env

# Validar la corrección
python tools/validate_sql.py

### Comprobar la nueva Huella
python tools/snapshot_manifest_inputs.py \
  --scope-version-uuid b710f4d6-1bd8-4c32-8b1d-a3425c252cb9


### Reiniciar el Worker
systemctl restart prefect-worker-pdd.service
systemctl status prefect-worker-pdd.service --no-pager

### Revisar Ejecución de Prefect
prefect flow-run ls   --flow-name "PDD - Backfill inicial y PDVB"   --limit 5