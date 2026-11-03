"""Starter templates and sequences for both businesses.

Seeding only inserts what's missing (matched by name), so it never overwrites
edits made in the dashboard.

Every starter email follows the same inbox-friendly shape: one short idea the
reader can use, at most one link, a question they can answer by replying, and
a P.S. They use the plain style, so they look like an email typed in Gmail.
"""

from . import db

TEMPLATES = {
    "tiling": {
        "Quote follow-up 1": (
            "Your tiling quote from {business_name}",
            """Hi {first_name},

Just checking your quote came through OK and that everything in it makes sense.

If you'd like to change the tiles, the layout or the timing, reply to this email and I'll update it.

Cheers,
{sender_name}

P.S. When are you hoping to get the work done? A rough month is fine."""),
        "Quote follow-up 2": (
            "A quick tip before you pick your tiles",
            """Hi {first_name},

One thing worth knowing before you lock in your tiles: order about 10% extra. Cuts and breakages use some up, and tiles from a later batch can be hard to match if you ever need a repair.

Got other questions, like how long the job takes or whether the old tiles need to come up first? Just reply here.

Thanks,
{sender_name}

P.S. Prefer a phone call? Reply with a good time and I'll ring you."""),
        "Quote follow-up 3": (
            "Should I keep your quote open?",
            """Hi {first_name},

I haven't heard back about your tiling quote, so I'll keep this short. Is the project still going ahead?

Reply "yes" and I'll pencil in a start date, or "no" and I'll close the quote off. Either is fine.

Thanks,
{sender_name}"""),
        "Job complete: review request": (
            "How did your new tiles turn out?",
            """Hi {first_name},

Thanks for choosing {business_name}. I hope you're enjoying the finished job.

Would you mind leaving a short review? It helps people nearby find a tiler they can trust, and it only takes a minute.

[[Leave a review|{review_url}]]

Thanks,
{sender_name}

P.S. If anything isn't quite right, reply to this email and we'll come back and fix it."""),
        "Tile care tips": (
            "One habit that keeps new tiles looking new",
            """Hi {first_name},

It's been about a month since we finished your tiling, so here's the habit that makes the biggest difference: **clean with a pH-neutral cleaner**. Bleach and acidic cleaners slowly eat into grout, and tired grout is what makes tiles look old.

In showers and other wet areas, reseal the grout every one to two years as well.

Cheers,
{sender_name}

P.S. Planning another room? Reply with what you have in mind and I'll put a quote together."""),
        "Seasonal promotion": (
            "Planning a bathroom or kitchen update?",
            """Hi {first_name},

A quick tip if you're thinking about new tiles this year: large tiles make a small bathroom look bigger, because there are fewer grout lines breaking up the space.

We're booking tiling jobs for the coming months now. Reply with the room you have in mind and I'll put a quote together.

Cheers,
{sender_name}

P.S. Photos help. Attach a couple of the room as it is now and I can give you a much closer price."""),
        # For a campaign 3 to 6 months later: only tag quote, skip tag won.
        "Quote check-in": (
            "Still thinking about your tiling, {first_name}?",
            """Hi {first_name},

A while back we quoted on some tiling for you. Plans often change, so I thought I'd check in.

If the job is back on, reply "yes" and I'll update the quote with current prices and our next start dates.

Cheers,
{sender_name}

P.S. If you've already had it done, no worries at all. Reply "done" and I won't email about it again."""),
        # A free offer other tilers charge for. Edit it to what you will really deliver.
        "Offer: free grout and seal check": (
            "A free grout check for your bathroom",
            """Hi {first_name},

Grout in showers wears down slowly, and by the time you notice cracks or dark lines, water can already be getting behind the tiles.

This month I'm doing free grout and seal checks for past customers. I'll take a look, tell you honestly if anything needs doing, and there's no charge if it doesn't.

Reply "check" and I'll find a time that suits you.

Cheers,
{sender_name}

P.S. It takes about 15 minutes, and you don't need to clear anything out first."""),
        # Follow-ups after a personal first email to a builder (sent by hand or by script).
        "Outreach follow-up 1": (
            "quick follow-up",
            """Hi {first_name},

Just bumping my email from earlier this week in case it got buried.

Have you got a bathroom, kitchen or floor coming up I could quote on? Send me the plans and I'll have an itemised quote back within 48 hours.

Cheers,
{sender_name}"""),
        "Outreach follow-up 2": (
            "one thing that saves rework in wet areas",
            """Hi {first_name},

One thing worth checking on every wet area: that the waterproofing membrane has fully cured before tiling starts. Tiling too early is a common cause of leaks that show up months later as defect claims.

Happy to quote your next bathroom whenever it suits.

Cheers,
{sender_name}"""),
        "Outreach follow-up 3": (
            "closing the loop",
            """Hi {first_name},

I won't keep following up after this one. If you ever need a tiler for a bathroom, kitchen or floor, just reply here and I'll get back to you quickly.

Cheers,
{sender_name}"""),
    },
    "ecoshine": {
        "Welcome": (
            "Thanks for getting in touch",
            """Hi {first_name},

Thanks for contacting {business_name}. We clean with eco-friendly products, and your home still gets properly clean.

What day suits you for your first clean? Reply with a day and how many bedrooms and bathrooms you have, and I'll send you a price.

Talk soon,
{sender_name}

P.S. Rather talk it through? Reply with your number and a good time to call."""),
        "Lead follow-up": (
            "Still looking for a cleaner, {first_name}?",
            """Hi {first_name},

Just following up in case my last email got buried.

A quick tip while you're deciding: for most homes, a clean every fortnight keeps things under control without the cost of a weekly visit.

If you'd like a price, reply with how often you'd like us and the size of your home.

Thanks,
{sender_name}"""),
        "Post-clean review": (
            "How was your clean?",
            """Hi {first_name},

Thanks for having us in your home. I hope everything is sparkling.

Could you leave a quick review? It makes a big difference to a small local business like ours.

[[Leave a review|{review_url}]]

Thanks,
{sender_name}

P.S. If we missed anything, reply here and we'll come back and fix it."""),
        "Rebook reminder": (
            "Time for your next clean?",
            """Hi {first_name},

It's been about three weeks since your last clean. Want me to book the next one?

Just reply with a day that suits you.

Thanks,
{sender_name}

P.S. Want us to come back regularly? Reply "regular" with how often, and I'll set it up so you don't have to think about it."""),
        "Holiday deep clean": (
            "Book a deep clean before the holidays",
            """Hi {first_name},

If you're having people over these holidays, start with the spots guests actually notice: the bathroom they'll use, the kitchen benches and the entry. Everything else can wait.

Or let us do the lot: kitchen, bathrooms, floors, skirting boards and the bits that usually get missed. Reply "deep clean" and I'll send you a price and the dates we have left.

Thanks,
{sender_name}

P.S. December fills up fast, so the earlier you reply, the more dates you can choose from."""),
        # For a campaign 3 to 6 months later: only tag lead, skip tag customer.
        "Lead check-in": (
            "Still after a cleaner, {first_name}?",
            """Hi {first_name},

You asked us about cleaning a few months ago, so I thought I'd check in.

If you'd still like a hand, reply with how often you'd like us and I'll send you a price and our next free days.

Thanks,
{sender_name}

P.S. Found someone already? No worries. Reply "sorted" and I won't email about it again."""),
        # A free offer other cleaners charge for. Edit it to what you will really deliver.
        "Offer: free oven clean": (
            "A free oven clean with your first booking",
            """Hi {first_name},

Most cleaners charge extra for the oven, because it's the job nobody wants to do.

Book your first clean with us this month and we'll do the oven for free, inside and out.

Reply "oven" with a day that suits you and I'll lock it in.

Thanks,
{sender_name}

P.S. We use eco-friendly products on the oven too, so there are no harsh fumes in your kitchen afterwards."""),
        # Follow-ups after a personal first email to an agency (sent by hand or by script).
        "Outreach follow-up 1": (
            "quick follow-up",
            """Hi {first_name},

Just bumping my email from earlier this week in case it got buried.

Have you got a vacate or a listing coming up I could quote? Reply with the address and I'll send a fixed price the same day.

Thanks,
{sender_name}"""),
        "Outreach follow-up 2": (
            "two spots inspectors always check",
            """Hi {first_name},

A quick tip you can pass on to tenants: the oven and the window tracks are two spots that are easy to miss on a vacate clean, and inspectors check both.

Happy to quote your next vacate whenever it suits.

Thanks,
{sender_name}"""),
        "Outreach follow-up 3": (
            "closing the loop",
            """Hi {first_name},

I won't keep following up after this one. If you ever need a vacate, pre-sale or deep clean, just reply here and I'll sort it.

Thanks,
{sender_name}"""),
    },
}

