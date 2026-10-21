local UIManager = require("ui/uimanager")
local logger = require("logger")

local I18N = require("mybooks_i18n")
local ListView = require("mybooks_list_view")
local MenuUI = require("mybooks_menu_ui")
local Metrics = require("mybooks_metrics")
local Page = require("mybooks_page")
local State = require("mybooks_state")
local Thumbnails = require("mybooks_thumbnails")
local Toast = require("mybooks_toast")

local M = {}

local ENTITIES = { amp = "&", lt = "<", gt = ">", quot = '"', apos = "'", nbsp = " " }

local function utf8_char(code)
    if code < 128 then
        return string.char(code)
    end
    if code < 2048 then
        return string.char(192 + math.floor(code / 64), 128 + code % 64)
    end
    if code < 65536 then
        return string.char(224 + math.floor(code / 4096), 128 + math.floor(code / 64) % 64, 128 + code % 64)
    end
    return "?"
end

local function entity(name)
    local mapped = ENTITIES[name]
    if mapped then
        return mapped
    end
    local decimal = name:match("^#(%d+)$")
    if decimal then
        return utf8_char(tonumber(decimal))
    end
    local hex = name:match("^#[xX](%x+)$")
    if hex then
        return utf8_char(tonumber(hex, 16))
    end
    return "&" .. name .. ";"
end

