// frontend/src/syntax/syntaxStyles.js

// Corresponds to QFont.Bold, common CSS value for bold
export const PYSIDE_FONT_BOLD = 'bold';

// Define style objects that will map to CSS classes
export const editorThemes = {
  dark: {
    Default: { color: "#ABB2BF", className: "sh-default" },
    Keyword: { color: "#C678DD", fontWeight: PYSIDE_FONT_BOLD, className: "sh-keyword" },
    PlaceholderLink: { color: "#98C379", textDecoration: "underline", className: "sh-placeholder-link" },
    Comment: { color: "#5C6370", fontStyle: "italic", className: "sh-comment" },
    String: { color: "#98C379", className: "sh-string" },
    Number: { color: "#D19A66", className: "sh-number" },
    SpecialTag: { color: "#E5C07B", className: "sh-specialtag" }, // XML-like <tags>

    // Custom rules from Python __init__
    LoadCommand: { color: "#569CD6", fontWeight: PYSIDE_FONT_BOLD, className: "sh-loadcommand" },
    SectionMarker: { color: "#C586C0", fontWeight: PYSIDE_FONT_BOLD, className: "sh-sectionmarker" },
    Insert: { color: "#FFAC33", fontWeight: PYSIDE_FONT_BOLD, className: "sh-insert" },
    TripleQuoteString: { color: "#FFA500", className: "sh-triplestring" }, // Default for """..."""
  }
};

export const currentTheme = editorThemes.dark; // Or make this configurable

// Helper to identify DSL keywords for disabling in .txt files
export const DSL_KEYWORDS_PATTERN = /\b(IF|THEN|ELSEIF|ELSE|ENDIF|SET|RETURN|LOAD|LOG|AND|OR|TRUE|FALSE|NONE)\b/i;

export const highlightingRules = [
  // Basic rules (order matters for overrides)
  { id: "comment", regex: /\/\/[^\n]*/g, styleKey: "Comment", isLink: false },
  // Strings will be handled carefully with triple quotes
  { id: "single_double_quote_string", regex: /(".*?"|'.*?')/g, styleKey: "String", isLink: false },
  { id: "dsl_keywords", regex: new RegExp(DSL_KEYWORDS_PATTERN.source, 'gi'), styleKey: "Keyword", isLink: false, isDslKeywordRule: true },
  { id: "special_tag", regex: /<[/!]?[a-zA-Z_][^>]*>/g, styleKey: "SpecialTag", isLink: false },
  { id: "number", regex: /\b\d+(\.\d+)?\b/g, styleKey: "Number", isLink: false },
  { id: "placeholder_link", regex: /(\[<)([^\]>]+?\.(?:script|txt))(>\])/g, styleKey: "PlaceholderLink", isLink: true, linkGroup: 2 }, // group 2 for path

  // Custom rules from Python __init__ (ensure regexes are global 'g' and case-insensitive 'i' where needed)
  { id: "load_tag_from", regex: /\bLOAD\s+[A-Z0-9_]+\s+FROM\s+['"][^'"]+['"]/gi, styleKey: "LoadCommand", isLink: false, isDslKeywordRule: true }, // LOAD is a DSL keyword
  { id: "section_marker", regex: /\[(?:#|\/)\s*[A-Z0-9_]+\s*]/gi, styleKey: "SectionMarker", isLink: false },
  { id: "insert_tag", regex: /\{\{[A-Z0-9_]+\}\}/g, styleKey: "Insert", isLink: false },
];

export const TRIPLE_QUOTE_MARKER = '"""';
export const TRIPLE_QUOTE_STYLE_KEY = "TripleQuoteString";