const vscode = require("vscode");
const fs     = require("fs");
const os     = require("os");
const path   = require("path");

// ── Shared temp file paths (must match coding_mode.py) ──
const SUGGESTION_FILE  = path.join(os.tmpdir(), "friday_suggestion.json");
const ACTIVE_FLAG      = path.join(os.tmpdir(), "friday_coding_active.flag");
const ACTIVE_FILE_TXT  = path.join(os.tmpdir(), "friday_active_file.txt");
const TRIGGER_FILE     = path.join(os.tmpdir(), "friday_autocomplete_trigger.json");

// ── Decoration type for ghost text (greyed-out, italic) ──
const ghostDecoration = vscode.window.createTextEditorDecorationType({
  after: {
    color:      new vscode.ThemeColor("editorGhostText.foreground"),
    fontStyle:  "italic",
  },
});

// ── Full-file diff decoration (added lines highlighted) ──
const addedDecoration = vscode.window.createTextEditorDecorationType({
  backgroundColor: new vscode.ThemeColor("diffEditor.insertedLineBackground"),
  isWholeLine: true,
});

const removedDecoration = vscode.window.createTextEditorDecorationType({
  backgroundColor: new vscode.ThemeColor("diffEditor.removedLineBackground"),
  isWholeLine: true,
});

// ── Extension state ──
let currentSuggestion  = null;   // { mode, file_path, original, suggested }
let typingTimer        = null;
let suggestionVisible  = false;
let suggestionWatcher  = null;

// ── Context key for keybinding ──
function setSuggestionVisible(val) {
  suggestionVisible = val;
  vscode.commands.executeCommand("setContext", "fridaySuggestionVisible", val);
}


// =============================================================================
// Activate
// =============================================================================

function activate(context) {
  console.log("[FRIDAY] Extension activated");

  // Tell FRIDAY which file is currently active
  reportActiveFile();

  // Watch the suggestion file for changes from FRIDAY
  startSuggestionWatcher(context);

  // Watch for active editor changes
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(() => reportActiveFile())
  );

  // Watch for typing pauses (auto line-completion)
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument(onTyping)
  );

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand("friday.acceptSuggestion", acceptSuggestion)
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("friday.dismissSuggestion", dismissSuggestion)
  );
}


// =============================================================================
// Report active file to FRIDAY
// =============================================================================

function reportActiveFile() {
  const editor = vscode.window.activeTextEditor;
  if (editor) {
    fs.writeFileSync(ACTIVE_FILE_TXT, editor.document.uri.fsPath, "utf8");
  }
}


// =============================================================================
// Watch suggestion file
// =============================================================================

function startSuggestionWatcher(context) {
  let lastMtime = 0;

  const interval = setInterval(() => {
    if (!fs.existsSync(SUGGESTION_FILE)) return;

    try {
      const mtime = fs.statSync(SUGGESTION_FILE).mtimeMs;
      if (mtime === lastMtime) return;
      lastMtime = mtime;

      const raw  = fs.readFileSync(SUGGESTION_FILE, "utf8");
      const data = JSON.parse(raw);

      currentSuggestion = data;

      if (data.mode === "complete") {
        showLineCompletion(data);
      } else {
        showDiffSuggestion(data);
      }
    } catch (e) {
      console.error("[FRIDAY] Error reading suggestion:", e);
    }
  }, 500);

  context.subscriptions.push({ dispose: () => clearInterval(interval) });
}


// =============================================================================
// Show inline diff suggestion (full-file edits)
// =============================================================================

function showDiffSuggestion(data) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;

  // Make sure we're looking at the right file
  const docPath = editor.document.uri.fsPath;
  if (docPath !== data.file_path) {
    vscode.window.showInformationMessage(
      `[FRIDAY] Suggestion ready for ${path.basename(data.file_path)}. Open it to review.`
    );
    return;
  }

  const originalLines  = data.original.split("\n");
  const suggestedLines = data.suggested.split("\n");

  // Compute simple line-level diff
  const added   = [];
  const removed = [];

  const maxLen = Math.max(originalLines.length, suggestedLines.length);
  for (let i = 0; i < maxLen; i++) {
    const orig = originalLines[i];
    const sugg = suggestedLines[i];
    if (orig !== sugg) {
      if (i < originalLines.length)  removed.push(i);
      if (i < suggestedLines.length) added.push(i);
    }
  }

  // Show diff decorations on current document
  const addedRanges   = added.map(i => {
    const line = Math.min(i, editor.document.lineCount - 1);
    return new vscode.Range(line, 0, line, editor.document.lineAt(line).text.length);
  });
  const removedRanges = removed.map(i => {
    const line = Math.min(i, editor.document.lineCount - 1);
    return new vscode.Range(line, 0, line, editor.document.lineAt(line).text.length);
  });

  editor.setDecorations(addedDecoration,   addedRanges);
  editor.setDecorations(removedDecoration, removedRanges);

  setSuggestionVisible(true);

  // Show status bar hint
  vscode.window.setStatusBarMessage(
    "$(sparkle) FRIDAY: Press Tab to accept changes, Escape to dismiss",
    60000
  );
}


