#!/usr/bin/env python3
"""Sport guide: German-language sports channels (from the curated DACH guide) + US sports channels.

  python3 scripts/sport.py OUT.xml.gz REPORT.tsv dach:guides/dach.xml.gz us:extra-us.xml.gz teams:extra-us-sports.xml.gz

- dach:  only sports channels (iptv-org category "sports" or a sports name), already deduplicated by dach.py
- us:    US sports networks; West-coast "(Pacific)" copies are left out (same programme, 3 h later), HD/SD
         spellings of one network are one channel (the one with the most programmes wins)
- teams: US team channels (NFL, NBA, NHL, MLB, MLS, WNBA, UFC – no minor leagues) with their next games
Only channels with programmes that are not over yet are written.
"""
import csv, gzip, os, re, sys, time
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT, REPORT = sys.argv[1], sys.argv[2]
INPUTS = [a.split(":", 1) for a in sys.argv[3:]]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = time.time()

SPORT_NAME = re.compile(r"(?i)sport|dazn|eurosport|bundesliga|sky sport|magenta ?sport|motorvision|auto motor|golf|tennis"
                        r"|fu(ss|ß)ball|esports?1|red ?bull|extreme|fight|wwe|ufc|nfl|nba|nhl|mlb|mls|espn|fs1|fs2|olymp"
                        r"|liga|arena|racing|speed|edge|blue event|willow|cricket|outdoor|sportsman|redzone|bein")
US_SPORT = re.compile(r"(?i)espn|fox ?sports|\bfs[12]\b|nba|nfl|mlb|nhl|golf|tennis|bein|cbs ?sports|nbc ?sports|big ?ten"
                      r"|\bsec\b|\bacc\b|marquee|\byes\b|\bmsg|nesn|\bsny\b|sportsnet|root ?sports|altitude|spectrum ?sports"
                      r"|outdoor|sportsman|willow|fight|wwe|redzone|red zone|floracing|motortrend|space city|fanduel"
                      r"|\btnt\b|\btbs\b|trutv|mlbei|extra innings|sunday ticket|league pass|ocho")
NOT_SPORT = re.compile(r"(?i)\(pacific|pacific\)|pacific feed|home and garden|bet\b|cinemax|hbo|starz|accuweather|bravo")
NOT_GERMAN = re.compile(r"(?i)\bdirect\b|\s(F|Un)$|\bD?F\s?\d*$|telecapri|turk|\biz\b|blue event f")
TEAMS = re.compile(r"^(NFL|NBA|NHL|MLB|MLS|WNBA|UFC) - ")
NOISE = {"hd", "fhd", "uhd", "sd", "4k", "tv", "us", "us2", "east", "national", "feed", "network", "channel"}

sports_ids = set()
for r in csv.DictReader(open(f"{ROOT}/data/channels.csv", encoding="utf-8")):
    if "sports" in r["categories"]:
        sports_ids.add(r["id"])

def ts(v):
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", v or "")
    if not m:
        return None
    t = time.mktime(time.strptime(m.group(1), "%Y%m%d%H%M%S")) - time.timezone
    if m.group(2):
        sign = 1 if m.group(2)[0] == "+" else -1
        t -= sign * (int(m.group(2)[1:3]) * 3600 + int(m.group(2)[3:5]) * 60)
    return t

def key(n):
    n = re.sub(r"(?i)fox sports (\d)", r"fs\1", n)
    out = []
    for t in re.split(r"[^a-z0-9+]+", n.lower()):
        if t and t not in NOISE and t not in out:
            out.append(t)
    return "".join(out)

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")

def read(path):
    """channel id -> [names, icon, programmes(xml strings, future only)]"""
    chans = {}
    with open(path, "rb") as f:
        gz = f.read(2) == b"\x1f\x8b"
    src = gzip.open(path, "rb") if gz else open(path, "rb")
    for _, el in ET.iterparse(src, events=("end",)):
        if el.tag == "channel":
            names = [d.text.strip() for d in el.findall("display-name") if d.text and d.text.strip()]
            ic = el.find("icon")
            chans[el.get("id")] = [names or [el.get("id").rsplit(".", 1)[0].replace(".", " ")],
                                   ic.get("src") if ic is not None else None, []]
            el.clear()
        elif el.tag == "programme":
            c = chans.get(el.get("channel"))
            st, sp = ts(el.get("start")), ts(el.get("stop"))
            if c is not None and st is not None and (sp or st) > NOW:
                c[2].append((st, ET.tostring(el, encoding="unicode").strip()))
            el.clear()
    return chans

picked = {}                               # key -> (group, id, names, icon, progs)
for label, path in INPUTS:
    try:
        chans = read(path)
    except (ET.ParseError, OSError, EOFError) as e:
        print(f"WARN {path}: {e}", file=sys.stderr)
        continue
    n0 = len(picked)
    for cid, (names, icon, progs) in chans.items():
        if not progs:
            continue
        text = " ".join(names) + " " + cid.replace(".", " ")
        if label == "dach":
            if not (cid in sports_ids or cid.split("@")[0] in sports_ids or SPORT_NAME.search(text)):
                continue
            if NOT_GERMAN.search(names[0]):        # French/Italian/Turkish feeds of Swiss and other packages
                continue
            group, k = "DE", "de:" + cid
        elif label == "us":
            if NOT_SPORT.search(text) or not US_SPORT.search(text):
                continue
            group, k = "US", "us:" + key(names[0])
        else:
            if not TEAMS.match(names[0]):
                continue
            group, k = "US-Teams", "team:" + key(names[0])
        if k in picked and len(picked[k][4]) >= len(progs):
            continue
        picked[k] = (group, cid, names, icon, progs)
    print(f"{label:6s} {os.path.basename(path)}: {len(picked) - n0} Sportsender")

rows = sorted(picked.values(), key=lambda r: (r[0], r[2][0].lower()))
with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as w:
    w.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="nova-epg sport">\n')
    for group, cid, names, icon, progs in rows:
        lang = "de" if group == "DE" else "en"
        w.write(f'  <channel id="{esc(cid)}">\n')
        for n in names[:12]:
            w.write(f'    <display-name lang="{lang}">{esc(n)}</display-name>\n')
        if icon:
            w.write(f'    <icon src="{esc(icon)}" />\n')
        w.write("  </channel>\n")
    for group, cid, names, icon, progs in rows:
        seen = set()
        for st, x in sorted(progs):
            if st in seen:
                continue
            seen.add(st)
            w.write("  " + x + "\n")
    w.write("</tv>\n")

with open(REPORT, "w", encoding="utf-8") as f:
    f.write(f"# Sport-Guide {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(NOW))}: {len(rows)} Sender\n")
    f.write("Gruppe\tSender\tID\tSendungen\tTage voraus\n")
    for group, cid, names, icon, progs in rows:
        last = max(ts(re.search(r'stop="([^"]+)"', x).group(1)) or s for s, x in progs)
        f.write(f"{group}\t{names[0]}\t{cid}\t{len(progs)}\t{(last - NOW) / 86400:.1f}\n")
counts = {g: sum(1 for r in rows if r[0] == g) for g in ("DE", "US", "US-Teams")}
print(f"Sport: {len(rows)} Sender ({', '.join(f'{g} {n}' for g, n in counts.items())})")
