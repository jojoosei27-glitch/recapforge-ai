import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

API_BASE = "https://api.dvidshub.net"
ALLOWED_MEDIA_HOSTS = {
    "d34w7g4gy10iej.cloudfront.net",
    "d1ldvf68ux039x.cloudfront.net",
    "dvidshub.net",
    "www.dvidshub.net",
}
USER_AGENT = "RecapForgeAI/0.1 (DVIDS media research tool)"

def workspace() -> Path:
    p = Path(os.environ.get("RECAPFORGE_WORKSPACE", "workspace")).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p

def api_key() -> str:
    key = os.environ.get("DVIDS_API_KEY", "").strip()
    if not key or key == "put_your_own_key_in_environment_not_in_git":
        raise SystemExit(
            "Missing DVIDS_API_KEY. Set it as an environment variable; do not put it in source code."
        )
    return key

def api_get(endpoint: str, params: dict) -> dict:
    params = dict(params)
    params["api_key"] = api_key()
    response = requests.get(
        f"{API_BASE}/{endpoint.lstrip('/')}",
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=(15, 90),
    )
    if response.status_code == 403:
        raise RuntimeError("DVIDS returned 403. Check your API key, app restrictions, and access.")
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get("errors"):
        raise RuntimeError(f"DVIDS API error: {data['errors']}")
    return data

def safe_name(value: str, max_len: int = 100) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "asset")
    return value.strip("._-")[:max_len] or "asset"

def flatten_result(item: dict) -> dict:
    return {
        "id": item.get("id", ""),
        "type": item.get("type", ""),
        "title": item.get("title", ""),
        "date": item.get("date", ""),
        "date_published": item.get("date_published", item.get("publishdate", "")),
        "branch": item.get("branch", ""),
        "unit_name": item.get("unit_name", ""),
        "credit": item.get("credit", ""),
        "duration_seconds": item.get("duration", ""),
        "width": item.get("width", ""),
        "height": item.get("height", ""),
        "description": item.get("short_description", item.get("description", "")),
        "keywords": item.get("keywords", ""),
        "thumbnail": item.get("thumbnail", ""),
        "source_url": item.get("url", ""),
    }

def search(args):
    params = {
        "q": args.query,
        "max_results": max(1, min(args.limit, 50)),
        "page": args.page,
        "prettyprint": 1,
        "short_description_length": 300,
    }
    if len(args.types) == 1:
        params["type"] = args.types[0]
    else:
        # Requests encodes this list as repeated type%5B%5D=video&type%5B%5D=image,
        # matching DVIDS' documented type[] filter.
        params["type[]"] = args.types
    if args.branch:
        params["branch"] = args.branch
    if args.hd:
        params["hd"] = 1
    if args.sort:
        params["sort"] = args.sort
        params["sortdir"] = args.sortdir

    data = api_get("search", params)
    results = data.get("results", [])
    root = workspace() / "searches"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = safe_name(args.query) + "_" + stamp
    json_path = root / f"{stem}.json"
    csv_path = root / f"{stem}.csv"
    payload = {
        "query": args.query,
        "types": args.types,
        "filters": {"branch": args.branch, "hd": args.hd, "sort": args.sort},
        "fetched_at_utc": stamp,
        "page_info": data.get("page_info", {}),
        "results": results,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = [flatten_result(x) for x in results]
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    print(f"Found {len(results)} result(s).")
    print(f"JSON manifest: {json_path}")
    if rows:
        print(f"CSV manifest:  {csv_path}")
    for i, item in enumerate(rows, 1):
        print(f"{i:>2}. [{item['id']}] {item['title']} — {item['type']} — {item['source_url']}")

def allowed_media_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host in ALLOWED_MEDIA_HOSTS or host.endswith(".dvidshub.net")
    )

def get_asset(asset_id: str) -> dict:
    data = api_get("asset", {"id": asset_id, "prettyprint": 1})
    item = data.get("results", data)
    if not isinstance(item, dict) or not item.get("id"):
        raise RuntimeError(f"Unexpected asset response for {asset_id}")
    return item

