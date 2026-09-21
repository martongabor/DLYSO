#!/usr/bin/env python3
"""Compile editable Markdown into a self-contained offline HTML reference."""

import base64
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import markdown
from dlyso_runtime import VERSION, model_root, sha256
from scripts.combineresult import THRESHOLDS


def main():
    assets = ROOT / "dlyso_assets"
    assets.mkdir(exist_ok=True)
    manifest = assets / "model-manifest.json"
    files = sorted(model_root().rglob("*.pt"))
    if len(files) == 48:
        manifest.write_text(
            json.dumps(
                {"version": VERSION, "sha256": {str(path.relative_to(model_root())): sha256(path) for path in files}},
                indent=2,
            )
            + "\n"
        )
    elif not manifest.exists():
        raise SystemExit("Cannot create model manifest: expected all 48 weights.")
    table = "| Model | SED | Dust-aware SED | AllWISE | DTDM |\n|---|---:|---:|---:|---:|\n"
    for model in THRESHOLDS["SEDplot"]:
        table += f"| `{model}` | " + " | ".join(f"{THRESHOLDS[m][model]:.3f}" for m in THRESHOLDS) + " |\n"
    schema = ROOT / "docs/OUTPUT_SCHEMA.md"
    text = schema.read_text()
    if "<!-- THRESHOLD_TABLE -->" in text:
        text = text.replace(
            "<!-- THRESHOLD_TABLE -->", "<!-- THRESHOLDS_START -->\n" + table + "<!-- THRESHOLDS_END -->"
        )
    else:
        text = re.sub(
            r"<!-- THRESHOLDS_START -->.*?<!-- THRESHOLDS_END -->",
            "<!-- THRESHOLDS_START -->\n" + table + "<!-- THRESHOLDS_END -->",
            text,
            flags=re.S,
        )
    schema.write_text(text)
    sources = [
        "USER_GUIDE",
        "GITHUB_INSTALL",
        "CLI_REFERENCE",
        "OUTPUT_SCHEMA",
        "MODEL_CARD",
        "DEVELOPMENT",
        "RELEASE_CHECKLIST",
        "VERIFICATION",
    ]
    sections = []
    nav = []
    for name in sources:
        path = ROOT / "docs" / f"{name}.md"
        if not path.exists():
            continue
        text = path.read_text()
        title = text.splitlines()[0].lstrip("# ")
        body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])
        sections.append(f'<section id="{name.lower()}">{body}</section>')
        nav.append(f'<a href="#{name.lower()}">{html.escape(title.replace("DLYSO ", ""))}</a>')
    for name in sources:
        path = ROOT / "docs" / f"{name}.md"
        if path.exists():
            (assets / path.name).write_text(path.read_text())
    (assets / "coordinates.csv").write_bytes((ROOT / "examples/coordinates.csv").read_bytes())
    screenshots = ""
    for name, caption in [
        ("project", "Project settings."),
        ("results", "Results browser with synthetic demonstration data."),
    ]:
        path = ROOT / "docs/images" / f"{name}.png"
        if path.exists():
            data = base64.b64encode(path.read_bytes()).decode()
            screenshots += f'<figure><img alt="{caption}" src="data:image/png;base64,{data}"><figcaption>{caption}</figcaption></figure>'
    css = """
:root{--ink:#172d36;--muted:#65777c;--teal:#167868;--line:#dce2dc}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:30px}
body{margin:0;background:#f5f6f2;color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
nav{position:fixed;inset:0 auto 0 0;width:255px;padding:38px 26px;background:var(--ink);color:#fff;overflow:auto}
nav strong{font-size:30px;letter-spacing:4px}nav p{font-size:12px;color:#bed0ce;margin-bottom:40px}
nav a{display:block;color:#d3e0d9;text-decoration:none;padding:10px 0;font-size:14px}nav a:hover{color:white;text-decoration:underline}
main{max-width:1130px;margin-left:255px;padding:55px 64px 90px}header{border-bottom:1px solid var(--line);padding-bottom:32px;margin-bottom:40px}
.kicker{font-size:12px;letter-spacing:2px;text-transform:uppercase;color:var(--teal);font-weight:600}header h1{font-size:44px;line-height:1.18;margin:12px 0}
header p{font-size:19px;color:var(--muted)}section{padding-top:24px;margin-top:45px;border-top:1px solid var(--line)}section h1{font-size:31px;line-height:1.3}
h2{font-size:23px;margin-top:42px;line-height:1.4}h3{font-size:18px;margin-top:30px}p,li{max-width:80ch}a{color:var(--teal);text-underline-offset:3px}
pre{overflow:auto;background:#172d36;color:#dbe9df;padding:20px 24px;border-radius:6px;line-height:1.6;font-size:13px}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.9em}p code,td code,li code{background:#e8ede6;padding:2px 4px;border-radius:3px}
table{width:100%;border-collapse:collapse;font-size:14px;margin:24px 0;background:white}th{text-align:left;background:#e9eee7}td,th{padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}
figure{margin:32px 0}img{max-width:100%;border:1px solid var(--line);border-radius:8px}figcaption{font-size:13px;color:var(--muted)}
@media(max-width:850px){nav{position:relative;width:auto;padding:24px}nav p{margin:8px 0}nav a{display:inline-block;margin-right:18px;padding:4px 0}main{margin:0;padding:30px 20px}table{display:block;overflow:auto}header h1{font-size:34px}}
@media print{nav{display:none}main{margin:0;padding:0;max-width:none}body{background:white;font-size:11pt}pre{white-space:pre-wrap;background:#f1f3ee;color:#172d36}section{break-before:page}a{color:inherit}figure{break-inside:avoid}}
"""
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DLYSO documentation</title><style>{css}</style></head><body><nav aria-label="Contents"><strong>DLYSO</strong><p>USER & TECHNICAL REFERENCE<br>Version {VERSION}</p>{"".join(nav)}</nav><main><header><h1>DLYSO documentation</h1><small>Use your browser’s Find command to search this reference. All images and styles are embedded.</small></header>{screenshots}{"".join(sections)}</main></body></html>"""
    # Internal Markdown documentation links should resolve inside the single file.
    for name in sources:
        document = re.sub(r'href="(?:docs/)?' + name + r'\.md(?:#[^"]*)?"', f'href="#{name.lower()}"', document)
    document = document.replace('href="VERIFICATION.md"', 'href="#verification"')
    (ROOT / "dlyso_pipeline_docs.html").write_text(document)
    (assets / "reference.html").write_text(document)
    print("Rendered offline reference and synchronized installable resources.")


if __name__ == "__main__":
    main()
