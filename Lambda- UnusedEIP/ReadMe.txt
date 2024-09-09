Use event bridge to triggere the lambda function:

Event bus: default
name: UnusedEBSTrigger
Schedule expression: cron(0 10 ? * MON,FRI *)
Service principal: events.amazonaws.com
Statement ID: lambda-d0db5f71-df6a-4875-8367-5a0b18c6862a
url: events/home#/rules/UnusedEBSTrigger