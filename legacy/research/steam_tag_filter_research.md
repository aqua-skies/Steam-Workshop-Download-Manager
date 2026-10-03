# Steam 创意工坊浏览页标签筛选机制 · 研究报告

> 日期：2026-09-23 · 目的：为 SWDM 标签提取 bug（提取结果混入"商店/创意工坊/cookie/隐私政策"等导航项）提供修复依据
> **关键说明：本机 steamcommunity.com 直连不通，但本次通过 Wayback Machine 拿到了三个真实浏览页快照，结论全部基于真实 HTML，非推测。**

## 证据样本（真实抓取的 HTML 快照）

| 快照 | 抓取时间 | 页面技术 | 标签侧栏形态 | 文件 |
|---|---|---|---|---|
| 旧版 | 2022-12-17 | 经典 SSR（PHP/V8 引擎渲染） | checkbox `<input>` 表单 | `research/_browse_legacy.html`（128KB） |
| 中间版 | 2024-12-30 | 经典 SSR（同上，结构完全一致） | 同上 | `research/_browse_2024.html`（128KB） |
| 新版 | 2026-09-13 | **React SSR**（`window.SSR.loaderData` 脱水 JSON） | React checkbox `<div>` | `research/_browse_snapshot.html`（683KB） |

三个快照均为 `https://steamcommunity.com/workshop/browse/?appid=4000`（Garry's Mod）。

---

## 0. 结论先行（推翻当前实现的核心假设）

**当前 `page_parser.py` 的整个提取策略建立在错误前提上。** 它假设浏览页侧栏存在 `<a href="...&requiredtags=<Tag>">Tag</a>` 链接，容器是 `id="tagFilter"` / `class="tagFilter"` / `class="browseFilter"`。

**三个真实快照中这些全部不存在，从未存在过：**

| 当前代码假设的锚点 | 2022 旧版 | 2024 中间版 | 2026 新版 |
|---|---|---|---|
| `<a href="…requiredtags=X">` 链接 | ❌ 0 处 | ❌ 0 处 | ❌ 0 处 |
| `id="tagFilter"` | ❌ 0 处 | ❌ 0 处 | ❌ 0 处 |
| `class="tagFilter"` | ❌ | ❌ | ❌ |
| `class="browseFilter"` | ❌ 0 处 | ❌ 0 处 | ❌ 0 处 |
| `requiredtags` 关键字 | 仅作为 checkbox 的 `name="requiredtags[]"` | 同左 | ❌ 0 处（连字符串都没有） |

**bug 根因**：容器锚点三级全部匹配失败 → 进入"全页面兜底扫描" → `_extract_tag_from_link` 对每条 `<a>` 链接，只要 href 里没有 requiredtags 就**回退用链接文本当标签名** → 于是页面上所有导航/页脚链接的文本（商店、创意工坊、cookie 设置、隐私政策…）全被当成标签。`tag_bar.py` 里的 `_NAV_TAGS` 黑名单能滤掉一部分，但黑名单永远追不上页面变更，且会误伤真标签。

---

## 1. 标签筛选侧栏的真实 HTML 结构

### 1.1 旧版/中间版（经典 SSR，2022 与 2024 结构完全一致）

侧栏容器层级（真实）：

```
<div id="rightContents" class="browsePage responsive_local_menu">
  <div class="sidebar">
    <div class="panel">
      <div class="rightSectionHolder">
        <div class="rightDetailsBlock">
          <form id="TagsFilterForm" name="TagsFilterForm" class="smallForm searchForm"
                method="GET" action="https://steamcommunity.com/workshop/browse/">
            <input type="hidden" name="appid" value="4000">
            <input type="hidden" name="browsesort" value="trend">
            <input type="hidden" name="section" value="readytouseitems">
            ...
            <div class="tagSearch">Show items tagged with all of the selected terms:</div>
            <div class="tag_category_desc">Content Type</div>
              <select class="selectTagsFilter" name="requiredtags[]" onchange="FilterByTags();">
                <option value="-1">< none specified ></option>
                <option value="Addon">Addon</option>
                <option value="Save">Save</option>
                <option value="Dupe">Dupe</option>
                <option value="Demo">Demo</option>
              </select>
            <div class="tag_category_desc">Addon Type</div>
              <div class="filterOption">
                <label for="12143">
                  <input type="checkbox" name="requiredtags[]" id="12143"
                         value="Gamemode" class="inputTagsFilter"
                         onclick="IncludeTag( this );" />
                  Gamemode
                </label>
                <span id="excludetag_12143" class="tag_filter_control_not"
                      data-tagid="12143" data-tag="Gamemode" …/>
              </div>
              ... (每个标签一个 filterOption)
```

