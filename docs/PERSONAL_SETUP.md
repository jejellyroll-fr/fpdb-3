# Personalizações do FPDB

Este fork mantém as personalizações na branch `personal`, baseada inicialmente
na versão upstream **v3.9.1**.

## Alterações

- Efeitos sonoros no hand replayer, com opção **Sound** e controle de volume.
- Preferências persistentes; volume inicial de 35%.
- Efeitos carregados da instalação local do PokerStars: check, fold, aposta,
  raise, distribuição de cartas, pilha de fichas para all-in e entrega do pote.
- Balanceamento de volume, preservando o timbre e o áudio estéreo.
- Reprodução ao avançar manualmente ou usar Play. Voltar e saltar na linha do
  tempo não reproduz uma sequência de efeitos; fechar o replayer interrompe o áudio.
- Comando de abertura, importador de mãos e atalho Linux reproduzíveis.

## Instalação Linux

Pré-requisitos: Git, `uv`, compilador C, CMake e `ffmpeg`. Python 3.13 é a versão
usada nesta instalação; `uv` pode baixar o interpretador automaticamente.

```bash
git clone https://github.com/thecrawler1/fpdb-3.git
```

Dentro do diretório do clone:

```bash
git switch personal
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e '.[linux]'
```

O ambiente `.venv` pertence a este clone. Se mover o clone, recrie o ambiente e
instale novamente os launchers.

### Configurar o PokerStars

Abra a aplicação uma vez para criar a configuração:

```bash
.venv/bin/fpdb_3_legacy
```

Em `~/.fpdb/HUD_config.xml`, configure o site `PokerStars` (ou use as preferências
de sites na interface):

- `screen_name`: seu nome de jogador.
- `HH_path`: a pasta dos históricos, usando o caminho Linux dentro do prefixo Wine.
- `site_path`: a pasta onde o PokerStars está instalado, usando o caminho Linux.

Exemplo genérico de prefixo Wine:

```text
site_path: ~/.local/share/wineprefixes/pokerstars/drive_c/Program Files (x86)/PokerStars/
HH_path:   ~/.local/share/wineprefixes/pokerstars/drive_c/users/SEU_USUARIO/AppData/Local/PokerStars/HandHistory/SEU_JOGADOR/
```

Substitua `~` pelo caminho absoluto de sua home nos atributos XML. A configuração
real e os dados pessoais ficam fora deste repositório.

Os efeitos são lidos de `site_path/Gx/table-view/audio/`. O `ffmpeg` prepara cópias
PCM no cache `~/.cache/fpdb/replayer-pokerstars-v2/` (ou em `$XDG_CACHE_HOME`).
O primeiro carregamento prepara os arquivos; os seguintes reutilizam o cache.
Mudanças nos arquivos do PokerStars geram novas entradas automaticamente.
Se a instalação ou o áudio não estiver disponível, o replayer continua funcionando
sem os efeitos. Os arquivos originais do PokerStars não são alterados.

### Instalar os comandos e o atalho

```bash
.venv/bin/python tools/install_personal_launchers.py
```

Isso instala:

- `~/.local/bin/fpdb`: abre este clone via X11/XWayland.
- `~/.local/bin/fpdb-import-pokerstars`: importa a pasta definida em `HH_path`.
- `~/.local/share/applications/fpdb.desktop`: atalho **FPDB 3**.

Launchers existentes com conteúdo diferente recebem um backup `.bak.TIMESTAMP`.
O instalador aceita `--config`, `--bin-dir` e `--applications-dir` para outros caminhos.
Inclua `~/.local/bin` no `PATH` para usar os comandos diretamente.

```bash
fpdb
fpdb-import-pokerstars
```

Usamos a instalação pelo código-fonte porque o pacote PyInstaller v3.9.1 apresentou
SIGSEGV neste Arch/Omarchy ao processar eventos de teclado. O core mostrou
`libxkbcommon` do pacote junto com `libxkbcommon-x11` do sistema; a incompatibilidade
entre essas bibliotecas é a causa provável. A instalação pelo código-fonte funcionou
na sessão validada pelo usuário.

## Acompanhar o projeto original

O remoto `origin` aponta para o fork; `upstream`, para o projeto original:

```bash
git remote add upstream https://github.com/jejellyroll-fr/fpdb-3.git
git fetch upstream --tags
```

Execute `remote add` apenas se `upstream` ainda não existir. Mantenha o diretório
de trabalho limpo antes de atualizar. Para adotar uma nova versão publicada:

```bash
git switch personal
git branch backup/personal-before-update
git merge vNOVA_VERSAO
```

Substitua `vNOVA_VERSAO` pela tag desejada e escolha outro nome de backup nas
atualizações seguintes. Resolva eventuais conflitos, atualize as dependências,
teste o replayer e então publique:

```bash
git push origin personal
```

Prefira merge para preservar os commits já publicados. A branch `development`
do upstream pode conter alterações posteriores à última versão publicada.

## Backup e dados locais

O Git registra código, testes e instruções de instalação. Mantenha um backup
separado de `~/.fpdb/` (configuração e banco), dos históricos do PokerStars e das
preferências de áudio em `~/.config/fpdb/replayer.conf`.

As preferências ficam no local escolhido pelo `QSettings`; no Linux o caminho
usual acima respeita `$XDG_CONFIG_HOME`. Os sons do PokerStars são carregados da
instalação local e não fazem parte do fork. O cache pode ser recriado.
