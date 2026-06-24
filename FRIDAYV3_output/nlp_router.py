"""
nlp_router.py — Central NLP routing for FRIDAY

Instead of keyword if-else chains, every plugin registers
its intents with example sentences. Commands are matched
using sentence embeddings + cosine similarity.

Usage:
    from nlp_router import classify

    intent, score, meta = classify(command, "study")
    if intent == "quiz":
        ...
"""

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# ================= 🧠 MODEL =================
# Shared model instance — loaded once, reused everywhere

print("[NLP ROUTER] Loading sentence model...")
_model = SentenceTransformer("all-MiniLM-L6-v2")
print("[NLP ROUTER] Model ready.")

# ================= 📚 INTENT REGISTRY =================
# Each domain registers its intents here.
# Format: { domain: { intent: [example sentences] } }

INTENT_REGISTRY = {

    # ================================================================
    # BRAIN — top-level routing
    # ================================================================
    "brain": {
        "app_control": [
            "open chrome", "launch browser", "start calculator",
            "open notepad", "launch vscode", "open spotify",
            "start an application", "open an app", "run program",
        ],
        "web_search": [
            "search google", "look something up", "find information online",
            "search formula 1 standings", "tell me about black holes",
            "who is elon musk", "look up spacex", "watch interstellar",
            "play music on youtube", "search youtube", "browse the web",
        ],
        "file_search": [
            "find my files", "search presentations", "show documents",
            "find robotics ppt", "search powerpoint files", "find my pdfs",
            "search files from january", "locate a document",
            "where is my file", "find a document on my computer",
        ],
        "system_control": [
            "increase volume", "mute computer", "take screenshot",
            "restart pc", "shutdown pc", "lower the volume",
            "turn up the sound", "lock the screen",
        ],
        "typing": [
            "write an email", "type a formal letter", "draft a message",
            "write a paragraph", "compose a mail", "write an essay",
            "type this out", "draft a report",
        ],
        "timer": [
            "set a timer", "start countdown", "set alarm",
            "remind me in 10 minutes", "start a 25 minute timer",
        ],
        "messaging": [
            "send whatsapp message", "text dad", "send a message",
            "tell dad hello", "whatsapp mom", "message my friend",
            "send a text to", "send whatsapp to",
        ],
        "automation": [
            "organize downloads", "sort my files", "clean my desktop",
            "arrange downloads", "organize desktop", "tidy up files",
        ],
        "mode": [
            "activate study mode", "enable coding mode",
            "switch to movie mode", "open study mode",
            "exit study mode", "start focus mode",
            "turn on coding mode", "switch to writing mode",
        ],
        "study": [
            "explain integration", "what is newtons law",
            "quiz me on thermodynamics", "solve my homework",
            "simulate projectile motion", "plot a graph of velocity",
            "solve this equation", "teach me about organic chemistry",
            "differentiate sin x", "give me practice questions on waves",
            "what is on my screen", "solve the question on my screen",
            "crack this equation", "how does photoelectric effect work",
        ],
        "planner": [
            "show my study plan", "what should I study today",
            "study schedule", "update my study plan",
            "my exam schedule", "regenerate plan",
            "show my plan", "what do I study today",
        ],
        "homework_tracker": [
            "enter my homework", "open homework tracker",
            "add today's assignment", "show pending homework",
            "what homework is due", "mark physics as done",
            "remaining homework", "homework status",
            "I finished my math homework", "done with chemistry assignment",
            "add homework for today", "record my homework",
            "what homework is left", "mark math as done",
            "done with physics", "done with chemistry",
            "homework tracker", "my pending assignments",
            "finished my physics homework", "completed chemistry assignment",
        ],
        "download_watcher": [
            "check my downloads", "scan downloads for homework",
            "any new homework files", "check for new assignments",
            "scan my downloads", "check whatsapp files",
            "new files in downloads", "start watching downloads",
            "stop watching downloads", "check for new files",
            "any new assignment files", "scan for homework",
        ],
        "notes": [
            "summarize my notes", "make notes from this PDF",
            "create flashcards from this document",
            "generate bullet notes for me",
            "summarize this document into notes",
            "make study notes from this file",
            "notes from my screen",
            "create flashcards from this",
            "condense my notes",
            "bullet point summary of this",
            "take notes from this", "generate notes",
            "create study notes", "make flashcards",
            "summarise this", "create bullet notes",
            "notes from this file", "make notes",
        ],
        "podcast": [
            "convert to podcast", "make a podcast from this PDF",
            "read this to me as a podcast",
            "audio version of my notes",
            "make an audio podcast from this",
            "turn my notes into a podcast",
            "notebook LM style podcast",
            "listen to my notes as audio",
            "create a podcast from this", "audio podcast",
            "read to me", "make audio from notes",
            "podcast from document", "listen to this file",
        ],
        "iot": [
            "turn on the lights", "turn off the fan",
            "switch on the AC", "switch off the TV",
            "turn on the bulb", "turn off the plug",
            "dim the lights", "set brightness to 50",
            "set AC to 24 degrees", "set temperature to 22",
            "set TV volume to 30", "change bulb color to red",
            "turn on smart bulb", "turn off smart plug",
            "what is the status of the fan", "list my devices",
            "show all alexa devices", "refresh devices",
            "turn on the ceiling fan", "switch off the lamp",
            "dim lights to 40", "set light to warm white",
        ],
        "email": [
            "send email to dad", "email mom about the meeting",
            "compose email to dad", "write an email to dad",
            "send an email to dad about", "draft email to mom",
            "email dad", "send mail to", "write email",
            "email my dad saying", "compose a mail to",
            "send a formal email to", "shoot an email to dad",
        ],
        "coding": [
            "explain this code", "what does this function do",
            "refactor my code", "clean up this code",
            "fix the bug", "debug this", "there is an error",
            "add a function", "implement this feature",
            "rewrite this", "optimize my code",
            "what is this code doing", "improve this function",
            "there is a bug in my code", "fix this error",
        ],
    },

    # ================================================================
    # STUDY MODE — internal routing
    # ================================================================
    "study": {
        "homework": [
            "solve my homework", "help with my homework",
            "I have homework to do", "can you do my homework",
            "answer my homework questions", "finish my homework",
            "homework help", "do my assignment",
            "answer all questions in this PDF",
            "solve the questions in my file",
        ],
        "explain": [
            "explain integration", "what is Newton's law",
            "teach me about thermodynamics", "how does photosynthesis work",
            "what are electromagnetic waves", "define entropy",
            "tell me about organic chemistry", "help me understand calculus",
            "I do not understand this concept", "break this down for me",
        ],
        "equation": [
            "solve x squared plus 5x plus 6", "differentiate sin x cos x",
            "integrate x squared", "simplify this expression",
            "calculate the derivative", "find the roots of this equation",
            "factorise this polynomial", "prove this theorem",
            "evaluate this integral", "expand this expression",
        ],
        "graph": [
            "plot velocity versus time", "draw a graph of sin x",
            "show me the graph of this function", "plot acceleration",
            "graph of quadratic equation", "visualize this data",
            "chart the results", "plot this equation",
        ],
        "simulate": [
            "simulate projectile motion", "show me a pendulum simulation",
            "animate simple harmonic motion", "demonstrate wave interference",
            "simulate a circuit", "show me how this works visually",
            "animate this physics concept", "run a simulation",
        ],
        "quiz": [
            "quiz me on integration", "test me on Newton's laws",
            "give me MCQ questions on thermodynamics",
            "practice questions on organic chemistry",
            "test my knowledge of waves", "I want to practice",
            "examine me on this topic", "give me questions to solve",
        ],
        "puzzle": [
            "solve this logic puzzle", "crack this brain teaser",
            "this is a word problem", "solve this riddle",
            "help me with this puzzle", "figure out this problem",
        ],
        "wrong_answers": [
            "explain my wrong answers", "what did I get wrong",
            "review my mistakes", "explain where I went wrong",
            "go over my incorrect answers", "my wrong answers from the quiz",
        ],
        "similar_problems": [
            "give me similar problems", "more questions like this",
            "practice problems on the same topic",
            "generate similar questions", "more of these",
        ],
    },

    # ================================================================
    # LEARNING — preferences, shortcuts, corrections
    # NOTE: Examples here must be VERY specific to avoid false matches
    # ================================================================
    "learning": {
        "preference": [
            "call me Sri", "my name is Sri",
            "remember that I like dark mode",
            "I prefer Chrome over Edge",
            "I hate loud notifications",
            "I always use VSCode",
            "remember I love Spotify",
            "I like studying at night",
            "remember my preference for dark theme",
            "I prefer this browser for everything",
        ],
        "shortcut": [
            "when I say home open chrome and spotify",
            "whenever I say work mode launch vscode",
            "if I say goodnight shutdown the PC",
            "create a shortcut for this command",
            "set up a voice shortcut called home",
            "when I say this phrase do that action",
        ],
        "correction": [
            "no I meant open spotify",
            "that is wrong Friday",
            "not that one",
            "I said the other one",
            "wrong answer Friday",
            "no Friday that is not what I wanted",
            "you misunderstood me completely",
            "that was the incorrect response",
        ],
        "recall": [
            "what do you know about me personally",
            "what preferences have you learned about me",
            "show me my saved preferences",
            "list all my voice shortcuts",
            "what commands do I use most often",
            "show my FRIDAY usage statistics",
            "tell me all my saved preferences",
            "what shortcuts have I created",
        ],
        "forget": [
            "forget that I like dark mode",
            "forget my saved name",
            "remove that preference from memory",
            "delete that from your memory",
            "forget what I told you about Chrome",
            "clear my preference for dark theme",
        ],
        "delete_shortcut": [
            "delete my home shortcut",
            "remove the work shortcut",
            "delete that voice shortcut",
            "remove this voice shortcut",
            "get rid of the shortcut called home",
        ],
    },

    # ================================================================
    # HOMEWORK TRACKER
    # ================================================================
    "homework_tracker": {
        "enter": [
            "enter my homework for today",
            "add today's homework assignments",
            "I have new homework to record",
            "let me add my assignments for today",
            "open homework tracker to enter work",
            "add homework for today in the tracker",
            "new assignment to add to tracker",
            "record my homework assignments",
        ],
        "show": [
            "show my pending homework assignments",
            "what homework is left to finish",
            "what assignments are due today",
            "what is pending in my homework list",
            "homework status check",
            "remaining homework assignments",
            "what do I still need to complete",
            "show my homework list",
        ],
        "mark_done": [
            "I finished my math homework assignment",
            "done with physics assignment today",
            "completed my chemistry homework",
            "mark English homework as done",
            "finished the CS project assignment",
            "I am done with math homework",
            "physics homework is complete",
            "tick off chemistry from homework",
        ],
    },
}

