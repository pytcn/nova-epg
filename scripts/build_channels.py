#!/usr/bin/env python3
"""Builds channels/shard*.xml from data/channels.csv (iptv-org/database) and the site lists of iptv-org/epg.

  python3 scripts/build_channels.py /path/to/iptv-org/epg

Rules
- one source per channel (no duplicates); only sites marked working (🟢) in SITES.md
- excluded countries: Russia, China, Japan, Africa and the Balkans (region lists from data/regions.csv; Turkey kept)
- sky.com, dazn.com and www.magenta.tv are included completely: their channels without xmltv_id are linked to
  the database by name, otherwise they get a readable id like "DAZN2.de"
- preferred sources for DE/AT/CH: German-language EPG providers; elsewhere a provider from the channel's country
- sites without any programme in a test run are avoided; channels that only exist there are left out
"""
import csv, glob, os, re, sys, unicodedata
from collections import Counter, defaultdict

EPG = sys.argv[1] if len(sys.argv) > 1 else "../iptv-org/epg"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARDS = 8

regions = {r["code"]: set(r["countries"].split(";")) for r in csv.DictReader(open(f"{ROOT}/data/regions.csv", encoding="utf-8"))}
EXCLUDED = {"RU", "CN", "JP"} | regions["AFR"] | (regions["BALKAN"] - {"TR"})
DACH = {"DE", "AT", "CH"}
PREF_DACH = ["web.magentatv.de", "www.magenta.tv", "tv.blue.ch", "tvheute.at", "sky.com", "dazn.com", "neo.io", "pluto.tv", "i.mjh.nz"]
EXTRA_SITES = {"sky.com", "dazn.com", "www.magenta.tv"}           # included completely, also without xmltv_id
NO_DATA = {"berrymedia.co.kr", "chaines-tv.orange.fr", "clickthecity.com", "digiturk.com.tr", "distro.tv", "dsmart.com.tr", "ena.skylifetv.co.kr", "foxsports.com.au", "galamtv.kz", "m.tv.sms.cz", "m.tving.com", "magticom.ge", "mediagenie.co.kr", "meuguia.tv", "musor.tv", "nuevosiglo.com.uy", "playtv.unifi.com.my", "programme-tv.vini.pf", "programtv.onet.pl", "sat.tv", "superguidatv.it", "tapdmv.com", "teleboy.ch", "turksatkablo.com.tr", "tv.lv", "tv.mail.ru", "tvcesoir.fr", "tvcubana.icrt.cu", "tvmi.mt", "tvmusor.hu", "v3.myafn.dodmedia.osd.mil", "walesi.com.fj", "watch.sportsnet.ca", "wavve.com", "zap.co.ao"}  # no programme at all in the test runs of 2026-11-01
LANG_COUNTRY = {"de": "DE", "it": "IT", "es": "ES", "fr": "FR", "pt": "PT", "nl": "NL", "en": "UK", "ja": "JP", "zh": "CN"}
SKY_PREFIX = {"DE": "DE", "GB": "UK", "IT": "IT"}

NOISE = {"hd", "fhd", "uhd", "sd", "4k", "8k", "hq", "lq", "hevc", "h265", "h264", "raw", "1080p", "720p", "576p", "540p", "480p",
         "50fps", "60fps", "fullhd", "backup", "live", "tv", "fernsehen", "channel", "de"}

def tokens(name):
    s = name.lower().replace("ß", "ss").replace("&", " und ")
    s = re.sub(r"\+\s*(\d)", r" plus\1 ", s).replace("+", " plus ")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    s = re.sub(r"(?<=[a-z0-9])[.\-'](?=[a-z0-9])", "", s)
    return [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in NOISE]

def key(name):
    return "".join(tokens(name))

status, size = {}, {}
for m in re.finditer(r'<td><a href="sites/([^"]+)">[^<]*</a></td><td align="right">(\d+)</td><td align="center">([^<]*)</td>',
                     open(f"{EPG}/SITES.md", encoding="utf-8").read()):
    status[m.group(1)] = m.group(3).strip(); size[m.group(1)] = int(m.group(2))

rows = {r["id"]: r for r in csv.DictReader(open(f"{ROOT}/data/channels.csv", encoding="utf-8"))}
by_name = defaultdict(set)          # (country, key) -> ids
for r in rows.values():
    if r["closed"]:
        continue
    for n in [r["name"]] + [a for a in r["alt_names"].split(";") if a.strip()]:
        k = key(n)
        if k:
            by_name[(r["country"], k)].add(r["id"])

rx = re.compile(r"<channel\s+([^>]*)>(.*?)</channel>")
attr = re.compile(r'(\w+)="([^"]*)"')

def camel(name):
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", unicodedata.normalize("NFKD", name)) if w) or "Channel"