# business -> [(name, trigger tag, exit tags, [(delay days, template name), ...])]
SEQUENCES = {
    "tiling": [
        ("Quote follow-up", "quote", "won,completed",
         [(2, "Quote follow-up 1"), (3, "Quote follow-up 2"), (7, "Quote follow-up 3")]),
        ("After the job", "completed", "",
         [(1, "Job complete: review request"), (30, "Tile care tips")]),
        # Tag a business 'outreach' on the day its first email goes out. Follow-ups go
        # on days 3, 7 and 14, and stop as soon as they reply (tagged 'replied' automatically).
        ("Builder outreach", "outreach", "replied,won",
         [(3, "Outreach follow-up 1"), (4, "Outreach follow-up 2"), (7, "Outreach follow-up 3")]),
    ],
    "ecoshine": [
        ("New lead", "lead", "customer",
         [(0, "Welcome"), (3, "Lead follow-up")]),
        ("Customer care", "customer", "",
         [(1, "Post-clean review"), (21, "Rebook reminder")]),
        ("Agency outreach", "outreach", "replied,customer",
         [(3, "Outreach follow-up 1"), (4, "Outreach follow-up 2"), (7, "Outreach follow-up 3")]),
    ],
}


def seed(conn) -> None:
    for business, templates in TEMPLATES.items():
        for name, (subject, body) in templates.items():
            conn.execute("INSERT OR IGNORE INTO templates (business, name, subject, body, style)"
                         " VALUES (?, ?, ?, ?, 'plain')", (business, name, subject, body))
    for business, sequences in SEQUENCES.items():
        for name, trigger, exits, steps in sequences:
            cur = conn.execute(
                "INSERT OR IGNORE INTO sequences (business, name, trigger_tag, exit_tags)"
                " VALUES (?, ?, ?, ?)", (business, name, trigger, db.store_tags(exits)))
            if cur.rowcount == 0:
                continue  # already exists; leave its steps alone
            seq_id = cur.lastrowid
            for position, (delay, template_name) in enumerate(steps, start=1):
                tpl_id = conn.execute("SELECT id FROM templates WHERE business = ? AND name = ?",
                                      (business, template_name)).fetchone()[0]
                conn.execute("INSERT INTO sequence_steps (sequence_id, position, delay_days,"
                             " template_id) VALUES (?, ?, ?, ?)",
                             (seq_id, position, delay, tpl_id))
    conn.commit()
