"""Fetch public source URLs with provenance; never infer accounting numbers.

Usage: python collect_sources.py --limit 3 --timeout 12
Downloaded source bytes are a private research cache, not redistributed.
CSV event/forecast promotion remains a manual accounting/date verification step.
"""

import argparse
import csv
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])


def fetch(record, cache, timeout):
    url = record["url"]
    p = urllib.parse.urlparse(url)
    allowed = {
        "www.ammc.ma",
        "attijaricib.com",
        "akdital.ma",
        "www.ir-bankofafrica.ma",
        "ir-bankofafrica.ma",
    }
    if p.scheme != "https" or p.hostname not in allowed:
        raise ValueError("Only registered public HTTPS source hosts are allowed")
    result = dict(
        source_id=record["source_id"],
        url=url,
        attempted_at=datetime.now(timezone.utc).isoformat(),
        status="ERROR",
        http_status="",
        bytes=0,
        sha256="",
        local_file="",
        message="",
    )
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "CasablancaEarningsResearch/1.0 (public documents; low request rate)"
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read(30_000_001)
            if len(data) > 30_000_000:
                raise ValueError("Source exceeds 30 MB cache limit")
            content = response.headers.get_content_type()
            if url.lower().endswith(".pdf") and not data.startswith(b"%PDF"):
                raise ValueError("Expected PDF; received HTML/error/login response")
            if content not in ("application/pdf", "text/html", "application/octet-stream"):
                raise ValueError(f"Unexpected content type {content}")
            ext = ".pdf" if data.startswith(b"%PDF") else ".html"
            path = cache / (record["source_id"] + ext)
            path.write_bytes(data)
            result.update(
                status="OK",
                http_status=response.status,
                bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                local_file=str(path),
                message=content,
            )
            if ext == ".html":
                parser = Links()
                parser.feed(data.decode("utf-8", errors="replace"))
                links = sorted(
                    {
                        urllib.parse.urljoin(url, link)
                        for link in parser.links
                        if ".pdf" in link.lower()
                    }
                )
                (cache / (record["source_id"] + "_pdf_links.json")).write_text(
                    json.dumps(links, indent=2), encoding="utf-8"
                )
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        result["message"] = f"{type(exc).__name__}: {exc}"
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--timeout", type=float, default=12)
    p.add_argument("--source-id", action="append")
    p.add_argument("--cache", default="source_cache")
    a = p.parse_args()
    if a.limit < 1 or not 1 <= a.timeout <= 60:
        p.error("limit must be positive and timeout between 1 and 60")
    root = Path(__file__).resolve().parent
    cache = root / a.cache
    cache.mkdir(parents=True, exist_ok=True)
    sources = json.loads((root / "data/earnings/sources.json").read_text(encoding="utf-8"))
    if a.source_id:
        sources = [r for r in sources if r["source_id"] in a.source_id]
    results = []
    for r in sources[: a.limit]:
        result = fetch(r, cache, a.timeout)
        results.append(result)
        print(r["source_id"], result["status"], result["message"], flush=True)
        time.sleep(0.5)
    path = root / "data/earnings/direct_collection_log.csv"
    if results:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(results[0]))
            writer.writeheader()
            writer.writerows(results)
    print(f"Logged {len(results)} attempts; raw failures are not treated as observations.")


if __name__ == "__main__":
    main()
