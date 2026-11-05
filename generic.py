"""Универсальный разбор страницы поиска интернет-магазина:
находит карточки товаров (ссылка + название), а рядом — цену и картинку."""
import re, html, urllib.parse

_SEP = r"[ ,   ]"
_JUNK = r"(?:</?[a-z][^>]{0,160}>|<!--.*?-->|&nbsp;|\s)*"
PRICE = re.compile(r"(?<![\d.,\-−–])(\d{1,3}(?:" + _SEP + r"\d{3})+|\d{3,6})(?:[.,]\d{1,2}(?!\d))?" + _JUNK + r"(?:грн|₴|uah\b)", re.I | re.S)
META_PRICE = re.compile(r'itemprop="price"[^>]*content="(\d+(?:\.\d+)?)"|content="(\d+(?:\.\d+)?)"[^>]*itemprop="price"')
ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
BAD_PATH = re.compile(r"search|/category/|/brand|/tag/|/cart|/login|/blog|wishlist|compare|/page/|/sections-|/genders-", re.I)
IMG = re.compile(r'<img\b[^>]*?(?:data-src|data-original|data-lazy-src|data-lazy|src)="([^"]+?\.(?:jpe?g|png|webp)(?:\?[^"]*)?)"', re.I)
NOT_SHOES = re.compile(r"куртк|гаман|футбол|шкарпет|носк|сумк|рюкзак|худі|худи|кепк|шапк|штан|шорт|світшот|свитшот|бананк|"
                       r"кофт|жилет|брелок|шнурк|устілк|стельк|догляд|спрей|crep|jacket|wallet|socks?\b|\bbag|hoodie|\bcap\b|\btee\b|t-shirt|"
                       r"\bpants?\b|trousers|shorts|sweat|shirt|jersey|beanie|\bhat\b|keychain|laces|insoles|backpack|"
                       r"\bvest\b|fleece|crewneck|parka|\bcoat\b|gift card|cleaner|"
                       r"фляг|фласк|рукавич|перчат|пляшк|бутыл|пояс|окуляр|очки|налокітн|гетр|рушник|полотенц|"
                       r"flask|bottle|gloves?\b|\bbelt\b|sunglasses|headband|\bbeanie|gaiter|towel|poles?\b", re.I)


# ── категории товаров: обувь / носки / одежда / аксессуары ──
CYR = re.compile(r"[а-яіїєґё]{3,}", re.I)
SHOE_WORD = re.compile(r"кросів|кросс|кед|черевик|ботин|взутт|обув|сліпон|слипон|мокасин|сандал|босоніж|босонож|туфл|"
                       r"чобот|чоботи|сапог|уггі|угги|шльоп|шлеп|тапоч|лофер|мюл|сабо|снікер|сникер", re.I)
SOCKS = re.compile(r"шкарпет|носк|носоч|\bsocks?\b|\bsokken\b|calze\b|chaussettes|skarpet|ponožk|ponozk|podkolan", re.I)
# польский / чешский / словацкий (Sportano часто отдаёт такие названия)
PL_SHOES = re.compile(r"\bbuty\b|obuwie|trampki|klapki|sandał|sandaly|kozaki|topánk|tenisk|\bobuv|botas\b", re.I)
APPAREL = re.compile(r"футбол|худі|худи|куртк|штан|шорт|світшот|свитшот|кофт|жилет|толстовк|сорочк|рубашк|джинс|легін|леггин|"
                     r"лосин|сукн|плать|спідниц|юбк|костюм|пуховик|вітровк|ветровк|майк|бомбер|парка\b|"
                     r"\btee\b|t-shirt|\bshirt|hoodie|sweat|jacket|\bpants?\b|trousers|shorts|jersey|\bvest\b|fleece|crewneck|"
                     r"parka|\bcoat\b|jeans|dress\b|skirt|tights|legging|\bpolo\b|anorak|windbreaker|tracksuit|overshirt|cardigan|knit\b|"
                     r"crop top|tank top|\bbra\b|bodysuit|\bbody\b|unitard|\bsinglet|longsleeve|long sleeve|short sleeve|"
                     r"sweater|pullover|\bjogger|\bbib\b|swim|boxer|briefs|underwear|"
                     r"spodenk|spodni|legginsy|biustonosz|stanik|bluza|kurtk|koszulk|t-shirt|mikina|tričk|tricko|kraťas|kratas|"
                     r"nohavic|bunda|kalhot|sukienk|spódnic|kamizelk|dres\b|szort", re.I)
