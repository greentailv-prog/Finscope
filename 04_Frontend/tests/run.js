/* 一把跑完所有测试：node tests/run.js
 * 退出码 0 = 全绿，非 0 = 有失败（可直接接进 CI 或交付前检查脚本）。
 */
const { spawnSync } = require("child_process");
const path = require("path");

const SUITES = [
  { file: "data.test.js",   label: "数据层：格式化口径 / 取数 / 中文名 / 溯源反查" },
  { file: "render.test.js", label: "渲染层：六页 render() 实跑 + 页面结构断言" }
];

let failed = 0;

SUITES.forEach(function (s) {
  console.log("\n" + "=".repeat(72));
  console.log("▶ " + s.label);
  console.log("=".repeat(72));

  const r = spawnSync(process.execPath, [path.join(__dirname, s.file)], {
    stdio: "inherit"
  });
  if (r.status !== 0) failed++;
});

console.log("\n" + "=".repeat(72));
if (failed) {
  console.log("✗ " + failed + " 个测试文件未通过");
} else {
  console.log("✓ 全部通过");
}
process.exit(failed ? 1 : 0);
