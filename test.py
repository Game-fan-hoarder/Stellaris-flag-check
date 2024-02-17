import zipfile
import tempfile
import shutil
from pathlib import Path

TARGET_PATH = ""

GAMESTATE = "gamestate"



temp_dir = tempfile.mktemp()

try:
    with zipfile.ZipFile(TARGET_PATH, 'r') as zipfile:
        zipfile.extractall(temp_dir)

    relevant_content = Path(temp_dir).joinpath(GAMESTATE)
    with open(relevant_content, 'r') as gamestate_file:
        all_content = gamestate_file.read()

    print("ok")

finally:
    shutil.rmtree(temp_dir)