**可靠锚点（经典版）**：
- 表单：`<form id="TagsFilterForm">`（唯一、稳定、跨 2022/2024 不变）
- 标签项：`<input type="checkbox" name="requiredtags[]" value="<标签名>" class="inputTagsFilter">`
- 分类标题：`<div class="tag_category_desc">Addon Type</div>`
- 排除按钮带 `data-tag="<标签名>"`（冗余佐证）
- 分类下拉：`<select class="selectTagsFilter" name="requiredtags[]">` 的 `<option value="…">`（Content Type 分类，非具体标签，可选是否纳入）

### 1.2 新版（2026 React SSR）

整页是 React SSR，类名全部混淆（如 `_5CceBD1-9Kg-`、`EnFuoPFRUQw-`），**但数据在脱水 JSON 里，比 HTML 可靠得多**：

```html
<script nonce="…">window.SSR={};window.SSR.loaderData = ["{…JSON字符串…}", "{…}", "{…}"];</script>
```

`loaderData` 是 JSON 字符串数组（3 个元素），第 2 个元素（item1）包含完整标签体系，顶层键：

```
app, appHubHeader, workshopConfig, strExistingSearchText,
existingSearchTextTarget, declaredTags, userAccess, userPreferences
```

**`declaredTags` 就是标签筛选的权威数据源**，结构（Garry's Mod appid=4000 实测）：

```
declaredTags: {
  guide_tags:        [ {name, htmlelement, tags:[{id,name,display_name,admin_only}…] }, … ],   // 3 组
  video_tags:        [],
  screenshot_tags:   [],
  image_tags:        [ 1 组 ],      // Meme, Poster
  merch_tags:        [ 5 组 ],
  mtx_tags:          [ 5 组 ],
  readytouse_tags:   [ 5 组 ],      // ← 浏览页 Addons section 实际渲染的就是这个
  collection_tags:   [ 5 组 ],
  visible_admin_tags:[]
}
```

`readytouse_tags` 的 5 个分组（name + htmlelement + 标签名）：

| 分组名 | 控件类型 | 标签（value/name） |
|---|---|---|
| Content Type | select | Addon, Save, Dupe, Demo |
| Addon Type | checkbox | Gamemode, Map, Weapon, Vehicle, NPC, Tool, Entity, Effects, Model, ServerContent |
| Addon Tags | checkbox | Build, Cartoon, Comic, Fun, Movie, Roleplay, Scenic, Realism, Water |
| Dupe Tags | checkbox | Buildings, Machines, Posed, Scenes, Vehicles, Others |
| Save Tags | checkbox | Buildings, Courses, Machines, Scenes, Others |

每个 tag 对象：`{"id":"12143","name":"Gamemode","display_name":"Gamemode","admin_only":false}`。
注意 `name`（URL 值，如 `ServerContent`）与 `display_name`（显示文本，如 `Server content`）**可能不同**。

新版侧栏渲染出的 HTML（混淆类名、无 href、无 value 属性，标签名是 div 纯文本）：

```html
<div class="_5CceBD1-9Kg-">Addon Tags</div>           <!-- 分类标题 -->
…
<div class="EnFuoPFRUQw- JptcMEODeH0- Qhm6jOAQZog-" style="--direction:row">
  <div class="_2z6k50vGJ-A- Panel" tabindex="0" role="button">  <!-- 勾选框 SVG -->
  <div class="kx3XQJqkhPg- Panel" tabindex="0" role="button">   <!-- 排除框 SVG -->
  <div class="Panel" tabindex="0" role="button">Build</div>     <!-- 标签名=纯文本 -->
</div>
```

**新版侧栏分区标题（实测）**：`Special Filters:` / `Content Type` / `Addon Type` / `Addon Tags` / `Dupe Tags` / `Save Tags` —— 与 `readytouse_tags` 的分组一一对应。

---

## 2. 标签链接的真实格式与标签计数

### 2.1 `requiredtags` 链接只出现在**详情页**，不在浏览页

项目自有 fixture（真实抓取的详情页）证实，`requiredtags` 链接存在于详情页的标签区块：

```html
<div data-panel="{…PanelGroup…}" class="workshopTags">
  <span class="workshopTagsTitle">Addon Type:&nbsp;</span>
  <a href="https://steamcommunity.com/workshop/browse/?appid=4000&browsesort=toprated
           &section=readytouseitems&requiredtags%5B%5D=Map">Map</a>
</div>
```

- 格式：`requiredtags%5B%5D=<Tag>`（**数组写法 `[]` 的 URL 编码**，不是 `requiredtags=Map` 单值写法）
- 容器：`class="workshopTags"`，标题：`class="workshopTagsTitle"`
- 该链接是"点击跳转到浏览页并按此标签筛选"，属于详情页的导航功能

