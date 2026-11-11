"""
Cliente bot do SD Chat (processo separado do servidor).

Organização (uma responsabilidade por módulo):

    config.py      BotConfig — parâmetros imutáveis do bot
    prompts.py     textos: prompt de sistema e ajuda
    errors.py      exceções da LLM (cada uma com seu código de protocolo)
    llm.py         ChatModel (abstração) + OllamaClient (implementação)
    history.py     HistoryStore — histórico curto e separado por usuário
    commands.py    CommandRegistry — comandos /reset, /ajuda...
    assistant.py   Assistant — regra de negócio (comandos, histórico, LLM)
    streaming.py   ChunkBuffer — agrupa tokens antes de enviar BOT_CHUNK
    connection.py  BotConnection — socket TLS, HELLO/WELCOME e envio seguro
    tracker.py     RequestTracker — solicitações em andamento e cancelamento
    app.py         ChatBot — sessão, reconexão, despacho de quadros e pool
    console.py     BotConsole — comandos digitados no terminal
    cli.py         linha de comando (raiz de composição)

Uso:  python -m bot [--help]
"""