# ================= 🔢 PRECOMPUTE EMBEDDINGS =================

print("[NLP ROUTER] Precomputing embeddings...")
_embeddings = {}

for domain, intents in INTENT_REGISTRY.items():
    _embeddings[domain] = {}
    for intent, examples in intents.items():
        _embeddings[domain][intent] = _model.encode(examples)

print("[NLP ROUTER] Embeddings ready.")

# ================= 🎯 CLASSIFY =================

def classify(command, domain, threshold=0.30):
    """
    Classify a command within a domain.

    Args:
        command:   the user's voice command (string)
        domain:    which intent set to use (e.g. "study", "learning")
        threshold: minimum similarity score to accept (default 0.30)

    Returns:
        (intent, score, all_scores_dict)
        intent is None if no match above threshold
    """
    if domain not in _embeddings:
        print(f"[NLP ROUTER] Unknown domain: {domain}")
        return None, 0.0, {}

    cmd_embedding = _model.encode([command.lower().strip()])

    scores = {}
    for intent, emb in _embeddings[domain].items():
        sim   = cosine_similarity(cmd_embedding, emb)[0]
        score = float(np.max(sim))
        scores[intent] = round(score, 3)

    best_intent = max(scores, key=scores.get)
    best_score  = scores[best_intent]

    # debug print
    top3 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    print(f"[NLP ROUTER] domain={domain} | top3={top3}")

    if best_score >= threshold:
        return best_intent, best_score, scores

    return None, best_score, scores


