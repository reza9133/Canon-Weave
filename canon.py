# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import typing

from genlayer import *

# Canon is the ROOT contract of the Canon Weave network.
#
# It holds the charter of a shared fictional universe (the binding rules that every
# linked Realm contract must respect) and a registry of the Realm contracts that were
# deployed with this contract's address.
#
# Linking flow:
#   1. Deploy Canon.
#   2. Deploy a Realm contract and pass the Canon address to its constructor.
#   3. The Realm owner calls Canon.register_realm(realm_address).
#      Canon verifies, through a synchronous view call, that the Realm points back to
#      this Canon and that the caller is the Realm owner.
#   4. From then on the Realm reads the charter from Canon on every submission, and the
#      Canon owner can suspend or reinstate the Realm.
#
# Registration policy: by default anyone may register a Realm that they own. The Canon
# owner can close registration, after which only the Canon owner can register Realms
# (curated mode). The Canon owner can always register any Realm that points to this
# Canon, and can suspend any registered Realm.

MAX_NAME = 60
MIN_CHARTER = 20
MAX_CHARTER = 3000
MAX_REALMS = 256
MAX_PAGE = 50

STATE_NONE = 0
STATE_ACTIVE = 1
STATE_SUSPENDED = 2

# Invisible, direction-changing or otherwise non-printing characters that can hide or
# reorder text. Besides the usual zero width characters this covers the direction
# isolates, the deprecated format characters, variation selectors, C1 controls and the
# Unicode tag characters, which can carry a whole hidden ASCII sentence that a language
# model may still read.
HIDDEN_RANGES = (
    (0x0080, 0x009F),  # C1 control characters
    (0x200B, 0x200F),  # zero width characters and direction marks
    (0x202A, 0x202E),  # direction embeddings and overrides
    (0x2060, 0x206F),  # word joiner, invisible operators, direction isolates, deprecated format characters
    (0xFE00, 0xFE0F),  # variation selectors
    (0xFFF9, 0xFFFB),  # interlinear annotation characters
    (0x115F, 0x1160),  # Hangul choseong and jungseong fillers
    (0x17B4, 0x17B5),  # Khmer inherent vowels (invisible)
    (0x1D173, 0x1D17A),  # musical symbol format controls
    (0xE0000, 0xE007F),  # tag characters
    (0xE0100, 0xE01EF),  # variation selectors supplement
)
HIDDEN_CODEPOINTS = {0x00AD, 0x034F, 0x061C, 0x180E, 0x2800, 0x3164, 0xFEFF, 0xFFA0}

# Line breaking characters other than "\n" are turned into a plain newline.
LINE_BREAK_CODEPOINTS = {0x0085, 0x2028, 0x2029}


def is_hidden_codepoint(code: int) -> bool:
    if code == 127 or code in HIDDEN_CODEPOINTS:
        return True
    for low, high in HIDDEN_RANGES:
        if low <= code <= high:
            return True
    return False


def zero_address() -> Address:
    return Address("0x" + "0" * 40)


def parse_address(value: str) -> Address:
    try:
        return Address(value)
    except Exception:
        raise gl.vm.UserError("Invalid address: " + str(value))


def clean_text(value: str) -> str:
    # Normalises text before it is stored or placed into a prompt: control and
    # invisible characters are dropped, fullwidth angle brackets become plain ones, and
    # the marker sequences are removed until none remain, so stored text can never
    # forge the delimiters that prompts use to fence untrusted content. Removal is
    # repeated because deleting one marker can join the characters around it into a new
    # one (for example "<<>>><" becomes "<<<" after a single pass).
    kept = []
    for ch in str(value):
        code = ord(ch)
        if code in LINE_BREAK_CODEPOINTS:
            kept.append("\n")
            continue
        if is_hidden_codepoint(code):
            continue
        if code < 32 and ch != "\n" and ch != "\t":
            continue
        kept.append(ch)
    text = "".join(kept).replace("\uff1c", "<").replace("\uff1e", ">")
    while "<<<" in text or ">>>" in text:
        text = text.replace("<<<", "").replace(">>>", "")
    return text.strip()


def clean_name(value: str) -> str:
    # Names are placed inline in prompts, so they are forced onto a single line and
    # cannot contain double quotes.
    return " ".join(clean_text(value).replace('"', "'").split())


def require_length(value: str, low: int, high: int, label: str) -> None:
    if len(value) < low or len(value) > high:
        raise gl.vm.UserError(
            label + " must be between " + str(low) + " and " + str(high) + " characters"
        )


