import zipfile
import tempfile
import shutil
import os
import platform
import warnings
import sqlite3
from pathlib import Path
from sqlite3 import Connection, Cursor
from typing import Iterable, Callable, Dict, Optional

import yaml

GAMESTATE = "gamestate"


def combine_multiple_savegames_folder(
        savegames_folder_iterable: Iterable[Path]) -> Iterable[Path]:
    """There are multiple place where the saves can be, therefore, we have
    to check for each location to not miss any of them.
    """
    for candidate_path in savegames_folder_iterable:
        # assume the user did not add custom files and folder there
        yield from candidate_path.glob("*")

def get_saves_folder() -> Iterable[Path]:
    """Return the stellaris save location"""
    # determine the platform
    system = platform.system()
    if system == "Windows":
        # WINDOWS
        base = Path(os.environ.get("USERPROFILE")) # search base
        target_1 = base.joinpath("Documents/Paradox Interactive/Stellaris/save games")
        target_2 = base.joinpath("Documents/Paradox Interactive/Stellaris Plaza/save games")
        return combine_multiple_savegames_folder([target_1, target_2])
    if system == "Darwin":
        # MAC
        target = Path(os.environ.get("HOME")).joinpath("Documents/Paradox Interactive/Stellaris/save games")
        return combine_multiple_savegames_folder([target])
    if system == "Linux":
        target_1 = Path(os.environ.get("HOME")).joinpath(".local/share/Paradox Interactive/Stellaris/save games")
        target_2 = Path(os.environ.get("$STEAMFOLDER")).joinpath(f"userdata/{os.environ.get('STEAMID')}/281990/remote/save games")
        target_3 = Path(os.environ.get("HOME")).joinpath(".local/share/Paradox Interactive/Stellaris Plaza/save games")
        return combine_multiple_savegames_folder([target_1, target_2, target_3])
    warnings.warn("Unrecognized system")

def recursivly_parse_flags(flag_amp:Dict, cursor: Cursor, upper_tag: Optional[str] = None):
    """
    TODO:
    :param flag_amp:
    :param cursor:
    :return:
    """
    # TODO: add one_of and any_of flag
    for key, value in flag_amp.items():
        if (key == "one_of") or (key == "any_of"):
            cursor.execute("""INSERT INTO one_of (tag_id) VALUES (?)""", (upper_tag,))
            # value is a list
            for subkey in value:
                recursivly_parse_flags(subkey, cursor, upper_tag)
        elif isinstance(value, dict):
            if "target" not in value.keys():
                # continue parsing
                cursor.execute("""INSERT INTO tags (tag_id, parent_tag_id, display) VALUES(?,?,?)""", (key, upper_tag, None))
                recursivly_parse_flags(value, cursor, key)
            else:
                # final parse
                cursor.execute("""INSERT INTO tags (tag_id, parent_tag_id, display, target) VALUES(?,?,?,?)""", (key, upper_tag, value["display"], value["target"]))


def load_flag_map(database_connection: Connection) -> Callable:
    """Loads flags pair from stellaris...
    Maybe next time, we will try to generate the flags.yaml instead of manually
    checking the flags but it too much work.
    """
    with open("flags.yaml", "r") as file:
        flag_map = yaml.safe_load(file)

    cursor = database_connection.cursor()

    recursivly_parse_flags(flag_map, cursor)

    database_connection.commit()
    cursor.close()

    def build_flags(save_state_content: str, save_id:str) -> Dict:
        """
        This is somewhat inefficient, need to check for performance later
        :param save_state_content:
        :return:
        """
        cursor = database_connection.cursor()
        cursor.execute("SELECT tags.tag_id, tags.target FROM tags WHERE tags.target IS NOT NULL")
        for tag_id, target in cursor.fetchall():
            if save_state_content.find(target)>0:
                # found
                cursor.execute("""INSERT INTO saves_tags (tag_id, save_id) VALUES (?,?)""", (tag_id, save_id))
        database_connection.commit()
        cursor.close()

    return build_flags

def init_database(database_dir):
    """Create a new database into a temp directory for searching."""
    connection = sqlite3.connect(Path(database_dir).joinpath("flags.db"))
    with open("database/init_script.sql", 'r') as migration_script:
        cursor = connection.cursor()
        cursor.executescript(migration_script.read())
        connection.commit()
        cursor.close()
    return connection

def get_flag_dict(dir_to_clean):
    """Get a dictionnary of flag_save pairs."""
    database_connection = init_database(dir_to_clean)
    call_function = load_flag_map(database_connection)
    for nation_save in get_saves_folder():
        with tempfile.TemporaryDirectory() as temp_dir:
            cursor = database_connection.cursor()
            save_id = nation_save.stem
            cursor.execute("""INSERT INTO saves (save_id, save_location) VALUES (?,?)""", (save_id, str(nation_save)))
            database_connection.commit()
            cursor.close()
            # assuming there may be multiple save, we only take the first one
            with zipfile.ZipFile(list(nation_save.glob("*.sav"))[0], 'r') as save_file:
                save_file.extractall(temp_dir)

            relevant_content = Path(temp_dir).joinpath(GAMESTATE)
            with open(relevant_content, 'r') as gamestate_file:
                all_content = gamestate_file.read()
                call_function(all_content, save_id)
    return database_connection

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp_dir:
        connection = get_flag_dict(temp_dir)
        connection.close()