// =============================================================================
// Show ghost text line completion
// =============================================================================

function showLineCompletion(data) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;

  const cursor   = editor.selection.active;
  const lineText = editor.document.lineAt(cursor.line).text;
  const original = data.original.trimEnd();
  const completed = data.suggested.trimEnd();

  // Show only the added part as ghost text
  const ghost = completed.startsWith(lineText.trimEnd())
    ? completed.slice(lineText.trimEnd().length)
    : " " + completed;

  const range = new vscode.Range(
    cursor.line, lineText.length,
    cursor.line, lineText.length
  );

  editor.setDecorations(ghostDecoration, [{
    range,
    renderOptions: { after: { contentText: ghost } },
  }]);

  setSuggestionVisible(true);

  vscode.window.setStatusBarMessage(
    "$(sparkle) FRIDAY: Tab to accept, Escape to dismiss",
    10000
  );
}


// =============================================================================
// Accept suggestion
// =============================================================================

async function acceptSuggestion() {
  if (!currentSuggestion) return;

  const editor = vscode.window.activeTextEditor;
  if (!editor) return;

  if (currentSuggestion.mode === "complete") {
    // Replace current line with completed version
    const cursor = editor.selection.active;
    const line   = editor.document.lineAt(cursor.line);
    await editor.edit(eb => {
      eb.replace(line.range, currentSuggestion.suggested.trimEnd());
    });
  } else {
    // Replace entire file content with suggested version
    const fullRange = new vscode.Range(
      editor.document.positionAt(0),
      editor.document.positionAt(editor.document.getText().length)
    );
    await editor.edit(eb => {
      eb.replace(fullRange, currentSuggestion.suggested);
    });
  }

  clearDecorations(editor);
  deleteSuggestionFile();
  setSuggestionVisible(false);
  currentSuggestion = null;

  vscode.window.setStatusBarMessage("$(check) FRIDAY: Changes applied", 3000);
}


// =============================================================================
// Dismiss suggestion
// =============================================================================

function dismissSuggestion() {
  const editor = vscode.window.activeTextEditor;
  if (editor) clearDecorations(editor);
  deleteSuggestionFile();
  setSuggestionVisible(false);
  currentSuggestion = null;
  vscode.window.setStatusBarMessage("$(x) FRIDAY: Suggestion dismissed", 2000);
}


// =============================================================================
// Typing pause → trigger autocomplete
// =============================================================================

function onTyping(event) {
  // Only fire when FRIDAY coding mode is active
  if (!fs.existsSync(ACTIVE_FLAG)) return;

  const editor = vscode.window.activeTextEditor;
  if (!editor) return;

  // Clear existing timer
  if (typingTimer) clearTimeout(typingTimer);

  // After 1.5s of silence, send current line to FRIDAY for completion
  typingTimer = setTimeout(() => {
    const cursor   = editor.selection.active;
    const lineText = editor.document.lineAt(cursor.line).text;

    // Only trigger if line has something worth completing
    if (lineText.trim().length < 3) return;

    const trigger = {
      file_path: editor.document.uri.fsPath,
      line:      lineText,
      timestamp: Date.now(),
    };

    fs.writeFileSync(TRIGGER_FILE, JSON.stringify(trigger), "utf8");
  }, 1500);
}


// =============================================================================
// Helpers
// =============================================================================

function clearDecorations(editor) {
  editor.setDecorations(ghostDecoration,   []);
  editor.setDecorations(addedDecoration,   []);
  editor.setDecorations(removedDecoration, []);
}

function deleteSuggestionFile() {
  try { if (fs.existsSync(SUGGESTION_FILE)) fs.unlinkSync(SUGGESTION_FILE); } catch {}
}

function deactivate() {
  if (suggestionWatcher) suggestionWatcher.close();
}

module.exports = { activate, deactivate };