"""使用 TMDB 官方 API 采集高分电影，按榜单返回的顺序导出 CSV。"""
# ↑ 模块顶部的文档字符串(docstring),用三引号括起来,说明这个文件是干什么的

import argparse              # ↑ 标准库:解析命令行参数(--limit、--language 等)
import csv                   # ↑ 标准库:读写 CSV 文件
from datetime import date    # ↑ 标准库:把日期字符串标准化(转成 ISO 格式)
import os                    # ↑ 标准库:读取环境变量
from pathlib import Path     # ↑ 标准库:跨平台处理文件路径
import sys                   # ↑ 标准库:往报错窗口(标准错误流)输出信息
from tempfile import NamedTemporaryFile  # ↑ 标准库:创建临时文件(先写临时文件再改名,更安全)
import time                  # ↑ 标准库:让程序暂停一小会儿(避免请求太频繁被限流)

import requests                          # ↑ 第三方库:发 HTTP 请求,访问 TMDB 接口
from requests.adapters import HTTPAdapter  # ↑ 用来给连接设置"重试次数"的适配器
from urllib3.util import Retry           # ↑ 定义重试策略(重连几次、等多久)


API_BASE = "https://api.themoviedb.org/3"          # TMDB 所有接口共用的网址前缀
MOVIE_BASE = "https://www.themoviedb.org/movie"    # TMDB 网页端单个电影页面的网址前缀
PROJECT_DIR = Path(__file__).resolve().parent      # 本文件所在文件夹 → 用来定位默认输出路径
FIELDS = (                                        # 输出的 CSV 有哪些列(列名顺序)
    "排名", "电影ID", "片名", "年份", "上映日期", "类型", "时长（分钟）",
    "评分（10分制）", "投票数", "原始语言", "导演", "编剧及故事作者",
    "主要演员", "宣传语", "简介", "详情链接",
)
WRITING_JOBS = {"Writer", "Screenplay", "Story", "Original Story", "Novel"}  # 哪些职位算"编剧/作者"


def create_session(token):
    """同一个 Session 复用连接，给每次请求附上读取令牌。"""
    session = requests.Session()   # 建一个 Session:连接可以复用,不用每次请求都重新握手
    session.headers.update({       # 给这个 Session 的所有请求统一加上请求头
        "Authorization": f"Bearer {token}",  # 用 Bearer 方式携带访问令牌(TMDB 要求的认证方式)
        "Accept": "application/json",        # 告诉服务器:我们只想要 JSON 格式的返回结果
    })
    retries = Retry(               # 定义"自动重试"规则
        total=2,                   # 最多重试 2 次
        backoff_factor=1,          # 重试前暂停的时间按 1 秒递增(1s、2s...)
        allowed_methods={"GET"},   # 只有 GET 请求才重试(数据读取类请求最安全)
        status_forcelist=(500, 502, 503, 504),  # 遇到这些服务器错误码才重试
        respect_retry_after_header=False,       # 不理会服务器"Retry-After"头,照自己的节奏重试
        raise_on_status=False,     # 重试用尽后不直接抛异常,把结果交给下面的代码判断
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))  # 给 https 请求挂上上面的重试策略
    return session                 # 把组装好的 Session 返回给调用方


def get_json(session, endpoint, **params):
    """完成一次 GET 请求，把常见失败转换为便于定位的提示。"""
    url = API_BASE + endpoint      # 拼出完整的接口地址,例如 /movie/top_rated
    context = f"{endpoint}（{params}）"  # 记录"正在请求哪个接口、带什么参数",出错时好定位
    try:
        response = session.get(url, params=params, timeout=(5, 20))  # 发起 GET 请求,(连接超时,读取超时)
    except requests.Timeout as error:              # 请求超时
        raise RuntimeError(f"{context} 请求超时。") from error      # 转成友好的中文错误
    except requests.ConnectionError as error:      # 连不上/网络断了
        raise RuntimeError(f"{context} 连接失败或等待响应超时。请检查网络后再试。") from error
    except requests.RequestException as error:     # 其它所有请求类异常
        raise RuntimeError(f"{context} 请求失败（{type(error).__name__}）。") from error

    if response.status_code == 401:                # 401 = 认证失败(令牌无效)
        raise RuntimeError("TMDB 返回 401。请检查 TMDB_READ_TOKEN 是否是有效的 API Read Access Token。")
    if response.status_code == 403:                # 403 = 没权限
        raise RuntimeError(f"{context} 返回 403，访问被拒绝。")
    if response.status_code == 429:                # 429 = 请求太频繁,被限流了
        retry_after = response.headers.get("Retry-After")   # 服务器建议等多少秒
        hint = f"Retry-After: {retry_after}。" if retry_after else ""  # 有就显示建议时间
        raise RuntimeError(f"{context} 返回 429，请等待后重新运行。{hint}")
    if response.status_code != 200:                # 其它非 200 的异常码
        raise RuntimeError(f"{context} 返回 HTTP {response.status_code}。")

    try:
        data = response.json()     # 把返回的 JSON 文本解析成 Python 的字典
    except ValueError as error:    # 内容不是合法 JSON
        raise RuntimeError(f"{context} 的响应无法解析为 JSON。") from error
    if not isinstance(data, dict) or data.get("success") is False:  # 结构不对,或接口明确报错
        raise RuntimeError(f"{context} 返回了意外的 JSON 结构。")
    return data                    # 一切正常,把解析好的数据返回出去


