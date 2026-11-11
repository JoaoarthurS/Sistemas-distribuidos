@echo off
rem ==========================================================================
rem  SD Chat - demonstracao completa no Windows
rem  Abre: servidor (+ painel no navegador), bot com LLM e 3 clientes humanos
rem        Ana (TLS), Bruno (TLS) e Carla (TCP sem criptografia, referencia).
rem  Pre-requisitos: Python 3.10+, Node.js 18+, Ollama com qwen3.5:4b.
rem ==========================================================================
chcp 65001 >nul
cd /d "%~dp0"

if not exist "certs\server.crt" (
  echo [1/3] Gerando certificados de teste...
  python -m pip install --quiet cryptography
  python certs\gen_certs.py || goto :erro
)

if not exist "client\node_modules\electron" (
  echo [2/3] Instalando o cliente Electron ^(npm install^)...
  pushd client
  call npm install || (popd & goto :erro)
  popd
)

echo [3/3] Iniciando componentes...
start "SD Chat - Servidor" cmd /k python -m server
timeout /t 2 /nobreak >nul
start "SD Chat - Bot (LLM)" cmd /k python -m bot
timeout /t 3 /nobreak >nul

start "Ana" /min cmd /c "cd client && npm start -- --name=Ana --autoconnect"
start "Bruno" /min cmd /c "cd client && npm start -- --name=Bruno --autoconnect"
start "Carla" /min cmd /c "cd client && npm start -- --name=Carla --plain --autoconnect"

echo.
echo Pronto! Painel do servidor: http://127.0.0.1:8080/
echo Feche as janelas para encerrar.
exit /b 0

:erro
echo.
echo Falha na preparacao. Veja as mensagens acima.
pause
exit /b 1