local function plain_text(html)
    html = tostring(html or "")
    html = html:gsub("<[Bb][Rr]%s*/?>", "\n")
    html = html:gsub("</[Pp]>", "\n")
    html = html:gsub("<[^>]+>", "")
    html = html:gsub("&(#?%w+);", entity)
    html = html:gsub("[ \t]+", " ")
    html = html:gsub("\n\n+", "\n\n")
    return (html:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function as_text(value)
    if type(value) == "table" then
        local parts = {}
        for _, item in ipairs(value) do
            parts[#parts + 1] = tostring(item)
        end
        return table.concat(parts, " / ")
    end
    return value
end

local function meta_item(label, value, hit)
    if value == nil or value == "" then
        return nil
    end
    return {
        kind = "row",
        title = I18N.T(label),
        sub = tostring(as_text(value)),
        hit = hit,
    }
end

function M.show(api, book)
    if not book or not book.id then
        return nil
    end
    Toast.loading(I18N.T("loading"))
    local rsp, err = api:get_abs("/api/book/" .. tostring(book.id), { track = "0" })
    Toast.dismiss()
    if err or not rsp or not rsp.book then
        Toast.error(ListView.error_text(err or "json"))
        return nil
    end
    local detail = rsp.book
    local files = detail.files or {}
    local formats = {}
    for _, file in ipairs(files) do
        formats[#formats + 1] = tostring(file.format or ""):upper()
    end
    State.set_book(detail.id, {
        title = detail.title,
        author = detail.author,
        img = detail.img,
        thumb = detail.thumb,
        formats = formats,
    })
    logger.dbg("MyBooks: detail loaded", detail.id, #files)

    local page
    local expanded = false
    local description = plain_text(detail.comments)

    local function build()
        local rows = {
            {
                kind = "row",
                title = detail.title,
                sub = detail.author,
                image = Thumbnails.get(detail) or Thumbnails.get(book),
                h = Metrics.dp(164),
            },
        }
        local state = detail.state or {}
        local status = {}
        if state.favorite == true or state.favorite == 1 then
            status[#status + 1] = I18N.T("favorite")
        end
        if state.wants == true or state.wants == 1 then
            status[#status + 1] = I18N.T("to_read")
        end
        if state.read_state == 1 then
            status[#status + 1] = I18N.T("reading")
        elseif state.read_state == 2 then
            status[#status + 1] = I18N.T("finished")
        end
        if #status > 0 then
            rows[#rows + 1] = meta_item("status", table.concat(status, " · "))
        end

        local series = detail.series
        if series and series ~= "" then
            if detail.series_index then
                series = string.format("%s #%s", series, detail.series_index)
            end
            rows[#rows + 1] = meta_item("series", series)
        end
        if detail.rating and tonumber(detail.rating) and tonumber(detail.rating) > 0 then
            rows[#rows + 1] = meta_item("rating", string.format("%d/10", tonumber(detail.rating)))
        end
        rows[#rows + 1] = meta_item("tags", detail.tag)
        rows[#rows + 1] = meta_item("publisher", detail.publisher)
        rows[#rows + 1] = meta_item("published", detail.pubdate)
        rows[#rows + 1] = meta_item("isbn", detail.isbn)
        rows[#rows + 1] = meta_item("language", detail.languages)

        if #files > 0 then
            rows[#rows + 1] = MenuUI.header(I18N.T("formats"))
            for _, file in ipairs(files) do
                rows[#rows + 1] = {
                    kind = "row",
                    title = tostring(file.format or ""):upper(),
                    badge = Metrics.format_size(file.size or 0),
                    hit = function()
                        require("mybooks_download").start(api, detail, file.format)
                    end,
                }
            end
        end
        local stats = detail.reading_stats or {}
        if #stats > 0 then
            rows[#rows + 1] = MenuUI.header(I18N.T("reading_stats"))
            for _, item in ipairs(stats) do
                rows[#rows + 1] = {
                    kind = "row",
                    title = tostring(item.format or ""):upper(),
                    sub = Metrics.format_percent(item.progress_percent or 0) .. " · " .. Metrics.format_duration(item.total_seconds or 0),
                    percent = item.progress_percent or 0,
                }
            end
        end

        rows[#rows + 1] = MenuUI.header(I18N.T("description"))
        rows[#rows + 1] = {
            kind = "text",
            text = description ~= "" and description or I18N.T("description_empty"),
            h = expanded and Metrics.dp(420) or Metrics.dp(120),
            hit = function()
                expanded = not expanded
                page:set_items(build(), false)
            end,
        }
        return rows
    end

    page = Page:new{
        title = detail.title or "",
        items = build(),
    }
    local function is_on(key)
        local value = (detail.state or {})[key]
        return value == true or value == 1
    end
    local function refresh_footer()
        local buttons = page.footer_buttons
        buttons[1].text = I18N.T(is_on("favorite") and "unfavorite" or "favorite")
        buttons[2].text = I18N.T(is_on("wants") and "unwant" or "to_read")
        buttons[3].text = I18N.T((detail.state or {}).read_state == 2 and "mark_unread" or "mark_read")
    end
    local function apply_state(changes)
        local Sync = require("mybooks_sync")
        local result = Sync.push_state(api, { book_id = detail.id, format = "epub" }, changes)
        if result and result.state then
            detail.state = result.state
            refresh_footer()
            page:set_items(build(), false)
        else
            Toast.error(I18N.T("err_network"))
        end
    end
    page.footer_buttons = {
        {
            text = I18N.T(is_on("favorite") and "unfavorite" or "favorite"),
            hit = function()
                apply_state({ favorite = not is_on("favorite") })
            end,
        },
        {
            text = I18N.T(is_on("wants") and "unwant" or "to_read"),
            hit = function()
                apply_state({ wants = not is_on("wants") })
            end,
        },
        {
            text = I18N.T((detail.state or {}).read_state == 2 and "mark_unread" or "mark_read"),
            hit = function()
                local finished = (detail.state or {}).read_state == 2
                apply_state({ read_state = finished and 0 or 2 })
            end,
        },
        {
            text = I18N.T("download"),
            hit = function()
                require("mybooks_download").start(api, detail)
            end,
        },
        {
            text = I18N.T("open"),
            hit = function()
                local Download = require("mybooks_download")
                local path = Download.local_path(detail)
                if path then
                    Download.open_file(path)
                else
                    Toast.show(I18N.T("no_local_file"))
                end
            end,
        },
    }
    UIManager:show(page)
    return page
end

return M
