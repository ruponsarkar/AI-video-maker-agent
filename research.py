"""
Snack Code - Step 3: local research
Searches your local SearXNG, downloads the top pages, and asks the local
model to pull out facts with their source links.

Usage:
    python research.py "call forwarding scam India"
"""
import os
import sys

import ollama
import requests
import trafilatura

MODEL = "qwen3:8b"
SEARXNG = "http://localhost:8080/search"
MAX_SOURCES = 6
CHARS_PER_SOURCE = 3000

if len(sys.argv) < 2:
    print('Usage: python research.py "your topic"')
    sys.exit(1)

topic = sys.argv[1]
os.makedirs("research", exist_ok=True)

print(f"Searching: {topic}")
res = requests.get(SEARXNG, params={"q": topic, "format": "json"}, timeout=30).json()
results = res.get("results", [])[:MAX_SOURCES]
if not results:
    print("No search results. Is SearXNG running? Try: docker start searxng")
    sys.exit(1)

notes = []
for r in results:
    url = r["url"]
    print(f"  reading {url}")
    html = trafilatura.fetch_url(url)
    text = trafilatura.extract(html) if html else None
    if text:
        notes.append(f"SOURCE: {url}\n{text[:CHARS_PER_SOURCE]}")

if not notes:
    print("Could not read any of the pages. Try a different search phrase.")
    sys.exit(1)

prompt = (
    f"Topic: {topic}\n\n"
    "Neeche diye sources se is topic ke important facts nikalo.\n"
    "Rules:\n"
    "- Har fact ke saath uska SOURCE link likho.\n"
    "- Jo baat sources mein nahi hai, woh bilkul mat likho.\n"
    "- Bullet points mein likho, simple Hinglish mein.\n\n"
    + "\n\n".join(notes)
)

print(f"Summarising with {MODEL} ...")
out = ollama.chat(
    model=MODEL,
    messages=[{"role": "user", "content": prompt}],
    think=False,
    options={"num_ctx": 8192},
)

path = "research/notes.md"
with open(path, "w", encoding="utf-8") as f:
    f.write(f"# Research: {topic}\n\n")
    f.write(out["message"]["content"])

print(f"Saved {path}. Open it and check 2-3 links yourself before writing the script.")
