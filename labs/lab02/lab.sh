#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

set -a
source .env
set +a

source $HOME/workspace/awsLab/labs/lab01/.venv/bin/activate

case "${1:-}" in
    login)
        aws sso login --profile "$AWS_PROFILE"
        ;;
    whoami)
        aws sts get-caller-identity
        ;;
    synth)
        cdk synth "$CDK_STACK" \
            -c allowedIpv4="$ALLOWED_IPV4"
        ;;
    diff)
        cdk diff "$CDK_STACK" \
            -c allowedIpv4="$ALLOWED_IPV4"
        ;;
    deploy)
        cdk deploy "$CDK_STACK" \
            -c allowedIpv4="$ALLOWED_IPV4"
        ;;
    *)
        echo "Usage: ./lab.sh {login|whoami|synth|diff|deploy}"
            exit 1
        ;;
esac