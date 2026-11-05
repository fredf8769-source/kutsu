"""KUTSU 靴 — поиск лучших цен на оригинальные кроссовки в Украине и Европе.
Запуск:  python server.py   →  http://localhost:8787
Только стандартная библиотека Python, ничего ставить не нужно.
"""
import json, re, time, html, sys, os, statistics, urllib.request, urllib.parse, urllib.error
import concurrent.futures as cf
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from generic import extract, classify, CATS

PORT = int(os.environ.get("PORT", 8787))
ROOT = Path(__file__).parent / "static"
if not (ROOT / "index.html").exists():          # если index.html загрузили в корень (например, на GitHub без папки static)
    ROOT = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "uk,en;q=0.8"}
POOL = cf.ThreadPoolExecutor(48)
CACHE = {}          # query -> (time, result)
CACHE_TTL = 1800
RATES = {"t": 0, "UAH": 1.0, "EUR": 48.0, "GBP": 56.0, "USD": 41.5, "SEK": 4.4, "DKK": 6.4, "CHF": 51.0, "PLN": 11.2}

# ── Уровни доверия ──────────────────────────────────────────────────────────
# official  — официальный ритейлер / магазин бренда / известный европейский бутик
# boutique  — украинский магазин оригиналов, независимых отзывов мало
# warning   — есть массовые жалобы на подделки (по независимым отзывам)
# market    — маркетплейс / частные продавцы: показываем только то, что прошло проверку цены
TRUST = {
    "official": "Официальный ритейлер",
    "boutique": "Магазин оригиналов",
    "warning": "Есть жалобы на подделки",
    "market": "Маркетплейс: проверено по цене",
}

# ── Украина ─────────────────────────────────────────────────────────────────
# {q} — запрос через %20, {p} — через «+»
UA_SHOPS = [
    ("MEGASPORT", "official", "https://megasport.ua/ua/search/?sq={q}"),
    ("Sportano", "official", "https://sportano.ua/catalogsearch/result/?q={q}"),
    ("New Balance UA", "official", "https://newbalance.ua/store?s={p}"),
    ("WERARE", "boutique", "https://werare.com.ua/index.php?route=product/search&search={q}"),
    ("Sneakers Banda", "boutique", "https://sneakersbanda.ua/index.php?route=product/search&search={q}"),
    ("Original Store", "boutique", "https://originalstore.com.ua/uk/search?search_query={p}&orderby=position&orderway=desc"),
    ("1310", "boutique", "https://www.1310.com.ua/?s={p}&post_type=product"),
    ("Merrell UA", "official", "https://merrell.ua/catalogsearch/result/?q={q}"),
    # vidhuk.ua: 2.8/5 по 627 отзывам, много жалоб «продали подделку»
    ("YES Original", "warning", "https://yesoriginal.com.ua/index.php?route=product/search&search={q}"),
]

