import aws_cdk as core
import aws_cdk.assertions as assertions

from lab02.lab02_stack import Lab02Stack

# example tests. To run these tests, uncomment this file along with the example
# resource in lab02/lab02_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = Lab02Stack(app, "lab02")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
