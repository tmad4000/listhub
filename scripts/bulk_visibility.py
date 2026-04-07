#!/usr/bin/env python3
"""Bulk visibility update + tag unlisted-intent items on ListHub."""
import json
import time
import urllib.error
import urllib.request

API_BASE = "https://listhub.globalbr.ai/api/v1"
TOKEN = "ec5107d6eb59357642976d61aafad1ad"
USERNAME = "jacobreal"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "X-ListHub-User": USERNAME,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 listhub-bulk-visibility",
}

MAKE_PUBLIC = [
    "adhd", "aieducation", "aspirations", "autodidacts", "bookslist",
    "buoyantfitness", "burningman",
    "chronicpain-backpain", "chronicpain-chronicpain", "chronicpain-si",
    "chronicpain-sijointpain", "chronicpain-sleep",
    "climatechange", "coronavirus", "covid19hackideas", "cryptoconnect",
    "culturalendangeredspecies", "culturaltechnology", "existentialcrisis",
    "foodslist-cheese", "foodslist-chocolate", "foodslist-tea",
    "healingartsgrant", "hiringlist", "hypnosis",
    "ideaflow-gestaltexplanation", "ideaflow-ifiran", "ideaflowbackground",
    "ideaflowproject",
    "infrastructure-codex", "infrastructure-infrastructure", "infrastructure-templates",
    "kidactivities", "lifechange", "lifechangingthings",
    "manifestos-perfectcoordination", "manifestos-visioncharter",
    "misc-commentaries", "misc-easilysolvableworldproblems",
    "misc-ilparty", "misc-lists", "misc-socialsupportforregenerativefarmers",
    "nvc",
    "philosophy-ethicaldilemmas", "philosophy-heidegger",
    "philosophy-philosophy", "philosophy-yogalist",
    "products", "pureland", "qigongcrew", "qiresearch", "questions",
    "quoteslist", "shadirecs", "stanfordclasses", "startupideas",
    "startuptrickswiki", "supplements", "systematicawesome",
    "thingsyoudidntknowexisted-thingsyoudidntknowexisted",
    "thingsyoudidntknowexisted-thingsyoudidntknowexistedatmit",
    "thingsyoudidntknowexisted-thingsyoudidntknowexistedinhawaii",
    "thingsyoudidntknowexisted-thingsyoudidntknowexistedinnyc",
    "thingsyoudidntknowexisted-thingsyoudidntknowexistedinportland",
    "thingsyoudidntknowexisted-thingsyoudidntknowexistedinsantacruz",
    "thingsyoudidntknowexisted-thingsyoudidntknowexistedinsf",
    "thingsyoudidntknowexisted-thingyoudidntknowexistedinsandiego",
    "thoughtfulweb", "toolstacks",
    "worldgestalts-globalideabank", "worldgestalts-worldgestalts",
    "worldproblems", "worldquestguild-salon", "worldquestguild-vrcoralreefs",
]

# Stay private, but tag so we can flip to unlisted when the feature ships
UNLISTED_INTENT = ["circuits", "misc-housinglist", "worldquestguild-favorverse"]


def api_get(path):
    req = urllib.request.Request(f"{API_BASE}{path}", headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_put(path, payload):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(payload).encode(),
        headers=HEADERS,
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())


print(f"== Making {len(MAKE_PUBLIC)} items public ==")
public_ok, public_err = 0, 0
for slug in MAKE_PUBLIC:
    try:
        code, item = api_put(f"/items/by-slug/{slug}", {"visibility": "public"})
        print(f"  ✓ {slug:60s} {item.get('visibility')}")
        public_ok += 1
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:120]
        print(f"  ✗ {slug:60s} HTTP {e.code}: {body}")
        public_err += 1
    except Exception as e:
        print(f"  ✗ {slug:60s} EXC: {e}")
        public_err += 1
    time.sleep(0.05)

print()
print(f"== Tagging {len(UNLISTED_INTENT)} items with unlisted-intent ==")
unlisted_ok, unlisted_err = 0, 0
for slug in UNLISTED_INTENT:
    try:
        item = api_get(f"/items/by-slug/{slug}")
        existing_tags = list(item.get("tags", []))
        if "unlisted-intent" not in existing_tags:
            existing_tags.append("unlisted-intent")
        code, updated = api_put(f"/items/by-slug/{slug}", {
            "tags": existing_tags,
            "visibility": "private",
        })
        print(f"  ✓ {slug:60s} tags: {existing_tags}")
        unlisted_ok += 1
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:120]
        print(f"  ✗ {slug:60s} HTTP {e.code}: {body}")
        unlisted_err += 1
    except Exception as e:
        print(f"  ✗ {slug:60s} EXC: {e}")
        unlisted_err += 1
    time.sleep(0.05)

print()
print("=" * 80)
print(f"PUBLIC            : {public_ok}/{len(MAKE_PUBLIC)} ok ({public_err} errors)")
print(f"UNLISTED-INTENT   : {unlisted_ok}/{len(UNLISTED_INTENT)} ok ({unlisted_err} errors)")
