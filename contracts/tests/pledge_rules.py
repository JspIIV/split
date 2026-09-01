"""The money rules, exercised through the real contract methods.

Not the helpers. A steward pointed out on an earlier project of ours that
testing the parsing functions alone proves nothing, because they can be right
while the public methods still pay the wrong person. So pledge.py is loaded
against a stub of the runtime, a real Pledge is built, and every assertion below
goes through verify, pledge, claim and close.

The one thing replaced is what the site does when the validators knock, at the
door and at the proof file, because that is the input the contract cannot
control and precisely what is being tested.

    python contracts/tests/pledge_rules.py
"""

import io
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT = os.path.join(HERE, "..", "pledge.py")


class _Store:
    def __init__(self, kind): self.kind = kind
    def __class_getitem__(cls, item): return cls("map" if isinstance(item, tuple) else "list")
    def make(self): return {} if self.kind == "map" else []


class _Address:
    def __init__(self, hex_value): self.as_hex = hex_value
    def __str__(self): return str(self.as_hex)


class _Message:
    def __init__(self):
        self.sender_address = _Address("0x" + "0" * 40)
        self.value = 0


class _Evm:
    """`contract_interface` is a decorator, not a call, and paying goes through
    the class it returns. Written the other way this contract deployed cleanly
    and failed only on the one path that pays anybody, so the stub models the
    decorator rather than the mistake."""
    def __init__(self):
        self.transfers = []
        outer = self

        def contract_interface(cls):
            class Bound:
                def __init__(self, address): self.address = str(address).lower()
                def emit_transfer(self, value): outer.transfers.append((self.address, int(value)))
            return Bound
        self.contract_interface = contract_interface


class _Web:
    """What the site does, at two different URLs.

    The proof file and the homepage answer separately, so a test can give a site
    an honest door and a missing proof, or the other way round. That pair is
    exactly what the control checks are about.
    """
    def __init__(self):
        self.quiet, self.declared = 200, 200
        self.proof, self.proof_status = "", 200

    def get(self, url, headers=None):
        if ".well-known" in url:
            if self.proof_status == 0:
                raise RuntimeError("hung up")
            return types.SimpleNamespace(status=self.proof_status,
                                         body=self.proof.encode("utf-8"))
        status = self.declared if headers and "User-Agent" in headers else self.quiet
        if status == 0:
            raise RuntimeError("hung up")
        return types.SimpleNamespace(status=status, body=b"")


class _Write:
    def __call__(self, fn): return fn
    def payable(self, fn): return fn


class _PublicNS:
    def __init__(self):
        self.write = _Write()
        self.view = lambda fn: fn


class _EqPrinciple:
    def strict_eq(self, run): return run()


class _GL:
    def __init__(self):
        self.Contract = object
        self.public = _PublicNS()
        self.message = _Message()
        self.evm = _Evm()
        self.nondet = types.SimpleNamespace(web=_Web())
        self.eq_principle = _EqPrinciple()


def load():
    gl = _GL()
    fake = types.ModuleType("genlayer")
    fake.gl = gl
    fake.DynArray = _Store
    fake.TreeMap = _Store
    fake.u32 = int
    fake.u256 = int
    fake.Address = _Address
    sys.modules["genlayer"] = fake
    module = types.ModuleType("pledge_under_test")
    exec(compile(io.open(CONTRACT, encoding="utf-8").read(), CONTRACT, "exec"), module.__dict__)
    return module, gl


def fresh(module):
    contract = module.Pledge.__new__(module.Pledge)
    for field, declared in module.Pledge.__annotations__.items():
        setattr(contract, field, declared.make())
    contract.__init__()
    return contract


RESULTS = []


def check(label, condition):
    RESULTS.append((label, bool(condition)))
    print(("  ok  " if condition else " FAIL "), label)


SITE = "0x1111111111111111111111111111111111111111"
AGENT = "0x2222222222222222222222222222222222222222"
OTHER = "0x3333333333333333333333333333333333333333"

PROMISE = "Agents acting for a person are served the same pages as a browser."
TERMS = ("shop.example", PROMISE, "100", "3600", "86400")