cands = defaultdict(list)
synthetic = 0
for f in sorted(glob.glob(f"{EPG}/sites/*/*.channels.xml")):
    site = f.split("/")[-2]
    if status.get(site) != "🟢":
        continue
    for m in rx.finditer(open(f, encoding="utf-8").read()):
        a = dict(attr.findall(m.group(1))); name = m.group(2)
        xid = a.get("xmltv_id", "")
        if xid:
            stem = xid.split("@")[0]
            r = rows.get(stem)
            if not r or r["closed"]:
                continue
            country = r["country"]
        elif site in EXTRA_SITES:
            if site == "sky.com":
                country = SKY_PREFIX.get(a["site_id"].split("#")[0])
            else:
                country = LANG_COUNTRY.get(a.get("lang", ""))
            if not country:
                continue
            ids = by_name.get((country, key(name)), set())
            if len(ids) == 1:
                stem = next(iter(ids)); xid = stem
            else:
                stem = f"{camel(name)}.{country.lower()}"; xid = stem; synthetic += 1
            a = dict(a, xmltv_id=xid)
        else:
            continue
        if country in EXCLUDED:
            continue
        tld = site.split(".")[-1]
        rank = (1 if site in NO_DATA else 0,)
        rank += ((PREF_DACH.index(site) if site in PREF_DACH else 50),) if country in DACH else ((0 if tld == country.lower() else 1 if site not in EXTRA_SITES else 0),)
        rank += (0 if (country not in DACH or a.get("lang") == "de") else 1, -size.get(site, 0), 0 if xid.endswith("@SD") or "@" not in xid else 1)
        cands[(country, stem)].append((rank, a, name))

# one source per channel; channels whose only sources delivered nothing are left out (they only cost time)
chosen = {k: sorted(v, key=lambda x: x[0])[0] for k, v in cands.items()}
dropped_no_data = [k for k, v in chosen.items() if v[1]["site"] in NO_DATA]
for k in dropped_no_data:
    chosen.pop(k)

# duplicate check: a channel from sky.com / dazn.com / www.magenta.tv without database id whose name equals a
# channel already in the list (same country) is the same channel -> keep the one with the database id.
# Different database ids are never merged (the database says they are different channels).
known = {}
for (country, stem), (rank, a, name) in chosen.items():
    if stem in rows:
        for n in [name, rows[stem]["name"]] + [x for x in rows[stem]["alt_names"].split(";") if x.strip()]:
            if key(n):
                known.setdefault((country, key(n)), (country, stem))
dupes = []
for (country, stem), (rank, a, name) in list(chosen.items()):
    if stem in rows:
        continue
    k = (country, key(name))
    if k in known:
        dupes.append(((country, stem), known[k], name))
        chosen.pop((country, stem))
# same stream twice (same site + site_id under two ids)
seen = {}
for (country, stem), (rank, a, name) in sorted(chosen.items(), key=lambda kv: kv[0][1] not in rows):
    sk = (a["site"], a["site_id"])
    if sk in seen:
        dupes.append(((country, stem), seen[sk], name)); chosen.pop((country, stem))
    else:
        seen[sk] = (country, stem)

# shards: balanced by channel count, one site stays in one shard (no parallel load on a site)
by_site = defaultdict(list)
for (country, stem), (rank, a, name) in chosen.items():
    by_site[a["site"]].append((a, name))
shards = [[] for _ in range(SHARDS)]; load = [0] * SHARDS
for site, items in sorted(by_site.items(), key=lambda kv: -len(kv[1])):
    i = load.index(min(load)); shards[i] += items; load[i] += len(items)
os.makedirs(f"{ROOT}/channels", exist_ok=True)
for f in glob.glob(f"{ROOT}/channels/*.xml"):
    os.remove(f)
for i, sh in enumerate(shards, 1):
    sh.sort(key=lambda x: (x[0]["site"], x[1].lower()))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<channels>"]
    lines += ['  <channel site="%s" lang="%s" xmltv_id="%s" site_id="%s">%s</channel>' % (a["site"], a.get("lang", ""), a["xmltv_id"], a["site_id"], n) for a, n in sh]
    lines.append("</channels>")
    open(f"{ROOT}/channels/shard{i}.xml", "w", encoding="utf-8").write("\n".join(lines) + "\n")

countries = Counter(c for c, _ in chosen)
print(f"channels: {len(chosen)} (synthetic ids: {synthetic}, duplicates removed: {len(dupes)}, without working source: {len(dropped_no_data)})")
print("shards:", load)
print("DACH:", sum(countries[c] for c in DACH), "| top:", countries.most_common(12))
print("per extra site:", {s: len(by_site.get(s, [])) for s in sorted(EXTRA_SITES)})
print("excluded countries present in list:", sorted(set(countries) & EXCLUDED))
for d, keep, name in dupes[:15]:
    print("  dup removed:", d, "kept", keep, "-", name)
