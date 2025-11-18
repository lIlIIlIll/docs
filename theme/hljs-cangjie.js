hljs.registerLanguage("cangjie", function (hljs) {
  "use strict";

  // ---- 关键字 / 字面量 / 内建 / 类型 ----
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

  // ---- 字符 / 字符串 & 转义 / Unicode / 插值 ${ ... } ----
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
    contains: [], // 下面补
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

  // ---- 类型名（大写开头），作为独立 token 标成 .hljs-type ----
  var TYPE_NAME = {
    className: "type",
    begin: /\b[A-Z]\w*\b/,
    relevance: 0,
  };

  // 插值里面也能识别注释 / 字符串 / 数字 / 注解 / 类型名
  SUBST.contains = [
    hljs.C_LINE_COMMENT_MODE,
    hljs.C_BLOCK_COMMENT_MODE,
    STR,
    CHAR,
    NUM,
    { className: "meta", begin: /@[_A-Za-z]\w*/ },
    TYPE_NAME,
  ];

  // ---- 文档注释 ----
  var LINE_DOC = {
    className: "doctag",
    begin: /\/\/\/\s?/,
    end: /$/,
    relevance: 0,
  };

  var BLOCK_DOC = hljs.inherit(hljs.C_BLOCK_COMMENT_MODE, {
    className: "doctag",
    begin: /\/\*\*+/,
    end: /\*+\//,
    contains: [{ begin: /@[\w.]+/ }],
    relevance: 0,
  });

  // ---- 普通注释（直接用 C 风格）----
  var LINE_COMMENT = hljs.C_LINE_COMMENT_MODE;
  var BLOCK_COMMENT = hljs.C_BLOCK_COMMENT_MODE;

  // ---- 注解 / 属性 ----
  var ANNOT = { className: "meta", begin: /@[_A-Za-z]\w*/, relevance: 1 };

  // ---- 声明里的名字（class / struct / func 名）----
  var DECL_TITLE = {
    className: "title",
    begin: /\b[_A-Za-z]\w*\b/,
    relevance: 0,
  };

  // ---- 泛型参数 <T, U?> ----
  var GENERIC = {
    begin: /<(?!:)/, // 避免 "<:" 之类误触发
    end: />/,
    relevance: 0,
    keywords: KW, // 泛型里照样识别关键字/类型
    illegal: /:/, // 避免吞到后面的冒号
    contains: [
      "self", // 允许嵌套 <A<B<C>>>
      TYPE_NAME,
      NUM,
      STR,
      CHAR,
      { begin: /[,?]/, relevance: 0 },
      LINE_COMMENT,
      BLOCK_COMMENT,
    ],
  };

  // ---- class / struct 声明 ----
  var CLASS_DECL = {
    className: "class",
    beginKeywords: "class struct",
    end: /[{;]/,
    excludeEnd: true,
    keywords: KW,
    contains: [
      ANNOT,
      DECL_TITLE, // 类名 / 结构体名
      GENERIC,
      LINE_COMMENT,
      BLOCK_COMMENT,
    ],
  };

  // ---- func / init 声明 ----
  var FUNC_DECL = {
    className: "function",
    beginKeywords: "func init",
    end: /[{;]/,
    excludeEnd: true,
    keywords: KW,
    contains: [
      ANNOT,
      DECL_TITLE, // 函数名
      GENERIC,
      LINE_COMMENT,
      BLOCK_COMMENT,
      // 想进一步搞参数列表/返回类型，可以再加规则
    ],
  };

  // ---- 汇总语言定义 ----
  return {
    name: "cangjie",
    aliases: ["cj", "cangjie"],
    keywords: KW,
    contains: [
      LINE_DOC,
      BLOCK_DOC,
      LINE_COMMENT,
      BLOCK_COMMENT,
      ANNOT,
      CLASS_DECL,
      FUNC_DECL,
      STR,
      CHAR,
      NUM,
      TYPE_NAME,  // 顶层只把“大写开头”的名字当类型，不会吃掉所有标识符
      GENERIC,
    ],
  };
});

