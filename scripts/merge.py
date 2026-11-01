#!/usr/bin/env python3
"""Merges the shard guides and writes compressed guides: all channels, DACH and one file per country.

Country = suffix of the iptv-org channel id ("DasErste.de@SD" -> "de").
Streaming (iterparse), so even several hundred MB never sit in memory at once.
"""
import glob, gzip, os, sys
import xml.etree.ElementTree as ET
from collections import defaultdict

src = sys.argv[1] if len(sys.argv) > 1 else "parts"
out = sys.argv[2] if len(sys.argv) > 2 else "public"
os.makedirs(os.path.join(out, "guides"), exist_ok=True)

def country(cid):
    stem = cid.split("@")[0]
    return stem.rsplit(".", 1)[-1].lower() if "." in stem else "xx"

writers = {}
def writer(name):
    if name not in writers:
        f = gzip.open(os.path.join(out, name), "wt", encoding="utf-8", compresslevel=9)
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="nova-epg">\n')
        writers[name] = f
    return writers[name]

def targets(cid):
    c = country(cid)
    t = ["guide.xml.gz", f"guides/{c}.xml.gz"]
    if c in ("de", "at", "ch"):
        t.append("guides/dach.xml.gz")
    return t

counts = defaultdict(lambda: [0, 0])
files = sorted(glob.glob(os.path.join(src, "**", "*.xml"), recursive=True))
# channels first, then programmes (XMLTV order)
for phase in ("channel", "programme"):
    for path in files:
        try:
            for _, el in ET.iterparse(path, events=("end",)):
                if el.tag != phase:
                    continue
                cid = el.get("id") if phase == "channel" else el.get("channel")
                if cid:
                    data = ET.tostring(el, encoding="unicode")
                    for t in targets(cid):
                        writer(t).write("  " + data.strip() + "\n")
                        counts[t][0 if phase == "channel" else 1] += 1
                el.clear()
        except ET.ParseError as e:
            print(f"WARN {path}: {e}", file=sys.stderr)

for f in writers.values():
    f.write("</tv>\n"); f.close()

lines = ["Datei\tSender\tSendungen\tGröße"]
for name in sorted(counts):
    size = os.path.getsize(os.path.join(out, name))
    lines.append(f"{name}\t{counts[name][0]}\t{counts[name][1]}\t{size/1e6:.1f} MB")
open(os.path.join(out, "stats.tsv"), "w").write("\n".join(lines) + "\n")
print("\n".join(l for l in lines if not l.startswith("guides/") or "dach" in l or l.startswith("guides/de.")))
