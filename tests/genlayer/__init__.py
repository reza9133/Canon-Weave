"""Minimal local mock of the GenLayer SDK, only for exercising the contract logic.

It is used by tests/check_mock.py and is not part of any deployed contract.
"""
import dataclasses
import itertools

__all__ = ["gl", "Address", "u32", "DynArray", "TreeMap", "allow_storage"]


class Address:
    def __init__(self, value):
        if isinstance(value, Address):
            value = value.as_hex
        if not isinstance(value, str) or not value.startswith("0x") or len(value) != 42:
            raise ValueError("bad address")
        int(value[2:], 16)
        self._hex = "0x" + value[2:].lower()

    @property
    def as_hex(self):
        return self._hex

    def __eq__(self, other):
        return isinstance(other, Address) and self._hex == other._hex

    def __hash__(self):
        return hash(self._hex)

    def __lt__(self, other):
        return self._hex < other._hex

    def __repr__(self):
        return "Address(" + self._hex + ")"


class u32(int):
    def __new__(cls, value=0):
        value = int(value)
        if value < 0 or value >= 2**32:
            raise OverflowError("u32 out of range")
        return int.__new__(cls, value)


class DynArray(list):
    def __class_getitem__(cls, item):
        return cls


class TreeMap(dict):
    def __class_getitem__(cls, item):
        return cls


def allow_storage(cls):
    return cls


class UserError(Exception):
    pass


class VMError(Exception):
    pass


class Return:
    def __init__(self, calldata):
        self.calldata = calldata


class _Ctx:
    def __init__(self):
        self.stack = []

    @property
    def sender_address(self):
        return self.stack[-1][0]

    @property
    def contract_address(self):
        return self.stack[-1][1]


class _Net:
    """Test controls: exec_prompt responses and consensus simulation."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.responses = []
        self.leader_override = None
        self.has_override = False
        self.prompts = []


NET = _Net()
CONTRACTS = {}
_counter = itertools.count(1)
CTX = _Ctx()


def _default_for(annotation):
    if annotation is Address:
        return Address("0x" + "0" * 40)
    if annotation is DynArray:
        return DynArray()
    if annotation is TreeMap:
        return TreeMap()
    if annotation is bool:
        return False
    if annotation is u32:
        return u32(0)
    if annotation is str:
        return ""
    return None


class Contract:
    def __new__(cls, *args, **kwargs):
        obj = object.__new__(cls)
        for klass in reversed(cls.__mro__):
            for fname, ann in getattr(klass, "__annotations__", {}).items():
                object.__setattr__(obj, fname, _default_for(ann))
        return obj


class _Public:
    @staticmethod
    def write(fn):
        fn._kind = "write"
        return fn

    @staticmethod
    def view(fn):
        fn._kind = "view"
        return fn


def deploy(cls, sender, *args):
    addr = Address("0x" + format(next(_counter), "040x"))
    obj = cls.__new__(cls)
    CTX.stack.append((sender, addr))
    try:
        obj.__init__(*args)
    finally:
        CTX.stack.pop()
    CONTRACTS[addr] = obj
    return addr


def call(addr, sender, method, *args):
    obj = CONTRACTS[addr]
    fn = getattr(obj, method)
    CTX.stack.append((sender, addr))
    try:
        return fn(*args)
    finally:
        CTX.stack.pop()


class _ViewProxy:
    def __init__(self, addr):
        self._addr = addr

    def __getattr__(self, name):
        addr = self._addr
        obj = CONTRACTS.get(addr)
        if obj is None:
            raise VMError("no contract at address")
        fn = getattr(obj, name, None)
        if fn is None or getattr(fn, "_kind", None) != "view":
            raise VMError("no such view method: " + name)
        caller = CTX.contract_address

        def run(*args):
            CTX.stack.append((caller, addr))
            try:
                return fn(*args)
            finally:
                CTX.stack.pop()

        return run


class _ContractAt:
    def __init__(self, addr):
        self._addr = addr

    def view(self):
        return _ViewProxy(self._addr)


def get_contract_at(addr):
    return _ContractAt(addr)


def run_nondet_unsafe(leader_fn, validator_fn):
    total = len(NET.responses)
    if NET.has_override:
        result = Return(NET.leader_override)
        validators = total
    else:
        validators = max(0, total - 1)
        try:
            result = Return(leader_fn())
        except UserError as exc:
            result = exc
    for _ in range(validators):
        if validator_fn(result) is not True:
            raise UserError("consensus disagreement")
    if not isinstance(result, Return):
        raise result
    return result.calldata


def exec_prompt(prompt, response_format="text"):
    NET.prompts.append(prompt)
    if not NET.responses:
        raise VMError("no mocked response")
    item = NET.responses.pop(0)
    if isinstance(item, Exception):
        raise item
    return item


class _VM:
    UserError = UserError
    VMError = VMError
    Return = Return
    run_nondet_unsafe = staticmethod(run_nondet_unsafe)


class _Nondet:
    exec_prompt = staticmethod(exec_prompt)


class gl:
    Contract = Contract
    public = _Public
    message = CTX
    vm = _VM
    nondet = _Nondet
    get_contract_at = staticmethod(get_contract_at)
