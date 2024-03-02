import logging
import os
import platform
import sqlite3
import tempfile
import warnings
import zipfile
from itertools import chain
from pathlib import Path
from sqlite3 import Connection, Cursor
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

import yaml
from tqdm import tqdm

GAMESTATE = "gamestate"


## CONSTANT REQUEST


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
        import winreg
        def read_reg(ep, p=r"", k=''):
            try:
                key = winreg.OpenKeyEx(ep, p)
                value = winreg.QueryValueEx(key, k)
                if key:
                    winreg.CloseKey(key)
                return value[0]
            except Exception as e:
                return None
            return None

        # WINDOWS
        base = Path(os.environ.get("USERPROFILE"))  # search base
        target_1 = base.joinpath("Documents/Paradox Interactive/Stellaris/save games")
        target_2 = base.joinpath("Documents/Paradox Interactive/Stellaris Plaza/save games")

        steam_path = str(read_reg(ep=winreg.HKEY_LOCAL_MACHINE, p=r"SOFTWARE\Wow6432Node\Valve\Steam", k='InstallPath'))
        targets_3 = [steam_user_path.joinpath("281990/remote/save games") for steam_user_path in
                     Path(steam_path).joinpath("userdata").glob("*")]
        return combine_multiple_savegames_folder([target_1, target_2, *targets_3])
    if system == "Darwin":
        # MAC
        target = Path(os.environ.get("HOME")).joinpath("Documents/Paradox Interactive/Stellaris/save games")
        return combine_multiple_savegames_folder([target])
    if system == "Linux":
        target_1 = Path(os.environ.get("HOME")).joinpath(".local/share/Paradox Interactive/Stellaris/save games")
        target_2 = Path(os.environ.get("$STEAMFOLDER")).joinpath(
            f"userdata/{os.environ.get('STEAMID')}/281990/remote/save games")
        target_3 = Path(os.environ.get("HOME")).joinpath(".local/share/Paradox Interactive/Stellaris Plaza/save games")
        return combine_multiple_savegames_folder([target_1, target_2, target_3])
    warnings.warn("Unrecognized system")


def recursivly_parse_flags(flag_amp: Dict, cursor: Cursor, upper_tag: Optional[str] = None):
    """
    TODO:
    :param flag_amp:
    :param cursor:
    :return:
    """
    # TODO: add one_of and any_of flag
    for key, value in flag_amp.items():
        if (key == "one_of") or (key == "any_of"):
            if key == "one_of":
                cursor.execute("""INSERT INTO one_of (tag_id) VALUES (?)""", (upper_tag,))
            # value is a list
            for subkey in value:
                recursivly_parse_flags(subkey, cursor, upper_tag)
        elif isinstance(value, dict):
            if "target" not in value.keys():
                # continue parsing
                cursor.execute("""INSERT INTO tags (tag_id, parent_tag_id, display) VALUES(?,?,?)""",
                               (key, upper_tag, None))
                recursivly_parse_flags(value, cursor, key)
            else:
                # final parse
                cursor.execute("""INSERT INTO tags (tag_id, parent_tag_id, display, target) VALUES(?,?,?,?)""",
                               (key, upper_tag, value["display"], value["target"]))


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

    def build_flags(save_state_content: str, save_id: str) -> Dict:
        """
        This is somewhat inefficient, need to check for performance later
        :param save_state_content:
        :return:
        """
        cursor = database_connection.cursor()
        cursor.execute("SELECT * FROM one_of")
        all_one_of_flag = cursor.fetchall()
        all_one_flag_dict = {flag[0]: {"found": False} for flag in all_one_of_flag}
        cursor.execute("SELECT tags.tag_id, tags.parent_tag_id, tags.target FROM tags")

        for tag_id, parent_tag_id, target in cursor.fetchall():
            if parent_tag_id in all_one_flag_dict:
                if all_one_flag_dict[parent_tag_id]["found"] is True:
                    continue
                if target is None:
                    all_one_flag_dict[parent_tag_id]["default"] = tag_id
            if target is not None:
                if save_state_content.find(target) > 0:
                    # found
                    cursor.execute("""INSERT INTO saves_tags (tag_id, save_id) VALUES (?,?)""", (tag_id, save_id))
                    if parent_tag_id in all_one_flag_dict:
                        all_one_flag_dict[parent_tag_id]["found"] = True
        for tag_value in all_one_flag_dict:
            if all_one_flag_dict[tag_value]["found"] is False:
                cursor.execute("""INSERT INTO saves_tags (tag_id, save_id) VALUES (?,?)""",
                               (all_one_flag_dict[tag_value]["default"], save_id))
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
    try:
        for nation_save in tqdm(get_saves_folder()):
            with tempfile.TemporaryDirectory() as temp_dir:
                cursor = database_connection.cursor()
                save_id = nation_save.stem
                cursor.execute("""INSERT INTO saves (save_id, save_location) VALUES (?,?)""",
                               (save_id, str(nation_save)))
                database_connection.commit()
                cursor.close()
                # assuming there may be multiple save, we only take the first one
                with zipfile.ZipFile(list(nation_save.glob("*.sav"))[0], 'r') as save_file:
                    save_file.extractall(temp_dir)

                relevant_content = Path(temp_dir).joinpath(GAMESTATE)
                with open(relevant_content, 'r') as gamestate_file:
                    all_content = gamestate_file.read()
                    call_function(all_content, save_id)
    except Exception as err:
        logging.exception(err)
        database_connection.close()
    return database_connection


