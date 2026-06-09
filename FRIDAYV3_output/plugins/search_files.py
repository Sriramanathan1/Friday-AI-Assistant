import os
import shutil
import tempfile
import threading
import time
from datetime import datetime

from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from voice import speak

# ================= 🧠 NLP MODEL =================

model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

# ================= 📁 SEARCH LOCATIONS =================

SEARCH_PATHS = [

    os.path.expanduser("D:/Desktop"),

    os.path.expanduser("D:/Documents"),

    os.path.expanduser("D:/Downloads")
]

# ================= 🚫 IGNORE FOLDERS =================

IGNORE_FOLDERS = {

    "arduino",
    "libraries",
    "library",
    "venv",
    "__pycache__",
    ".git",
    "node_modules",
    ".vscode",
    "build"
}

# ================= 📅 MONTH MAP =================

MONTHS = {

    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12
}

# ================= 📄 FILE TYPES =================

IMAGE_EXTENSIONS = [

    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp"
]

FILE_TYPES = {

    "powerpoint": [".ppt", ".pptx"],
    "presentation": [".ppt", ".pptx"],
    "slides": [".ppt", ".pptx"],

    "pdf": [".pdf"],

    "word": [".doc", ".docx"],
    "document": [".doc", ".docx"],
    "certificate": [".pdf", ".doc", ".docx"],
    "bonafide": [".pdf", ".doc", ".docx"],
    "letter": [".pdf", ".doc", ".docx"],
    "resume": [".pdf", ".doc", ".docx"],

    "python": [".py"],
    "code": [".py", ".js", ".html", ".css", ".cpp", ".java"],
    "script": [".py"],

    "text": [".txt"],

    "image": IMAGE_EXTENSIONS,
    "images": IMAGE_EXTENSIONS,
    "picture": IMAGE_EXTENSIONS,
    "pictures": IMAGE_EXTENSIONS,
    "photo": IMAGE_EXTENSIONS,
    "photos": IMAGE_EXTENSIONS,
    "wallpaper": IMAGE_EXTENSIONS,
    "selfie": IMAGE_EXTENSIONS,

    "video": [
        ".mp4",
        ".mov",
        ".avi",
        ".mkv"
    ],

    "music": [
        ".mp3",
        ".wav"
    ]
}

# ================= 📂 TEMP FOLDER =================

TEMP_FOLDER = os.path.join(
    tempfile.gettempdir(),
    "FRIDAY_TEMP_RESULTS"
)

# ================= 🧹 CLEANUP =================

def cleanup_temp_folder(delay=600):

    def cleaner():

        time.sleep(delay)

        if os.path.exists(TEMP_FOLDER):

            try:

                shutil.rmtree(TEMP_FOLDER)

                print(
                    "FRIDAY temp folder deleted"
                )

            except Exception as e:

                print(
                    "Cleanup error:",
                    e
                )

    threading.Thread(
        target=cleaner,
        daemon=True
    ).start()

# ================= 🧠 FILE TYPE DETECTION =================

# FIX 1: Match on whole words only, not substrings.
# Old code did `if keyword in command` which caused "music" to match
# "find my music project", "code" to match "locate", "pic" to match
# "opic", etc. Now we split the command into words and check membership.

def detect_file_type(command):

    command_words = set(command.lower().split())

    for keyword, extensions in FILE_TYPES.items():

        if keyword in command_words:

            print(
                "DIRECT FILE TYPE:",
                keyword
            )

            return extensions

    return None

# ================= 🧠 QUERY CLEANING =================

def clean_query(command):

    REMOVE_WORDS = {

        "find",
        "search",
        "show",
        "open",
        "locate",
        "bring",

        "my",
        "me",
        "the",
        "a",
        "an",

        "files",
        "file",

        "from",

        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",

        # FIX 2: Removed "pdf", "code", "text", "pic" from REMOVE_WORDS.
        # These are also FILE_TYPES keys and meaningful query words.
        # Stripping them caused empty semantic queries and broken scoring.
        "document",
        "documents",
        "presentation",
        "presentations",
        "powerpoint",
        "ppt",
        "slides",

        "image",
        "images",
        "picture",
        "pictures",
        "photo",
        "photos",

        "video",
        "videos",

        "music",
        "song",
        "songs",

        "python"
    }

    words = command.lower().split()

    cleaned_words = [

        word for word in words

        if word not in REMOVE_WORDS
    ]

    cleaned = " ".join(cleaned_words).strip()

    # FIX 3: If cleaning left nothing meaningful (1 char or empty),
    # fall back to a trimmed version of the original command so the
    # scorer always has something real to work with.

    if len(cleaned) <= 1:

        fallback_remove = {"find", "search", "show", "open", "my", "me", "a", "the"}

        cleaned = " ".join(
            w for w in words if w not in fallback_remove
        ).strip()

    return cleaned

# ================= 📂 MAIN SEARCH =================

