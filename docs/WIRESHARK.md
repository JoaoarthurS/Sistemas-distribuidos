# Roteiro de captura no Wireshark (com e sem criptografia)

Objetivo (item 4 do enunciado): mostrar uma **mensagem conhecida** trafegando
**legível** na execução de referência sem criptografia e **cifrada** na
execução com TLS, identificando os fluxos e explicando por que o conteúdo
fica protegido.

O servidor escuta nas duas portas ao mesmo tempo:

| Porta | Enlace | Uso na captura |
|---|---|---|
| **5000** | TCP puro | referência sem criptografia |
| **5443** | TLS 1.3 sobre TCP | comunicação protegida |

## 1. Preparação

1. Instale o Wireshark com o **Npcap**, marcando *"Support loopback traffic
   capture"* (necessário porque cliente e servidor estão na mesma máquina).
2. Abra o Wireshark e escolha a interface **Adapter for loopback traffic
   capture** (ou a placa de rede, se o cliente estiver em outra máquina —
   nesse caso inicie o servidor com `--host 0.0.0.0`).
3. Filtro de captura (opcional): `tcp port 5000 or tcp port 5443`.

## 2. Execução de referência — SEM criptografia (porta 5000)

1. Inicie o servidor: `python -m server`.
2. Comece a captura no Wireshark.
3. Abra um cliente sem TLS: `cd client && npm start -- --name=Carla --plain`
   (ou desmarque "Conexão segura" na tela de login).
4. Envie a mensagem conhecida, por exemplo:
   **`MENSAGEM-SECRETA-123 senha do wifi: sd2-unimontes`**.
5. Filtro de exibição: `tcp.port == 5000`.
6. Clique com o botão direito em um pacote → **Follow → TCP Stream**.

**O que aparece:** o JSON completo e legível, por exemplo
`{"type":"MSG","id":"…","from":"Carla","to":"*","content":"MENSAGEM-SECRETA-123 senha do wifi: sd2-unimontes",…}`.
O filtro `frame contains "MENSAGEM-SECRETA-123"` encontra o pacote.

> 📸 **Evidência 1:** captura do *Follow TCP Stream* com o texto legível.

## 3. Execução protegida — COM TLS (porta 5443)

1. Com a captura rodando, abra um cliente com TLS:
   `cd client && npm start -- --name=Ana` (porta 5443, padrão).
2. Envie **a mesma mensagem**: `MENSAGEM-SECRETA-123 senha do wifi: sd2-unimontes`.
3. Filtro de exibição: `tcp.port == 5443` (ou `tls`).
4. Procure a mensagem: `frame contains "MENSAGEM-SECRETA-123"` → **nenhum resultado**.
5. *Follow → TCP Stream* mostra apenas bytes aleatórios.

**O que aparece:**

| Pacotes | Conteúdo visível |
|---|---|
| Client Hello | versão, suítes de cifra oferecidas, extensão `key_share` (chave pública efêmera X25519/ECDHE) |
| Server Hello | suíte escolhida (`TLS_AES_256_GCM_SHA384`) e a chave efêmera do servidor |
| Change Cipher Spec / Application Data | **tudo o mais** — inclusive o certificado do servidor (no TLS 1.3 ele já vai cifrado) e todos os quadros JSON |

> 📸 **Evidência 2:** lista de pacotes com `Application Data` e o *Follow TCP Stream* ilegível.

## 4. Identificação dos fluxos

Cada conexão é um fluxo TCP identificado pela quádrupla
`(IP cliente, porta efêmera do cliente) ↔ (IP servidor, porta do servidor)`:

- Use **Statistics → Conversations → TCP** para listar os fluxos.
- A porta efêmera de cada cliente aparece no **painel do servidor**
  (`http://127.0.0.1:8080`, coluna *Participantes*, ex.: `127.0.0.1:51586`)
  e na gaveta **Conexão e protocolo** do cliente (campo *Endereço local*).
  Assim dá para dizer qual fluxo é da Ana, do Bruno, da Carla e do bot.
- O filtro `tcp.stream eq N` isola um fluxo.

Exemplo de tabela para o relatório:

| Fluxo | Cliente | Porta cliente → servidor | Protegido? |
|---|---|---|---|
| 0 | bot | 51059 → 5443 | sim (TLS 1.3) |
| 1 | Ana | 51586 → 5443 | sim (TLS 1.3) |
| 2 | Bruno | 51583 → 5443 | sim (TLS 1.3) |
| 3 | Carla | 51584 → 5000 | **não** (referência) |

## 5. Por que o conteúdo fica protegido

1. **Troca de chaves efêmera (ECDHE/X25519):** no handshake, cliente e
   servidor trocam chaves públicas temporárias e derivam um segredo comum que
   **nunca trafega na rede**. Quem só observa os pacotes não consegue
   calculá-lo (problema do logaritmo discreto em curvas elípticas). Por ser
   efêmera, a chave também garante *forward secrecy*: vazar a chave privada
   do servidor depois não revela capturas antigas.
2. **Autenticação do servidor:** o servidor assina o handshake com a chave
   privada do certificado `server.crt`. O cliente só aceita se o certificado
   foi emitido pela CA configurada (`ca.crt`) **e** se o nome/IP acessado
   está no SAN. Isso impede um intermediário (*man-in-the-middle*) de se
   passar pelo servidor.
3. **Cifra autenticada AES-256-GCM:** cada registro TLS é cifrado e recebe uma
   etiqueta de autenticação. Sem a chave, o conteúdo é indistinguível de
   bytes aleatórios, e qualquer alteração faz a verificação falhar e a
   conexão ser encerrada.

**Onde ocorre a decifragem:** dentro do processo do **servidor**, na thread
leitora da conexão (`ssl.SSLSocket.recv`), antes da delimitação dos quadros.
O servidor precisa do texto para rotear (ler `to`, detectar `@bot`) e então
**cifra de novo** com a chave da conexão do destinatário. Portanto a proteção é
**por enlace (cliente↔servidor)**, não ponta a ponta: o servidor é confiável
e enxerga o conteúdo. Se o destinatário estiver na porta 5000 (Carla), o
trecho servidor→Carla vai em texto puro — por isso a interface do cliente
avisa quando o outro participante não usa TLS.

## 6. (Opcional) Provar que os dados estão lá — decifrando com as chaves

Para mostrar que a captura cifrada contém de fato a mensagem, inicie o
servidor exportando as chaves de sessão **apenas neste teste**:

```bat
set SSLKEYLOGFILE=%CD%\sslkeys.txt
python -m server
```

No Wireshark: **Edit → Preferences → Protocols → TLS → (Pre)-Master-Secret
log filename** → selecione `sslkeys.txt`. Os pacotes `Application Data`
passam a mostrar o JSON. Sem esse arquivo (que só existe nas pontas), a mesma
captura continua ilegível — é exatamente isso que protege a comunicação.
Apague `sslkeys.txt` depois.
