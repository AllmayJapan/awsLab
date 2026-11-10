import textwrap

from constructs import Construct
from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as iam,
)


def create_compute(
    scope: Construct,
    vpc: ec2.Vpc,
    app_sg: ec2.SecurityGroup,
) -> ec2.Instance:

    user_data = ec2.UserData.for_linux()

    server_script = textwrap.dedent("""\
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import socket

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = {"status": "ok"}
        else:
            body = {
                "message": "Hello from Lab02 EC2",
                "hostname": socket.gethostname(),
                "path": self.path,
            }

        data = json.dumps(body).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
    """)
    service_unit = textwrap.dedent("""\
[Unit]
Description=Lab02 Web Application
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/lab02/server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target

    """)
    user_data.add_commands(
"mkdir -p /opt/lab02",
"cat > /opt/lab02/server.py <<'PY'\n"
+ server_script + "PY",
"cat > /etc/systemd/system/lab02-web.service << 'EOF'\n"
+ service_unit + "EOF",
"systemctl daemon-reload",
"systemctl enable --now lab02-web",
    )

    ssm_role = iam.Role(
        scope,
        "WebInstanceRole",
        assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        description="IAM Role for Lab02 EC2 SSM access",
    )

    ssm_role.add_managed_policy(
        iam.ManagedPolicy.from_aws_managed_policy_name(
            "AmazonSSMManagedInstanceCore"
        )
    )

    web_instance = ec2.Instance(
        scope,
        "WebInstance",
        vpc=vpc,
        instance_type=ec2.InstanceType("t3.micro"),
        machine_image=ec2.MachineImage.latest_amazon_linux2023(),
        role=ssm_role,
        security_group=app_sg,
        vpc_subnets=ec2.SubnetSelection(
            subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
        ),
        user_data=user_data,
        require_imdsv2=True,
    )

    return web_instance