class Canon(gl.Contract):
    owner: Address
    pending_owner: Address
    name: str
    charter: str
    version: u32
    registration_open: bool
    realms: DynArray[Address]
    realm_state: TreeMap[Address, u32]

    def __init__(self, name: str, charter: str):
        name = clean_name(name)
        charter = clean_text(charter)
        require_length(name, 1, MAX_NAME, "name")
        require_length(charter, MIN_CHARTER, MAX_CHARTER, "charter")
        self.owner = gl.message.sender_address
        # Set explicitly instead of relying on the zero default of an Address field.
        self.pending_owner = zero_address()
        self.name = name
        self.charter = charter
        self.version = u32(1)
        self.registration_open = True

    # ------------------------------------------------------------------ helpers

    def _require_owner(self) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("Only the canon owner can do this")

    # ------------------------------------------------------------ owner actions

    @gl.public.write
    def amend_charter(self, new_charter: str) -> None:
        self._require_owner()
        charter = clean_text(new_charter)
        require_length(charter, MIN_CHARTER, MAX_CHARTER, "charter")
        if charter == self.charter:
            raise gl.vm.UserError("The new charter is identical to the current one")
        self.charter = charter
        self.version = u32(int(self.version) + 1)

    @gl.public.write
    def set_registration_open(self, registration_open: bool) -> None:
        self._require_owner()
        self.registration_open = registration_open

    @gl.public.write
    def set_realm_suspended(self, realm_address: str, suspended: bool) -> None:
        self._require_owner()
        realm_addr = parse_address(realm_address)
        current = int(self.realm_state.get(realm_addr, u32(0)))
        if current == STATE_NONE:
            raise gl.vm.UserError("Realm is not registered")
        if suspended:
            self.realm_state[realm_addr] = u32(STATE_SUSPENDED)
        else:
            self.realm_state[realm_addr] = u32(STATE_ACTIVE)

    # Ownership moves in two steps so that a mistyped address cannot lock the canon:
    # the owner proposes a new owner, and the new owner must accept.

    @gl.public.write
    def transfer_ownership(self, new_owner: str) -> None:
        self._require_owner()
        new_owner_addr = parse_address(new_owner)
        if new_owner_addr == zero_address():
            raise gl.vm.UserError("The zero address cannot own the canon")
        self.pending_owner = new_owner_addr

    @gl.public.write
    def cancel_ownership_transfer(self) -> None:
        self._require_owner()
        self.pending_owner = zero_address()

    @gl.public.write
    def accept_ownership(self) -> None:
        if self.pending_owner == zero_address():
            raise gl.vm.UserError("There is no pending ownership transfer")
        if gl.message.sender_address != self.pending_owner:
            raise gl.vm.UserError("Only the pending owner can accept ownership")
        self.owner = self.pending_owner
        self.pending_owner = zero_address()

    # ------------------------------------------------------------- registration

    @gl.public.write
    def register_realm(self, realm_address: str) -> None:
        sender = gl.message.sender_address
        is_curator = sender == self.owner

        if not self.registration_open and not is_curator:
            raise gl.vm.UserError(
                "Registration is closed; ask the canon owner to register the realm"
            )

        realm_addr = parse_address(realm_address)

        if int(self.realm_state.get(realm_addr, u32(0))) != STATE_NONE:
            raise gl.vm.UserError("Realm is already registered")
        if len(self.realms) >= MAX_REALMS:
            raise gl.vm.UserError("The realm registry is full")

        try:
            realm = gl.get_contract_at(realm_addr)
            declared_canon = str(realm.view().get_canon_address())
            declared_owner = str(realm.view().get_owner())
        except Exception:
            raise gl.vm.UserError("Target is not a compatible Realm contract")

        if declared_canon.lower() != gl.message.contract_address.as_hex.lower():
            raise gl.vm.UserError("Realm was deployed for a different canon")
        if not is_curator and declared_owner.lower() != sender.as_hex.lower():
            raise gl.vm.UserError("Only the realm owner can register it")

        self.realm_state[realm_addr] = u32(STATE_ACTIVE)
        self.realms.append(realm_addr)

    # -------------------------------------------------------------------- views

    @gl.public.view
    def get_info(self) -> typing.Any:
        return {
            "name": str(self.name),
            "charter": str(self.charter),
            "version": int(self.version),
            "owner": self.owner.as_hex,
            "pending_owner": self.pending_owner.as_hex,
            "registration_open": bool(self.registration_open),
            "realm_count": len(self.realms),
        }

    @gl.public.view
    def get_name(self) -> str:
        return str(self.name)

    @gl.public.view
    def get_charter(self) -> str:
        return str(self.charter)

    @gl.public.view
    def get_version(self) -> int:
        return int(self.version)

    @gl.public.view
    def get_owner(self) -> str:
        return self.owner.as_hex

    @gl.public.view
    def get_realm_count(self) -> int:
        return len(self.realms)

    @gl.public.view
    def get_realms(self, offset: int, limit: int) -> typing.Any:
        if offset < 0 or limit < 0:
            raise gl.vm.UserError("offset and limit must be non-negative")
        total = len(self.realms)
        end = min(total, offset + min(limit, MAX_PAGE))
        return [self.realms[i].as_hex for i in range(offset, end)]

    @gl.public.view
    def get_realm_state(self, realm_address: str) -> int:
        # 0 = not registered, 1 = active, 2 = suspended
        realm_addr = parse_address(realm_address)
        return int(self.realm_state.get(realm_addr, u32(0)))

    @gl.public.view
    def is_realm(self, realm_address: str) -> bool:
        realm_addr = parse_address(realm_address)
        return int(self.realm_state.get(realm_addr, u32(0))) != STATE_NONE
