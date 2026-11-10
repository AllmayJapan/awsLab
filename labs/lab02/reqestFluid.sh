#!/bin/bash

set -euo pipefail

: "${ALB_DNS:?ALB_DNS is not set}"

for i in $(seq 1 300); do
	status=$(curl --max-time 5 -s -o /dev/null \
	-w "%{http_code}\n" \
	"http://${ALB_DNS}/?rate-test=${i}")

	printf '%s request=%03d status=%s\n' \
		"$(date +%H:%M:%S)" "$i" "$status"

	sleep 0.2
done
