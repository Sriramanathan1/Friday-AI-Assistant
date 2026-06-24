"""
tools.py — FRIDAY Tool Definitions (V4)

Every capability FRIDAY has is declared here as a structured tool spec.
The Groq LLM receives these and decides which tool(s) to call.

CHANGES FROM V3:
  + plan_task        — multi-step task planner
  + search_memory    — fuzzy search across facts + conversation history
  + query_documents  — RAG search over ingested files
  + ingest_document  — add a file to FRIDAY's knowledge base
  + create_workflow  — save a reusable named voice workflow
  + run_workflow     — execute a saved workflow by name
"""

TOOLS = [

    # ── System ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "control_volume",
            "description": "Increase, decrease, or mute the computer's system volume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["increase", "decrease", "mute", "unmute"],
                        "description": "What to do with the volume."
                    },
                    "steps": {
                        "type": "integer",
                        "description": "How many key-presses (default 5).",
                        "default": 5
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Capture and save a screenshot of the current screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "save_path": {
                        "type": "string",
                        "description": "Optional file path to save the screenshot (default: screenshot.png).",
                        "default": "screenshot.png"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "power_control",
            "description": "Shutdown or restart the computer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["shutdown", "restart"],
                        "description": "Whether to shut down or restart."
                    }
                },
                "required": ["action"]
            }
        }
    },

    # ── App Control ─────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Launch an application on the computer (e.g. Chrome, Notepad, Calculator, VS Code, Spotify).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                        "description": "Name of the application to open (e.g. 'chrome', 'notepad', 'calculator', 'vscode', 'spotify')."
                    }
                },
                "required": ["app"]
            }
        }
    },

    # ── Live Web Search (real-time + summarised) ────────────────
    {
        "type": "function",
        "function": {
            "name": "live_search",
            "description": (
                "Search the web in real time and return a spoken summary plus relevant links. "
                "Use this for ANY query that needs current, live, or present-tense information — "
                "things that change over time and cannot be answered from memory alone. "
                "Examples: prices, product recommendations, sports scores, match tickets, "
                "upcoming events, weather (if get_weather does not apply), news, "
                "stock prices, restaurant recommendations, travel deals, or any question "
                "containing words like: cheapest, best, find me, where can I buy, "
                "upcoming, latest, right now, currently, today, near me, how much does. "
                "Always prefer this over web_search for questions that need a summarised "
                "spoken answer rather than just opening a browser tab."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A focused search query optimised for Google — include specific "
                            "details the user mentioned (dimensions, location, dates, price range). "
                            "Examples: '125cm pull up bar buy India', "
                            "'cheapest FIFA World Cup 2026 tickets', "
                            "'weather Chennai right now'."
                        )
                    }
                },
                "required": ["query"]
            }
        }
    },

    # ── Web ──────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": "Open a specific website directly in the browser (YouTube, Gmail, WhatsApp Web, LinkedIn, GitHub, ChatGPT).",
            "parameters": {
                "type": "object",
                "properties": {
                    "site": {
                        "type": "string",
                        "enum": ["youtube", "gmail", "whatsapp", "linkedin", "github", "chatgpt"],
                        "description": "Which website to open."
                    }
                },
                "required": ["site"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search Google for information and return a text snippet. Use this for current events, news, weather, stock prices, sports scores, or any factual query needing live data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query."
                    },
                    "open_browser": {
                        "type": "boolean",
                        "description": "Also open the search in the browser (default false).",
                        "default": False
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City or location name. Leave empty to use the user's current location."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_search",
            "description": "Search YouTube or play a video/song on YouTube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for or play on YouTube."
                    }
                },
                "required": ["query"]
            }
        }
    },

    # ── Timer ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Set a countdown timer or alarm. Use this when the user says 'set a timer', 'remind me in X minutes', or 'set alarm'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_seconds": {
                        "type": "integer",
                        "description": "How many seconds to count down."
                    },
                    "label": {
                        "type": "string",
                        "description": "Optional label for the timer (e.g. 'study break', 'pasta').",
                        "default": "Timer"
                    }
                },
                "required": ["duration_seconds"]
            }
        }
    },

    # ── Messaging ────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp",
            "description": "Send a WhatsApp message to a contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact": {
                        "type": "string",
                        "description": "Name of the contact (e.g. 'dad', 'mom', 'John')."
                    },
                    "message": {
                        "type": "string",
                        "description": "The message text to send."
                    }
                },
                "required": ["contact", "message"]
            }
        }
    },

    # ── Files ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "organise_files",
            "description": "Sort and organise files in a folder (e.g. Downloads) by type into subfolders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "Path of the folder to organise. Defaults to Downloads.",
                        "default": "~/Downloads"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "Search for files by name, type, or keyword across the computer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Filename, extension, or keyword to search for (e.g. 'robotics', '.pptx', 'resume')."
                    },
                    "folder": {
                        "type": "string",
                        "description": "Root folder to search. Default is the user's home directory.",
                        "default": "~"
                    }
                },
                "required": ["query"]
            }
        }
    },

    # ── Smart Typing ─────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "smart_type",
            "description": "Generate polished text (an email, message, essay, letter) and type it at the current cursor position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "What text to compose (e.g. 'a professional email apologising for being late')."
                    },
                    "tone": {
                        "type": "string",
                        "enum": ["professional", "casual", "formal", "friendly"],
                        "description": "Tone of the generated text.",
                        "default": "professional"
                    }
                },
                "required": ["request"]
            }
        }
    },

    # ── Memory ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save a fact about the user to long-term memory (e.g. their name, preferences, school, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Category/key for the fact (e.g. 'name', 'school', 'favourite_browser')."
                    },
                    "value": {
                        "type": "string",
                        "description": "The value to remember."
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Recall what FRIDAY knows about the user — their name, preferences, facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Specific fact to recall. Leave empty to return all facts.",
                        "default": ""
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "forget_memory",
            "description": "Delete a saved fact from FRIDAY's memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The key/category to forget (e.g. 'name', 'school')."
                    }
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search long-term memory for anything FRIDAY knows — past conversations, user facts, preferences, or past tasks. Use when the user asks 'do you remember', 'did I tell you', 'what did I say about'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for (e.g. 'my exam date', 'homework', 'favourite food', 'what I said yesterday')."
                    }
                },
                "required": ["query"]
            }
        }
    },

    # ── Email ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email via Gmail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address or contact name."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line."
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body text."
                    }
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_emails",
            "description": "Read the latest unread emails from Gmail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "How many recent emails to fetch (default 5).",
                        "default": 5
                    }
                },
                "required": []
            }
        }
    },

    # ── Modes ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "set_mode",
            "description": "Activate or deactivate a focus mode (study mode, coding mode, movie mode).",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["study", "coding", "movie", "normal"],
                        "description": "Which mode to switch to. Use 'normal' to exit all modes."
                    },
                    "active": {
                        "type": "boolean",
                        "description": "True to activate, False to deactivate.",
                        "default": True
                    }
                },
                "required": ["mode"]
            }
        }
    },

    # ── Coding ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "coding_assist",
            "description": "Help with coding: write code, explain errors, review code, or run code snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "What coding help is needed (e.g. 'write a python function to sort a list', 'explain this error: ...')."
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (e.g. 'python', 'javascript'). Optional.",
                        "default": "python"
                    }
                },
                "required": ["task"]
            }
        }
    },

    # ── Study ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "study_assist",
            "description": "Help with studying: explain concepts, solve equations, quiz the user, plot graphs, or answer homework questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "What study help is needed (e.g. 'explain Newton's second law', 'quiz me on thermodynamics', 'solve x^2 + 5x + 6 = 0')."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Subject area (e.g. 'physics', 'math', 'chemistry'). Optional."
                    }
                },
                "required": ["task"]
            }
        }
    },

    # ── IoT ──────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "iot_control",
            "description": (
                "Control a smart home / Alexa-connected device (lights, fans, AC, "
                "plugs, TVs, etc.). Extract the device's type and any location/room "
                "or descriptor the user mentioned (e.g. 'bedroom', 'master', 'living "
                "room') into `device`, so it can be matched against the user's real "
                "device names (e.g. 'bedroom ac' matches a device named "
                "'Master Bedroom AC')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {
                        "type": "string",
                        "description": "Device description including any location/room mentioned (e.g. 'bedroom ac', 'living room light', 'fan')."
                    },
                    "action": {
                        "type": "string",
                        "description": "What to do, in natural language (e.g. 'turn on', 'turn off', 'set brightness to 50', 'set to 24 degrees', 'set volume to 30')."
                    }
                },
                "required": ["device", "action"]
            }
        }
    },

    # ── RAG / Documents ──────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "ingest_document",
            "description": "Read a file (PDF, TXT, notes) and add it to FRIDAY's searchable knowledge base so you can answer questions from it later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the file to ingest (e.g. 'C:/Users/Sri/Documents/notes.pdf')."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_documents",
            "description": "Search documents, notes, or files previously added to FRIDAY's knowledge base and return relevant passages. Use when user asks about something that might be in their files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for (e.g. 'Newton's laws', 'project deadline', 'chapter 3 summary')."
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of passages to return (default 3).",
                        "default": 3
                    }
                },
                "required": ["query"]
            }
        }
    },

    # ── Multi-Step Planning ──────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "plan_task",
            "description": "Break a complex multi-step goal into sub-tasks and execute them in order. Use when the user asks for several things at once (e.g. 'set up my study session', 'get me ready for bed').",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "The high-level task the user wants accomplished."
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered list of sub-task descriptions to execute (e.g. ['open VS Code', 'mute volume', 'set a 2 hour timer'])."
                    }
                },
                "required": ["goal", "steps"]
            }
        }
    },

    # ── Workflows ────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_workflow",
            "description": "Save a named sequence of commands as a reusable workflow (e.g. 'study mode' = open VS Code + mute volume + 2hr timer). User can say 'run study mode' later to trigger it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short name for the workflow (e.g. 'study mode', 'morning routine', 'movie night')."
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered list of voice commands to execute when the workflow runs."
                    }
                },
                "required": ["name", "steps"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_workflow",
            "description": "Execute a previously saved workflow by name (e.g. 'run my study mode workflow').",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the workflow to run."
                    }
                },
                "required": ["name"]
            }
        }
    },

    # ── Speak (fallback) ─────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "speak_response",
            "description": "Speak a plain conversational reply aloud. Use this when no other tool applies — for greetings, general questions, jokes, chitchat, or anything that just needs a spoken answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text FRIDAY should say."
                    }
                },
                "required": ["text"]
            }
        }
    },
]

# Quick lookup by name
TOOL_MAP = {t["function"]["name"]: t for t in TOOLS}