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
    (r"//[^\n]*", SyntaxStyleDark.get_format(SyntaxStyleDark.Comment), False),
    (r"(\".*?\"|\'.*?\')", SyntaxStyleDark.get_format(SyntaxStyleDark.String), False),
    (r"\b(IF|THEN|ELSEIF|ELSE|ENDIF|SET|RETURN|LOAD|LOG|AND|OR|TRUE|FALSE|NONE)\b", SyntaxStyleDark.get_format(SyntaxStyleDark.Keyword), False), # CaseInsensitiveOption будет добавлена в highlighter
    (r"<[/!]?[a-zA-Z_][^>]*>", SyntaxStyleDark.get_format(SyntaxStyleDark.SpecialTag), False),
    (r"\b\d+(\.\d+)?\b", SyntaxStyleDark.get_format(SyntaxStyleDark.Number), False),
    (r"(\[<)([^\]>]+?\.(?:script|txt))(>\])", SyntaxStyleDark.get_format(SyntaxStyleDark.Placeholder), True), # is_link_rule = True
]