# ── Европа: магазины на Shopify, у всех одинаковый открытый поиск ───────────
# (название, домен, страна, mixed) — mixed=True: магазин продаёт и одежду, берём только то, что точно обувь
EU_SHOPS = [
    # мультибрендовые сникер-шопы
    ("afew", "afew-store.com", "Германия", False),
    ("Overkill", "www.overkillshop.com", "Германия", False),
    ("Asphaltgold", "www.asphaltgold.com", "Германия", False),
    ("STOY", "www.stoy.com", "Германия", True),
    ("Kith EU", "eu.kith.com", "Европа", True),
    ("Patta", "www.patta.nl", "Нидерланды", True),
    ("Sneakersnstuff", "www.sneakersnstuff.com", "Швеция", False),
    ("Très Bien", "www.tres-bien.com", "Швеция", True),
    ("Naked", "www.nakedcph.com", "Дания", True),
    ("SlamJam", "www.slamjam.com", "Италия", True),
    ("One Block Down", "www.oneblockdown.it", "Италия", True),
    ("Antonioli", "www.antonioli.eu", "Италия", True),
    ("Footdistrict", "www.footdistrict.com", "Испания", False),
    ("The Next Door", "www.thenextdoor.fr", "Франция", False),
    ("Urban Jungle", "www.urbanjunglestore.com", "Европа", False),
    ("END.", "www.endclothing.com", "Великобритания", True),
    ("Footpatrol", "www.footpatrol.com", "Великобритания", False),
    ("Goodhood", "www.goodhoodstore.com", "Великобритания", True),
    ("Oi Polloi", "www.oipolloi.com", "Великобритания", True),
    ("Urban Industry", "www.urbanindustry.co.uk", "Великобритания", True),
    # официальные магазины брендов (EU-версии)
    ("Karhu", "www.karhu.com", "Финляндия", True),
    ("Salming", "www.salming.com", "Швеция", True),
    ("Satisfy", "www.satisfyrunning.com", "Франция", True),
    ("Le Coq Sportif", "www.lecoqsportif.com", "Франция", True),
    ("Kappa", "www.kappa.com", "Италия", True),
    ("Lotto", "www.lotto.it", "Италия", True),
    ("Diemme", "www.diemme.com", "Италия", False),
    ("Premiata", "www.premiata.it", "Италия", True),
    ("Sebago", "www.sebago.com", "Италия", True),
    ("Hummel", "www.hummel.net", "Дания", True),
    ("Last Resort AB", "www.lastresortab.com", "Швеция", True),
    ("Ghōud", "www.ghoud.com", "Италия", True),
    ("Mason Garments", "www.masongarments.com", "Испания", True),
    ("Wildling", "www.wildling.shoes", "Германия", True),
    ("Blundstone", "www.blundstone.co.uk", "Великобритания", True),
    ("Stepney Workers Club", "www.stepneyworkersclub.com", "Великобритания", True),
]
FOOT = re.compile(r"sneaker|shoe|trainer|boot|sandal|slide|runner|running|clog|mule|loafer|footwear|derby|oxford|moccasin|"
                  r"slipper|espadrill|schuh|chaussure|basket|scarpe|calzatur|zapatill|calzado|\bsko\b|skor\b|kengät|"
                  r"\b(low|high|mid)\b|\bmax\b|\bdunk\b|\bforce\b|\bsamba\b|\bgazelle\b|\bcampus\b|\b\d{3,4}v?\d?\b", re.I)

REPLICA = re.compile(r"репл[іи]к|копі[яї]|копи[яи]|\b1\s*[:в]\s*1\b|\blux\b|люкс|в['’]?[єе]тнам|vietnam|топ як[іо]ст|топ качеств|"
                     r"\baaa\b|premium quality|не ориг|оригінальна якість|качество оригинал|fake|\breplica", re.I)


BACKOFF = {}   # host -> до какого времени не обращаемся (магазин попросил притормозить: HTTP 429)


def fetch(url, timeout=12):
    host = urllib.parse.urlparse(url).netloc
    if BACKOFF.get(host, 0) > time.time():
        raise RuntimeError("пауза после 429")
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            retry = e.headers.get("Retry-After")
            BACKOFF[host] = time.time() + (int(retry) if retry and retry.isdigit() else 600)
        raise


def rates():
    """Курсы НБУ (все валюты), обновляются раз в 6 часов."""
    if time.time() - RATES["t"] < 6 * 3600:
        return RATES
    try:
        for row in json.loads(fetch("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json", 8)):
            RATES[row["cc"]] = float(row["rate"])
        RATES["t"] = time.time()
    except Exception as e:
        print("курс НБУ недоступен:", e, file=sys.stderr)
    return RATES


# как бренд называют в магазинах, если это отличается от названия на кнопке
ALIASES = {"on running": "on", "hoka one one": "hoka", "dr. martens": "dr martens", "dr martens": "martens",
           "vibram fivefingers": "fivefingers", "arc'teryx": "arcteryx", "ghoud": "ghōud", "361°": "361",
           "the north face": "north face", "le coq sportif": "coq sportif", "stepney workers club": "stepney",
           "last resort ab": "last resort", "onitsuka tiger": "onitsuka", "hoka ora": "ora recovery"}


