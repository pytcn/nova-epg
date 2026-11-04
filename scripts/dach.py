#!/usr/bin/env python3
"""Curated guide: one clean channel list for Germany, Austria and Switzerland (or more countries with
--countries=de,at,ch,uk,us), every channel with programmes.

  python3 scripts/dach.py OUT.xml.gz REPORT.tsv  own:guide.xml.gz  de:extra-de.xml.gz  at:extra-at.xml.gz  ch:extra-ch.xml.gz ...

Inputs are labelled with their default country ("own" = our own grab, country from the channel id suffix).
Rules
- a channel is kept only with programmes that are not over yet ("astrein": no empty channels)
- DACH only: own grab by country suffix de/at/ch; external guides by language of the programmes – German, or
  French/Italian only for Swiss channels (RTS, RSI, …) listed in data/channels.csv
- duplicates are found by the PROGRAMME, not by the name: two channels whose next 48 h are ≥ 85 % identical are one
  channel (HD/SD/UHD feeds, Austrian/Swiss copies with the same schedule, renamed channels like
  Sky Sport 1 → Sky Sport Top Event). Same name + clearly different schedule = two channels (both kept, told apart).
- per channel the source with the most programmes (with descriptions) wins; others only extend it after its last
  programme (more days ahead). All names of the merged channels stay as display names, so NOVA+ finds
  "VOX AT", "Sky Sport 1 HD", … by name; the id is the iptv-org database id where one is known.
- test/placeholder channels and radio are left out
"""
import csv, gzip, os, re, sys, time, unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

