<p align="center">
  <img src="docs/assets/order-of-the-sinking-star-store.jpg" width="560" alt="沉星之序 Steam 商店横图：朝左的戴冠人物">
</p>

<h1 align="center">Editor-of-the-Sinking-Star</h1>

<p align="center"><strong>《沉星之序》游戏内录制与宏编辑器</strong></p>

> **预览版提示**  
> 本项目仍处于开发阶段，尚非正式版本。最近一次本机可运行验证：**2026-10-30**（启动及相关工具检查，非全场景或异机验收）。  
> 如遇问题，欢迎前往 [Issues](https://github.com/scenesuki/Editor-of-the-Sinking-Star/issues) 反馈，并提供版本与复现步骤。  

`0.1.0-preview` · `Windows 10 / 11 x64` · `中文 / English` · `MIT`

[下载预览版](https://github.com/scenesuki/Editor-of-the-Sinking-Star/releases/tag/v0.1.0-preview) · [English](README.en.md) · [使用细则](docs/使用细则.md) · [许可](licenses/LICENSE.md)

---

> **正常游玩录制 → 时间轴编辑 → 检查点试调 → 从头播放**  

## 功能一览

| 录制与编辑 | 存档与调试 |
| --- | --- |
| 游戏内双栏面板，短按录制与当前现场追加 | 固定工程起点，独立临时战役副本 |
| 手动添加、修改、删除、拖动及编辑撤销 | 检查点重复试调额外等待 |
| 跟随游戏键位，可配置工具键与鼠标切换键 | 工程内暂停、0.25×、1×、4× |
| 每工程独立保存间隔与等待值 | 独立的完整存档备份／恢复工具 |

## 快速开始

1. 从[预览版下载页](https://github.com/scenesuki/Editor-of-the-Sinking-Star/releases/tag/v0.1.0-preview)获取 `win-x64.zip` 与 `SHA256SUMS.txt`，校验后完整解压到可写文件夹，**无需安装 Python 或 Frida**；不要在 ZIP 内运行。
2. 关闭游戏与编辑器，先用 `SaveBackup.exe` 备份全部存档。
3. 打开受支持版本的游戏，运行 `SinkingStarEditor.exe`，点击“加载游戏内面板”。
4. 回到游戏，按一次**反引号／波浪号键**开启鼠标模式。新建工程后正常短按游玩，完成后结束录制并保存。

> **录制只用短按，不要长按。** 普通间隔默认 250ms，额外等待默认 1000ms，相加为 1250ms；各工程可独立调整。

**源码开发：** 克隆仓库后按[源码运行与构建](docs/BUILD.zh-CN.md)操作；仓库本身不包含 EXE。

## 便携包内文件

| 文件／目录 | 用途 |
| --- | --- |
| `SinkingStarEditor.exe` | 从这里开始：加载游戏内编辑器 |
| `SaveBackup.exe` | 独立存档备份／恢复；先关闭游戏及编辑器 |
| `README.md` / `README.en.md` | 中文／英文首页 |
| `docs/` | 中英文使用细则及页首图片 |
| `licenses/` | MIT 与第三方许可原文 |
| `metadata/` | 构建信息、逐文件校验清单 |
| `_internal/`、`SSEKeyWorker.exe`、`portable.json` | 必需运行文件，保持原位；输入助手无需手动启动 |
| `data/` | 首次运行后生成，保存你的工程、配置、日志与备份 |

**更新时保留 `data/`。** 不要将未结束的工程会话搬到另一台电脑；异常恢复规则见[使用细则](docs/使用细则.md)。

## 源码目录

| 目录 | 内容 |
| --- | --- |
| [assets/](assets/) | 商店横图与文档素材 |
| [docs/](docs/) | 中英使用细则与构建说明 |
| [licenses/](licenses/) | MIT 与第三方许可 |
| [locales/](locales/) | 中英文界面翻译 |
| [release/](release/) | 打包入口、配置与发行文稿 |
| [research/](research/) | 必需的游戏接口与覆盖层脚本 |
| [solution_editor/](solution_editor/) | 工程、录制、时间轴与存档管理 |
| [tests/](tests/) | 文件安全、备份与发行检查 |

## 当前边界

- **预览包禁用 P 快速完成。** 开发版保留实验代码，不作为可用功能承诺。
- 仅接受已登记的游戏构建；完整指纹、操作流程及恢复规则见 [使用细则](docs/使用细则.md)。
- 暂不支持工程跨设备迁移、自动播放调速、女王直选、长按／组合键及手柄录制。
- 已做相关工具与本机启动检查；异机兼容、游戏动作效果及路线结果仍由使用者试用判断。

## 下一步开发

本项目下一步开发的是按键P，其作用是在大地图快速完成关卡，开发其的目的是便于录制大地图的解密部分。目前已找到相关接口，但具体实现仍有待开发。

## 借鉴与致谢

感谢 [qiekn/ootss-cmd](https://github.com/qiekn/ootss-cmd)。本项目借鉴了其 **Solution Player / Editor** 的操作步骤编辑、按键回放及利用游戏原生撤销／重开的思路，并参考了游戏内存布局与调速资料。

`ootss-cmd` 不作为本项目的运行时依赖；原项目许可保留于 [ootss-cmd-LICENSE.txt](licenses/ootss-cmd-LICENSE.txt)。

---

自有源码采用 [MIT](licenses/LICENSE.md)；第三方条款见 [许可声明](licenses/THIRD_PARTY_NOTICES.md)。页首图片来自 [Steam 商店](https://store.steampowered.com/app/499170/)，相关权利归原权利人所有。不附游戏程序或用户存档，本项目不隶属于游戏开发方。
