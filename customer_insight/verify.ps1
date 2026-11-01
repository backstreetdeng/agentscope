# 用户洞察智能体 · 开发期校验入口（只读，不写库、不改业务数据）
# 用法：从任意目录运行本脚本；它会定位项目根并执行本包测试。
# 说明：项目现有测试统一用 stdlib unittest（requirements.txt 无 pytest），本入口沿用该约定。

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$Python = Join-Path (Split-Path -Parent $ProjectRoot) 'Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw "未找到 Python 解释器：$Python"
}

Set-Location $ProjectRoot
& $Python -B -m unittest discover -s customer_insight/tests -p "test_*.py" -v
exit $LASTEXITCODE
