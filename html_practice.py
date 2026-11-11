"""用本地电影页面样例练习 XPath、翻页、清洗和 CSV 导出。"""

import re
from urllib.parse import urljoin

from lxml import html

from main import PROJECT_DIR, clean_release_date, write_csv


DEMO_BASE = "https://example.invalid"
DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
RUNTIME_PATTERN = re.compile(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?", re.IGNORECASE)
MOVIE_LINK_PATTERN = re.compile(r"/movie/(\d+)(?:-[^/]+)?")
CARD_XPATH = ".//article[contains(concat(' ', normalize-space(@class), ' '), ' card ')]"


def release_date_from_html(raw_date):
    match = DATE_PATTERN.search(raw_date)
    return clean_release_date(match.group()) if match else ""


def runtime_minutes(raw_runtime):
    match = RUNTIME_PATTERN.fullmatch(raw_runtime.strip())
    if not match:
        return ""
    hours, minutes = match.groups()
    if hours is None and minutes is None:
        return ""
    return int(hours or 0) * 60 + int(minutes or 0)


def get_detail_row(rank, movie_id, link, detail):
    # string(...) 同时取得子标签里的文字。没有匹配节点时返回空串。
    title = detail.xpath("string(.//h2)").strip()
    release_date = release_date_from_html(detail.xpath("string(.//span[@class='release'])"))
    runtime = runtime_minutes(detail.xpath("string(.//span[@class='runtime'])"))
    percent = detail.xpath("string(.//div[@data-percent]/@data-percent)")
    return {
        "排名": rank,
        "电影ID": movie_id,
        "片名": title,
        "年份": release_date[:4],
        "上映日期": release_date,
        "类型": " / ".join(detail.xpath(".//span[@class='genres']/a/text()")),
        "时长（分钟）": runtime,
        "评分（10分制）": int(percent) / 10 if percent else "",
        "详情链接": urljoin(DEMO_BASE, link),
    }


def main():
    source = PROJECT_DIR / "sample_movies.html"
    document = html.fromstring(source.read_text(encoding="utf-8"))
    rows = []
    seen_ids = set()

    for page in document.xpath("//section[@data-page]"):
        for card in page.xpath(CARD_XPATH):
            links = card.xpath(".//h3/a/@href")
            link = links[0] if links else ""
            match = MOVIE_LINK_PATTERN.fullmatch(link)
            if not match:
                raise ValueError(f"样例电影链接格式有变：{link!r}")
            movie_id = int(match.group(1))
            if movie_id in seen_ids:
                continue

            details = document.xpath("//article[@data-movie-id=$movie_id]", movie_id=str(movie_id))
            if len(details) != 1:
                raise ValueError(f"样例中电影 {movie_id} 的详情数量应为 1。")
            row = get_detail_row(len(rows) + 1, movie_id, link, details[0])
            rows.append(row)
            seen_ids.add(movie_id)
            print(f"第 {page.get('data-page')} 页 | {row['片名']} | 片长 {row['时长（分钟）']!r}")

    if not rows:
        raise ValueError("样例中没有找到电影卡片，请检查 XPath。")
    output = PROJECT_DIR / "movies_demo.csv"
    write_csv(output, rows)
    print(f"已导出 {len(rows)} 条虚构样例 → {output}")


if __name__ == "__main__":
    main()
