# TMDB 高分电影 Top 100 采集

用 Python 采集高分电影榜单及详情，按榜单顺序导出 CSV。项目配有本地 HTML 练习，可以用 XPath 抽取字段，再用正则清洗日期和片长。

[逐步讲解](逐步讲解.md) 把课程第 126–136 集映射到代码、断点和练习。 [课程原视频](https://www.bilibili.com/video/BV1sHU9BmEne/?p=126)

## 在 PyCharm 运行

1. 选择 **File → Open**，打开整个 **tmdb-movie-collector** 文件夹。
2. 在 **Settings → Project → Python Interpreter** 为项目新建 `.venv`，建议以 Python 3.12 为基础解释器。打开底部的 **Terminal**，从项目目录安装依赖。

   ~~~powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ~~~

3. 右键运行 **html_practice.py**。控制台应显示三部虚构电影的片长 `142`、`40`、`120`，目录里会出现 `movies_demo.csv`。这一步只读取项目自带的 HTML。
4. 在 TMDB 账户的 **Settings → API** 申请并复制 **API Read Access Token**。在 PyCharm 的 **Run → Edit Configurations** 添加 **Python** 配置。**Script path** 选 `main.py`，**Parameters** 填 `--limit 3`，在 **Environment variables** 增加 `TMDB_READ_TOKEN` 并填入令牌。保持 **Store as project file** 未选中。 [TMDB 认证](https://developer.themoviedb.org/docs/authentication-application) · [PyCharm 运行配置](https://www.jetbrains.com/help/pycharm/run-debug-configuration-python.html)
5. 运行配置，确认 `movies.csv` 有 3 条记录。再把参数改成 `--limit 100`。输出默认在脚本所在目录，也可以用 `--output` 指定路径。运行 `.\.venv\Scripts\python.exe main.py --help` 可查看选项。

## 文件和输出

| 文件 | 用途 |
|---|---|
| `html_practice.py` 和 `sample_movies.html` | 本地练习，覆盖电影卡片、相对链接、详情定位、两页去重和正则清洗。 |
| `main.py` | 请求 TMDB 榜单和详情，整理字段并导出 CSV。 |
| `movies_demo.csv` | 本地练习生成的 3 条虚构记录。 |
| `movies.csv` | 配置有效令牌后生成，包含排名、电影 ID、片名、日期、片长、评分、演职员等字段。 |

`--language` 默认 `zh-CN`，用于请求本地化内容。原始语言列使用 `en`、`zh` 等代码。年份取 API 上映日期的前四位，评分是 10 分制。主演取接口返回的前五条演员记录。日期、片长或宣传语缺失时，对应单元格留空。

数据来自 TMDB 官方 Top Rated API。浏览器网页的筛选条件可能与接口默认值不同，得到的顺序和上映日期也可能不同。 [榜单接口](https://developer.themoviedb.org/reference/movie-top-rated-list) · [详情接口](https://developer.themoviedb.org/reference/movie-details) · [演职员接口](https://developer.themoviedb.org/reference/movie-credits)

## 数据来源

数据由 The Movie Database（TMDB）提供。 [TMDB 官网](https://www.themoviedb.org)

> This product uses the TMDB API but is not endorsed or certified by TMDB.

[TMDB 署名要求与官方标志](https://www.themoviedb.org/about/logos-attribution)