def collect_top_movies(session, limit, language):
    """按页收集不同的电影 ID，直到满足数量或到达榜单末尾。"""
    movies = []        # 收集到的高分电影列表
    seen_ids = set()   # 记录已经见过的电影 ID,防止一页里重复
    page = 1           # 从第 1 页开始翻
    while True:        # 一直循环,直到拿到足够数量或翻完所有页
        data = get_json(session, "/movie/top_rated", language=language, page=page)  # 取当前页榜单
        results = data.get("results")        # 这一页的电影列表
        total_pages = data.get("total_pages")  # 总共有多少页
        if data.get("page") != page or not isinstance(results, list) or type(total_pages) is not int:
            # 校验返回的页码、列表、总页数是否合法
            raise RuntimeError(f"榜单第 {page} 页缺少有效的页码、结果列表或总页数。")
        if not results and page < total_pages:  # 还没到最后一页就返回了空,不正常
            raise RuntimeError(f"榜单第 {page} 页提前返回了空结果。")

        for movie in results:        # 遍历这一页里的每一部电影
            movie_id = movie.get("id") if isinstance(movie, dict) else None  # 取出电影 ID
            if type(movie_id) is not int or movie_id <= 0:   # ID 必须是正整数
                raise RuntimeError(f"榜单第 {page} 页有记录缺少有效的电影 ID。")
            if movie_id in seen_ids:  # 这 ID 前面见过了 → 跳过,避免重复
                continue
            seen_ids.add(movie_id)    # 把新 ID 记进"已见"集合
            movies.append(movie)      # 把这部电影加进结果
            if len(movies) == limit:  # 已经攒够数量了
                print(f"已读到榜单第 {page} 页，取得 {len(movies)} 部不同电影。")
                return movies         # 直接返回结果,不继续翻了

        print(f"榜单第 {page} 页处理完毕，累计 {len(movies)} 部不同电影。")
        if page >= min(total_pages, 500):   # 翻到头了(接口最多让翻 500 页)还没攒够
            raise RuntimeError(f"榜单只取得 {len(movies)} 部不同电影，目标是 {limit} 部。")
        page += 1                  # 去下一页
        time.sleep(0.25)           # 停 0.25 秒,别把接口打爆


def clean_release_date(value):
    """输出标准日期，空值或无法解析的日期在 CSV 中留空。"""
    if not isinstance(value, str):   # 值不是字符串(比如 None)
        return ""                    # 直接返回空字符串
    try:
        return date.fromisoformat(value.strip()).isoformat()  # 转成标准的 YYYY-MM-DD 格式
    except ValueError:               # 格式不对,解析失败
        return ""                    # 返回空


def join_names(items):
    """合并名称，保持原顺序，并去掉空值和重复名字。"""
    names = []                       # 收集有效名字的列表
    for item in items:               # 遍历每一项(导演、演员...)
        name = (item.get("name") or "").strip()  # 取名字,没有就是空,再去掉首尾空格
        if name:                     # 名字非空才要
            names.append(name)
    return " / ".join(dict.fromkeys(names))  # 用 dict 去重并保持顺序,再用" / "拼接成字符串


def make_movie_row(rank, movie, detail):
    """将榜单及详情的嵌套 JSON 整理成一行 CSV。"""
    movie_id = movie["id"]                   # 当前电影 ID
    credits = detail.get("credits")          # 详情里的演职员信息
    if detail.get("id") != movie_id or not isinstance(credits, dict):  # 校验详情和榜单是同一部电影
        raise RuntimeError(f"电影 {movie_id} 的详情 ID 不符或缺少 credits。")
    cast = credits.get("cast")   # 演员列表
    crew = credits.get("crew")   # 工作人员列表(导演、编剧等)
    genres = detail.get("genres")  # 类型列表
    if not all(isinstance(items, list) for items in (cast, crew, genres)):  # 三者都必须是列表
        raise RuntimeError(f"电影 {movie_id} 的类型或演职员字段格式有变。")

    title = detail.get("title") or movie.get("title") or detail.get("original_title")  # 片名,一级级兜底
    score = movie.get("vote_average")      # 评分
    vote_count = movie.get("vote_count")   # 投票数
    if not isinstance(title, str) or not title.strip():  # 片名必须是有效字符串
        raise RuntimeError(f"电影 {movie_id} 缺少片名。")
    if type(score) not in (int, float) or not 0 <= score <= 10:  # 评分必须在 0~10 之间
        raise RuntimeError(f"电影 {movie_id} 缺少有效评分。")
    if type(vote_count) is not int or vote_count < 0:   # 投票数必须是非负整数
        raise RuntimeError(f"电影 {movie_id} 缺少有效投票数。")

    release_date = clean_release_date(detail.get("release_date") or movie.get("release_date"))  # 上映日期
    runtime = detail.get("runtime")        # 时长(分钟)
    directors = [person for person in crew if person.get("job") == "Director"]  # 筛选出导演
    writers = [person for person in crew if person.get("job") in WRITING_JOBS]  # 筛选出编剧/作者
    return {                               # 组装成一行(C 依次对应 FIELDS 里的每一列)
        "排名": rank,
        "电影ID": movie_id,
        "片名": title.strip(),
        "年份": release_date[:4],          # 取日期的前 4 位当成年份
        "上映日期": release_date,
        "类型": join_names(genres),
        "时长（分钟）": runtime if type(runtime) is int and runtime > 0 else "",  # 时长合法才有值
        "评分（10分制）": score,
        "投票数": vote_count,
        "原始语言": detail.get("original_language") or "",
        "导演": join_names(directors),
        "编剧及故事作者": join_names(writers),
        "主要演员": join_names(cast[:5]),  # 只取前 5 个主演
        "宣传语": (detail.get("tagline") or "").strip(),
        "简介": (detail.get("overview") or "").strip(),
        "详情链接": f"{MOVIE_BASE}/{movie_id}",
    }