def main():
    module, gl = load()

    def as_(address, value=0):
        gl.message.sender_address = _Address(address)
        gl.message.value = value

    def door(quiet, declared):
        gl.nondet.web.quiet, gl.nondet.web.declared = quiet, declared

    def proof(text, status=200):
        gl.nondet.web.proof, gl.nondet.web.proof_status = text, status

    c = fresh(module)

    print("nobody can pledge a domain they have not proved they control")
    as_(SITE, 1000)
    unproved = json.loads(c.pledge(*TERMS))
    check("a pledge without proof is refused", not unproved["ok"])
    check("and the collateral comes straight back", gl.evm.transfers == [(SITE, 1000)])

    print("\nproof of control is read off the domain itself")
    as_(SITE)
    proof("", 404)
    check("no proof file, no control", not json.loads(c.verify("shop.example"))["ok"])
    proof("we love agents here")
    check("a file that does not name the caller proves nothing",
          not json.loads(c.verify("shop.example"))["ok"])
    proof(OTHER)
    check("a file naming somebody else does not vouch for the caller",
          not json.loads(c.verify("shop.example"))["ok"])
    proof(SITE + " is our operator, contact ops@shop.example")
    check("an address merely mentioned in a sentence is not a vouching",
          not json.loads(c.verify("shop.example"))["ok"])
    proof(SITE)
    check("a file naming exactly the caller does", json.loads(c.verify("shop.example"))["ok"])
    check("and the domain now reads as controlled",
          json.loads(c.controller("shop.example"))["controller"] == SITE)

    print("\nsomebody else's proof is not yours")
    as_(OTHER, 900)
    gl.evm.transfers.clear()
    taken = json.loads(c.pledge(*TERMS))
    check("a different address cannot pledge it", not taken["ok"])
    check("and is refunded", gl.evm.transfers == [(OTHER, 900)])

    print("\nthe terms are fixed by the party putting up the money")
    as_(SITE, 1000)
    gl.evm.transfers.clear()
    opened = json.loads(c.pledge(*TERMS))
    check("the pledge opens", opened["ok"])
    check("the payout per claim is set at pledge time", opened["payout_each"] == "100")
    check("so is the window and the cap inside it",
          opened["window_seconds"] == 3600 and opened["max_claims_per_window"] == 3)

    print("\nthe promise is kept, and the other ways of not paying")
    as_(AGENT)
    door(200, 200)
    kept = json.loads(c.claim("shop.example"))
    check("a claim fails when the door opens for both", kept["ok"] and not kept["upheld"])
    door(503, 503)
    check("a site that is down breaks no promise",
          not json.loads(c.claim("shop.example"))["upheld"])
    door(403, 403)
    check("refusing everybody breaks no promise about agents",
          not json.loads(c.claim("shop.example"))["upheld"])
    door(0, 0)
    check("an unreachable site pays nobody", not json.loads(c.claim("shop.example"))["upheld"])
    check("still nobody paid", not gl.evm.transfers)

    print("\nthe promised failure, and only it")
    door(200, 403)
    broken = json.loads(c.claim("shop.example"))
    check("served silent, refused declared: the claim is upheld", broken["upheld"])
    check("the claimant is paid what the pledge fixed, and cannot name a figure",
          gl.evm.transfers == [(AGENT, 100)] and broken["paid"] == "100")
    check("the collateral falls by exactly that",
          json.loads(c.promise("shop.example"))["collateral"] == 900)

    print("\nrotating addresses cannot empty the collateral")
    gl.evm.transfers.clear()
    paid = []
    for n in range(6):
        as_("0x9%039d" % n)
        out = json.loads(c.claim("shop.example"))
        if int(out["paid"]) > 0:
            paid.append(int(out["paid"]))
    check("only what the window still allowed was paid", paid == [100, 100])
    check("and nothing else left the contract",
          sum(t[1] for t in gl.evm.transfers) == 200)
    capped = json.loads(c.claim("shop.example"))
    check("a further claim is still recorded as upheld", capped["upheld"])
    check("but pays nothing and says why",
          capped["paid"] == "0" and "cap" in (capped["capped"] or ""))
    check("the collateral is untouched past the cap",
          json.loads(c.promise("shop.example"))["collateral"] == 700)

    print("\nan address is paid once per domain however often it claims")
    gl.evm.transfers.clear()
    as_(AGENT)
    again = json.loads(c.claim("shop.example"))
    check("a second claim from a paid address is refused", not again["ok"])
    check("and pays nothing", not gl.evm.transfers)

    print("\nthe owner cannot claim against itself, or cash out early")
    as_(SITE)
    check("the owner is refused", not json.loads(c.claim("shop.example"))["ok"])
    check("closing before the term ends is refused",
          not json.loads(c.close("shop.example"))["ok"])

    print("\na deposit that cannot be accepted is paid back, never kept")
    gl.evm.transfers.clear()
    as_(OTHER, 500)
    refused = json.loads(c.pledge("not a domain", PROMISE, "100", "3600", "86400"))
    check("a malformed domain is refused", not refused["ok"])
    check("and the money goes straight back", gl.evm.transfers == [(OTHER, 500)])

    print("\nproof does not last forever, because domains change hands")
    record = json.loads(c.controllers["shop.example"])
    record["proved_epoch"] = int(record["proved_epoch"]) - (module.PROOF_TTL + 60)
    c.controllers["shop.example"] = json.dumps(record)
    check("a stale proof no longer names a controller",
          not json.loads(c.controller("shop.example"))["ok"])
    gl.evm.transfers.clear()
    as_(SITE, 300)
    stale = json.loads(c.pledge(*TERMS))
    check("and cannot be topped up on", not stale["ok"])
    check("with the money returned", gl.evm.transfers == [(SITE, 300)])

    failed = [label for label, ok in RESULTS if not ok]
    print()
    if failed:
        print("%d of %d checks failed" % (len(failed), len(RESULTS)))
        return 1
    print("%d checks, all through verify, pledge, claim and close on a real Pledge instance"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
