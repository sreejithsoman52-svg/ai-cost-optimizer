# What was fixed from the original plan document

This repo is a corrected, completed version of the original
`AI_Cloud_Cost_Optimisation_Plan_Final.docx`. Everything below was found
by actually parsing/running the code, not by inspection alone.

## Bugs fixed

1. **`waste_detector/handler.py` — syntax error.**
   `for inst in reservation["Instances"]:",` had a stray `",` making the
   file fail to import at all. Removed.

2. **`terraform/main.tf` — HCL syntax error (x2).**
   `Action = [...]  Resource = "*"` on one line with no comma is invalid
   HCL. Fixed for the `ses:SendEmail` and `lambda:InvokeFunction`
   statements.

3. **`alerter/handler.py` — runtime crash on real data.**
   The original parsed the forecasted dollar amount out of Claude's
   free-text `forecast_commentary` with
   `.split("$")[1].split(" ")[0]`. This broke the first time it was run
   against real AI-generated text containing more than one `$` sign
   (`ValueError: could not convert string to float: '29.82/day.'`).
   Fixed by reading `forecast_30day_usd` directly from the forecast
   DynamoDB table as a number, instead of parsing it out of prose.

## Gaps filled

4. **Terraform only defined 1 of 6 Lambdas.** The original had a comment
   — `# (Repeat similar aws_lambda_function blocks for: ...)` — instead
   of actual resources. Added `aws_lambda_function` resources for
   `waste_detector`, `bill_forecaster`, `claude_analyser`,
   `report_generator`, and `alerter`, each with the correct environment
   variables matching what their `handler.py` actually reads from
   `os.environ`.

5. **Missing EventBridge wiring.** Added scheduled triggers (and the
   matching `aws_lambda_permission`) for every Lambda that needs one,
   staggered 5 minutes apart since each stage depends on the previous
   stage's DynamoDB writes completing first.

6. **Missing SES identity resource.** Added `aws_ses_email_identity` for
   the sender address (you still need to click AWS's verification email
   after `apply` — that step can't be automated).

7. **Missing `outputs.tf`.** Referenced in the folder structure but
   never provided. Added.

8. **Missing `requirements.txt` for 4 of 6 Lambdas.** Only
   `cost_collector` and `claude_analyser` had one in the original.
   Added `boto3>=1.34.0` for `waste_detector`, `bill_forecaster`,
   `report_generator`, and `alerter` (all pure-`boto3`+stdlib, no other
   dependencies needed).

## Known remaining limitation

- `claude_analyser` needs a live Anthropic API key in Secrets Manager to
  actually call the model. The demo seed script (`seed_demo_data.py`)
  writes a representative analysis directly to DynamoDB so you can demo
  the report/alert without needing that key configured.
- Cross-platform Lambda packaging (compiled deps in `anthropic`'s
  dependency tree) is handled in `scripts/build_all.sh` via
  `--platform manylinux2014_x86_64 --only-binary=:all:`.
