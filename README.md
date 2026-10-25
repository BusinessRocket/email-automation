# Email automation

A GitHub Actions workflow sends a personalized email to every recipient in a list through Gmail SMTP. It runs **daily at 02:00 UTC**, and you can also start it by hand from the Actions tab.

The repo is public, so it contains no addresses or passwords. All of those live in encrypted repository secrets.

## Setup

1. **Create a Gmail App Password.** Turn on 2-Step Verification for your Google account, then create a password at https://myaccount.google.com/apppasswords.
2. **Add three repository secrets** under Settings → Secrets and variables → Actions:

   | Secret | Value |
   |---|---|
   | `GMAIL_ADDRESS` | your Gmail address |
   | `GMAIL_APP_PASSWORD` | the 16-character app password |
   | `RECIPIENTS_CSV` | the full CSV text, using the same format as `recipients.example.csv` |

3. **Edit the message** in `template/subject.txt` and `template/body.txt`. You can use any CSV column as a placeholder, for example `{name}`.
4. **Test it.** Go to Actions → Send emails → Run workflow. A manual run is a dry run by default: it logs each email without sending anything. Untick "Dry run" to send for real.

## Behaviour

- Scheduled runs always send live.
- If one recipient fails, the error is logged and the run continues with the rest. The job is then marked failed so the problem is visible.
- If a secret is missing, the run fails with a message that names the missing secret.
- Gmail limits personal accounts to about 500 recipients per day.
- GitHub may start scheduled runs a few minutes late. It also disables schedules on public repos after 60 days without commits. You can re-enable a disabled schedule from the Actions tab.
- To change the time, edit `cron` in `.github/workflows/send-emails.yml`. The cron time is in UTC.
