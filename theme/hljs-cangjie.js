hljs.registerLanguage(
  "cangjie",
  (function () {
    "use strict";
    return function (e) {
      var KW = {
        keyword:
          "package import class extend func init prop " +
          "public private protected internal mut " +
          "abstract final sealed open override static " +
          "operator foreign macro unsafe " +
          "if else for while break continue return throw try catch finally " +
          "match case when in is as where get set new this super " +
          "let var const struct main ",
        literal: "true false None Some _ unit",
        built_in: "print println eprint eprintln spawn len range assert panic",
        type:
          "Int UInt Int8 Int16 Int32 Int64 " +
          "UInt8 UInt16 UInt32 UInt64 " +
          "Float16 Float32 Float64 Rune String CString Unit Any",
      };

      // ---- 数字字面量（含后缀 i/u/f + 位宽）----
      var SUFFIX = "(?:[iuf](?:8|16|32|64|128)?)";
      var INT_CORE = "(?:0|[1-9](?:_?[0-9])*)";
      var BIN = "0b[01](?:_?[01])*";
      var OCT = "0o[0-7](?:_?[0-7])*";
      var HEX = "0x[0-9A-Fa-f](?:_?[0-9A-Fa-f])*";
      var DEC_FRAC =
        "(?:" + INT_CORE + "\\.(?:[0-9](?:_?[0-9])*)|\\.[0-9](?:_?[0-9])*)";
      var DEC_EXP = "[eE][+-]?[0-9](?:_?[0-9])*";
      var FLOAT_CORE =
        "(?:" + DEC_FRAC + "(?:" + DEC_EXP + ")?|" + INT_CORE + DEC_EXP + ")";

      var NUM = {
        className: "number",
        variants: [
          { begin: "\\b" + BIN + "(?:" + SUFFIX + ")?\\b" },
          { begin: "\\b" + OCT + "(?:" + SUFFIX + ")?\\b" },
          { begin: "\\b" + HEX + "(?:" + SUFFIX + ")?\\b" },
          { begin: "\\b" + FLOAT_CORE + "(?:" + SUFFIX + ")?\\b" },
          { begin: "\\b" + INT_CORE + "(?:" + SUFFIX + ")?\\b" },
        ],
        relevance: 0,
      };

      // ---- 字符/字符串 & 转义/Unicode/插值 ${ ... } ----
      var CHAR = {
        className: "string",
        begin: /'/,
        end: /'/,
        illegal: /\\n/,
        contains: [
          { className: "escape", begin: /\\[nrt'\\"]/ },
          { className: "escape", begin: /\\u\{[0-9A-Fa-f_]+\}/ },
        ],
      };

      var SUBST = {
        className: "subst",
        begin: /\$\{/,
        end: /\}/,
        keywords: KW,
        // 递归在下方填充
        contains: [],
      };

      var STR = {
        className: "string",
        begin: /"/,
        end: /"/,
        contains: [
          { begin: "{{" }, // 容错插值大括号
          { begin: "}}" },
          { className: "escape", begin: /\\[nrt'"\\]/ },
          { className: "escape", begin: /\\u\{[0-9A-Fa-f_]+\}/ },
          SUBST,
        ],
      };

      // 让插值中也能有注释/字符串/数字/注解/类型名
      SUBST.contains = [
        e.C_LINE_COMMENT_MODE,
        e.C_BLOCK_COMMENT_MODE,
        STR,
        CHAR,
        NUM,
        { className: "meta", begin: /@[_A-Za-z]\w*/ },
        { className: "title", begin: /\b[A-Z]\w*\b/ },
      ];

      // ---- 文档注释 ----
      var LINE_DOC = {
        className: "doctag",
        begin: /\/\/\/\s?/,
        end: /$/,
        relevance: 0,
      };
      var BLOCK_DOC = e.inherit(e.C_BLOCK_COMMENT_MODE, {
        className: "doctag",
        begin: /\/\*\*+/,
        end: /\*+\//,
        contains: [{ begin: /@[\w.]+/ }],
        relevance: 0,
      });

      // ---- 注解 / 属性 ----
      var ANNOT = { className: "meta", begin: /@[_A-Za-z]\w*/, relevance: 1 };

      // ---- 类型名（首字母大写）
      var TYPE_TITLE = {
        className: "title",
        begin: /\b[a-zA-Z]\w*\b/,
        relevance: 0,
      };
      var GENERIC = {
        begin: /<(?!:)/, // 关键：排除 "<:" 触发
        end: />/,
        relevance: 0,
        keywords: KW, // 在尖括号内也继续识别关键字/字面量（保险）
        illegal: /:/, // 如果在未闭合时遇到冒号，直接让此模式失败，避免吞后文
        contains: [
          "self", // 允许嵌套 <A<B<C>>>
          TYPE_TITLE,
          NUM,
          STR,
          CHAR,
          { begin: /[,?]/, relevance: 0 }, // 逗号 / 可空标记（按需）
          e.C_LINE_COMMENT_MODE,
          e.C_BLOCK_COMMENT_MODE,
        ],
      };

      // ---- 返回语言定义 ----
      return {
        name: "cangjie",
        aliases: ["cj", "cangjie"],
        keywords: KW,
        contains: [
          LINE_DOC,
          BLOCK_DOC,
          e.C_LINE_COMMENT_MODE,
          e.C_BLOCK_COMMENT_MODE,
          ANNOT,
          STR,
          CHAR,
          NUM,
          TYPE_TITLE,
          GENERIC,
        ],
      };
    };
  })(),
);
