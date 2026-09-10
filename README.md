# Simple Remote (Windows-first, pronto para uso)

Sistema próprio de acesso remoto com:
- captura de tela remota
- controle de mouse/teclado
- autenticação por token
- pareamento por código + aprovação
- proteção por allowlist de IP
- TLS opcional (WSS)
- gerador de pacote `.zip` pronto para distribuição

## 1) Início rápido (sem instalador)

1. Instale dependências:
```bash
python -m pip install -r requirements.txt
```

2. Inicie host no modo pareamento (recomendado):
```bash
python host.py --host 0.0.0.0 --port 8765 --token "SEU_TOKEN_SEGURO" --pairing
```

3. No cliente, abra `viewer/index.html` no navegador.

4. No host, gere código:
```bash
curl http://IP_DO_HOST:8765/pair
```

5. Cole código no viewer e conecte.

6. Copie `sid` retornado e aprove:
```bash
curl "http://IP_DO_HOST:8765/approve?token=SEU_TOKEN_SEGURO&sid=SID"
```

7. A sessão começa automaticamente no cliente.

## 2) Opções de segurança e rede

```bash
python host.py \
  --host 0.0.0.0 --port 8765 \
  --token "SEU_TOKEN_SEGURO" \
  --pairing \
  --allow-ips "192.168.1.0/24,10.0.0.0/8" \
  --fps 12 \
  --ssl-cert cert.pem \
  --ssl-key key.pem
```

- `--allow-ips`: permite só redes/IPs informados (CSV)
- `--pairing`: exige código antes de conectar
- `--auto-approve`: aprova sessão automaticamente (use só em rede privada)

## 3) Configuração para produção simples

- Em produção:
  - `--ssl-cert` + `--ssl-key` com certificado válido
  - `--allow-ips` estrito
  - token aleatório alto e único
  - firewall permitindo só porta 8765 para IPs confiáveis

## 4) Modo de instalação (Windows)

Arquivos incluídos para instalação:
- `scripts/install.bat`
- `scripts/install.ps1`
- `scripts/start-host.bat`
- `scripts/start-host-pairing.bat`
- `scripts/start-viewer.bat`

Instalação (Windows):
```bash
scripts\\install.bat
```

- Isso cria ambiente virtual, instala dependências e cria atalhos no desktop:
  - `SimpleRemote - Host.lnk`
  - `SimpleRemote - Viewer.lnk`

## 5) Gerar pacote pronto (`.zip`) para distribuir

```bash
python host.py --package
```

Resultado:
- `simple-remote-package.zip` no diretório atual com:
  - `host.py`
  - `viewer/index.html`
  - `requirements.txt`
  - `README.md`
  - pasta `scripts/` completa

## 6) Instalação em qualquer computador (via nuvem, 1 comando)

1. Suba `simple-remote-package.zip` para uma URL pública:
   - OneDrive (link público)
   - Google Drive (link direto)
   - S3, GitHub Releases ou qualquer CDN

2. Em qualquer máquina Windows execute:

```powershell
$url = "https://SEU_LINK_PUBLICO/simple-remote-package.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Invoke-WebRequest -Uri $url -OutFile $env:TEMP\\simple-remote-package.zip; ^
   Expand-Archive -Path $env:TEMP\\simple-remote-package.zip -DestinationPath $env:TEMP\\simple-remote -Force; ^
   powershell -NoProfile -ExecutionPolicy Bypass -File $env:TEMP\\simple-remote\\scripts\\cloud-bootstrap.ps1 -PackageUrl $url -InstallDir 'C:\\Program Files\\SimpleRemote' -NoInteractive"
```

3. Comando equivalente (mais curto) se você já estiver com o bootstrap disponível em URL:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://SEU_LINK_BOOTSTRAP/cloud-bootstrap.ps1 -UseBasicParsing -OutFile $env:TEMP\\cloud-bootstrap.ps1; powershell -NoProfile -ExecutionPolicy Bypass -File $env:TEMP\\cloud-bootstrap.ps1 -PackageUrl $url -NoInteractive"
```

- `-Token` (opcional): define token de controle.
- `-InstallDir` (opcional): pasta de instalação.
- `-NoInteractive` (opcional): instala sem prompts.

## 7) Endpoints úteis

- `GET /pair`: gera código de pareamento (quando `--pairing`)
- `POST /pair`: consome código e retorna `sid`
- `GET /session-status?sid=...`: consulta aprovação
- `POST /approve?token=...&sid=...`: aprova sessão
- `GET /admin/sessions?token=...`: consulta status de códigos/sessões (admin)
- `GET /ws`: websocket remoto
- `GET /health`: check

## 7) Estrutura de arquivos

- `host.py`: serviço do host
- `viewer/index.html`: cliente web
- `scripts/*`: utilitários de execução/instalação
- `requirements.txt`: dependências