def search_parent(tag_dict: Dict, tag_name: str, counter=0):
    """Search the top parent of a tag"""
    if counter >= len(tag_dict):
        raise ValueError("Infinite loop when searching for top tag.")
    if tag_dict[tag_name]["parent_tag"] is None:
        return tag_name
    else:
        return search_parent(tag_dict, tag_dict[tag_name]["parent_tag"], counter + 1)


def get_tags_header(connection: sqlite3.Connection) -> Dict:
    """
    Get the root labels
    :param connection:
    :return: a dictionary with keys 'display' and 'top'
    """
    cursor = connection.cursor()
    cursor.execute("SELECT tag_id, parent_tag_id, display FROM tags")
    tags = cursor.fetchall()
    tag_dict = {tag_id: {"parent_tag": parent_tag_id, "display": display} for tag_id, parent_tag_id, display in tags}
    return {tag: {
        "display": tag_dict[tag]["display"] if tag_dict[tag]["display"] is not None else tag.replace("_", " ").title(),
        "top_parent": search_parent(tag_dict, tag)}
            for tag in tag_dict}


def get_tags_dict(connection: sqlite3.Connection, parent=None, depth: int = 0):
    """Really inefficient way to get the tree but performance is not the main point here."""
    cursor = connection.cursor()
    tag_tree_dict = {}

    if depth > 100:
        raise Exception("Max depth exceeded, probably a loop with the flags.yaml")

    if (parent is None):
        cursor.execute("SELECT tag_id, parent_tag_id, display FROM tags WHERE parent_tag_id IS NULL")
        tags = cursor.fetchall()
        cursor.close()
        for tag_id, _, display in tags:
            tag_tree_dict[tag_id] = {"display": display if display is not None else tag_id.replace("_", " ").title(),
                                     "childs": get_tags_dict(connection, tag_id, depth + 1)}
    else:
        cursor.execute(
            "SELECT tag_id, parent_tag_id, display FROM tags WHERE parent_tag_id = ?", (parent,))
        tags = cursor.fetchall()
        cursor.close()
        for tag_id, _, display in tags:
            tag_tree_dict[tag_id] = {
                "display": display if display is not None else tag_id.replace("_", " ").title(),
                "childs": get_tags_dict(connection, tag_id, depth + 1)}

    return tag_tree_dict


def get_flags(save_iterable: Iterable[Tuple[str, str]], connection: sqlite3.Connection) -> Dict:
    """
    TODO
    :param tags_save_iterable:
    :return:
    """
    cursor = connection.cursor()
    saves_flag = {}
    for save_id, save_location in save_iterable:
        cursor.execute(
            """SELECT tags.tag_id FROM saves_tags JOIN tags ON saves_tags.tag_id = tags.tag_id WHERE save_id=? AND tags.display IS NOT NULL""",
            (save_id,))
        flags = list(chain(*cursor.fetchall()))
        saves_flag[save_id] = {"location": save_location, "flags": flags}
    return saves_flag


def search_saves_where_tags(connection: sqlite3.Connection, tags: Union[Tuple[str, ...], List[str]],
                            text: Optional[str] = None) -> Iterable[Tuple[str, str]]:
    """

    :param connection:
    :param tags:
    :return:
    """
    cursor = connection.cursor()
    if (text is None) or len(text) == 0:
        sql_query = """
        SELECT DISTINCT saves.save_id, saves.save_location 
        FROM saves 
        JOIN saves_tags on saves.save_id = saves_tags.save_id 
        JOIN tags ON saves_tags.tag_id = tags.tag_id 
        WHERE display IN ({})
        GROUP BY saves.save_id
        HAVING COUNT(DISTINCT display) = {};
        """.format(", ".join(['?' for _ in tags]), len(tags))
        cursor.execute(sql_query, tuple(tags))
    else:
        sql_query = """
                SELECT DISTINCT saves.save_id, saves.save_location
                FROM saves JOIN
                (SELECT DISTINCT saves.save_id, saves.save_location 
                FROM saves 
                JOIN saves_tags on saves.save_id = saves_tags.save_id 
                JOIN tags ON saves_tags.tag_id = tags.tag_id 
                WHERE display IN ({})
                GROUP BY saves.save_id
                HAVING COUNT(DISTINCT display) = {}) AS sec
                ON saves.save_id = sec.save_id
                JOIN saves_tags on saves_tags.save_id = saves.save_id
                JOIN tags ON saves_tags.tag_id = tags.tag_id 
                WHERE (display LIKE ? OR saves.save_id LIKE ?)
                """.format(", ".join(['?' for _ in tags]), len(tags))
        vars = tuple([*tags, f"%{text}%", f"%{text}%"])
        cursor.execute(sql_query, vars)
    saves = cursor.fetchall()
    cursor.close()
    return saves


def search_saves(connection: sqlite3.Connection, text: Optional[str] = None) -> Iterable[Tuple[str, str]]:
    """

    :param connection:
    :param text:
    :return:
    """
    cursor = connection.cursor()
    if (text is None) or len(text) == 0:
        cursor.execute("SELECT save_id, save_location FROM saves")
    else:
        cursor.execute(
            """SELECT DISTINCT saves.save_id, saves.save_location FROM saves JOIN saves_tags on saves.save_id = saves_tags.save_id JOIN tags ON saves_tags.tag_id = tags.tag_id where display LIKE ? OR saves.save_id LIKE ?""",
            (f"%{text}%", f"%{text}%"))
    saves = cursor.fetchall()
    cursor.close()
    return saves