def select_download(item: dict):
    asset_id = item.get("id", "asset:unknown")
    kind = asset_id.split(":", 1)[0]
    if kind == "image":
        return item.get("image"), ".jpg"
    if kind == "video":
        files = item.get("files") or []
        mp4s = [f for f in files if f.get("src") and ("mp4" in f.get("type", "") or ".mp4" in f.get("src", "").lower())]
        if mp4s:
            # Prefer highest resolution, then bitrate; metadata size can be missing.
            best = sorted(mp4s, key=lambda f: (int(f.get("width") or 0) * int(f.get("height") or 0), int(f.get("bitrate") or 0)), reverse=True)[0]
            return best.get("src"), ".mp4"
        return None, ".mp4"
    return None, ""

def download_one(asset_id: str, max_mb: int | None):
    item = get_asset(asset_id)
    url, ext = select_download(item)
    if not url:
        print(f"SKIP {asset_id}: no direct downloadable image/MP4 listed by DVIDS.")
        return
    if not allowed_media_url(url):
        print(f"SKIP {asset_id}: returned media host is not on the allowlist.")
        return

    assets_dir = workspace() / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    base = safe_name(f"{asset_id}_{item.get('title', 'asset')}")
    target = assets_dir / f"{base}{ext}"
    metadata_path = assets_dir / f"{base}.metadata.json"
    if target.exists() and target.stat().st_size > 0 and metadata_path.exists():
        print(f"EXISTS {target}")
        return

    with requests.get(url, stream=True, timeout=(20, 120), headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        length = int(r.headers.get("content-length", "0") or 0)
        if max_mb and length and length > max_mb * 1024 * 1024:
            print(f"SKIP {asset_id}: file is {length/1024/1024:.1f} MB, above --max-mb {max_mb}.")
            return
        tmp = target.with_suffix(target.suffix + ".part")
        written = 0
        try:
            with tmp.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if max_mb and written > max_mb * 1024 * 1024:
                        raise RuntimeError(f"Download exceeded --max-mb {max_mb}; partial file removed.")
                    f.write(chunk)
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    credits = item.get("credit", "")
    if isinstance(credits, list):
        credits = "; ".join(
            " ".join(str(part) for part in [c.get("rank", ""), c.get("name", "")] if part).strip()
            for c in credits if isinstance(c, dict)
        )
    record = {
        "id": item.get("id"),
        "title": item.get("title"),
        "description": item.get("description"),
        "source_url": item.get("url"),
        "download_url": url,
        "type": item.get("type", asset_id.split(":", 1)[0]),
        "date": item.get("date"),
        "date_published": item.get("date_published"),
        "branch": item.get("branch"),
        "unit_name": item.get("unit_name"),
        "creator_credit": credits,
        "keywords": item.get("keywords"),
        "virin": item.get("virin"),
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "copyright_review_required": True,
        "usage_note": "Check the individual DVIDS asset page for copyright/usage restrictions before publication. Do not imply DoD endorsement.",
    }
    metadata_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"DOWNLOADED {target}")
    print(f"METADATA   {metadata_path}")

def download(args):
    if not args.ids:
        raise SystemExit("Provide one or more IDs, e.g. --ids video:284392 image:366678")
    for asset_id in args.ids:
        try:
            download_one(asset_id, args.max_mb)
        except Exception as exc:
            print(f"ERROR {asset_id}: {exc}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(prog="recapforge", description="DVIDS research and asset preparation")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Search DVIDS for military media")
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--types", nargs="+", choices=["video", "image"], default=["video", "image"])
    p_search.add_argument("--limit", type=int, default=20, help="Results per page, max 50")
    p_search.add_argument("--page", type=int, default=1)
    p_search.add_argument("--branch", choices=["Army", "Navy", "Air Force", "Marines", "Coast Guard", "Joint", "Civilian", "Space Force"])
    p_search.add_argument("--hd", action="store_true", help="Filter for HD videos (API behavior applies to video search)")
    p_search.add_argument("--sort", choices=["date", "publishdate", "timestamp", "score", "rating"])
    p_search.add_argument("--sortdir", choices=["asc", "desc"], default="desc")
    p_search.set_defaults(func=search)

    p_download = sub.add_parser("download", help="Download explicitly selected DVIDS assets")
    p_download.add_argument("--ids", nargs="+", required=True, help="Asset IDs from DVIDS search, e.g. video:284392")
    p_download.add_argument("--max-mb", type=int, default=None, help="Optional maximum size per file")
    p_download.set_defaults(func=download)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        raise SystemExit(f"Error: {exc}")

if __name__ == "__main__":
    main()
