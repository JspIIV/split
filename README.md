# Split

**A standing record of what the web serves people, and what it serves the agents
acting for them.**

Send an agent to buy something for you and it does not reach the store you see.
On a large share of the sites people actually use, the same request that opens
for a browser is refused when the client says it is an agent fetching a page for
the person who asked.

That is not an accusation, it is a measurement, and this repository is the
measurement plus every dataset it has produced.

* `measure.py` runs it. `python measure.py`
* `sites.txt` is the list, one host per line
* `results/` holds every run, dated, never edited afterwards
* `docs/` is the page that reads the newest dataset

## What it does

One homepage per site, fetched once per identity from the same machine within
seconds of itself. Exactly one thing changes between fetches: **who the client
says it is.** A browser, an agent fetching for a person who just asked
(`ChatGPT-User`, `Claude-User`, `Perplexity-User`), a crawler (`GPTBot`), and a
plain script.

Everything else is held still, because everything else is what would otherwise
explain the difference. Same machine, same seconds, same headers, same location,
same page.

It also reads `robots.txt` and records which named agent clients a site bars from
the whole site. Only a bare `Disallow: /` counts. Keeping agents out of a cart or
a search page is ordinary crawler hygiene and counting it would inflate the
number.

**Nothing is bypassed.** No login, no CAPTCHA solving, no proxy rotation, and no
pretending to be a browser we are not. When a site refuses a client, the refusal
is the finding.

## The one number, and why it is smaller than it could be

The control is not a real browser. It is a command line client sending a browser
user agent string: no JavaScript, no browser TLS fingerprint. Roughly half the
sites we test refuse it too, and refusing every non browser client is a different
thing from refusing agents.

So those sites are marked `not_comparable` and **dropped from the denominator**
rather than counted as discrimination. The headline share is out of the sites
that served the control, which is the smaller, defensible number. Anyone wanting
a bigger one can compute it from the same dataset; we would rather publish the
one we can defend.

## What it does not show

**This measures the front door, not the price.** Whether an agent is let in and
whether it is handed the same page. It says nothing about what an agent is
charged, and no number here should be read that way. Measuring price needs a
different design, with currency, geography, session and A/B testing controlled
for, and until that exists the claim will not be made.

One location, one moment, homepages only.

## Why keep the record somewhere neutral

Two parties can see this today and neither has a reason to write it down. The
sites are the ones doing it. The agent vendors sell a product that looks worse
for it. A measurement that only exists on the blog of one of them is a
measurement nobody has to accept.

So the runs are dated, never edited, and the method ships with them. The
intended end state is that each run's summary is anchored where neither side
can revise it, and the raw dataset stays here for anyone who wants to
recompute the number themselves and get a different one honestly.

## Reproducing

```
python measure.py            # every site
python measure.py --limit 10 # a quick pass
```

Results land in `results/<date>.json` with the full per identity detail, the
method text, and the identities used. To point the page at the newest run, copy
it to `docs/data.json`.

Numbers move. A site that refuses an agent today may serve it next month, and
that change is the interesting part, which is why old runs are kept rather than
overwritten.

## Taking us out of the middle

The measurement above has one weakness that measuring more carefully cannot fix:
**you have to take our word for it.** We say nike.com refuses an agent. Nike can
answer that we made it up, or ran it wrong, and nothing in the dataset settles
that.

`contracts/attest.py` removes us. `check(host)` opens a GenLayer consensus round
in which every validator fetches the site itself, from its own machine, twice
and seconds apart: once saying nothing about itself, once declaring an agent
identity. The round completes only if the validators agree on both legs.

Live on GenLayer Studionet at `0x23F124bda497e32AcB84Be5F3a309A8943501F1d`.

| host | silent | declared |
|---|---|---|
| nike.com | SERVED | **REFUSED** |
| airbnb.com | SERVED | **REFUSED** |
| walmart.com | SERVED | SERVED |

Walmart is the control, measured the same way in the same round. The tool is not
an accusation machine; where there is no difference it records none.

**The finding this produced.** The blocking is not aimed at machines. It is aimed
at machines that say what they are. Of the 16 sites that refuse a named agent
identity, 5 served an unnamed script client in the same second, and the
validators, whose HTTP client declares nothing, were served by nike.com and
airbnb.com until the moment they declared.

That is worth stating plainly, because the whole industry is currently building
standards for agents to identify themselves honestly: **right now, honesty is
the thing being punished.**

**Two rules the round obeys.** Nothing inside the nondeterministic block reads
storage, which ends the transaction on this network, and nothing inside it
raises, which reverts it. A site that hangs up comes back as data. And a round
the validators cannot agree on records nothing at all: the host stays unchecked
rather than being written down as a disagreement.

## Where you measure from changes the answer

The same 72 sites, the same method, the same day, run once from a home
connection and once from a datacentre: **18 of them disagreed.** Amazon served
an agent from one vantage and refused it from the other. Several sites that
refuse a home connection outright are comparable from a datacentre, and several
that are comparable from home refuse the datacentre before the question of
identity ever arises.

This is why runs carry a `vantage` and are never averaged together. A single
number covering both would be true of neither, and the difference is not noise
to be smoothed away: it is a second axis of the same behaviour, address
reputation stacked on top of declared identity.

It is also the strongest argument for `contracts/attest.py`. A validator set is
many independent vantages at once, on machines nobody here controls. When they
agree, the finding no longer depends on where we happened to be sitting.
