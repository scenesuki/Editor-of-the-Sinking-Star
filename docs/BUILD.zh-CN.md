# 从源码运行与构建

Windows 10／11 x64，Python 3.11 x64（含 Tkinter）。**源码包不含 EXE 和第三方运行时**；仅阅读说明不需要安装依赖。

## 运行

在源码根目录打开 PowerShell：

```powershell
python -m pip install --target .deps -r requirements.txt
$env:PYTHONPATH=".;.deps"
python -B release/entry.py
```

仅检查启动依赖、不连接游戏：

```powershell
python -B release/entry.py --diagnostics diagnostics.json
```

独立备份窗口：`python -B release/entry.py --backup`。实际使用流程见[使用细则](使用细则.md)；文中的 EXE 名称对应打包后的入口。

## 构建

```powershell
python -m pip install --target .build-deps -r release/requirements-build.txt
python -B release/build.py
```

构建中间物在 `.build/`，交付文件在 `deliverables/`。程序 ZIP、源码 ZIP 和 `SHA256SUMS.txt` 一起生成。默认开启 Preview 限制，P 停用。

## 源码目录

| 目录／文件 | 用途 |
| --- | --- |
| `solution_editor/`、`research/` | Python 与 JS 运行源码；两者均为必需 |
| `locales/` | 中英文翻译 |
| `release/` | 构建入口、文稿与许可源文件 |
| `tests/` | 发行／备份的相关工具检查，不是游戏路线验收 |
| `assets/`、`docs/`、`licenses/`、`metadata/` | 文档素材、使用细则、许可和完整性清单 |
| `portable.json`、`release_profile.json` | 便携数据与 Preview 配置，保留原位 |
| `data/` | 运行后生成的个人数据，更新时保留 |

不含游戏程序、用户存档或开发机数据。存档保护、原生读档语义及已知边界见[使用细则](使用细则.md)。
