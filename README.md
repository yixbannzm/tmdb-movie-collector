# TMDB 电影榜单数据采集与清洗

使用 Python 从 TMDB API 分页获取高分电影榜单，按电影 ID 关联详情与演职员信息，清洗后按榜单顺序导出 CSV。

**运行结果**　一次实际运行采集了 5 页、100 部电影，导出 16 个字段。结果中电影 ID 唯一，排名从 1 到 100 连续。

## 数据处理流程

1. **采集榜单**　逐页读取 Top Rated API，按电影 ID 去重，保留接口返回顺序，达到目标数量后停止翻页。
2. **补齐详情**　按电影 ID 请求详情，通过 `append_to_response=credits` 同时取得演职员信息。
3. **清洗和校验**　将嵌套 JSON 转为表格记录，统一日期和片长格式，保留可选字段的空值，校验详情 ID、片名、评分和投票数。
4. **导出结果**　使用 UTF-8 BOM 编码写入 CSV。先写临时文件，再替换目标文件，避免采集中断覆盖上一次的完整结果。

请求使用 `requests.Session` 复用连接，设置连接与读取超时，对连接异常和部分服务端错误进行有限重试。收到 HTTP 429 时会提示等待后重跑。

## 运行方式

建议使用 Python 3.12。从项目目录创建虚拟环境并安装依赖。

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

在 TMDB 账户的 **Settings → API** 获取 **API Read Access Token**，通过环境变量 `TMDB_READ_TOKEN` 提供。在 PyCharm 中，可以在 **Run → Edit Configurations → Environment variables** 为 `main.py` 设置该变量。 [TMDB 认证文档](https://developer.themoviedb.org/docs/authentication-application)

先采集 3 部验证配置，再运行完整采集。

~~~powershell
.\.venv\Scripts\python.exe main.py --limit 3 --output movies_preview.csv
.\.venv\Scripts\python.exe main.py --limit 100
~~~

完整采集默认生成 `movies.csv`，包含排名、电影 ID、片名、年份、上映日期、类型、片长、评分、投票数、原始语言、演职员、宣传语、简介和详情链接。`--language` 默认 `zh-CN`，可通过 `--output` 指定输出路径。

## 数据来源

数据由 The Movie Database（TMDB）提供。 [榜单接口](https://developer.themoviedb.org/reference/movie-top-rated-list) · [详情接口](https://developer.themoviedb.org/reference/movie-details) · [演职员接口](https://developer.themoviedb.org/reference/movie-credits)

> This product uses the TMDB API but is not endorsed or certified by TMDB.

[TMDB 署名要求与官方标志](https://www.themoviedb.org/about/logos-attribution)