def handle(command):

    command = str(
        command
    ).lower().strip()

    print(
        "\n========== FILE SEARCH =========="
    )

    # ================= 🧠 CLEAN QUERY =================

    semantic_query = clean_query(
        command
    )

    print(
        "QUERY:",
        semantic_query
    )

    # ================= 🧠 QUERY EMBEDDING =================

    query_embedding = None

    # FIX 4: Only embed if query is actually meaningful (> 2 chars).
    # A 1-char query like "a" gave fuzz.partial_ratio ~100 for every
    # filename, handing ~35 free points to everything and making the
    # score threshold meaningless.

    if len(semantic_query) > 2:

        query_embedding = model.encode(
            [semantic_query]
        )

    # ================= 📄 FILE TYPE =================

    target_extensions = detect_file_type(
        command
    )

    print(
        "TARGET EXTENSIONS:",
        target_extensions
    )

    # ================= 📅 MONTH =================

    target_month = None

    for month_name, month_num in MONTHS.items():

        if month_name in command:

            target_month = month_num
            break

    # ================= 📅 DAY =================

    target_day = None

    words = command.split()

    for word in words:

        clean_word = (
            word.replace("st", "")
            .replace("nd", "")
            .replace("rd", "")
            .replace("th", "")
        )

        if clean_word.isdigit():

            number = int(clean_word)

            if 1 <= number <= 31:

                target_day = number

    # ================= 📅 YEAR =================

    target_year = None

    for word in words:

        if word.isdigit() and len(word) == 4:

            target_year = int(word)

    print("MONTH:", target_month)
    print("DAY:", target_day)
    print("YEAR:", target_year)

    # ================= 🧹 CLEAN TEMP =================

    if os.path.exists(TEMP_FOLDER):

        try:

            shutil.rmtree(
                TEMP_FOLDER
            )

        except Exception as e:

            print(
                "TEMP DELETE ERROR:",
                e
            )

    os.makedirs(
        TEMP_FOLDER,
        exist_ok=True
    )

    # ================= 📂 SEARCH =================

    ranked_results = []

    for base_path in SEARCH_PATHS:

        print(
            "SEARCHING:",
            base_path
        )

        for root, dirs, files in os.walk(base_path):

            # 🚫 skip junk folders
            dirs[:] = [

                d for d in dirs

                if d.lower() not in IGNORE_FOLDERS
            ]

            for file in files:

                try:

                    full_path = os.path.join(
                        root,
                        file
                    )

                    filename_only = os.path.splitext(
                        file
                    )[0].lower()

                    extension = os.path.splitext(
                        file
                    )[1].lower()

                    # ================= 📄 EXTENSION FILTER =================

                    if target_extensions:

                        if extension not in target_extensions:
                            continue

                    # ================= 📅 DATE FILTER =================

                    modified_time = os.path.getmtime(
                        full_path
                    )

                    file_date = datetime.fromtimestamp(
                        modified_time
                    )

                    if target_month:

                        if file_date.month != target_month:
                            continue

                    if target_day:

                        if file_date.day != target_day:
                            continue

                    if target_year:

                        if file_date.year != target_year:
                            continue

                    # ================= 🧠 SCORING =================

                    score = 0

                    joined_query = semantic_query.replace(
                        " ", ""
                    )

                    joined_filename = filename_only.replace(
                        " ", ""
                    ).replace("_", "").replace("-", "")

                    # ================= EXACT MATCH =================

                    if joined_query:

                        if joined_query == joined_filename:

                            score += 1000

                        elif joined_query in joined_filename:

                            score += 500

                    # ================= WORD MATCH =================

                    query_words = semantic_query.split()

                    for word in query_words:

                        if len(word) < 3:
                            continue  # skip tiny words like "a", "my"

                        if word == filename_only:

                            score += 300

                        elif word in filename_only:

                            score += 120

                    # ================= FUZZY MATCH =================

                    # FIX 4 (continued): Only fuzz if query is long enough
                    # to be meaningful. Short queries score near 100 against
                    # everything and pollute results.

                    if len(semantic_query) > 2:

                        fuzzy_score = fuzz.partial_ratio(
                            semantic_query,
                            filename_only
                        )

                        score += fuzzy_score * 0.35

                    # ================= SEMANTIC SCORE =================

                    if query_embedding is not None:

                        file_embedding = model.encode(
                            [filename_only]
                        )

                        semantic_score = cosine_similarity(
                            query_embedding,
                            file_embedding
                        )[0][0]

                        score += semantic_score * 2

                    # ================= BONUS =================

                    if "certificate" in filename_only:
                        score += 150

                    if "bonafide" in filename_only:
                        score += 200

                    if "profile" in filename_only:
                        score += 100

                    # FIX 5: "pic" bonus was matching unrelated words like
                    # "topic", "epic", "public". Now checks as a whole word
                    # by looking at filename split on common separators.

                    filename_words = filename_only.replace(
                        "_", " "
                    ).replace("-", " ").split()

                    if "pic" in filename_words or "picture" in filename_words:
                        score += 80

                    # ================= PENALTIES =================

                    junk_words = [

                        "arduino",
                        "liquidcrystal",
                        "library",
                        "libraries",
                        "i2c",
                        "esp32",
                        "nodemcu"
                    ]

                    for junk in junk_words:

                        if junk in filename_only:

                            score -= 300

                    print(
                        filename_only,
                        "->",
                        round(score, 2)
                    )

                    # ================= REJECT =================

                    if score < 55:
                        continue

                    ranked_results.append(

                        (
                            score,
                            full_path,
                            file
                        )
                    )

                except Exception as e:

                    print(
                        "SEARCH ERROR:",
                        e
                    )

    # ================= 📂 SORT =================

    ranked_results.sort(

        reverse=True,
        key=lambda x: x[0]
    )

    # ================= 📄 COPY RESULTS =================

    found_files = []

    for score, full_path, file in ranked_results[:25]:

        try:

            destination = os.path.join(
                TEMP_FOLDER,
                file
            )

            shutil.copy2(
                full_path,
                destination
            )

            found_files.append(file)

        except Exception as e:

            print(
                "COPY ERROR:",
                e
            )

    # ================= 📂 RESULTS =================

    if found_files:

        print(
            "\nFOUND FILES:"
        )

        for file in found_files:

            print(file)

        speak(
            f"I found "
            f"{len(found_files)} matching files"
        )

        os.startfile(
            TEMP_FOLDER
        )

        cleanup_temp_folder()

        return True

    else:

        print(
            "\nNO FILES FOUND"
        )

        speak(
            "No matching files were found"
        )

        return True