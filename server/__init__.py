"""
Servidor do SD Chat.

Organização (uma responsabilidade por módulo):

    config.py       ServerConfig — parâmetros imutáveis do servidor
    validation.py   regras de nome, HELLO e menções (@bot)
    monitor.py      estatísticas e feed de eventos/mensagens para o painel
    connection.py   ClientConnection — threads leitora/escritora de um socket
    registry.py     ClientRegistry — participantes conectados (thread-safe)
    sessions.py     SessionManager — entrada (HELLO/WELCOME) e saída
    router.py       MessageRouter — despacho de quadros por tipo
    bot_broker.py   BotBroker — solicitações ao bot, correlação e tempo limite
    listener.py     TcpListener — socket de escuta + thread que aceita conexões
    chat_server.py  ChatServer — compõe as peças e controla o ciclo de vida
    dashboard/      interface gráfica (painel web servido por HTTP + SSE)
    cli.py          linha de comando (raiz de composição)

Uso:  python -m server [--help]
"""