def write_csv(output, rows):
    """先写临时文件，写完再替换目标文件。"""
    output.parent.mkdir(parents=True, exist_ok=True)  # 先确保输出目录存在(不存在就创建)
    temp = NamedTemporaryFile(   # 建一个临时文件(避免写到一半突然断电导致文件损坏)
        mode="w", encoding="utf-8-sig", newline="",   # 用带 BOM 的 UTF-8(Excel 打开不乱码)
        dir=output.parent, suffix=".tmp", delete=False,  # 放在目标目录下、叫 .tmp、先不自动删
    )
    temporary_path = Path(temp.name)  # 拿到临时文件的完整路径
    try:
        with temp:                     # 进入"写文件"上下文
            writer = csv.DictWriter(temp, fieldnames=FIELDS)  # 用列名映射的方式写 CSV
            writer.writeheader()       # 先写表头(第一行列名)
            writer.writerows(rows)     # 再写所有数据行
        # Windows 下，关闭文件句柄后才能替换。
        temporary_path.replace(output)  # 把临时文件改名/替换成正式文件
    finally:
        temporary_path.unlink(missing_ok=True)  # 无论如何都清理临时文件(不存在也没关系)


def main():
    parser = argparse.ArgumentParser(description=__doc__)  # 创建参数解析器,说明文字取自顶部 docstring
    parser.add_argument("--limit", type=int, default=100, help="采集数量（1 至 100，默认 100）")  # --limit 参数
    parser.add_argument("--language", default="zh-CN", help="语言，例如 zh-CN 或 en-US")          # --language 参数
    parser.add_argument("--output", type=Path, default=PROJECT_DIR / "movies.csv", help="CSV 输出路径")  # --output 参数
    args = parser.parse_args()        # 真正去解析用户在命令行输入的值
    if not 1 <= args.limit <= 100:    # 校验数量范围
        parser.error("--limit 必须在 1 至 100 之间。")  # 不合法就报错退出

    token = os.environ.get("TMDB_READ_TOKEN", "").strip()  # 从环境变量取令牌,取不到就给空串
    if not token:                     # 令牌是空的
        parser.error("请先在 PyCharm 运行配置中设置环境变量 TMDB_READ_TOKEN。")  # 提示用户先去配置

    rows = []                         # 用来装所有整理好的行
    try:
        with create_session(token) as session:   # 建好带令牌的 Session(用 with 保证用完自动关)
            movies = collect_top_movies(session, args.limit, args.language)  # ① 先拉榜单,拿到电影列表
            for rank, movie in enumerate(movies, start=1):  # 逐部处理,rank 从 1 开始计名次
                if rank > 1:          # 不是第一部,请求前稍停片刻
                    time.sleep(0.25)
                detail = get_json(    # ② 再拉这部电影的详情(附带 credits 演职员信息)
                    session, f"/movie/{movie['id']}",
                    language=args.language, append_to_response="credits",
                )
                row = make_movie_row(rank, movie, detail)  # ③ 把榜单+详情整理成一行
                rows.append(row)      # 收集到结果里
                print(f"[{rank}/{args.limit}] {row['片名']}")  # 在终端打印进度
        write_csv(args.output, rows)  # ④ 把所有行一次写入 CSV
    except (RuntimeError, OSError) as error:  # 捕获我们抛出的友好错误和文件系统错误
        print(f"采集未完成（已整理 {len(rows)}/{args.limit} 条）\n{error}", file=sys.stderr)  # 往错误流打印
        return 1                      # 返回 1 表示失败(给操作系统看)

    print(f"已导出 {len(rows)} 条记录 → {args.output.resolve()}")  # 提示导出成功和路径
    print("This product uses the TMDB API but is not endorsed or certified by TMDB.")  # TMDB 要求保留的免责声明
    return 0                          # 返回 0 表示成功


if __name__ == "__main__":            # 只有当这个文件被"直接运行"时才执行(被 import 时跳过)
    raise SystemExit(main())          # 调用 main() 并把它的返回值当作程序退出码