# OC灯光工具

面向 Cinema 4D 2026 + OctaneRender 的原生灯光管理面板。

## 一键安装

Windows 已安装 Node.js 时，在 PowerShell 或命令提示符运行：

```powershell
npx --yes github:kwok0304/oc-light-tool install
```

更新、查看状态和卸载：

```powershell
npx --yes github:kwok0304/oc-light-tool update
npx --yes github:kwok0304/oc-light-tool status
npx --yes github:kwok0304/oc-light-tool uninstall
```

安装器会自动查找 `%APPDATA%\MAXON\Maxon Cinema 4D 2026_*`。检测到多个配置时可交互选择，也可以使用 `--all` 或 `--profile "配置目录名称"`。

更新或卸载不会直接删除旧版，而会移入 `%APPDATA%\MAXON\OC-Light-Tool-Backups`。

## 功能

- 集中显示和管理场景中的 Octane 灯光
- 与 C4D 对象管理器双向同步单选和多选
- 多灯独显及全部恢复默认
- 功率滑条、动态最大值和精确数值输入
- 快速颜色设置与摄像机可见性
- 双击灯光名称重命名

## 兼容性

- Cinema 4D 2026.2+
- 当前已在 Cinema 4D 2026.3.0 与 Octane Studio+ 1.9.3 验证
- 安装器需要 Windows 和 Node.js 18+

## 快捷键

插件不会自动注册快捷键，以免覆盖用户现有配置。可在 C4D 命令管理器搜索“OC灯光工具”并自行分配。