# --countries=de,at,ch,uk,us builds a guide for more countries (default: DACH)
ARGS = [a for a in sys.argv[1:] if not a.startswith("--countries=")]
COUNTRIES = next((a.split("=", 1)[1].lower().split(",") for a in sys.argv[1:] if a.startswith("--countries=")), ["de", "at", "ch"])
OUT, REPORT = ARGS[0], ARGS[1]
INPUTS = [a.split(":", 1) for a in ARGS[2:]]
LANG_OF = {"de": "de", "at": "de", "ch": "de", "uk": "en", "us": "en", "ie": "en", "ca": "en", "au": "en"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = time.time()
HORIZON = NOW + 48 * 3600          # fingerprint window
SIM = 0.8                          # share of matching programmes for "same channel"

NOISE = {"hd", "fhd", "uhd", "sd", "4k", "8k", "hq", "hevc", "raw", "1080p", "720p", "tv", "fernsehen", "channel", "de",
         "d", "at", "ch", "deutschland", "austria", "osterreich", "schweiz", "suisse", "svizzera", "germany", "plus1"}
DROP = re.compile(r"(?i)\b(test|testkanal|teststream|radio|webradio|audio only|backup)\b|\(pacific|pacific\)|pacific feed")

# Spellings of one name in the different guides
ALIAS = {"skyspoaustria": "skysportaustria", "skyaut": "skysportaustria", "skysportaustria1": "skysportaustria",
         "pro7": "prosieben", "pro7maxx": "prosiebenmaxx", "pro7fun": "prosiebenfun", "kabel1": "kabeleins",
         "kabel1doku": "kabeleinsdoku", "kabel1classics": "kabeleinsclassics", "k1": "kabeleins", "rtl2": "rtlzwei",
         "orfiii": "orf3", "atvii": "atv2", "pulsacht": "puls8", "qvczwei": "qvc2", "skyatlantik": "skyatlantic",
         "nationalgeographic": "natgeo", "nationalgeographicwild": "natgeowild", "dtmusikfernsehen": "dmf",
         "deutschesmusikfernsehen": "dmf", "esportsone": "esports1", "hoehenrausch": "hohenrausch", "servus": "servustv"}

def key(name):
    s = (name or "").lower().replace("ß", "ss").replace("&", " und ")
    s = re.sub(r"\+\s*(\d)", r" plus\1 ", s).replace("+", " plus ")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    s = re.sub(r"(?<=[a-z0-9])[.\-'](?=[a-z0-9])", "", s)
    k = "".join(t for t in re.split(r"[^a-z0-9]+", s) if t and t not in NOISE)
    return ALIAS.get(k, k)

def ts(v):
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", v or "")
    if not m:
        return None
    t = time.mktime(time.strptime(m.group(1), "%Y%m%d%H%M%S")) - time.timezone
    if m.group(2):
        sign = 1 if m.group(2)[0] == "+" else -1
        t -= sign * (int(m.group(2)[1:3]) * 3600 + int(m.group(2)[3:5]) * 60)
    return t

def open_any(path):
    with open(path, "rb") as f:
        gz = f.read(2) == b"\x1f\x8b"
    return gzip.open(path, "rb") if gz else open(path, "rb")

# iptv-org database: DACH ids by name (for clean ids) and Swiss channels (French/Italian ones are kept)
# per country, so "Discovery Channel" UK and US keep their own ids
db_by_key, db_name, swiss_keys = {}, {}, set()
for r in csv.DictReader(open(f"{ROOT}/data/channels.csv", encoding="utf-8")):
    cc = r["country"].lower()
    if cc not in COUNTRIES or r["closed"]:
        continue
    for n in [r["name"]] + [a for a in r["alt_names"].split(";") if a.strip()]:
        k = key(n)
        if k:
            db_by_key.setdefault((cc, k), r["id"])
            db_name.setdefault((cc, k), r["name"])
            if r["country"] == "CH":
                swiss_keys.add(k)

class Chan:
    __slots__ = ("src", "id", "names", "icon", "progs", "langs", "country")
    def __init__(self, src, cid):
        self.src, self.id, self.names, self.icon, self.progs, self.langs, self.country = src, cid, [], None, [], Counter(), None
    def score(self):
        n = len(self.progs)
        desc = sum(1 for p in self.progs if p[3]) / n if n else 0
        return n * (0.6 + 0.4 * desc)
    def fingerprint(self):
        return {(int(p[0] // 300), p[2]) for p in self.progs if p[0] < HORIZON}

def suffix(cid):
    stem = cid.split("@")[0]
    return stem.rsplit(".", 1)[-1].lower() if "." in stem else ""

chans = []
for label, path in INPUTS:
    cur = {}
    try:
        for _, el in ET.iterparse(open_any(path), events=("end",)):
            if el.tag == "channel":
                c = Chan(label, el.get("id"))
                c.names = [d.text.strip() for d in el.findall("display-name") if d.text and d.text.strip()]
                ic = el.find("icon")
                c.icon = ic.get("src") if ic is not None and ic.get("src") else None
                c.country = suffix(c.id) if label == "own" else label
                cur[c.id] = c
                el.clear()
            elif el.tag == "programme":
                c = cur.get(el.get("channel"))
                st, sp = ts(el.get("start")), ts(el.get("stop"))
                if c is not None and st is not None and (sp or st) > NOW:
                    t = el.find("title")
                    title = (t.text or "").strip() if t is not None else ""
                    if t is not None and t.get("lang"):
                        c.langs[t.get("lang").lower()[:2]] += 1
                    c.progs.append((st, sp or st, key(title)[:40], el.find("desc") is not None and bool((el.findtext("desc") or "").strip()),
                                    ET.tostring(el, encoding="unicode").strip()))
                el.clear()
    except (ET.ParseError, OSError, EOFError) as e:
        print(f"WARN {path}: {e}", file=sys.stderr)
    for c in cur.values():
        if not c.names:
            c.names = [re.sub(r"\.[a-z]{2}\d?$", "", c.id).replace(".", " ")]
        if not c.progs or DROP.search(" ".join(c.names)):
            continue
        k = key(c.names[0])
        if label == "own":
            if c.country not in COUNTRIES:
                continue
        else:
            lang = c.langs.most_common(1)[0][0] if c.langs else "de"
            # epg.pw marks titles with wrong languages; its German file counts as German.
            if label == "de" and path.find("epg_DE") >= 0:
                lang = "de"
            if lang != LANG_OF.get(label, "de") and not (label == "ch" and lang in ("fr", "it") and k in swiss_keys):
                continue
        chans.append(c)
    print(f"{label:4s} {os.path.basename(path)}: {sum(1 for c in chans if c.src == label)} Sender mit Daten")

# ---- clustering: union-find over (same name with compatible schedule) and (≥ SIM identical schedule)
parent = list(range(len(chans)))
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]; i = parent[i]
    return i
# Brands that are never one channel, even when a guide mislabels one with the other's schedule.
APART = [({"hse", "hseextra", "hsetrend"}, {"hope", "hopechannel", "hopechanneldeutsch", "hopechannelgerman"}),
         ({"sport1plus"}, {"sportdigital1plus", "sportdigital"}, {"orfsport1plus", "orfsportplus"}),
         ({"eo"}, {"morethansports"}),
         ({"skysportaustria", "skysportaustria1", "skyaut", "skyspoaustria"}, {"skysport", "skysportuhd", "skysportnews"}),
         ({"sport1"}, {"esports1", "esportsone"})]
ckeys = None                           # root -> name keys of the cluster (filled once chans exist)
def union(a, b):
    a, b = find(a), find(b)
    if a == b:
        return
    for groups in APART:
        ga = {n for n, g in enumerate(groups) if g & ckeys[a]}
        gb = {n for n, g in enumerate(groups) if g & ckeys[b]}
        if ga and gb and ga != gb:
            return
    parent[b] = a
    ckeys[a] |= ckeys[b]

ckeys = [{key(n) for n in c.names[:3]} for c in chans]

# Schedules as (start, title prefix) in the next 48 h. Two programmes are "the same" if they start within
# 10 minutes of each other and their titles begin alike – sources differ by a minute or a subtitle.
win = [sorted((p[0], p[2][:6]) for p in c.progs if p[0] < HORIZON and p[2]) for c in chans]
def ratio(i, j, titles=True):
    a, b = win[i], win[j]
    if len(a) > len(b):
        a, b = b, a
    if len(a) < 6:
        return None
    m = k0 = 0
    for st, t in a:
        while k0 < len(b) and b[k0][0] < st - 600:
            k0 += 1
        k = k0
        while k < len(b) and b[k][0] <= st + (600 if titles else 180):
            if not titles or b[k][1] == t:
                m += 1
                break
            k += 1
    return m / len(a)

# 1. same name: one channel unless the programme start times clearly contradict each other (sources differ in
#    titles – series vs. episode title – but not in start times). Compared with every member already joined.
by_key = defaultdict(list)
for i, c in enumerate(chans):
    for n in c.names[:3]:
        k = key(n)
        if k and i not in by_key[k]:
            by_key[k].append(i)
def same_name_ok(i, j):
    a, b = chans[i], chans[j]
    if a.src != b.src and a.country == b.country:
        return True                    # one channel seen by two guides
    if LANG_OF.get(a.country) != LANG_OF.get(b.country):
        r = ratio(i, j)                # other language: only with the same titles (practically never)
        return r is not None and r >= 0.6
    if a.country != b.country and not ({a.country, b.country} <= {"de", "at", "ch"}):
        r = ratio(i, j)                # UK vs US "National Geographic": same language, different channel
        return r is not None and r >= 0.6
    r = ratio(i, j, titles=False)
    return r is None or r >= (0.3 if a.src != b.src else 0.5)
for k, idx in by_key.items():
    idx = sorted(idx, key=lambda i: -chans[i].score())
    for x, j in enumerate(idx[1:], 1):
        hit = next((i for i in idx[:x] if same_name_ok(i, j)), None)
        if hit is not None:
            union(hit, j)

# 1b. our own grab: feeds of one channel (ARD.de@SD, ARD.de@HD …) are one channel
stem = defaultdict(list)
for i, c in enumerate(chans):
    if c.src == "own":
        stem[c.id.split("@")[0]].append(i)
for idx in stem.values():
    for j in idx[1:]:
        union(idx[0], j)

def digits(c):
    return {frozenset(re.findall(r"\d+", n)) for n in c.names[:3] if re.search(r"\d", n)}

# 2. different names, same programme (HD/SD feeds, copies, renamed channels): candidates via a coarse index,
#    confirmed with the tolerant comparison. Generic titles ("Unsere Highlights", "Sendepause", "Session") that
#    run on many channels prove nothing and are left out of this comparison.
spread = defaultdict(set)
for i, w_ in enumerate(win):
    for _, t in w_:
        spread[t].add(find(i))
win = [[(st, t) for st, t in w_ if len(spread[t]) <= 6] for w_ in win]
index = defaultdict(set)
for i, w_ in enumerate(win):
    for st, t in w_:
        index[(int(st // 1800), t)].add(i)
pairs = Counter()
for item, idx in index.items():
    if len(idx) > 40:                  # e.g. "Sendepause" at the same time on many channels
        continue
    idx = sorted(idx)
    for x in range(len(idx)):
        for y in range(x + 1, len(idx)):
            pairs[(idx[x], idx[y])] += 1
for (i, j), n in pairs.items():
    if find(i) == find(j) or n < 6:
        continue
    # Event channels (blue Sport 1 … 25, DAZN 1/2, Sky Sport 1 … 10) share placeholder schedules: numbered
    # channels are only merged with the same number.
    di, dj = digits(chans[i]), digits(chans[j])
    if di and dj and not (di & dj):
        continue
    r = ratio(i, j)
    if r is not None and r >= SIM:
        # confirm with the strongest member of each side, so a mislabelled feed cannot chain two channels
        bi = max((x for x in range(len(chans)) if find(x) == find(i)), key=lambda x: chans[x].score()) if find(i) != i else i
        bj = max((x for x in range(len(chans)) if find(x) == find(j)), key=lambda x: chans[x].score()) if find(j) != j else j
        rb = ratio(bi, bj) if (bi, bj) != (i, j) else r
        if rb is None or rb >= SIM:
            union(i, j)

clusters = defaultdict(list)
for i in range(len(chans)):
    clusters[find(i)].append(chans[i])

# ---- one channel per cluster
out_ids, rows = set(), []
w = gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9)
w.write(f'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="nova-epg {"-".join(COUNTRIES)}">\n')
# Countries in the order given win the plain names: with --countries=de,at,ch,uk,us the German "National
# Geographic" keeps its name and the British one becomes "National Geographic UK" – NOVA+ matches by name
# after removing "DE:"/"UK |" prefixes, so equal names in two countries would give one of them the wrong guide.
DACH = {"de", "at", "ch"}
def rank(members):
    return min((COUNTRIES.index(c.country) if c.country in COUNTRIES else 99) for c in members)
records, used_names, used_keys = [], set(), set()
for members in sorted(clusters.values(), key=lambda m: (min(rank(m), 3 if rank(m) < 3 else rank(m)), -max(c.score() for c in m))):
    members.sort(key=lambda c: -c.score())
    best = members[0]
    names = []
    for c in members:
        for n in c.names:
            if n not in names:
                names.append(n)
    # name + id: the iptv-org database entry if one of the names is known there (clean spelling, the id playlists
    # carry as tvg-id), our own grab's id only if it really names this channel (the grab has mislabelled feeds)
    mkeys = []
    for c in members:
        for n in c.names:
            k = key(n)
            if k and k not in mkeys:
                mkeys.append(k)
    # database lookup in the channel's country first, then in the countries of the same language (3sat seen
    # by the Austrian guide is still the German 3sat entry)
    group = [best.country] + [c for c in COUNTRIES if c != best.country and LANG_OF.get(c) == LANG_OF.get(best.country)]
    dbk = next(((cc, k) for cc in group for k in mkeys if (cc, k) in db_by_key and db_by_key[(cc, k)] not in out_ids), None)
    def id_key(cid):
        return key(re.sub(r"\.[a-z]{2}\d?$", "", cid.split("@")[0]).replace(".", " "))
    own = next((c for c in members if c.src == "own" and id_key(c.id) in mkeys), None)
    cands = ([own.id] if own else []) + ([db_by_key[dbk]] if dbk else []) + [c.id for c in members]
    cid = next((x for x in cands if x and x not in out_ids), None) or f"{best.id}.{len(out_ids)}"
    pretty = db_name[dbk] if dbk else next((n for n in best.names if not n.isupper()), best.names[0])
    if best.country not in DACH:
        tag = " " + best.country.upper()
        names = [n + tag if key(n) in used_keys else n for n in names]
        if key(pretty) in used_keys:
            pretty += tag
    if pretty in used_names:          # two channels must not look alike in the list
        pretty = next((n for n in best.names + names if n not in used_names), f"{pretty} ({best.country or 'DACH'})")
    used_names.add(pretty)
    used_keys.update(key(n) for n in [pretty] + names)
    seen_n = {pretty.lower()}
    names = [pretty] + [n for n in names if not (n.lower() in seen_n or seen_n.add(n.lower()))]
    out_ids.add(cid)
    progs = sorted(best.progs)
    last = progs[-1][1] if progs else 0
    extended = []
    for c in members[1:]:
        more = [p for p in sorted(c.progs) if p[0] >= last]
        if more:
            progs += more; last = more[-1][1]; extended.append(c.src)
    records.append((pretty, cid, names, best.icon or next((c.icon for c in members if c.icon), None), progs, best, members, extended))

records.sort(key=lambda r: key(r[0]))
for name, cid, names, icon, progs, best, members, extended in records:
    w.write(f'  <channel id="{ET.Element("x", v=cid).get("v").replace("&", "&amp;").replace(chr(34), "&quot;")}">\n')
    for n in names[:12]:
        w.write(f'    <display-name lang="de">{n.replace("&", "&amp;").replace("<", "&lt;")}</display-name>\n')
    if icon:
        w.write(f'    <icon src="{icon.replace("&", "&amp;").replace(chr(34), "&quot;")}" />\n')
    w.write("  </channel>\n")
for name, cid, names, icon, progs, best, members, extended in records:
    seen = set()
    for p in progs:
        if p[0] in seen:
            continue
        seen.add(p[0])
        el = ET.fromstring(p[4]); el.set("channel", cid)
        w.write("  " + ET.tostring(el, encoding="unicode").strip() + "\n")
    days = (progs[-1][1] - NOW) / 86400 if progs else 0
    rows.append(f"{name}\t{cid}\t{best.src}{'+' + ','.join(sorted(set(extended))) if extended else ''}\t{len(seen)}\t{days:.1f}\t"
                + "; ".join(f"{c.src}:{c.names[0]}" for c in members[1:]))
w.write("</tv>\n"); w.close()

merged = sum(len(r[6]) - 1 for r in records)
with open(REPORT, "w", encoding="utf-8") as f:
    f.write(f"# Guide {'/'.join(c.upper() for c in COUNTRIES)} {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(NOW))}: {len(records)} Sender, {merged} Dubletten zusammengeführt\n")
    f.write("Sender\tID\tQuelle\tSendungen\tTage voraus\tzusammengeführt mit\n")
    f.write("\n".join(rows) + "\n")
print(f"{'/'.join(c.upper() for c in COUNTRIES)}: {len(records)} Sender mit Programm, {merged} Dubletten zusammengeführt, {sum(len(r[4]) for r in records)} Sendungen")
