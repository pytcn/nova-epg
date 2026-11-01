#!/usr/bin/env python3
"""Merges the shard guides (+ external XMLTV guides) and writes compressed guides:
all channels, DACH and one file per country.

  python3 scripts/merge.py parts public [external.xml.gz ...]

- Country = suffix of the channel id ("DasErste.de@SD" -> "de").
- External guides only add channels we do not have yet (same id or same name in the same country)
  and only programmes that are not over yet; an outdated external file adds nothing.
- Duplicate programmes (same channel + same start) are written once.
- Streaming (iterparse): several hundred MB never sit in memory at once.
"""
import glob, gzip, os, re, sys, time, unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict

src = sys.argv[1] if len(sys.argv) > 1 else "parts"
out = sys.argv[2] if len(sys.argv) > 2 else "public"
externals = sys.argv[3:]
os.makedirs(os.path.join(out, "guides"), exist_ok=True)
NOW = time.time()

NOISE = {"hd", "fhd", "uhd", "sd", "4k", "hq", "hevc", "raw", "1080p", "720p", "tv", "fernsehen", "channel", "de"}
def key(name):
    s = (name or "").lower().replace("ß", "ss").replace("&", " und ")
    s = re.sub(r"\+\s*(\d)", r" plus\1 ", s).replace("+", " plus ")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    s = re.sub(r"(?<=[a-z0-9])[.\-'](?=[a-z0-9])", "", s)
    return "".join(t for t in re.split(r"[^a-z0-9]+", s) if t and t not in NOISE)

def country(cid):
    stem = cid.split("@")[0]
    return stem.rsplit(".", 1)[-1].lower() if "." in stem else "xx"

def stop_ts(v):
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", v or "")
    if not m:
        return None
    t = time.mktime(time.strptime(m.group(1), "%Y%m%d%H%M%S")) - time.timezone
    if m.group(2):
        sign = 1 if m.group(2)[0] == "+" else -1
        t -= sign * (int(m.group(2)[1:3]) * 3600 + int(m.group(2)[3:5]) * 60)
    return t

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
def emit(el, cid, phase):
    data = ET.tostring(el, encoding="unicode").strip()
    for t in targets(cid):
        writer(t).write("  " + data + "\n")
        counts[t][0 if phase == "channel" else 1] += 1

def open_any(path):
    with open(path, "rb") as f:
        gz = f.read(2) == b"\x1f\x8b"
    return gzip.open(path, "rb") if gz else open(path, "rb")

def parse(path, tag):
    try:
        for _, el in ET.iterparse(open_any(path), events=("end",)):
            if el.tag == tag:
                yield el
                el.clear()
    except (ET.ParseError, OSError, EOFError) as e:
        print(f"WARN {path}: {e}", file=sys.stderr)

files = sorted(glob.glob(os.path.join(src, "**", "*.xml"), recursive=True))
ids, names = set(), set()
seen_prog = set()
for path in files:
    for el in parse(path, "channel"):
        cid = el.get("id")
        if cid and cid not in ids:
            ids.add(cid)
            for d in el.findall("display-name"):
                names.add((country(cid), key(d.text)))
            emit(el, cid, "channel")
for path in files:
    for el in parse(path, "programme"):
        cid = el.get("channel"); k = (cid, el.get("start"))
        if cid in ids and k not in seen_prog:
            seen_prog.add(k); emit(el, cid, "programme")

ext_report = []
for path in externals:
    # Only channels with programmes that are not over yet – an outdated file adds nothing.
    fresh, stale = set(), 0
    for el in parse(path, "programme"):
        st = stop_ts(el.get("stop"))
        if st is None or st >= NOW:
            fresh.add(el.get("channel"))
        else:
            stale += 1
    added, dup, kept = set(), 0, 0
    for el in parse(path, "channel"):
        cid = el.get("id")
        if not cid or cid not in fresh:
            continue
        if cid in ids or any((country(cid), key(d.text)) in names for d in el.findall("display-name")):
            dup += 1
            continue
        added.add(cid); ids.add(cid)
        emit(el, cid, "channel")
    for el in parse(path, "programme"):
        cid = el.get("channel")
        st = stop_ts(el.get("stop"))
        if cid not in added or (st is not None and st < NOW):
            continue
        k = (cid, el.get("start"))
        if k not in seen_prog:
            seen_prog.add(k); kept += 1; emit(el, cid, "programme")
    ext_report.append(f"{os.path.basename(path)}\t+{len(added)} Sender (schon vorhanden: {dup})\t{kept} aktuelle Sendungen\t{stale} abgelaufen")

for f in writers.values():
    f.write("</tv>\n"); f.close()

lines = ["Datei\tSender\tSendungen\tGröße"]
for name in sorted(counts):
    size = os.path.getsize(os.path.join(out, name))
    lines.append(f"{name}\t{counts[name][0]}\t{counts[name][1]}\t{size/1e6:.1f} MB")
lines += ["", "Externe Guides"] + ext_report
open(os.path.join(out, "stats.tsv"), "w").write("\n".join(lines) + "\n")
print("\n".join(l for l in lines if not l.startswith("guides/") or "dach" in l or l.startswith("guides/de.")))
