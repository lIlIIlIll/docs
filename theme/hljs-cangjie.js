/*
 * Language: Cangjie
 */
function cangjie(hljs) {
  const regex = hljs.regex;
  const IDENTIFIER =
    "((`[\u00C0-\u9fa5a-zA-Z_][\u00C0-\u9fa5a-zA-Z_0-9]*`)|([\u00C0-\u9fa5a-zA-Z_][\u00C0-\u9fa5a-zA-Z_0-9]*))";
  const NUMBER_SUFFIX = "(u8|u16|u32|u64|i8|i16|i32|i64|f16|f32|f64)\?";
  const KEYWORDS = [
    "as",
    "abstract",
    "break",
    "Bool",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "Rune",
    "do",
    "else",
    "enum",
    "extend",
    "for",
    "from",
    "func",
    "false",
    "finally",
    "foreign",
    "Float16",
    "Float32",
    "Float64",
    "if",
    "in",
    "is",
    "init",
    "import",
    "interface",
    "Int8",
    "Int16",
    "Int32",
    "Int64",
    "IntNative",
    "let",
    "mut",
    "main",
    "macro",
    "match",
    "Nothing",
    "open",
    "operator",
    "override",
    "prop",
    "public",
    "internal",
    "package",
    "private",
    "protected",
    "quote",
    "redef",
    "return",
    "sealed",
    "spawn",
    "super",
    "static",
    "struct",
    "synchronized",
    "try",
    "this",
    "true",
    "type",
    "throw",
    "This",
    "unsafe",
    "Unit",
    "UInt8",
    "UInt16",
    "UInt32",
    "UInt64",
    "UIntNative",
    "var",
    "VArray",
    "where",
    "while",
  ];
  const NUMBERS = {
    className: "number",
    variants: [
      { begin: "\\b(\\.)?0o([0-7_]+)" + NUMBER_SUFFIX },
      {
        begin:
          "\\b(\\.)?0x([A-Fa-f0-9_]*)" +
          NUMBER_SUFFIX +
          "([eEpP][+-]?[0-9_]+)?",
      },
      {
        begin:
          "\\b(\\.)?(\\d[\\d_]*(\\.[0-9_]+)?([eEpP][+-]?[0-9_]+)?)" +
          NUMBER_SUFFIX,
      },
      { begin: "\\b(\\.)?b'" + IDENTIFIER + "'" },
      { begin: "\\b(\\.)?b'" + "\\\\" + IDENTIFIER + "'" },
      { begin: "\\b(\\.)?b'" + IDENTIFIER + "'" + "{" + "([0-9]+)" + "}" },
      {
        begin:
          "\\b(\\.)?b'" + "\\\\" + IDENTIFIER + "{" + "([0-9]+)" + "}" + "'",
      },
      { begin: "(^|[^\\.])(\\.\\d+)([eEpP][+-]?[0-9_]+)?" + NUMBER_SUFFIX },
    ],
    relevance: 0,
  };

  const FUNC_TYPE = {
    begin: "(\\()",
    end: "(\\)|/|{|=)",
    contains: [
      "self", // 递归调用自身以支持嵌套泛型
      hljs.C_LINE_COMMENT_MODE,
      hljs.COMMENT("/\\*", "\\*/", { contains: ["self"] }),
      {
        begin: "\\b(" + KEYWORDS.join("|") + ")\\b",
        relevance: 0,
        className: "keyword",
      },
      {
        begin: "(\\+|\\-|\\*|\\/|\\%)(\\s*)" + IDENTIFIER,
        relevance: 0,
        className: "variable",
      },
      {
        begin: IDENTIFIER + "\\b" + "(?!(\\s*)(:|\\+|\\-|\\*|\\/|\\%))",
        relevance: 0,
        className: "title.class",
      },
      {
        begin: "\\b" + IDENTIFIER + "\\b",
        relevance: 0,
        className: "variable",
      },
      {
        begin: ",",
        relevance: 0,
      },
      NUMBERS,
    ],
  };
  const GENERICS = {
    begin: "(<)(?!(:|-))",
    end: "((>)|\\n|\\r)",
    contains: [
      "self", // 递归调用自身以支持嵌套泛型
      hljs.C_LINE_COMMENT_MODE,
      hljs.COMMENT("/\\*", "\\*/", { contains: ["self"] }),
      FUNC_TYPE,
      {
        begin: "\\b(" + KEYWORDS.join("|") + ")\\b",
        relevance: 0,
        className: "keyword",
      },
      {
        begin: IDENTIFIER,
        relevance: 0,
        className: "title.class",
      },
      {
        begin: ",",
        relevance: 0,
      },
      {
        begin: "->",
        relevance: 0,
      },
      NUMBERS,
    ],
  };
  const STRINGS = [
    {
      className: "string",
      begin: "'",
      end: "'",
      contains: [hljs.BACKSLASH_ESCAPE],
    },
    {
      className: "string",
      begin: '"',
      end: '"',
      contains: [
        {
          className: "subst",
          begin: "\\$\\{",
          end: "\\}",
          contains: [
            "self",
            {
              className: "keyword",
              begin: "\\b(" + KEYWORDS.join("|") + ")\\b",
            },
            {
              className: "title.function",
              begin: "\\b(" + KEYWORDS.join("|") + ")\\b" + "(?=(\\s*)\\()",
            },
            {
              className: "title.function",
              begin: IDENTIFIER + "(?=(\\s*)\\()",
            },
            {
              className: "variable",
              begin: IDENTIFIER,
            },
            {
              className: "number",
              begin: "\\b(\\.)?\\d+(\\.\\d+)?",
              relevance: 0,
            },
            {
              className: "string",
              begin: '"',
              end: '"',
            },
          ],
        },
        hljs.BACKSLASH_ESCAPE,
      ],
    },
    {
      className: "string",
      begin: '"""',
      end: '"""',
      contains: [
        {
          className: "subst",
          begin: "\\$\\{",
          end: "\\}",
          contains: [
            "self",
            {
              className: "keyword",
              begin: "\\b(" + KEYWORDS.join("|") + ")\\b",
            },
            {
              className: "title.function",
              begin: "\\b(" + KEYWORDS.join("|") + ")\\b" + "(?=(\\s*)\\()",
            },
            {
              className: "title.function",
              begin: IDENTIFIER + "(?=(\\s*)\\()",
            },
            {
              className: "variable",
              begin: IDENTIFIER,
            },
            {
              className: "number",
              begin: "\\b(\\.)?\\d+(\\.\\d+)?",
              relevance: 0,
            },
            {
              className: "string",
              begin: '"',
              end: '"',
            },
          ],
        },
        hljs.BACKSLASH_ESCAPE,
      ],
    },
    {
      className: "string",
      variants: [
        { begin: /b?(#*)("|')(.|\n)*?("|')\1(?!#)/ },
        { begin: /b?'\\?(x\w{2}|u\w{4}|U\w{8}|.)'/ },
      ],
    },
  ];
  return {
    name: "Cangjie",
    aliases: ["cj"],
    keywords: KEYWORDS,
    illegal: "</",
    contains: [
      hljs.C_LINE_COMMENT_MODE,
      hljs.COMMENT("/\\*", "\\*/", { contains: ["self"] }),
      NUMBERS,
      ...STRINGS,
      {
        className: "symbol",
        begin: /'[a-zA-Z_][a-zA-Z0-9_]*/,
      },
      {
        begin: [/(?:package)/, /\s+/, IDENTIFIER + "(\\." + IDENTIFIER + ")*"],
        className: {
          1: "keyword",
          3: "package",
        },
      },
      {
        begin: [
          /(?:from)/,
          /\s+/,
          IDENTIFIER + "(\\." + IDENTIFIER + ")*",
          /\s+/,
          /(?:import)/,
          /\s+/,
          IDENTIFIER + "(\\." + IDENTIFIER + ")*" + "(\\.\\*)?",
        ],
        className: {
          1: "keyword",
          3: "package",
          5: "keyword",
          7: "package",
        },
      },
      {
        begin: [
          /(?:import)/,
          /\s+/,
          IDENTIFIER + "(\\." + IDENTIFIER + ")*" + "(\\.\\*)?",
          /\s+/,
          /(?:as)/,
          /\s+/,
          IDENTIFIER + "(\\." + IDENTIFIER + ")*" + "(\\.\\*)?",
        ],
        className: {
          1: "keyword",
          3: "package",
          5: "keyword",
          7: "package",
        },
      },
      {
        begin: [
          /(?:import)/,
          /\s+/,
          "(" +
            IDENTIFIER +
            "\\.)*\\{(" +
            IDENTIFIER +
            "(\\." +
            IDENTIFIER +
            ")*" +
            "(\\.\\*)?" +
            ",?\\s*)+\\}",
        ],
        className: {
          1: "keyword",
          3: "package",
        },
      },
      {
        begin: [
          /(?:import)/,
          /\s+/,
          IDENTIFIER + "(\\." + IDENTIFIER + ")*" + "(\\.\\*)?",
        ],
        className: {
          1: "keyword",
          3: "package",
        },
      },
      {
        begin: [/main/, /\s*/, /\(/, /\)/],
        className: {
          1: "keyword",
        },
      },
      {
        begin: [/func/, /\s+/, IDENTIFIER],
        className: {
          1: "keyword",
          3: "title.function",
        },
      },
      {
        className: "keyword",
        relevance: 0,
        begin: regex.concat(
          /\b/,
          "\\b(" + KEYWORDS.join("|") + ")\\b",
          regex.lookahead(/\s*\(/),
        ),
      },
      {
        className: "title.function",
        relevance: 0,
        begin: regex.concat(
          /\b/,
          IDENTIFIER,
          regex.lookahead(/(?<=[\t\s]*)\(/),
        ),
      },
      {
        className: "title.function",
        relevance: 0,
        begin: regex.concat("`" + IDENTIFIER + "`", regex.lookahead(/\s*\(/)),
      },
      {
        begin: [/@/, IDENTIFIER + "(\\." + IDENTIFIER + ")*"],
        className: {
          2: "title.function",
        },
      },
      {
        begin: [/let|var|const|prop/, /\s+/, IDENTIFIER],
        className: {
          1: "keyword",
          3: "variable",
        },
      },
      {
        begin: [/type/, /\s+/, IDENTIFIER],
        className: {
          1: "keyword",
          3: "title.class",
        },
      },
      {
        begin: [
          /(?:class|interface|enum|struct|extend)/,
          /\s+/,
          "\\b(" + KEYWORDS.join("|") + ")\\b",
        ],
        className: {
          1: "keyword",
          3: "keyword",
        },
      },
      {
        begin: [/(?:class|interface|enum|struct|extend)/, /\s+/, IDENTIFIER],
        className: {
          1: "keyword",
          3: "title.class",
        },
      },
      {
        begin: [
          /VArray/,
          /\s*/,
          /</,
          /\s*/,
          "\\b(" + KEYWORDS.join("|") + ")\\b",
          /\s*/,
          /,/,
          /\s*/,
          /\$/,
          /([0-9]+)/,
          />/,
        ],
        className: {
          1: "keyword",
          5: "keyword",
          10: "number",
        },
      },
      {
        begin: [
          /VArray/,
          /\s*/,
          /</,
          /\s*/,
          IDENTIFIER,
          /\s*/,
          /,/,
          /\s*/,
          /\$/,
          /([0-9]+)/,
          />/,
        ],
        className: {
          1: "keyword",
          5: "title.class",
          10: "number",
        },
      },
      {
        begin: [/VArray/, /\s*/, regex.lookahead(/\s*\(/)],
        className: {
          1: "keyword",
        },
      },
      {
        begin: [/init/, /\s*/, regex.lookahead(/\s*\(/)],
        className: {
          1: "keyword",
        },
      },
      {
        begin: [/~init/, /\s*/, regex.lookahead(/\s*\(/)],
        className: {
          1: "keyword",
        },
      },
      {
        begin: "(:|-\\>)(?!(\\s*)\\[)",
        end: "(,|/|\\)|]|{|=|\\r|\\n)",
        contains: [
          hljs.C_LINE_COMMENT_MODE,
          hljs.COMMENT("/\\*", "\\*/", { contains: ["self"] }),
          {
            begin: "<<",
          },
          GENERICS,
          FUNC_TYPE,
          {
            begin: "\\b(" + KEYWORDS.join("|") + ")\\b",
            className: "keyword",
          },
          {
            begin: IDENTIFIER,
            className: "title.class",
          },
          {
            begin: "\\|",
          },
          NUMBERS,
          ...STRINGS,
        ],
      },
      {
        begin: ["(^|[^&])&", /\s*/, "\\b(" + KEYWORDS.join("|") + ")\\b"],
        className: {
          3: "keyword",
        },
      },
      {
        begin: ["(^|[^&])&", /\s*/, IDENTIFIER],
        className: {
          3: "title.class",
        },
      },
      {
        begin: IDENTIFIER + "(?=(\\s*)(<:))",
        className: "title.class",
      },
      {
        begin: IDENTIFIER + "(?=\\s*\\<[\\*\\<\\,\\-\\(\\)\\w\\s]*\\>)",
        className: "title.class",
      },
      {
        begin: "<<",
      },
      GENERICS,
      {
        begin: "\\b(" + KEYWORDS.join("|") + ")\\b",
        relevance: 0,
        className: "keyword",
      },
      {
        className: "variable",
        begin: IDENTIFIER,
        relevance: 0,
      },
    ],
  };
}

hljs.registerLanguage("cangjie", cangjie);