> **`page_parser.py` 注释里"单值参数 `requiredtags=<tag>`"的说法，在三个浏览页快照中均无实证；浏览页的 URL 参数（旧版 form 提交时）是 `requiredtags[]=Map` 数组形式。** 详情页 fixture 实测也是数组形式。单值写法缺乏依据。

### 2.2 标签计数（热度）：**浏览页不存在，无法获取**

三个真实快照逐一核查：

| 检测项 | 2022 旧版 | 2024 中间版 | 2026 新版 |
|---|---|---|---|
| `(1234)` / `(1,234)` 括号计数文本 | 0 处 | 0 处 | 0 处 |
| `count` / `tagCount` 字段 | 0 处 | 0 处 | 0 处 |
| 结果总数文本 | 仅 tooltip "Exclude results with this tag: X" | 同左 | 0 处 |

**结论**：浏览页标签筛选侧栏**从不显示每个标签的 mod 数量**。`parse_available_tags_with_counts` 期望的 `(N)` 计数在浏览页不存在，`TagChip` 的热度计数数据源必须另寻（例如按标签逐个查询 `GetPublishedFileDetails`/`QueryFiles` 统计，代价高），或直接弃置计数显示。

---

## 3. 新版 React 数据：不是 React Query dehydration

新版用的是 **React Router 风格的 loader 数据脱水**（`window.SSR.loaderData`），**不是** React Query 的 dehydration（无 `queryClient` / `queries` 数组 / `dehydratedState`）。

- 字段名：`window.SSR.loaderData`（JSON 字符串数组，需二次 `JSON.loads`）
- 标签数据路径：`loaderData[1]` → `declaredTags` → `<section>_tags` → 各分组 `tags[]`
- 每项 tag：`{id, name, display_name, admin_only}`
- 另有 `workshopConfig` 含 `tags_as_tabs`（本次为空数组）、`section` 等配置

混淆类名（`tK5agp5sRy8-` 这类）每次构建变化，**绝不可用作锚点**；但 `window.SSR.loaderData` 这个全局变量名、以及 `declaredTags` / `readytouse_tags` 等字段名是业务语义命名，稳定可依赖（至少本快照如此；仍建议加兜底）。

---

## 4. 如何可靠区分"标签筛选项"与"导航/页脚链接"

**核心判据：标签筛选项在浏览页根本不是 `<a>` 链接。**

| 判据 | 说明 | 可靠性 |
|---|---|---|
| **A. 结构判据（首选）** | 旧版：`<input type="checkbox" name="requiredtags[]">` 且 `class="inputTagsFilter"`，位于 `#TagsFilterForm` 表单内；新版：`declaredTags` JSON 中的 `readytouse_tags` 分组 | ★★★★★ 唯一锚点 |
| **B. 禁止文本回退** | 提取标签名时**只用 input 的 `value` 属性 / JSON 的 `name` 字段**，绝不回退到元素文本或 `<a>` 链接文本 | ★★★★★ 这是 bug 的直接根源 |
| C. 域名判据（辅助） | 标签链接（详情页场景）href 必含 `steamcommunity.com/workshop/browse?` 且带 `requiredtags%5B%5D=` | ★★★☆☆ 仅详情页场景 |
| D. 黑名单（最后防线） | `_NAV_TAGS`/`_LEGAL_KEYWORDS` 保留，但降级为"异常兜底"而非主防线 | ★★☆☆☆ 不可单独依赖 |

**为什么黑名单路线是错的**：真标签集是游戏自定义的（GMod 有 34 个 Addon 标签，其它游戏完全不同），黑名单既无法覆盖所有导航文案变体（多语言、A-B 测试、新版导航），也可能误杀真标签（例如某游戏若有叫 "Fun" 的导航项就会被误滤）。结构锚点一次性解决两个方向的误判。

---

## 5. 建议的可靠定位策略（多级兜底，按优先级）

```
①【新版·JSON 优先】定位 window.SSR.loaderData → JSON.parse 两轮 →
   item 中含 declaredTags 的那个 → declaredTags.readytouse_tags[*].tags[*].name
   （Content Type 那组是 select 分类，按需决定是否纳入；section 可由 URL 参数或
    workshopConfig 确定，GMod 默认 readytouseitems）

②【旧版·表单锚点】定位 <form id="TagsFilterForm"> → 表单范围内所有
   <input type="checkbox" name="requiredtags[]" class="inputTagsFilter"> 取 value
   （不取 label 文本；label 文本可能与 value 不同，如 "Server content" vs "ServerContent"）
   分类下拉 <select class="selectTagsFilter"> 的 option value 同样是合法 requiredtags 值

③【旧版·宽兜底】无 #TagsFilterForm 时，全页面扫描
   <input[^>]*name="requiredtags[]"[^>]*value="…"> （属性级匹配，不用链接文本）

④【最终兜底】全部失败 → 返回空列表 + 状态栏提示（当前 tag_bar.py 已有此 UI 通道）。
   ★绝不再退化到"扫描所有 <a> 取文本"★ —— 这正是 bug 本身。
```

