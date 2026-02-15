# Hotmart Downloader

Script pra baixar cursos da Hotmart. Baixa vídeos, PDFs e anexos embutidos.

## Origem

Baseado no gist do [@juvenal](https://gist.github.com/juvenal/2d9a822325769d30c45c635fbf388c1b) com melhorias pra downloads de PDFs embutidos do Google Drive.

## Por que precisa de subdomínio manual?

A API da Hotmart mudou (2026) e agora o endpoint `check_token` retorna `resources: []` vazio, mesmo quando você tem cursos comprados. Por isso o script precisa que você informe manualmente o subdomínio dos cursos no arquivo `config_cursos.py`. É um workaround até acharem outra forma de listar os cursos automaticamente.

## Requisitos

- Python 3.6+
- FFMPEG (precisa estar no PATH do sistema)
- Conexão estável se for baixar vídeos

## Como usar

1. Instale as dependências:
```bash
pip install -r requirements.txt
```

2. Edite `config_cursos.py` e adicione os subdomínios dos seus cursos:
```python
CURSOS_SUBDOMINIOS = ["nome-do-seu-curso"]
```

**Como achar o subdomínio:**
1. Vai em https://sun.hotmart.com/minhas-compras
2. Clica em "Acessar" no curso
3. Na URL você vai ver algo assim: `https://hotmart.com/pt-BR/club/punchneedlelucrativo/products/...`
4. O subdomínio é a parte depois de `/club/` e antes de `/products/` (no exemplo acima seria `punchneedlelucrativo`)

3. Roda:
```bash
python hotmark.py
```

Coloca seu email e senha da Hotmart quando pedir.

## O que baixa

- Vídeos (Hotmart, Vimeo, YouTube)
- Anexos normais (PDFs, arquivos zip, etc)
- PDFs embutidos do Google Drive (esses ficavam escondidos antes)
- Links de leitura complementar
- Descrições das aulas

Tudo organizado certinho em pastas por módulo e aula.

## Alguns detalhes

- Se der erro baixando anexo, tenta 3 vezes antes de desistir
- PDFs do Google Drive são salvos como `gdrive_xxxxx.pdf` na pasta Materiais
- Se já baixou antes, não baixa de novo (economiza tempo)
- Cria log de tudo que faz pra você poder acompanhar

## Avisos

- Use só pra cursos que você comprou
- Alguns cursos são pesados, vai demorar
- Precisa de bastante espaço em disco

## Problemas?

Se não funcionar:
1. Confere se o FFMPEG tá instalado (`ffmpeg -version` no terminal)
2. Vê se o email/senha tá certo
3. Olha o arquivo `log.txt` pra ver o erro

---

Projeto educacional. Use com responsabilidade.
