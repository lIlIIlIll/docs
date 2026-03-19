local M = {}

local uv = vim.uv or vim.loop

local function read_file(path)
  local fd = assert(uv.fs_open(path, "r", 438), "failed to open docs index: " .. path)
  local stat = assert(uv.fs_fstat(fd), "failed to stat docs index: " .. path)
  local data = assert(uv.fs_read(fd, stat.size, 0), "failed to read docs index: " .. path)
  uv.fs_close(fd)
  return data
end

local function json_decode(text)
  if vim.json and vim.json.decode then
    return vim.json.decode(text)
  end
  return vim.fn.json_decode(text)
end

local function normalize_term(value)
  return (value or ""):lower()
end

local function trim(value)
  return (value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function markdown_text(value)
  if not value or value == "" then
    return nil
  end
  return {
    kind = "markdown",
    value = value,
  }
end

local function add_unique(list, seen, value)
  if value and value ~= "" and not seen[value] then
    seen[value] = true
    list[#list + 1] = value
  end
end

local function validate_symbol(symbol)
  local required = {
    "id",
    "fqname",
    "kind",
    "package",
    "module",
    "display",
    "signature",
    "summary_short_md",
    "page_url",
    "aliases",
    "search_keys",
    "search_keys_normalized",
  }
  for _, key in ipairs(required) do
    if symbol[key] == nil then
      error("docs-index symbol missing required field: " .. key)
    end
  end
end

local function build_symbol_maps(symbols)
  local by_id = {}
  local by_fqname = {}
  local by_alias = {}
  local by_search_key = {}

  for _, symbol in ipairs(symbols) do
    validate_symbol(symbol)
    by_id[symbol.id] = symbol
    by_fqname[symbol.fqname] = symbol

    for _, alias in ipairs(symbol.aliases or {}) do
      by_alias[alias] = by_alias[alias] or {}
      table.insert(by_alias[alias], symbol)
    end

    for _, key in ipairs(symbol.search_keys_normalized or {}) do
      local normalized = normalize_term(key)
      by_search_key[normalized] = by_search_key[normalized] or {}
      table.insert(by_search_key[normalized], symbol)
    end

    for _, key in ipairs(symbol.search_keys or {}) do
      local normalized = normalize_term(key)
      by_search_key[normalized] = by_search_key[normalized] or {}
      table.insert(by_search_key[normalized], symbol)
    end
  end

  return by_id, by_fqname, by_alias, by_search_key
end

local function build_diagnostic_map(diagnostics)
  local by_code = {}
  for _, item in ipairs(diagnostics or {}) do
    local code = tostring(item.code)
    by_code[code] = by_code[code] or {}
    table.insert(by_code[code], item)
  end
  return by_code
end

local function score_symbol(symbol, term)
  local normalized = normalize_term(term)
  if normalized == "" then
    return nil
  end

  local best
  local function consider(candidate, score)
    if not candidate or candidate == "" then
      return
    end
    local text = normalize_term(candidate)
    if text == normalized then
      best = math.max(best or 0, score)
      return
    end
    if vim.startswith(text, normalized) then
      best = math.max(best or 0, score - 10)
      return
    end
    if text:find(normalized, 1, true) then
      best = math.max(best or 0, score - 20)
    end
  end

  consider(symbol.fqname, 120)
  consider(symbol.display, 110)
  consider(symbol.container and (symbol.container .. "." .. symbol.display) or nil, 100)

  for _, alias in ipairs(symbol.aliases or {}) do
    consider(alias, 95)
  end
  for _, key in ipairs(symbol.search_keys or {}) do
    consider(key, 90)
  end

  return best
end

local function format_related_links(symbol)
  local links = symbol.related_links or {}
  if vim.tbl_isempty(links) then
    return nil
  end

  local lines = { "相关链接：" }
  for _, link in ipairs(links) do
    local title = link.title or link.url
    local kind = link.kind and ("[" .. link.kind .. "] ") or ""
    lines[#lines + 1] = string.format("- %s[%s](%s)", kind, title, link.url)
  end
  return table.concat(lines, "\n")
end

local function format_deprecated(symbol)
  local deprecated = symbol.deprecated
  if not deprecated or not deprecated.is_deprecated then
    return nil
  end

  local parts = { "Deprecated" }
  if deprecated.since then
    parts[1] = parts[1] .. " since " .. deprecated.since
  end
  if deprecated.message_md and deprecated.message_md ~= "" then
    parts[#parts + 1] = deprecated.message_md
  end
  if deprecated.replacement_fqname and deprecated.replacement_fqname ~= "" then
    local replacement = "Replacement: `" .. deprecated.replacement_fqname .. "`"
    if deprecated.replacement_url and deprecated.replacement_url ~= "" then
      replacement = replacement .. " ([docs](" .. deprecated.replacement_url .. "))"
    end
    parts[#parts + 1] = replacement
  end
  return table.concat(parts, "\n\n")
end

local function format_availability(symbol)
  local availability = symbol.availability
  if not availability then
    return nil
  end

  local lines = {}
  if availability.supported_platforms and not vim.tbl_isempty(availability.supported_platforms) then
    lines[#lines + 1] = "Supported platforms: " .. table.concat(availability.supported_platforms, ", ")
  end
  if availability.unsupported_platforms and not vim.tbl_isempty(availability.unsupported_platforms) then
    lines[#lines + 1] = "Unsupported platforms: " .. table.concat(availability.unsupported_platforms, ", ")
  end
  if vim.tbl_isempty(lines) then
    return nil
  end
  return table.concat(lines, "\n")
end

local function format_extension_info(symbol)
  local info = symbol.extension_info
  if not info then
    return nil
  end
  local parts = {}
  if info.target_display and info.target_display ~= "" then
    parts[#parts + 1] = "Extension target: `" .. info.target_display .. "`"
  end
  if info.implements and info.implements ~= "" then
    parts[#parts + 1] = "Implements: `" .. info.implements .. "`"
  end
  if info.extension_owner_fqname and info.extension_owner_fqname ~= "" then
    parts[#parts + 1] = "Owner: `" .. info.extension_owner_fqname .. "`"
  end
  if vim.tbl_isempty(parts) then
    return nil
  end
  return table.concat(parts, "\n")
end

local function format_examples(symbol)
  local examples = symbol.examples_md or {}
  if vim.tbl_isempty(examples) then
    return nil
  end

  local chunks = { "示例：" }
  for _, example in ipairs(examples) do
    chunks[#chunks + 1] = example
  end
  return table.concat(chunks, "\n\n")
end

local function format_callable_details(symbol)
  local callable = symbol.callable
  if not callable then
    return nil
  end

  local sections = {}
  if callable.params and not vim.tbl_isempty(callable.params) then
    local lines = { "参数：" }
    for _, param in ipairs(callable.params) do
      local header = "- `" .. (param.label or "?") .. "`"
      if param.type and param.type ~= "" then
        header = header .. ": `" .. param.type .. "`"
      end
      local tags = {}
      if param.is_named then
        tags[#tags + 1] = "named"
      end
      if param.has_default then
        tags[#tags + 1] = "default"
      end
      if not vim.tbl_isempty(tags) then
        header = header .. " (" .. table.concat(tags, ", ") .. ")"
      end
      lines[#lines + 1] = header
      if param.doc_md and param.doc_md ~= "" then
        lines[#lines + 1] = "  " .. param.doc_md
      end
      if param.default_value_md and param.default_value_md ~= "" then
        lines[#lines + 1] = "  默认值: `" .. param.default_value_md .. "`"
      end
    end
    sections[#sections + 1] = table.concat(lines, "\n")
  end

  if symbol.returns_md and symbol.returns_md ~= "" then
    sections[#sections + 1] = "返回值：\n" .. symbol.returns_md
  elseif callable.return_type and callable.return_type ~= "" and callable.return_type ~= "Unit" then
    sections[#sections + 1] = "返回类型：`" .. callable.return_type .. "`"
  end

  if callable.throws and not vim.tbl_isempty(callable.throws) then
    local lines = { "异常：" }
    for _, item in ipairs(callable.throws) do
      local line = "- `" .. (item.type or "?") .. "`"
      if item.doc_md and item.doc_md ~= "" then
        line = line .. " " .. item.doc_md
      end
      lines[#lines + 1] = line
    end
    sections[#sections + 1] = table.concat(lines, "\n")
  end

  if vim.tbl_isempty(sections) then
    return nil
  end
  return table.concat(sections, "\n\n")
end

local function build_hover_value(symbol)
  local chunks = {}
  add_unique(chunks, {}, "```cangjie\n" .. (symbol.signature or symbol.display) .. "\n```")

  local deprecated = format_deprecated(symbol)
  if deprecated then
    chunks[#chunks + 1] = deprecated
  end

  local availability = format_availability(symbol)
  if availability then
    chunks[#chunks + 1] = availability
  end

  local extension = format_extension_info(symbol)
  if extension then
    chunks[#chunks + 1] = extension
  end

  if symbol.summary_short_md and symbol.summary_short_md ~= "" then
    chunks[#chunks + 1] = symbol.summary_short_md
  end

  if symbol.summary_md and symbol.summary_md ~= "" and symbol.summary_md ~= symbol.summary_short_md then
    chunks[#chunks + 1] = symbol.summary_md
  end

  if symbol.details_md and symbol.details_md ~= "" then
    chunks[#chunks + 1] = symbol.details_md
  end

  if symbol.notes_md and symbol.notes_md ~= "" and symbol.notes_md ~= symbol.details_md then
    chunks[#chunks + 1] = symbol.notes_md
  end

  local callable = format_callable_details(symbol)
  if callable then
    chunks[#chunks + 1] = callable
  end

  if symbol.exceptions_md and symbol.exceptions_md ~= "" then
    chunks[#chunks + 1] = symbol.exceptions_md
  end

  if symbol.see_also_md and symbol.see_also_md ~= "" then
    chunks[#chunks + 1] = symbol.see_also_md
  end

  local examples = format_examples(symbol)
  if examples then
    chunks[#chunks + 1] = examples
  end

  local related = format_related_links(symbol)
  if related then
    chunks[#chunks + 1] = related
  end

  chunks[#chunks + 1] = string.format("[查看文档](%s%s)", symbol.page_url, symbol.anchor and ("#" .. symbol.anchor) or "")
  return table.concat(chunks, "\n\n")
end

local function build_parameter_documentation(param)
  local parts = {}
  if param.type and param.type ~= "" then
    parts[#parts + 1] = "类型：`" .. param.type .. "`"
  end
  if param.doc_md and param.doc_md ~= "" then
    parts[#parts + 1] = param.doc_md
  end
  if param.default_value_md and param.default_value_md ~= "" then
    parts[#parts + 1] = "默认值：`" .. param.default_value_md .. "`"
  end
  return markdown_text(table.concat(parts, "\n\n"))
end

function M.load(path)
  local data = json_decode(read_file(path))
  assert(type(data) == "table", "docs index must decode to a table")
  assert(data.format == 4, "unsupported docs index format: " .. tostring(data.format))
  assert(type(data.symbols) == "table", "docs index missing symbols")
  assert(type(data.diagnostics) == "table", "docs index missing diagnostics")

  local by_id, by_fqname, by_alias, by_search_key = build_symbol_maps(data.symbols)
  local diagnostics_by_code = build_diagnostic_map(data.diagnostics)

  return setmetatable({
    path = path,
    raw = data,
    symbols = data.symbols,
    diagnostics = data.diagnostics,
    by_id = by_id,
    by_fqname = by_fqname,
    by_alias = by_alias,
    by_search_key = by_search_key,
    diagnostics_by_code = diagnostics_by_code,
  }, { __index = M })
end

function M:get_symbol(ref)
  if not ref or ref == "" then
    return nil
  end
  return self.by_id[ref] or self.by_fqname[ref]
end

function M:get_symbols_by_alias(alias)
  return self.by_alias[alias] or {}
end

function M:find_symbols(term, opts)
  opts = opts or {}
  local limit = opts.limit or 20
  local matches = {}

  for _, symbol in ipairs(self.symbols) do
    local score = score_symbol(symbol, term)
    if score then
      matches[#matches + 1] = {
        symbol = symbol,
        score = score,
      }
    end
  end

  table.sort(matches, function(a, b)
    if a.score ~= b.score then
      return a.score > b.score
    end
    if a.symbol.fqname ~= b.symbol.fqname then
      return a.symbol.fqname < b.symbol.fqname
    end
    return a.symbol.id < b.symbol.id
  end)

  local result = {}
  for i = 1, math.min(limit, #matches) do
    result[#result + 1] = matches[i].symbol
  end
  return result
end

function M:get_diagnostic(code, source)
  local items = self.diagnostics_by_code[tostring(code)] or {}
  if not source or source == "" then
    return items[1]
  end
  for _, item in ipairs(items) do
    if item.source == source then
      return item
    end
  end
  return items[1]
end

function M:hover(symbol)
  return markdown_text(build_hover_value(symbol))
end

function M:completion_documentation(symbol)
  local parts = {}
  if symbol.signature_short and symbol.signature_short ~= "" then
    parts[#parts + 1] = "```cangjie\n" .. symbol.signature_short .. "\n```"
  end
  if symbol.summary_short_md and symbol.summary_short_md ~= "" then
    parts[#parts + 1] = symbol.summary_short_md
  end
  if symbol.example_snippets_short and not vim.tbl_isempty(symbol.example_snippets_short) then
    parts[#parts + 1] = "示例：\n- `" .. table.concat(symbol.example_snippets_short, "`\n- `") .. "`"
  end
  local deprecated = format_deprecated(symbol)
  if deprecated then
    parts[#parts + 1] = deprecated
  end
  return markdown_text(table.concat(parts, "\n\n"))
end

function M:signature_information(symbol)
  local callable = symbol.callable
  if not callable then
    return nil
  end

  local parameters = {}
  for _, param in ipairs(callable.params or {}) do
    parameters[#parameters + 1] = {
      label = param.label,
      documentation = build_parameter_documentation(param),
    }
  end

  local docs = {}
  if symbol.summary_short_md and symbol.summary_short_md ~= "" then
    docs[#docs + 1] = symbol.summary_short_md
  end
  if symbol.returns_md and symbol.returns_md ~= "" then
    docs[#docs + 1] = "返回值：\n" .. symbol.returns_md
  end

  return {
    label = symbol.signature,
    documentation = markdown_text(table.concat(docs, "\n\n")),
    parameters = parameters,
  }
end

function M:to_completion_item(symbol)
  return {
    label = symbol.display,
    detail = symbol.signature_short or symbol.signature,
    documentation = self:completion_documentation(symbol),
    data = {
      docs_index_id = symbol.id,
      docs_index_fqname = symbol.fqname,
    },
  }
end

function M:resolve_completion_item(item)
  if not item or not item.data then
    return item
  end
  local symbol = self:get_symbol(item.data.docs_index_id) or self:get_symbol(item.data.docs_index_fqname)
  if not symbol then
    return item
  end
  item.detail = symbol.signature_short or symbol.signature
  item.documentation = self:completion_documentation(symbol)
  return item
end

function M:code_description_href(code, source)
  local diagnostic = self:get_diagnostic(code, source)
  if not diagnostic then
    return nil
  end
  return diagnostic.page_url .. (diagnostic.anchor and ("#" .. diagnostic.anchor) or "")
end

function M:reload()
  return M.load(self.path)
end

return M
