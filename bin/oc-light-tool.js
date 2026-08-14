#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const readline = require("node:readline/promises");

const PACKAGE_ROOT = path.resolve(__dirname, "..");
const SOURCE_PLUGIN = path.join(PACKAGE_ROOT, "plugin", "OctaneLightSolo");
const PLUGIN_FOLDER = "OctaneLightSolo";
const VERSION = fs.readFileSync(path.join(SOURCE_PLUGIN, "VERSION"), "utf8").trim();
const PROFILE_PATTERN = /^Maxon Cinema 4D 2026(?:_|$)/i;

function maxonRoot() {
  if (process.env.OC_LIGHT_TOOL_MAXON_ROOT) {
    return path.resolve(process.env.OC_LIGHT_TOOL_MAXON_ROOT);
  }
  if (process.platform !== "win32") {
    throw new Error("当前安装器仅支持 Windows 版 Cinema 4D 2026。");
  }
  const appData = process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming");
  return path.join(appData, "MAXON");
}

function parseArgs(argv) {
  const result = { command: "install", all: false, profile: null };
  const args = argv.slice(2);
  if (args[0] && !args[0].startsWith("-")) result.command = args.shift().toLowerCase();
  while (args.length) {
    const arg = args.shift();
    if (arg === "--all") result.all = true;
    else if (arg === "--profile") {
      if (!args.length) throw new Error("--profile 后面需要填写配置目录名称。");
      result.profile = args.shift();
    } else if (arg === "--help" || arg === "-h") result.command = "help";
    else throw new Error(`未知参数：${arg}`);
  }
  return result;
}

function discoverProfiles(root) {
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && PROFILE_PATTERN.test(entry.name))
    .map((entry) => ({ name: entry.name, dir: path.join(root, entry.name) }))
    .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
}

async function chooseProfiles(root, options) {
  const profiles = discoverProfiles(root);
  if (!profiles.length) {
    throw new Error(`未找到 Cinema 4D 2026 配置目录：${root}\n请先启动一次 Cinema 4D 2026。`);
  }
  if (options.profile) {
    const exact = profiles.find((item) => item.name.toLowerCase() === options.profile.toLowerCase());
    if (!exact) throw new Error(`找不到配置目录：${options.profile}`);
    return [exact];
  }
  if (options.all || profiles.length === 1) return options.all ? profiles : [profiles[0]];
  if (!process.stdin.isTTY) {
    throw new Error("检测到多个 C4D 2026 配置目录，请使用 --all 或 --profile \"目录名称\"。");
  }
  console.log("检测到多个 Cinema 4D 2026 配置：");
  profiles.forEach((item, index) => console.log(`  ${index + 1}. ${item.name}`));
  const terminal = readline.createInterface({ input: process.stdin, output: process.stdout });
  const answer = await terminal.question("请选择序号（直接回车安装到全部）：");
  terminal.close();
  if (!answer.trim()) return profiles;
  const index = Number(answer) - 1;
  if (!Number.isInteger(index) || !profiles[index]) throw new Error("选择无效。");
  return [profiles[index]];
}

function installedVersion(target) {
  const versionFile = path.join(target, "VERSION");
  if (!fs.existsSync(target)) return null;
  if (!fs.existsSync(versionFile)) return "旧版/未知";
  return fs.readFileSync(versionFile, "utf8").trim() || "未知";
}

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function backupTarget(root, profile, target) {
  if (!fs.existsSync(target)) return null;
  const backupDir = path.join(root, "OC-Light-Tool-Backups", profile.name, timestamp());
  fs.mkdirSync(backupDir, { recursive: true });
  const destination = path.join(backupDir, PLUGIN_FOLDER);
  fs.renameSync(target, destination);
  return destination;
}

function installOne(root, profile) {
  const pluginsDir = path.join(profile.dir, "plugins");
  const target = path.join(pluginsDir, PLUGIN_FOLDER);
  const staging = path.join(pluginsDir, `${PLUGIN_FOLDER}.installing-${process.pid}`);
  fs.mkdirSync(pluginsDir, { recursive: true });
  if (fs.existsSync(staging)) fs.rmSync(staging, { recursive: true, force: true });
  fs.cpSync(SOURCE_PLUGIN, staging, { recursive: true, errorOnExist: true });
  let backup = null;
  try {
    backup = backupTarget(root, profile, target);
    fs.renameSync(staging, target);
  } catch (error) {
    if (fs.existsSync(staging)) fs.rmSync(staging, { recursive: true, force: true });
    if (backup && !fs.existsSync(target)) fs.renameSync(backup, target);
    throw error;
  }
  console.log(`✓ ${profile.name}：已安装 OC灯光工具 v${VERSION}`);
  if (backup) console.log(`  旧版备份：${backup}`);
}

function uninstallOne(root, profile) {
  const target = path.join(profile.dir, "plugins", PLUGIN_FOLDER);
  if (!fs.existsSync(target)) {
    console.log(`- ${profile.name}：未安装`);
    return;
  }
  const backup = backupTarget(root, profile, target);
  console.log(`✓ ${profile.name}：已卸载（可恢复备份：${backup}）`);
}

function statusOne(profile) {
  const target = path.join(profile.dir, "plugins", PLUGIN_FOLDER);
  const current = installedVersion(target);
  console.log(`${current ? "✓" : "-"} ${profile.name}：${current ? `已安装 v${current}` : "未安装"}`);
  if (current) console.log(`  ${target}`);
}

function showHelp() {
  console.log(`OC灯光工具安装器 v${VERSION}

用法：
  oc-light-tool install                 安装或更新
  oc-light-tool update                  与 install 相同
  oc-light-tool status                  查看安装状态
  oc-light-tool uninstall               卸载并保留备份

选项：
  --all                                 处理全部 C4D 2026 配置
  --profile "Maxon Cinema 4D 2026_xxx"  指定配置目录
  --help                                显示帮助`);
}

async function main() {
  const options = parseArgs(process.argv);
  if (options.command === "help") return showHelp();
  if (!["install", "update", "status", "uninstall"].includes(options.command)) {
    throw new Error(`未知命令：${options.command}`);
  }
  if (!fs.existsSync(SOURCE_PLUGIN)) throw new Error("安装包不完整：缺少 plugin/OctaneLightSolo。");
  const root = maxonRoot();
  const profiles = await chooseProfiles(root, options);
  for (const profile of profiles) {
    if (options.command === "status") statusOne(profile);
    else if (options.command === "uninstall") uninstallOne(root, profile);
    else installOne(root, profile);
  }
  if (options.command === "install" || options.command === "update") {
    console.log("完成。若 Cinema 4D 正在运行，请重启软件或执行“重载 Python 插件”。");
  }
}

main().catch((error) => {
  console.error(`安装器错误：${error.message}`);
  process.exitCode = 1;
});
