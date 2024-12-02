#!/bin/bash

PROJECT_DIR="$(cd "$(dirname "$0")"; pwd)"
CONDA_ENV_NAME="capstone"

osascript <<EOF
tell application "Terminal"
    do script "cd '$PROJECT_DIR'; source ~/.zshrc; conda deactivate; conda activate $CONDA_ENV_NAME; python tests/server1.py"
    delay 1
    do script "cd '$PROJECT_DIR'; source ~/.zshrc; conda deactivate; conda activate $CONDA_ENV_NAME; python tests/server2.py"
    delay 1
    do script "cd '$PROJECT_DIR'; source ~/.zshrc; conda deactivate; conda activate $CONDA_ENV_NAME; python tests/server3.py"
    delay 1
    do script "cd '$PROJECT_DIR'; source ~/.zshrc; conda deactivate; conda activate $CONDA_ENV_NAME; python tests/client1.py"
end tell
EOF
