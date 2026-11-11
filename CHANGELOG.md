# Histórico de versões

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
o versionamento segue [SemVer](https://semver.org/lang/pt-BR/).

## [1.0.0] — 2026-11-11

Primeira entrega do trabalho de Sistemas Distribuídos II.

### Adicionado
- Protocolo de aplicação NDJSON (JSON + `\n`) com remetente, destinatário,
  tipo, conteúdo e `req_id`; especificação em `docs/PROTOCOLO.md`.
- Servidor TCP/TLS com uma thread leitora e uma escritora por conexão,
  watchdog de solicitações ao bot e estruturas compartilhadas protegidas por lock.
- `SafeSocket`: acesso ao objeto SSL serializado entre threads (corrige
  falhas intermitentes do OpenSSL com leitura e escrita simultâneas).
- Painel web do servidor (interface gráfica) atualizado por Server-Sent Events:
  participantes, enlaces, mensagens, eventos, solicitações e threads.
- Cliente humano em Electron com interface estilo WhatsApp, socket `net`/`tls`
  do Node.js e validação explícita do certificado pela CA do projeto.
- Bot em processo separado com Qwen 3.5 4B (Q4_K_M) via Ollama: resposta
  privada em streaming, histórico de 4 turnos por usuário, comandos
  `/reset` e `/ajuda`, tempos limite de inatividade e de duração.
- Script de geração da CA de teste e do certificado do servidor.
- Testes unitários (Python e Node.js) e teste de integração com Ollama simulado.
- `demo.bat`, README, relatório-base e roteiro de captura no Wireshark.

### Arquitetura
- Código organizado segundo os princípios SOLID: módulos com responsabilidade
  única, tabelas de tratadores por tipo de quadro, interfaces pequenas
  (`ConnectionHandler`, `AdminService`, `ChatModel`) e raízes de composição
  nos pontos de entrada (`python -m server`, `python -m bot`, `npm start`).

[1.0.0]: https://github.com/JoaoarthurS/Sistemas-distribuidos/releases/tag/v1.0.0
