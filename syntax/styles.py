from PySide6.QtGui import QColor, QFont, QTextCharFormat

class SyntaxStyleDark:
    TextEditBackground = QColor("#282C34")
    DefaultText = QColor("#ABB2BF")

    Default = {"foreground": DefaultText}
    Keyword = {"foreground": QColor("#C678DD"), "font_weight": QFont.Bold}
    Placeholder = {"foreground": QColor("#98C379"), "underline": True}
    Comment = {"foreground": QColor("#5C6370"), "italic": True}
    String = {"foreground": QColor("#98C379")}
    Number = {"foreground": QColor("#D19A66")}
    SpecialTag = {"foreground": QColor("#E5C07B")}
    VarInsert = {"foreground": QColor("#56B6C2"), "font_weight": QFont.Bold}

    @staticmethod
    def get_format(style_dict):
        fmt = QTextCharFormat()
        if "foreground" in style_dict:
            fmt.setForeground(style_dict["foreground"])
        if "background" in style_dict:
            fmt.setBackground(style_dict["background"])
        if style_dict.get("font_weight") == QFont.Bold:
            fmt.setFontWeight(QFont.Bold)
        if style_dict.get("italic"):
            fmt.setFontItalic(True)
        if style_dict.get("underline"):
            fmt.setFontUnderline(True)
        return fmt

HIGHLIGHTING_RULES_DARK_TUPLES = [
    # Matches: // comment text
    (r"//[^\n]*", SyntaxStyleDark.get_format(SyntaxStyleDark.Comment), False),
    
    # Matches: "string" or 'string'
    (r"(\"[^\"]*\"|'[^']*')", SyntaxStyleDark.get_format(SyntaxStyleDark.String), False),
    
    # Matches: IF, THEN, ELSEIF, ELSE, ENDIF, SET, RETURN, LOAD, LOG, ADD_SYSTEM_INFO, AND, OR, TRUE, FALSE, NONE, LOCAL
    (r"\b(IF|THEN|ELSEIF|ELSE|ENDIF|SET|RETURN|LOAD|LOG|ADD_SYSTEM_INFO|AND|OR|TRUE|FALSE|NONE|LOCAL)\b",
     SyntaxStyleDark.get_format(SyntaxStyleDark.Keyword), False),
    
    # Matches: <tag>, </tag>, <!tag>
    (r"<[/!]?[a-zA-Z_][^>]*>", SyntaxStyleDark.get_format(SyntaxStyleDark.SpecialTag), False),
    
    # Matches: 123, 123.456
    (r"\b\d+(\.\d+)?\b", SyntaxStyleDark.get_format(SyntaxStyleDark.Number), False),
    
    # Matches: [<file.script>], [<path/file.txt>], [<module.system>]
    (r"(\[<)([^>]+\.(?:script|txt|system))(>\])", SyntaxStyleDark.get_format(SyntaxStyleDark.Placeholder), True),
    
    # Matches: [{VAR_NAME}], [{player_name}]
    (r"(\[\{)([A-Za-z_][A-Za-z0-9_]*)(\}\])", SyntaxStyleDark.get_format(SyntaxStyleDark.VarInsert), False),
    
    # Matches: {{INSERT_NAME}}, {{SYS_INFO}}
    (r"\{\{[A-Z0-9_]+\}\}", SyntaxStyleDark.get_format(SyntaxStyleDark.SpecialTag), False),
]