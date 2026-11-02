"""Starter templates and sequences for both businesses.

Seeding only inserts what's missing (matched by name), so it never overwrites
edits made in the dashboard.
"""

from . import db

TEMPLATES = {
    "tiling": {
        "Quote follow-up 1": (
            "Your tiling quote from {business_name}",
            """Hi {first_name},

Thanks again for asking us to quote on your tiling project. I wanted to check the quote came through and that everything in it makes sense.

If you'd like to change the tile choice, the layout or the timing, just reply to this email and we'll update it.

[[Call us on {phone}|tel:{phone_tel}]]

Cheers,
The {business_name} team"""),
        "Quote follow-up 2": (
            "Any questions about your tiling project?",
            """Hi {first_name},

People often have a few questions before they go ahead with tiling work: how long it will take, how much mess there will be, and whether the old tiles need to come up first.

We're happy to answer any of these. Reply here, or book a time and we'll talk it through.

[[Book a time|{booking_url}]]

Thanks,
The {business_name} team"""),
        "Quote follow-up 3": (
            "Should we keep your quote open, {first_name}?",
            """Hi {first_name},

We haven't heard back about your tiling quote, so I'll keep this short. If the project is still going ahead, reply and we'll lock in a start date.

If your plans have changed, that's no problem. Let us know and we'll close the quote off.

Thanks,
The {business_name} team"""),
        "Job complete: review request": (
            "How did your new tiles turn out?",
            """Hi {first_name},

Thanks for choosing {business_name}. We hope you're enjoying the finished job.

If you have a minute, a short review helps other people in the area find a tiler they can trust.

[[Leave a review|{review_url}]]

If anything about the job isn't right, reply to this email and we'll come back and fix it.

Thanks,
The {business_name} team"""),
        "Tile care tips": (
            "Keeping your new tiles looking their best",
            """Hi {first_name},

It's been about a month since we finished your tiling, so here are a few habits that keep it looking new.

**Use a pH-neutral cleaner.** Bleach and acidic cleaners wear grout down over time.

**Wipe up spills quickly**, especially on natural stone.

**Reseal grout every one to two years** in wet areas like showers.

Planning another room? Reply here and we'll put a quote together.

The {business_name} team"""),
        "Seasonal promotion": (
            "Planning a bathroom or kitchen update?",
            """Hi {first_name},

We're now booking tiling jobs for the coming months. If you've been thinking about a new bathroom, kitchen splashback or floor, now is a good time to get a quote in.

[[Get a quote|{booking_url}]]

Or call us on {phone}.

The {business_name} team"""),
    },
    "ecoshine": {
        "Welcome": (
            "Thanks for contacting {business_name}",
            """Hi {first_name},

Thanks for getting in touch with {business_name}. We clean with eco-friendly products and still leave your home properly clean.

To book your first clean, reply with a day that suits you, or book online.

[[Book a clean|{booking_url}]]

Talk soon,
The {business_name} team"""),
        "Lead follow-up": (
            "Still looking for a cleaner, {first_name}?",
            """Hi {first_name},

Just following up in case my last email got buried. We'd love to look after your home, whether that's a one-off deep clean or a regular weekly or fortnightly clean.

Reply with what you need and we'll send you a price.

The {business_name} team"""),
        "Post-clean review": (
            "How was your clean?",
            """Hi {first_name},

Thanks for having {business_name} in your home. We hope everything is sparkling.

Could you leave us a quick review? It makes a big difference to a local business like ours.

[[Leave a review|{review_url}]]

If we missed anything, reply here and we'll put it right.

The {business_name} team"""),
        "Rebook reminder": (
            "Time for your next clean?",
            """Hi {first_name},

It's been about three weeks since your last clean. Want us to book the next one?

[[Book your next clean|{booking_url}]]

Or just reply with a day that suits you.

The {business_name} team"""),
        "Holiday deep clean": (
            "Book a deep clean before the holidays",
            """Hi {first_name},

The holidays are coming up fast. If you're having people over, let us take care of the deep clean: kitchen, bathrooms, floors, skirting boards and the spots that usually get missed.

[[Book a deep clean|{booking_url}]]

December gets busy, so book early if you can.

The {business_name} team"""),
    },
}

# business -> [(name, trigger tag, exit tags, [(delay days, template name), ...])]
SEQUENCES = {
    "tiling": [
        ("Quote follow-up", "quote", "won,completed",
         [(2, "Quote follow-up 1"), (3, "Quote follow-up 2"), (7, "Quote follow-up 3")]),
        ("After the job", "completed", "",
         [(1, "Job complete: review request"), (30, "Tile care tips")]),
    ],
    "ecoshine": [
        ("New lead", "lead", "customer",
         [(0, "Welcome"), (3, "Lead follow-up")]),
        ("Customer care", "customer", "",
         [(1, "Post-clean review"), (21, "Rebook reminder")]),
    ],
}


def seed(conn) -> None:
    for business, templates in TEMPLATES.items():
        for name, (subject, body) in templates.items():
            conn.execute("INSERT OR IGNORE INTO templates (business, name, subject, body)"
                         " VALUES (?, ?, ?, ?)", (business, name, subject, body))
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
