import aws_cdk as core
import aws_cdk.assertions as assertions

from lab01.lab01_stack import Lab01Stack

# example tests. To run these tests, uncomment this file along with the example
# resource in lab01/lab01_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = Lab01Stack(app, "lab01")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
