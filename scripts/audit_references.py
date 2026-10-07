"""Check reference identities, years, reading records and bibliography consistency."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = {"roca2020rlc", "golaghazadeh2022parity", "michel2023flec",
        "iyengar2021recovery", "kuhn2022congestion"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_bib(path, sources):
    text = path.read_text(encoding="utf-8")
    records = re.split(r"(?=@(?:article|misc|techreport)\{)", text)[1:]
    keys = [record.split("\n", 1)[0].split("{", 1)[1].rstrip(",") for record in records]
    require(len(keys) == len(set(keys)) and set(keys) == {r["key"] for r in sources},
            "BibTeX identities differ: " + str(path.relative_to(ROOT)))
    for ref in sources:
        record = records[keys.index(ref["key"])]
        require(f"year = {{{ref['year']}}}" in record and ref["url"] in record,
                "BibTeX year/URL mismatch: " + ref["key"])


def audit():
    docs = json.loads((ROOT / "docs/reference-audit.json").read_text(encoding="utf-8"))
    paper = json.loads((ROOT / "paper/references.json").read_text(encoding="utf-8"))
    low, high = docs["publication_range"]
    require((low, high) == (2020, 2026), "Reference interval differs from the project requirement")
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", docs["verified_on"]), "Missing reference-check date")
    for sources in (docs["sources"], paper):
        keys = [r["key"] for r in sources]
        require(CORE <= set(keys) and len(keys) == len(set(keys)), "Missing core or duplicate reference")
        for ref in sources:
            require(low <= ref["year"] <= high, "Reference outside interval: " + ref["key"])
            require(ref["access"] in {"abstract", "full_text"} and ref["locator"] and ref["status"],
                    "Missing reading/status record: " + ref["key"])
            require(ref["url"].startswith("https://"), "Missing primary link: " + ref["key"])
    by_key = {r["key"]: r for r in paper}
    require([r["id"] for r in docs["sources"]] == list(range(1, len(docs["sources"]) + 1)),
            "Proposal reference numbering has gaps or duplicates")
    for ref in docs["sources"]:
        require(ref["key"] in by_key and all(ref[k] == by_key[ref["key"]][k]
                for k in ("year", "url", "access", "status")),
                "Proposal/paper metadata differ: " + ref["key"])
    check_bib(ROOT / "docs/references.bib", docs["sources"])
    check_bib(ROOT / "paper/references.bib", paper)
    proposal = (ROOT / "docs/proposal.md").read_text(encoding="utf-8")
    body, bibliography = proposal.split("## References (2020-2026)", 1)
    records = re.findall(r"^\[(\d+)\] (.+)$", bibliography, re.M)
    require([int(n) for n, _ in records] == [r["id"] for r in docs["sources"]],
            "Proposal reference count/ordering differ")
    require({int(n) for n in re.findall(r"\[(\d+)\]", body)} == {r["id"] for r in docs["sources"]},
            "Unused or unresolved proposal citation")
    for (_, text), ref in zip(records, docs["sources"]):
        require(by_key[ref["key"]]["text"] in text and ref["url"] in text,
                "Proposal citation differs: " + ref["key"])
    return {"status": "passed", "checked_on": docs["verified_on"],
            "publication_range": [low, high], "proposal_references": len(docs["sources"]),
            "paper_references": len(paper),
            "paper_reading_depth": {level: sum(r["access"] == level for r in paper)
                                    for level in ("full_text", "abstract")}}


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
