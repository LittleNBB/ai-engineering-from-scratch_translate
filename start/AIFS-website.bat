@echo off
:: AI Engineering from Scratch - Website Launcher
:: 启动本地 HTTP 服务器，用于预览网站

X:
cd X:\Projects\Python\ai-engineering-from-scratch\site

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║  AI Engineering from Scratch - Website           ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  服务器启动中...
echo  浏览器访问: http://localhost:8080
echo  按 Ctrl+C 停止服务器
echo.

python -m http.server 8080

pause