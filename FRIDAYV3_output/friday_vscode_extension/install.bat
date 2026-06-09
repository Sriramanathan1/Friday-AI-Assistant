@echo off
echo.
echo  Installing FRIDAY VS Code Extension...
echo.

cd /d "%~dp0friday-vscode-extension"

echo  Installing dependencies...
call npm install

echo  Packaging extension...
call npx vsce package --no-dependencies -o friday-coding.vsix

echo  Installing into VS Code...
call code --install-extension friday-coding.vsix

echo.
echo  Done! Restart VS Code and say "coding mode" to activate FRIDAY.
echo.
pause
