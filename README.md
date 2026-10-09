# Canon Weave

A network of linked GenLayer Intelligent Contracts for building a **shared fictional universe**.

- **`canon.py`** is the main (root) contract. It stores the universe charter, which is the set of binding rules, and keeps a registry of the child contracts that were built from its address.
- **`realm.py`** is the child contract. Each Realm is deployed with the address of a Canon. It is a living chronicle where every new entry is judged by an LLM against the Canon charter, the Realm's own law, its opening premise and its latest entries.

The contracts are tied together in both directions: a Realm reads the charter and its own status from the Canon, the Canon verifies and tracks its Realms, and Realms read each other's accepted entries to allow crossover stories.

```
                    +-----------------------+
                    |        Canon          |   charter, version, realm registry
                    |  (deploy this first)  |   suspend / reinstate realms
                    +-----------+-----------+
          registers / verifies   |   ^  reads charter, version, realm status
                                 v   |
        +------------------+  +------------------+
        |   Realm  A       |  |   Realm  B       |   each deployed with the Canon address
        |  chronicle + law |<-|  chronicle + law |   B reads A's accepted entries
        +------------------+  +------------------+   to judge crossover submissions
```
## Deployed Instances (Testnet)

| Contract | Address |
| --- | --- |
| **Canon** (`canon.py`) | `0x480805e4C5f2eC836f6b8d6064c0e46BCe665584` |
| **Realm** (`realm.py` - Vessa Market) | `0x0814d577BD86C9fD8D6fe6658b867FF6c33BEC1e` |

---
## How the linking works

1. Deploy `Canon` with a name and a charter.
2. Copy the Canon address. Deploy `Realm` and pass that address to its constructor.
3. The Realm owner calls `register_realm(realm_address)` on the Canon. The Canon makes a synchronous view call to the Realm and checks that
   - the Realm points back to this exact Canon, and
   - the caller is the Realm owner.
4. The Realm is now `active`. Every submission reads the live charter and status from the Canon first.
5. The Canon owner can `set_realm_suspended(...)` to freeze a Realm and later reinstate it.

A Realm that has not been registered, or that is suspended, refuses all submissions.

**Registration policy.** By default anyone can register a Realm they own. The Canon owner can call `set_registration_open(false)` to switch to curated mode, where only the Canon owner can register Realms. The Canon owner can always register any Realm that points to their Canon, and can suspend any registered Realm.

## What makes a Realm interesting

