"""Make a single-file preview of the site with the price data baked in (for sharing as an artifact)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
data = json.loads((ROOT / "docs" / "data" / "prices.json").read_text(encoding="utf-8"))
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "preview.html"

head = re.search(r"<head>(.*?)</head>", page, re.S).group(1)
body = re.search(r"<body>(.*?)</body>", page, re.S).group(1)
head = re.sub(r'<meta charset[^>]*>\s*|<meta name="viewport"[^>]*>\s*', "", head)
seed = '<script id="seed-data" type="application/json">' + json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n"
body = body.replace("<script>", seed + "<script>", 1)
out.write_text(head.strip() + "\n" + body.strip() + "\n", encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
