# Email automation

This repo has two parts:

- **Marketing engine** (`engine/`): email marketing for Capital Tile Studio and EcoShine Cleaning. Each business sends from its own Gmail account. It runs on your PC with a local dashboard.
- **Daily GitHub Actions sender** (`send_emails.py`): the original simple sender, described further down. It is unchanged.

## Marketing engine

What it does:

- **Contact lists**: a separate list for each business. You can add contacts by hand or import a CSV. It picks up columns like Email, First/Last Name, Mobile, Suburb and Tags. Duplicates are merged, and an unsubscribed contact stays unsubscribed.
- **Templates**: plain-text bodies with `{first_name}`-style placeholders, `**bold**` and `[[Link text|https://link]]` links. Each template has a style:
  - **Plain** (the default) looks like an email typed in Gmail, and Gmail usually puts it in the Primary tab.
  - **Branded** adds a coloured header and turns links into buttons. Gmail usually files it under Promotions.

  Every email gets the business details and an unsubscribe line. `{sender_name}` signs the email; set `sender_name` in `businesses.json` (for example "Sam"), or it reads "The Capital Tile Studio team".

  Besides the sequence emails, each business has two campaign templates you send yourself:
  - **Quote check-in / Lead check-in** re-contact people who asked but never booked. Send them 3 to 6 months later.
  - **Offer: free grout and seal check / free oven clean** give away something other businesses charge for. Edit the offer to what you will really deliver before you send it.
- **Campaigns**: send a template to a business's whole list, or to one tag only, optionally skipping another tag. For example, only `quote` and skip `won` reaches everyone who got a quote but didn't go ahead. Dry run first. A campaign never sends to the same person twice, so if it stops partway (daily limit, errors) you send it again to continue.
- **Sequences**: automatic follow-ups. Each one is started by a tag and stopped by exit tags:

  | Business | Sequence | Starts on tag | Steps | Stops on |
  |---|---|---|---|---|
  | Tiling | Quote follow-up | `quote` | day 2, 5, 12 | `won`, `completed` |
  | Tiling | After the job | `completed` | review request day 1, care tips day 31 | |
  | EcoShine | New lead | `lead` | welcome right away, follow-up day 3 | `customer` |
  | EcoShine | Customer care | `customer` | review request day 1, rebook day 22 | |

- **Unsubscribes and bounces**: every email has a `List-Unsubscribe` header and a "reply unsubscribe" footer. The daily run reads each inbox over IMAP and marks those senders unsubscribed. It marks bounced addresses too.
- **Safety**: everything is a dry run unless you choose to send. Each business has its own daily cap (`daily_limit`, 400 by default; free Gmail allows about 500 a day and Google Workspace about 2,000). A run stops after 5 failures in a row.

### Setup (Windows)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

1. **Gmail app passwords.** Each business account needs 2-Step Verification turned on. Then create an app password at https://myaccount.google.com/apppasswords. Put both addresses and passwords in `.env`. `.env` is git-ignored.
2. **Business details.** Fill in `phone`, `website`, `address`, `review_url` and `booking_url` in `businesses.json`. Buttons with an empty link are left out of emails. Anti-spam law (the Spam Act in Australia, CAN-SPAM in the US) expects your business identity in the footer, and you should only email people who have agreed to hear from you or are existing customers.
3. **Check the logins:** `.venv\Scripts\python -m engine check`
4. **Open the dashboard:** `.venv\Scripts\python -m engine serve`, then go to http://127.0.0.1:5050

### Getting into the inbox

- **Write like a person.** The starter templates all follow one shape: one useful idea, at most one link, a question answered by replying, and a P.S. Keep that shape when you write new ones.
- **Ask for replies.** Replies tell Gmail people want your emails more than anything else does.
- **Test where it lands.** In the template editor, send a test to a Gmail, an Outlook and an iCloud address you own, plus the address mail-tester.com gives you for a spam score.
- **Start slowly.** A new Gmail account should send about 20 to 30 emails a day for the first two weeks. Lower `daily_limit` in `businesses.json` while you warm up.
- **Only email people who know you,** and split lists with tags so each email suits its reader.
- **Leave unsubscribing easy.** People who don't want your emails and can't leave mark them as spam, which hurts every later send.
- **Longer term,** send from your own domain through Google Workspace. Mail from a business domain is trusted more than a free @gmail.com address.

### Scheduled run

Sequences only send when something runs them. `tick.pyw` checks both inboxes for unsubscribes, then sends whatever is due, and logs to `data\tick.log`. Run it every 15 minutes so a new lead gets the Welcome email within minutes. Emails only go out between 8am and 7pm on this PC's clock (`SEND_FROM_HOUR` and `SEND_UNTIL_HOUR` in `engine/__main__.py`); anything due overnight waits for the morning. To schedule it, run this in PowerShell:

```powershell
schtasks /Create /SC MINUTE /MO 15 /TN "Marketing engine" /TR '"C:\Users\thinl\email-automation\.venv\Scripts\pythonw.exe" "C:\Users\thinl\email-automation\tick.pyw"'
```

`pythonw` runs it without a console window. It only runs while you're logged in and the PC is on; overdue emails go out on the next run. You can also run sequences from the dashboard's Overview page.

### Command line

```
python -m engine init                      create the database and starter templates
python -m engine check                     test both Gmail logins
python -m engine import tiling leads.csv --tag quote
python -m engine campaign 3 [--live]       send campaign #3 (dry run without --live)
python -m engine tick [--live] [--any-time]  check inboxes, then run sequences
python -m engine sync-unsubscribes
python -m engine serve [--port 5050]
```

Contacts, templates and send history are stored in `data/engine.db`. That folder is git-ignored because this repo is public, so back it up yourself. When you import an old customer list, tag it with something like `past-customer` and not `completed` or `customer`. Otherwise everyone on it gets the review-request sequence.

## Daily GitHub Actions sender

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