- **Live canon.** The charter is read from the Canon on every submission. When the Canon owner amends the charter, its `version` increases and each new entry stores the version it was judged under.
- **Local law.** Each Realm adds its own rules on top of the shared charter. The Realm owner can amend them.
- **Continuity.** The judge sees the opening premise and the three latest accepted entries, so contradictions are rejected.
- **Crossovers.** `submit_crossover` lets one Realm continue an accepted entry of a sibling Realm. The sibling must be an active Realm of the same Canon. Its name, law and the referenced entry are read live from the sibling contract and given to the judge.
- **Layered prompt-injection defense.** Every piece of text written by someone other than the Canon owner (realm law, realm opening, earlier entries, the proposed entry, and in crossovers the sibling's law and entry) is placed in its own fenced block, and the judge is told that fenced text is untrusted data. The charter is stated to outrank every realm law. Marker sequences, control characters, invisible and direction-changing characters (zero width characters, direction marks, embeddings, overrides and isolates, variation selectors, and the Unicode tag characters that can hide a whole ASCII sentence), and fullwidth angle brackets are removed from all input before it is stored or used, so text cannot forge or split a marker. Unusual line separators become a plain newline. Names are forced onto one line without double quotes. Data read from other contracts (the canon's name and charter, a sibling's name, law and entry) is cleaned and length-limited in the same way.

## Files

| File | Role |
| --- | --- |
| `canon.py` | Root contract: charter, versioning, realm registry, suspension |
| `realm.py` | Child contract: chronicle, local law, LLM judging, crossovers |
| `tests/check_mock.py` | Local logic checks (161 checks), development only |
| `tests/genlayer/__init__.py` | Small mock of the GenLayer SDK used by the checks, development only |

Both contract files are self-contained single-file contracts, so each one can be pasted into GenLayer Studio on its own. They intentionally duplicate a few tiny helper functions for that reason. Nothing in `tests/` is deployed.

## Deploying on GenLayer Studio (studionet)

Select the Studio network in your tool, then deploy in this order.

### 1. Deploy `canon.py`

Constructor arguments:

| Argument | Example |
| --- | --- |
| `name` | `Ashen Atlas` |
| `charter` | `Magic always costs a memory. Nobody can be resurrected. The story never refers to the real world. Tone is melancholic and quiet.` |

Copy the deployed Canon address.

### 2. Deploy `realm.py`

Constructor arguments:

| Argument | Example |
| --- | --- |
| `canon_address` | the Canon address from step 1 |
| `name` | `Vessa Market` |
| `local_law` | `This realm is a floating sky market. Everything is traded by barter only, and money does not exist here.` |
| `opening` | `The market of Vessa drifts above the clouds, and nobody remembers who built it.` |

Copy the deployed Realm address. Deploy from the same account you will use to register it.

### 3. Register the Realm (write call on the Canon, same account as the deployer)

```
register_realm(realm_address)
```

Afterwards, `get_realm_state(realm_address)` on the Canon returns `1`.

### 4. Write

On the Realm:

```
submit_chronicle("A merchant sells a bottled sunrise for three secrets.")
```

Wait for the transaction to finalize, then read:

```
get_last_ruling()
get_chronicle_count()
get_chronicles(0, 10)
```

### 5. Optional: a second Realm and a crossover

Deploy another Realm with the same Canon address, register it, add an entry to it, then on the first Realm call:

```
submit_crossover(second_realm_address, 0, "A sky merchant from Vessa lands on the coast and trades a bottled sunrise for the lighthouse lamp's first flame.")
```

## Contract reference

### Canon

| Method | Type | Description |
| --- | --- | --- |
| `__init__(name, charter)` | deploy | Creates the universe. The deployer becomes the owner. |
| `register_realm(realm_address)` | write | Registers a Realm. Caller must own that Realm, and it must point to this Canon. |
| `set_realm_suspended(realm_address, suspended)` | write, owner | Suspends or reinstates a registered Realm. |
| `amend_charter(new_charter)` | write, owner | Replaces the charter and increases `version` by one. |
| `set_registration_open(registration_open)` | write, owner | Open registration (default) or curated mode where only the owner registers Realms. |
| `transfer_ownership(new_owner)` | write, owner | Proposes a new owner. Ownership does not move until that address accepts. |
| `cancel_ownership_transfer()` | write, owner | Cancels a pending ownership transfer. |
| `accept_ownership()` | write, pending owner | Completes the transfer. Only the proposed owner can call it. |
| `get_info()` | view | Name, charter, version, owner, pending owner, registration flag, realm count. |
| `get_name()`, `get_charter()`, `get_version()`, `get_owner()` | view | Individual fields. |
| `get_realm_count()` | view | Number of registered Realms. |
| `get_realms(offset, limit)` | view | Paged list of Realm addresses (max 50 per call). |
| `get_realm_state(realm_address)` | view | `0` not registered, `1` active, `2` suspended. |
| `is_realm(realm_address)` | view | True if registered, whether active or suspended. |

### Realm

| Method | Type | Description |
| --- | --- | --- |
| `__init__(canon_address, name, local_law, opening)` | deploy | Creates the Realm. The deployer becomes the owner. |
| `submit_chronicle(text)` | write | Submits an entry (20 to 1200 characters) for judging. |
| `submit_crossover(other_realm, chronicle_id, text)` | write | Submits an entry that builds on an accepted entry of a sibling Realm. |
| `set_open(open_to_all)` | write, owner | Open to everyone (default) or owner only. |
| `amend_local_law(new_law)` | write, owner | Replaces the local law. |
| `get_summary()` | view | Name, canon, owner, openness, counts, last ruling. |
| `get_last_ruling()` | view | Result of the most recent submission, accepted or rejected, with the judge's note. |
| `get_chronicle_count()` | view | Number of accepted entries. |
| `get_chronicle(index)` | view | One accepted entry with author, kind, score, note, canon version and link data. |
| `get_chronicle_text(index)` | view | Text of one accepted entry. |
| `get_chronicles(offset, limit)` | view | Paged entries (max 20 per call). |
| `get_canon_address()`, `get_owner()`, `get_name()`, `get_local_law()`, `get_opening()` | view | Individual fields. |

## Consensus design

For every submission the leader asks the LLM for a JSON ruling:

```
{"verdict": "accept" | "reject", "score": 0-10, "note": "one sentence"}
```

Each validator re-runs the same judgment independently, using `gl.vm.run_nondet_unsafe`. The leader's result is accepted only when:

- the verdicts are identical, and
- for accepted entries, the scores differ by at most 2.

Free-text notes are stored but never compared. Because the leader's output is untrusted, each validator first checks that it is a well formed ruling (a malformed result simply counts as disagreement), and after consensus every node normalises the agreed ruling once more: the score is clamped to 0-10 and the note is cleaned and cut to its length limit before anything is stored. If the LLM returns something that is not a usable ruling, the leader raises an error, the validators disagree, and the network retries with a different leader. State only changes after consensus. A rejected entry is a valid outcome: it is not stored, the rejected counter increases and the reason is saved in `last_ruling`.

All cross-contract calls happen before the non-deterministic block, never inside it, and storage is only written after consensus.

## Threat model and security notes

**Roles.** The Canon owner is trusted to write the charter and to moderate Realms. A Realm owner is trusted only inside their own Realm. Everyone else, including other Realm owners and any contract that registers itself, is untrusted.

**What the contracts defend against**

| Risk | Defense |
| --- | --- |
| A submitter forges prompt delimiters to smuggle instructions | Marker sequences removed until none remain, hidden and control characters removed, fullwidth brackets normalised, every untrusted text in its own fenced block |
| A previously accepted entry poisons later judgments (second-order injection) | Earlier entries are fenced and labelled as background data |
| A hostile sibling contract feeds instructions through its name, law or entry | All sibling data is sanitised, length-limited, fenced and labelled as non-binding |
| A Realm owner writes a law that excuses charter violations | The prompt states that the charter always wins, and the judge must ignore conflicting parts of the law |
| Someone hijacks another owner's Realm registration | The Canon verifies through a view call that the Realm points to it and that the caller owns it |
| A spammer fills the registry with fake Realms | The Canon owner can close registration (curated mode) and suspend any Realm |
| A mistyped new owner address locks the Canon | Two-step ownership transfer, the zero address is refused |
| Validators disagree because the LLM formats output differently | Verdict must match exactly, scores may differ by 2, score formats such as `8/10` are parsed |
| A malicious leader sends a malformed, oversized or dirty ruling (for example a huge note, a negative score, or something that is not a dictionary) | Validators reject malformed results, and the agreed ruling is normalised again before storage, so scores stay in 0-10 and notes stay short and clean |
| A Realm is deployed with a wrong or hostile canon address | Failed reads of the canon give a clear error, and the canon's name, charter and version are length-limited and checked before use |
| Unauthorised admin calls | Every owner action checks `gl.message.sender_address` |

**What they cannot fully guarantee**

- An LLM judge can still be fooled by a cleverly written entry. If a crafted entry makes every validator's LLM answer the same way, consensus will agree on the wrong ruling. Fencing and explicit rules reduce this risk but cannot remove it, so do not use a Realm ruling to guard anything of financial value.
- A contract that only imitates the Realm interface can register itself in open mode. It receives no special power beyond appearing as a crossover source, whose text is fenced and sanitised. Close registration or suspend it if it is abused.
- Open Realms can be spammed with submissions, which costs validator work. The Realm owner can switch to owner-only with `set_open(false)`.
- The Canon owner has real power: amending the charter changes how every Realm is judged from the next submission on. Choose the owner address carefully.
- All state is public on-chain, including every submitted entry and ruling.

## Design notes and limits

- A rejection is stored as the latest ruling, not as a separate record. Only accepted entries are kept in the chronicle.
- `last_ruling` is global to a Realm, so read it right after your own transaction finalizes if several people write at once.
- Contracts cannot be edited after deployment. To change the logic, deploy a new Canon or Realm.
- Crossovers are one-directional. The home Realm stores the crossover and a link to the sibling entry. The sibling Realm is only read, never written.
- A Realm only learns that it points to a wrong Canon address when you try to register it or submit to it, so double-check the address when deploying.
- Registry size is capped at 256 Realms per Canon, and all text inputs have length limits.
- Removing hidden characters also removes the zero width joiner and non-joiner, so a few scripts and emoji sequences that rely on them are shown in a simplified form. Entries are intended to be plain English text.

## Local checks

The contract logic (registration checks, permissions, suspension, charter versioning, consensus agreement and disagreement, crossovers, paging) is exercised against a local mock of the GenLayer SDK with 161 checks. They include attack cases: forged delimiters, invisible and tag characters, a hostile fake Realm contract, a hostile canon, a malicious leader that returns malformed or oversized rulings, and ownership hijack attempts.

Run them from the project folder with plain Python 3 (no packages needed):

```
python3 tests/check_mock.py
```

The script prints each failed check and a final `passed: N failed: M` line, and exits with a non-zero status if anything failed. You can also pass another folder that contains `canon.py` and `realm.py`.

The mock does not replace GenVM, so the checks only cover the contract logic, not SDK behaviour. Before relying on the contracts:

1. Run the GenVM linter from the GenLayer docs on both files.
2. Do a full run in Studio: deploy, register, submit an accepted entry, submit a rejected one, suspend the Realm, and try a crossover.
