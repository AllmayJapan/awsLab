#!/bin/bash

for i in $(seq 1 120); do
	curl -s -o /dev/null \
	-w "%{http_code}\n" \
	"http://Lab02S-WebAl-zE0omlP3FDzY-775356634.ap-northeast-1.elb.amazonaws.com/"
	sleep 0.2
done