def classify_multi(command, domains, threshold=0.30):
    """
    Classify across multiple domains at once.
    Returns the best match overall.

    Args:
        command: user command
        domains: list of domain names to check
        threshold: minimum score

    Returns:
        (domain, intent, score)
    """
    best = (None, None, 0.0)

    for domain in domains:
        intent, score, _ = classify(command, domain, threshold)
        if score > best[2]:
            best = (domain, intent, score)

    return best


def is_intent(command, domain, intent, threshold=0.32):
    """
    Quick boolean check — is this command likely this intent?

    Usage:
        if is_intent(command, "learning", "preference"):
            handle_preference(command)
    """
    _, score, _ = classify(command, domain)
    matched_intent, _, _ = classify(command, domain, threshold)
    return matched_intent == intent


# ================= 🔍 SUBJECT DETECTOR =================

SUBJECT_EXAMPLES = {
    "maths": [
        "calculus integration differentiation",
        "algebra equations polynomials matrices",
        "trigonometry sin cos tan",
        "probability statistics",
        "coordinate geometry",
        "binomial theorem logarithms",
    ],
    "physics": [
        "force motion velocity acceleration Newton",
        "energy work power momentum",
        "waves optics light refraction",
        "electricity current resistance circuits",
        "magnetism electromagnetic induction",
        "thermodynamics heat entropy",
        "modern physics quantum nuclear",
        "projectile motion kinematics",
    ],
    "chemistry": [
        "organic chemistry carbon compounds hydrocarbons",
        "chemical reactions equilibrium acids bases",
        "atomic structure periodic table elements",
        "electrochemistry redox reactions",
        "polymer biomolecules",
        "solutions colligative properties",
        "coordination compounds",
    ],
    "english": [
        "grammar vocabulary comprehension",
        "essay writing literature poetry",
        "reading passage writing skills",
    ],
    "cs": [
        "programming code algorithm data structures",
        "python java loops functions arrays",
        "computer science networking database",
        "sorting searching recursion",
    ],
}

_subject_embeddings = {
    subj: _model.encode(examples)
    for subj, examples in SUBJECT_EXAMPLES.items()
}

def detect_subject_nlp(command, threshold=0.25):
    """
    Detect subject from command using NLP instead of keyword matching.
    Returns subject name or None.
    """
    cmd_emb = _model.encode([command.lower()])
    scores  = {}

    for subj, emb in _subject_embeddings.items():
        sim    = cosine_similarity(cmd_emb, emb)[0]
        scores[subj] = float(np.max(sim))

    best_subj  = max(scores, key=scores.get)
    best_score = scores[best_subj]

    print(f"[NLP ROUTER] Subject scores: { {k: round(v,3) for k,v in scores.items()} }")

    if best_score >= threshold:
        return best_subj

    return None