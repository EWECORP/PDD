systemctl daemon-reload
systemctl enable --now prefect-worker-pdd.service
systemctl status prefect-worker-pdd.service



systemctl restart prefect-worker-pdd.service
systemctl status prefect-worker-pdd.service --no-pager