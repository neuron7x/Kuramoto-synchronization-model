"""Hash-chained append-only event ledger for ECP-AS."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple

GENESIS = "0" * 64

def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

@dataclass(frozen=True, slots=True)
class LedgerEvent:
    seq: int
    event_type: str
    claim_id: str
    payload: dict[str, Any]
    prev_hash: str
    event_hash: str

class HashChainLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists(): self.path.touch()
        self.verify()

    @staticmethod
    def _digest(seq: int, event_type: str, claim_id: str, payload: dict[str, Any], prev_hash: str) -> str:
        body={"seq":seq,"event_type":event_type,"claim_id":claim_id,"payload":payload,"prev_hash":prev_hash}
        return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()

    def events(self) -> Tuple[LedgerEvent, ...]:
        rows=[]
        for line_no,line in enumerate(self.path.read_text(encoding="utf-8").splitlines(),1):
            if not line.strip(): continue
            try: raw=json.loads(line)
            except json.JSONDecodeError as exc: raise ValueError(f"ledger line {line_no} invalid JSON") from exc
            try: rows.append(LedgerEvent(int(raw["seq"]),str(raw["event_type"]),str(raw["claim_id"]),dict(raw["payload"]),str(raw["prev_hash"]),str(raw["event_hash"])))
            except (KeyError,TypeError,ValueError) as exc: raise ValueError(f"ledger line {line_no} malformed") from exc
        return tuple(rows)

    def verify(self) -> None:
        prev=GENESIS
        for expected_seq,event in enumerate(self.events()):
            if event.seq != expected_seq: raise ValueError(f"ledger sequence break at {expected_seq}")
            if event.prev_hash != prev: raise ValueError(f"ledger hash-chain break at {expected_seq}")
            expected=self._digest(event.seq,event.event_type,event.claim_id,event.payload,event.prev_hash)
            if event.event_hash != expected: raise ValueError(f"ledger event hash mismatch at {expected_seq}")
            prev=event.event_hash

    def append(self, event_type: str, claim_id: str, payload: dict[str, Any]) -> LedgerEvent:
        self.verify()
        existing=self.events(); seq=len(existing); prev=existing[-1].event_hash if existing else GENESIS
        digest=self._digest(seq,event_type,claim_id,payload,prev)
        event=LedgerEvent(seq,event_type,claim_id,payload,prev,digest)
        row={"seq":seq,"event_type":event_type,"claim_id":claim_id,"payload":payload,"prev_hash":prev,"event_hash":digest}
        with self.path.open("a",encoding="utf-8") as fh:
            fh.write(canonical_json(row)+"\n"); fh.flush()
        return event

    def for_claim(self, claim_id: str) -> Tuple[LedgerEvent, ...]:
        return tuple(e for e in self.events() if e.claim_id == claim_id)