要点：
- **标签名来源只能是 `value` 属性 / JSON `name` 字段**，不能是显示文本（display_name 与 name 可能不同，如 `ServerContent` ↔ `Server content`、`Others` ↔ `Other`）。UI 显示用 display_name，拼接筛选 URL 用 name —— 新版 JSON 两个字段都有，应分别使用。
- 新版 JSON 解析需两次反序列化（loaderData 元素本身是 JSON 字符串）。
- 新版页面的渲染 HTML（混淆类名的 checkbox div）不作为解析目标，只作为 ① 失败时的最后验证手段（分类标题 `_5CceBD1-9Kg-` 的文本可对照）。

---

## 6. 各问题的明确回答

| # | 问题 | 回答 |
|---|---|---|
| 1 | 标签筛选侧栏容器真实 id/class | **旧版**：表单 `id="TagsFilterForm"`（class `smallForm searchForm`）；标签项容器 `class="filterOption"`；分类标题 `class="tag_category_desc"`；输入框 `class="inputTagsFilter"`。**新版**：React 混淆类名（`_5CceBD1-9Kg-` 等，不稳定）；权威数据在 `window.SSR.loaderData[·].declaredTags`。**`tagFilter`/`browseFilter` 从未存在过。** |
| 2 | 标签链接真实格式 | 浏览页**没有 requiredtags 链接**；旧版是 `<input type="checkbox" name="requiredtags[]" value="Map">`；`requiredtags%5B%5D=Map` 数组形式链接只出现在**详情页** `class="workshopTags"` 区块。**标签计数：浏览页不存在，三快照实测 0 处 —— 无法获取。** |
| 3 | 新版是否 React Query dehydration | **否**。是 React Router 风格 loader 脱水：`window.SSR.loaderData`（JSON 字符串数组）；字段名 `declaredTags` → `readytouse_tags` 等分组 → `tags[]` 每项 `{id, name, display_name, admin_only}`。 |
| 4 | 区分标签与导航项的可靠锚点 | 标签项是 `name="requiredtags[]"` 的 checkbox input（旧版）或 declaredTags JSON（新版），**不是 `<a>` 链接**；标签名只取 `value`/`name` 字段，**禁止回退链接文本**。 |

---

## 7. 无法确认 / 需联网验证的事项

1. **新版 `window.SSR.loaderData` 的稳定性**：字段名（`declaredTags` / `readytouse_tags`）是业务命名，理论上比混淆类名稳定，但**未来重构仍可能改名**；建议 ① 失败时保留旧版 input 兜底，两者都失败再报空。
2. **各 section 与 `declaredTags` 分组的映射**：本次只验证了 GMod 默认 `section=readytouseitems` → `readytouse_tags`。其它 section（collections、guides 等）与分组键的对应关系未逐一验证（guide_tags / collection_tags / image_tags 等键已确认存在，映射规则按命名推断，标注为**推断未实测**）。
3. **标签计数的数据来源**：浏览页确认无计数。若产品必须展示热度，需按标签逐项查询统计（API 代价高），或改用其它展示形式。无现成接口。
4. **当前生产环境实际返回的是哪一版**：本次快照来自 Wayback Machine（2026-09-13）。本机无法直连 steamcommunity.com，**无法确认用户当前访问时返回新版还是旧版**（Steam 可能按账号/灰度/UA 分流）。因此实现必须**同时兼容两套结构**，按上面 §5 的优先级兜底。
5. `requiredtags=<Tag>` **单值**写法的出处：当前代码注释声称实测自 appid=730 的链接，本次三快照与项目 fixture 均未见到单值写法；只有数组写法 `requiredtags%5B%5D=`。若该写法来自其它页面（如 hub 页），与浏览页标签提取无关。

---

## 附录：证据文件清单

- `research/_browse_snapshot.html` — 2026-09-13 新版 React SSR 浏览页（683KB，含 `window.SSR.loaderData`）
- `research/_browse_2024.html` — 2024-12-30 经典浏览页（128KB）
- `research/_browse_legacy.html` — 2022-12-17 经典浏览页（128KB，含 `#TagsFilterForm` 完整表单）
- `tests/fixtures/detail_4000_3803871160.html` — 项目自有真实详情页（含 `class="workshopTags"` + `requiredtags%5B%5D=` 链接，证明该链接形态属详情页）

（快照来源：`https://web.archive.org/web/<timestamp>id_/https://steamcommunity.com/workshop/browse/?appid=4000`）