ACC = re.compile(r"сумк|рюкзак|гаман|кепк|шапк|окуляр|очки|пляшк|бутил|бутыл|фляг|фласк|рукавич|рукавиц|перчат|пояс|ремін|ремень|"
                 r"шнурк|устілк|стельк|догляд|спрей|брелок|палиц|палки|рушник|полотенц|гетр|налокітн|чохол|чехол|"
                 r"\bbag\b|backpack|wallet|\bcap\b|\bhat\b|beanie|bottle|flask|\bgloves?\b|mittens?|\bbelt\b|\blaces\b|insoles?|"
                 r"cleaner|keychain|sunglasses|headband|towel|\bpoles?\b|umbrella|gift card|\bcrep\b|tote\b|pouch|scarf|"
                 r"м['’]?яч|\bball\b|ракетк|racket|сітка|скакалк|еспандер|\bmat\b|килимок|коврик|"
                 r"duffel|duffle|holdall|\bsack\b|"
                 r"czapk|torba|plecak|batoh|taška|taska|čiapk|ciapk|šiltovk|siltovk|rękawic|rekawic|piłk|pilka|ruksak|"
                 r"saszetk|portfel|nerk|opask|bidon|ręcznik|recznik|okulary", re.I)
CATS = ("shoes", "socks", "apparel", "acc")


def classify(title, extra="", default="shoes"):
    t = title + " " + extra
    if SOCKS.search(t):
        return "socks"
    if SHOE_WORD.search(title) or PL_SHOES.search(title):
        return "shoes"
    if APPAREL.search(t):
        return "apparel"
    if ACC.search(t):
        return "acc"
    if CYR.search(title):
        return "acc"          # тип не распознан, но точно не обувь (в названии нет «кросівки/кеди/…»)
    return default


def words(q):
    return [w for w in re.findall(r"\w+", q.lower()) if len(w) > 1]


def _clean(s):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _num(s):
    return int(re.sub(r"\D", "", s))


def extract(page, base, q, limit=30):
    ws = words(q)
    page = re.sub(r"&#x433;&#x440;&#x43[dD];|&#1075;&#1088;&#1085;", "грн", page)
    host = urllib.parse.urlparse(base).netloc.replace("www.", "")
    by, order = {}, []
    for m in ANCHOR.finditer(page):
        attrs, inner = m.group(1), m.group(2)
        hm = re.search(r'href="([^"]+)"', attrs)
        if not hm or hm.group(1).startswith(("#", "javascript:", "?")):
            continue
        p = urllib.parse.urlparse(urllib.parse.urljoin(base, html.unescape(hm.group(1))))
        if host not in p.netloc or BAD_PATH.search(p.path) or p.path.strip("/") == "":
            continue
        query = "?" + p.query if ("product" in p.query and "search" not in p.query) else ""
        url = f"{p.scheme}://{p.netloc}{p.path}{query}"
        title = _clean(inner)
        if len(title) < 6:
            t2 = (re.search(r'title="([^"]{6,})"', attrs) or re.search(r'alt="([^"]{6,})"', inner)
                  or re.search(r'aria-label="([^"]{6,})"', attrs))
            title = html.unescape(t2.group(1)).strip() if t2 else title
        if url not in by:
            by[url] = {"s": m.start(), "e": m.end(), "title": ""}
            order.append(url)
        d = by[url]
        d["e"] = max(d["e"], m.end())
        if len(title) > len(d["title"]) and len(title) < 200:
            d["title"] = title
    prods = [u for u in order if by[u]["title"] and all(w in by[u]["title"].lower() for w in ws)]
    out = []
    for i, u in enumerate(prods):
        d = by[u]
        prev_end = by[prods[i - 1]]["e"] if i else d["s"] - 2500
        next_start = by[prods[i + 1]]["s"] if i + 1 < len(prods) else d["e"] + 2500
        # карточка начинается с первой ссылки на товар (обычно картинка) — назад смотрим совсем чуть-чуть,
        # иначе первая карточка «цепляет» цены из баннеров шапки
        lo, hi = max(0, prev_end, d["s"] - 300), min(next_start, d["e"] + 2500)
        win = page[lo:hi]
        metas = [float(a or b) for a, b in META_PRICE.findall(win)]
        nums = [n for n in (_num(x) for x in PRICE.findall(win)) if 400 <= n <= 300000][:3]
        if metas:                       # schema.org-цена надёжнее всего
            price = int(min(metas))
        elif nums:
            price = min(nums)
        else:
            continue
        old = max(nums) if nums and max(nums) > price * 1.03 else None
        imgs = [x for x in IMG.findall(page[max(lo, d["s"] - 2500):hi]) if "logo" not in x.lower()]
        title = re.sub(r"\s+-\s+\d{4,}$", "", d["title"])          # «… - 180197» у Megasport
        title = re.sub(r"\s+\d{1,3}(?:[  ]\d{3})*\s*(грн|₴)\.?", "", title).strip(" ,")   # цены внутри названия
        title = re.sub(r",\s*(Розмір|Размер|Наявність|Наличие):.*$", "", title)
        title = re.sub(r"\s+(купити|купить)(\s.*)?$", "", title, flags=re.I)
        out.append({"title": title, "url": u, "price": price, "old_price": old, "cat": classify(title),
                    "image": urllib.parse.urljoin(base, html.unescape(imgs[0])) if imgs else ""})
        if len(out) >= limit:
            break
    return out
