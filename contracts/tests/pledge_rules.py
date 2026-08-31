"""The money rules, exercised through the real contract methods.

A previous project of ours shipped tests that only touched the helper functions,
and a steward pointed out that this proves nothing: the helpers can be right
while the public methods still pay the wrong person. So the whole of pledge.py
is loaded against a stub of the runtime, a real Pledge is built, and every
assertion below goes through pledge, claim and close.

The one thing replaced is what the site does when the validators knock, because
that is the input the contract cannot control and precisely what is being tested.

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


class _Message:
    def __init__(self):
        self.sender_address = _Address("0x" + "0" * 40)
        self.value = 0


class _Evm:
    """Stands in for gl.evm. `contract_interface` is a decorator, not a base
    class, and paying goes through the class it returns: a mistake worth
    encoding here, because writing it the other way deployed cleanly and then
    failed only on the one path that pays anybody."""
    def __init__(self):
        self.transfers = []
        outer = self

        def contract_interface(cls):
            class Bound:
                def __init__(self, address): self.address = str(address.as_hex).lower()
                def emit_transfer(self, value): outer.transfers.append((self.address, int(value)))
            return Bound
        self.contract_interface = contract_interface


class _Web:
    """What the site does. Set per test."""
    def __init__(self): self.quiet, self.declared = 200, 200
    def get(self, url, headers=None):
        status = self.declared if headers and "User-Agent" in headers else self.quiet
        if status == 0:
            raise RuntimeError("hung up")
        return types.SimpleNamespace(status=status, body=b"")


class _Public:
    def _passthrough(self, fn): return fn
    def __init__(self):
        self.view = self._passthrough
        self.write = self._passthrough
        self.write.payable = self._passthrough


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


def main():
    module, gl = load()
    site = "0x1111111111111111111111111111111111111111"
    agent = "0x2222222222222222222222222222222222222222"
    other = "0x3333333333333333333333333333333333333333"

    def as_(address, value=0):
        gl.message.sender_address = _Address(address)
        gl.message.value = value

    def door(quiet, declared):
        gl.nondet.web.quiet, gl.nondet.web.declared = quiet, declared

    PROMISE = "Agents acting for a person are served the same pages as a browser."

    c = fresh(module)
    as_(site, 1000)
    out = json.loads(c.pledge("shop.example", PROMISE, "3600"))
    check("a pledge is published with collateral behind it", out["ok"] and out["collateral"] == "1000")

    print("\nthe promise is kept")
    as_(agent)
    door(200, 200)
    kept = json.loads(c.claim("shop.example", "100"))
    check("a claim fails when the door opens for both", kept["ok"] and not kept["upheld"])
    check("and nobody is paid", not gl.evm.transfers)

    print("\nthe site is simply down, or shut to everyone")
    door(503, 503)
    check("a claim fails, this is not the promised failure",
          not json.loads(c.claim("shop.example", "100"))["upheld"])
    door(403, 403)
    check("refusing everybody breaks no promise about agents",
          not json.loads(c.claim("shop.example", "100"))["upheld"])
    door(0, 0)
    check("an unreachable site pays nobody",
          not json.loads(c.claim("shop.example", "100"))["upheld"])
    check("still nobody paid", not gl.evm.transfers)

    print("\nthe promised failure, and only it")
    door(200, 403)
    broken = json.loads(c.claim("shop.example", "100"))
    check("served silent, refused declared: the claim is upheld", broken["upheld"])
    check("the claimant is paid what was asked",
          gl.evm.transfers == [(agent, 100)] and broken["paid"] == "100")
    check("the collateral falls by exactly that",
          json.loads(c.promise("shop.example"))["collateral"] == 900)

    print("\none address cannot be paid twice for the same domain")
    again = json.loads(c.claim("shop.example", "100"))
    check("a second claim from the same address is refused", not again["ok"])
    check("and pays nothing more", gl.evm.transfers == [(agent, 100)])
    as_(other)
    third = json.loads(c.claim("shop.example", "100"))
    check("a different address can still claim", third["ok"] and third["upheld"])

    print("\nthe owner cannot claim against itself, and cannot cash out early")
    as_(site)
    check("the owner is refused", not json.loads(c.claim("shop.example", "100"))["ok"])
    check("closing before the term ends is refused",
          not json.loads(c.close("shop.example"))["ok"])

    print("\na payout can never exceed what is behind the promise")
    as_(other)
    left = json.loads(c.promise("shop.example"))["collateral"]
    gl.evm.transfers.clear()
    as_("0x4444444444444444444444444444444444444444")
    drain = json.loads(c.claim("shop.example", str(left * 10)))
    check("asking for more than is there pays exactly what is there",
          drain["paid"] == str(left) and gl.evm.transfers[-1][1] == left)
    check("and the pledge closes when the collateral is gone",
          json.loads(c.promise("shop.example"))["state"] == "CLOSED")
    check("a claim against a closed pledge is refused",
          not json.loads(c.claim("shop.example", "1"))["ok"])

    print("\na deposit that cannot be accepted is paid back, never kept")
    gl.evm.transfers.clear()
    as_(other, 500)
    refused = json.loads(c.pledge("not a domain", PROMISE, "3600"))
    check("the pledge is refused", not refused["ok"])
    check("and the money goes straight back", gl.evm.transfers == [(other, 500)])
    gl.evm.transfers.clear()
    as_(other, 700)
    taken = json.loads(c.pledge("shop.example", PROMISE, "3600"))
    check("somebody else's domain cannot be pledged", not taken["ok"])
    check("and that money goes back too", gl.evm.transfers == [(other, 700)])

    failed = [label for label, ok in RESULTS if not ok]
    print()
    if failed:
        print("%d of %d checks failed" % (len(failed), len(RESULTS)))
        return 1
    print("%d checks, all through pledge, claim and close on a real Pledge instance"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