def norm(s):
    return re.sub(r"[’'`.]", "", s.lower())


def relevant(text, q):
    t = norm(text)
    for w in re.findall(r"\w+", norm(q)):
        if len(w) <= 1:
            continue
        if len(w) <= 3:
            if not re.search(rf"\b{re.escape(w)}\b", t):
                return False
        elif w not in t:
            return False
    return True


def item(**kw):
    kw.setdefault("old_price", None)
    kw.setdefault("note", "")
    return kw


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        print(f"{getattr(fn, '__name__', fn)}: {e}", file=sys.stderr)
        return None


# ── источники ───────────────────────────────────────────────────────────────
def make_generic(name, trust, tpl):
    def src(q):
        url = tpl.format(q=urllib.parse.quote(q), p=urllib.parse.quote_plus(q))
        return [item(store=name, trust=trust, currency="UAH", country="Украина", **it)
                for it in extract(fetch(url, 15), url, q)]
    src.__name__ = name
    return src


SHOP_CUR = {}   # host -> (time, валюта витрины); Shopify показывает цены в валюте страны покупателя


def shop_currency(host):
    c = SHOP_CUR.get(host)
    if c and time.time() - c[0] < 24 * 3600:     # валюта витрины меняется редко — не дёргаем магазин лишний раз
        return c[1]
    cur = json.loads(fetch(f"https://{host}/cart.js", 8)).get("currency") or "EUR"
    SHOP_CUR[host] = (time.time(), cur)
    return cur


def make_shopify(name, host, country, mixed):
    def src(q):
        qs = urllib.parse.quote(q)
        data = json.loads(fetch(f"https://{host}/search/suggest.json?q={qs}&resources[type]=product&resources[limit]=10"))
        cur = shop_currency(host)
        out = []
        for p in data["resources"]["results"]["products"]:
            if not p.get("available", True):
                continue
            kind = str(p.get("type", ""))
            tags = " ".join(str(t) for t in (p.get("tags") or []))
            # теги у магазинов часто общие («sneakers» на всей коллекции) — для смешанных магазинов смотрим только название и тип
            default = "shoes" if (not mixed or FOOT.search(p["title"] + " " + kind)) else "apparel"
            cat = classify(p["title"], kind, default)
            price = float(p["price"])
            old = float(p.get("compare_at_price_max") or 0)
            url = p["url"] if p["url"].startswith("http") else f"https://{host}{p['url'].split('?')[0]}"
            out.append(item(store=name, trust="official", title=p["title"], vendor=str(p.get("vendor", "")), cat=cat,
                            price=price, currency=cur,
                            old_price=old if old > price else None, url=url,
                            image=p.get("image") or "", country=country))
        return out
    src.__name__ = name
    return src


UA_SOURCES = [(n, make_generic(n, tr, t)) for n, tr, t in UA_SHOPS]
EU_SOURCES = [(n, make_shopify(n, h, co, mx)) for n, h, co, mx in EU_SHOPS]


# ── проверка на оригинал ────────────────────────────────────────────────────
def check(items):
    """Сравниваем каждую цену с медианой официальных магазинов по этому же запросу.
    Оригинал редко продают дешевле 45% от типичной цены — такое помечаем как вероятную подделку."""
    shoes = [i for i in items if i.get("cat") == "shoes"]
    ref_pool = [i["price_uah"] for i in shoes if i["trust"] == "official" and not i.get("kids")]
    ref = statistics.median(ref_pool) if len(ref_pool) >= 3 else None
    for i in items:
        flags = []
        if i.get("cat") != "shoes":          # носки, одежду и аксессуары с ценой кроссовок не сравниваем
            i["flags"] = []
            i["verdict"] = "caution" if i["trust"] == "warning" else "ok"
            continue
        if REPLICA.search(i["title"] + " " + i.get("note", "")):
            flags.append("в описании признаки реплики")
        # официальные ритейлеры продают оригинал даже на распродаже — их по цене не судим
        if ref and not i.get("kids") and i["trust"] != "official":
            ratio = i["price_uah"] / ref
            i["ratio"] = round(ratio, 2)
            if ratio < 0.45:
                flags.append(f"цена на {round((1 - ratio) * 100)}% ниже рынка")
            elif ratio < 0.6 and i["trust"] in ("market", "warning"):
                flags.append("подозрительно дёшево для частного продавца")
        if i["trust"] == "market" and ref is None:
            flags.append("не с чем сравнить цену")
        i["flags"] = flags
        i["verdict"] = "suspect" if flags else ("caution" if i["trust"] in ("warning", "market") else "ok")
    return ref


