"""Сборщики данных: новости МВД, процедуры МВД (gov.il), законы Кнессета (OData).

Все эндпоинты проверены 11.06.2026.
Каждый fetch_* возвращает список словарей:
    {"id": str, "title": str, "date": "ДД.ММ.ГГГГ", "extra": str, "url": str}
"""
import aiohttp

import config

# Управление населения и иммиграции (רשות האוכלוסין וההגירה)
OFFICE_ID = "95b283ad-fc02-40e6-ac6f-8986acac6b86"
# Тип «נהלים והנחיות» (процедуры и инструкции)
POLICY_TYPE = "2efa9b53-5df9-4df9-8e9d-21134511f368"
# Публичный ключ фронтенда gov.il (зашит в код сайта; без него API отвечает 500)
GOVIL_CLIENT_ID = "9KFgciHHGDyNiqz5MdQS0eK2ApeJYMc6YnElUICpN1atirZc"

# Шлюз openapi-gc требует Referer с gov.il, иначе тихо отдаёт 500/пустоту
GW_HEADERS = {
    "x-client-id": GOVIL_CLIENT_ID,
    "Referer": "https://www.gov.il/",
    "Origin": "https://www.gov.il",
}

NEWS_URL = (
    "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/"
    "collectors/v1/api/DataCollector/GetResults"
)
POLICY_URL = "https://www.gov.il/he/api/PolicyApi/Index"
KNESSET_BILLS_URL = "https://knesset.gov.il/Odata/ParliamentInfo.svc/KNS_Bill"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


async def _get_json(url: str, params: dict | None = None, headers: dict | None = None):
    h = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params, headers=h) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


def _iso_to_ru(date_str: str | None) -> str:
    """'2026-06-09T12:15:00Z' -> '09.06.2026'."""
    if not date_str or len(date_str) < 10:
        return ""
    y, m, d = date_str[:10].split("-")
    return f"{d}.{m}.{y}"


async def fetch_news(limit: int = 5) -> list[dict]:
    """Новости МВД (раздел «новости» рשות האוכלוסין)."""
    data = await _get_json(
        NEWS_URL,
        params={
            "CollectorType": "news",
            "officeId": OFFICE_ID,
            "culture": "he",
            "skip": "0",
        },
        headers=GW_HEADERS,
    )
    out = []
    for x in (data.get("results") or [])[:limit]:
        meta = (x.get("tags") or {}).get("metaData") or {}

        def first_title(key: str) -> str:
            vals = meta.get(key) or []
            return (vals[0] or {}).get("title", "") if vals else ""

        url = x.get("url") or ""
        if url and not url.startswith("http"):
            url = "https://www.gov.il" + url
        out.append(
            {
                "id": url or x.get("title", ""),
                "title": x.get("title", "") or "(без названия)",
                "date": first_title("תאריך פרסום"),
                "extra": first_title("נושא"),
                "url": url,
            }
        )
    return out


def _parse_gateway_item(x: dict) -> dict:
    """Разбор элемента из шлюза openapi-gc (DataCollector/GetResults)."""
    meta = (x.get("tags") or {}).get("metaData") or {}

    def first_title(key: str) -> str:
        vals = meta.get(key) or []
        return (vals[0] or {}).get("title", "") if vals else ""

    url = x.get("url") or ""
    if url and not url.startswith("http"):
        url = "https://www.gov.il" + url
    date = first_title("תאריך עדכון") or first_title("תאריך פרסום")
    return {
        "id": f"{url}:{date}",
        "title": x.get("title", "") or "(без названия)",
        "date": date,
        "extra": first_title("נושא") or first_title("יחידות"),
        "url": url,
    }


async def _fetch_procedures_gateway(limit: int) -> list[dict]:
    """Основной путь: процедуры через шлюз openapi-gc
    (www.gov.il блокирует серверные IP, шлюз с Referer — нет)."""
    # имена параметров подсмотрены в запросах самой страницы policies:
    # CollectorType=policy&CollectorType=pmopolicy (именно так, не policies)
    params = [
        ("CollectorType", "policy"),
        ("CollectorType", "pmopolicy"),
        ("officeId", OFFICE_ID),
        ("Type", POLICY_TYPE),
        ("culture", "he"),
        ("skip", "0"),
        ("limit", str(max(limit, 10))),
    ]
    data = await _get_json(NEWS_URL, params=params, headers=GW_HEADERS)
    results = data.get("results") or []
    return [_parse_gateway_item(x) for x in results[:limit]]


async def fetch_procedures(limit: int = 5) -> list[dict]:
    """Процедуры МВД (נהלים והנחיות), отсортированы по дате обновления.

    Сначала шлюз openapi-gc (работает с серверов), при сбое — прямой
    PolicyApi (работает из браузеров/локально)."""
    try:
        return await _fetch_procedures_gateway(limit)
    except Exception:  # noqa: BLE001 — пробуем прямой API
        pass
    data = await _get_json(
        POLICY_URL,
        params={
            "OfficeId": OFFICE_ID,
            "Type": POLICY_TYPE,
            "limit": str(limit),
            "skip": "0",
        },
    )
    out = []
    for x in (data.get("results") or [])[:limit]:
        updated = x.get("DocUpdateDate") or x.get("DocPublishedDate") or ""
        url_name = x.get("UrlName") or ""
        out.append(
            {
                # В id входит дата обновления: обновление документа = новое событие
                "id": f'{x.get("ItemUniqueId", url_name)}:{updated}',
                "title": x.get("Title", "") or "(без названия)",
                "date": _iso_to_ru(updated),
                "extra": ", ".join(x.get("UnitsDesc") or []),
                "url": f"https://www.gov.il/he/pages/{url_name}" if url_name else "",
            }
        )
    return out


async def fetch_laws(limit: int = 5) -> list[dict]:
    """Принятые законы Кнессета (KNS_Bill, StatusID = принят)."""
    data = await _get_json(
        KNESSET_BILLS_URL,
        params={
            "$filter": f"StatusID eq {config.LAW_STATUS_ID}",
            "$orderby": "LastUpdatedDate desc",
            "$top": str(limit),
            "$format": "json",
        },
    )
    out = []
    for x in (data.get("value") or [])[:limit]:
        bill_id = x.get("BillID")
        number = x.get("Number")
        out.append(
            {
                "id": str(bill_id),
                "title": x.get("Name", "") or "(без названия)",
                "date": _iso_to_ru(x.get("PublicationDate") or x.get("LastUpdatedDate")),
                "extra": f"законопроект №{number}" if number else "",
                "url": (
                    "https://main.knesset.gov.il/Activity/Legislation/Laws/Pages/"
                    f"LawBill.aspx?t=lawsuggestionssearch&lawitemid={bill_id}"
                ),
            }
        )
    return out