KIDS = re.compile(r"дитяч|детск|підлітк|подростк|для (хлопчика|дівчинки|мальчика|девочки)|\bkids?\b|junior|infant|toddler|"
                  r"\b(gs|ps|td|bg)\b|\(ps\)|\(gs\)|\(td\)", re.I)


def search(q):
    q = q.strip()[:80]
    q = ALIASES.get(q.lower(), q)
    key = q.lower()
    if key in CACHE and time.time() - CACHE[key][0] < CACHE_TTL:
        return CACHE[key][1]
    rt = rates()
    jobs = {POOL.submit(_safe, fn, q): (region, name)
            for region, srcs in (("ua", UA_SOURCES), ("eu", EU_SOURCES)) for name, fn in srcs}
    res = {"query": q, "ua": [], "eu": [], "stores": {"ua": [], "eu": []},
           "failed": [], "rates": {k: rt.get(k) for k in ("EUR", "GBP", "USD")}, "trust": TRUST}
    try:
        for fut in cf.as_completed(jobs, timeout=35):
            region, name = jobs[fut]
            items = fut.result()
            if items is None:
                res["failed"].append(name)
                continue
            res["stores"][region].append(name)
            for it in items:
                if not relevant(it["title"] + " " + it.get("vendor", ""), q) or it["currency"] not in rt:
                    continue
                it.setdefault("cat", "shoes")
                it["price_uah"] = round(it["price"] * rt[it["currency"]])
                it["kids"] = bool(KIDS.search(it["title"]))
                if region == "eu":
                    it["duty"] = it["price_uah"] / rt["EUR"] > 150   # порог беспошлинного ввоза в Украину
                res[region].append(it)
    except cf.TimeoutError:
        res["failed"] += [n for f, (r, n) in jobs.items() if not f.done()]
    res["ref_price"] = check(res["ua"] + res["eu"])
    for r in ("ua", "eu"):
        seen, uniq = set(), []
        for it in sorted(res[r], key=lambda x: x["price_uah"]):
            if it["url"] in seen:
                continue
            seen.add(it["url"]); uniq.append(it)
        res[r] = uniq[:160]
    res["stores"]["total"] = len(UA_SOURCES) + len(EU_SOURCES)
    res["counts"] = {c: sum(1 for r in ("ua", "eu") for i in res[r] if i["cat"] == c) for c in CATS}
    if len(res["failed"]) < 0.3 * res["stores"]["total"]:      # неполный ответ не кэшируем — повторим позже
        CACHE[key] = (time.time(), res)
    return res


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/info":
            body = json.dumps({"ua": len(UA_SOURCES), "eu": len(EU_SOURCES)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/api/search":
            q = urllib.parse.parse_qs(u.query).get("q", [""])[0]
            body = json.dumps(search(q) if q.strip() else {"error": "пустой запрос"}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def log_message(self, fmt, *a):
        if "/api/" in (a[0] if a else ""):
            sys.stderr.write("%s\n" % (a[0],))


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    # На хостинге (Render и т.п.) слушаем все адреса, на своём компьютере — только локальный
    HOST = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1")
    print(f"KUTSU 靴 работает: http://{'localhost' if HOST == '127.0.0.1' else HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
