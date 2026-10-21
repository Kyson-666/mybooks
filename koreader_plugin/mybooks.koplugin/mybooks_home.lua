local UIManager = require("ui/uimanager")
local logger = require("logger")

local DeviceInfo = require("mybooks_device")
local I18N = require("mybooks_i18n")
local MenuUI = require("mybooks_menu_ui")
local Metrics = require("mybooks_metrics")
local Page = require("mybooks_page")
local State = require("mybooks_state")
local Thumbnails = require("mybooks_thumbnails")
local Toast = require("mybooks_toast")
local UI = require("mybooks_ui")

local M = {}

local SECTION_LABELS = {
    favorites = "my_favorites",
    wants = "my_wishlist",
    read_done = "my_read",
    categories = "categories",
    tags = "tags",
    authors = "authors",
    recent = "latest",
}

local META_KINDS = {
    categories = "category",
    tags = "tag",
    authors = "author",
}

local HomePage = Page:extend{
    show_back = false,
}

local function first_char(text)
    text = tostring(text or "")
    local byte = text:byte(1)
    if not byte then
        return "?"
    end
    local length = 1
    if byte >= 240 then
        length = 4
    elseif byte >= 224 then
        length = 3
    elseif byte >= 192 then
        length = 2
    end
    return text:sub(1, length)
end

function HomePage:init()
    Page.init(self)
    self.title = I18N.T("app_title")
    self.footer_h = 0
    self.list_h = self.dimen.h - self.header_h
    self.header_buttons = {
        {
            text = "⚙",
            hit = function()
                require("mybooks_settings_page").show(self.api)
            end,
        },
        {
            text = "≡",
            hit = function()
                require("mybooks_browse").show_tree(self.api)
            end,
        },
    }
    self.data = State.home()
end

function HomePage:load_home()
    local rsp, err = self.api:get("/home")
    if err then
        logger.warn("MyBooks: home load failed", err)
        Toast.error(require("mybooks_list_view").error_text(err))
        return false
    end
    State.set_home(rsp)
    self.data = rsp
    local profile = rsp.profile or {}
    if profile.avatar and profile.avatar ~= "" then
        local cached = State.setting("avatar_url", "")
        local path = DeviceInfo.cache_dir() .. "/avatar.jpg"
        if cached ~= profile.avatar or not DeviceInfo.file_exists(path) then
            local part = path .. ".part"
            local saved = self.api:fetch_file(self.api:resolve(profile.avatar), part)
            if saved then
                os.rename(part, path)
                State.set_setting("avatar_url", profile.avatar)
            else
                pcall(os.remove, part)
            end
        end
    end
    self:refresh()
    Thumbnails.prefetch(self.api, rsp.reading_now, 3)
    self:refresh()
    return true
end

function HomePage:open_book(book)
    local Download = require("mybooks_download")
    local path = Download.local_path(book)
    if path then
        Download.open_file(path)
        return
    end
    require("mybooks_detail").show(self.api, book)
end

function HomePage:open_section(kind, title)
    local Browse = require("mybooks_browse")
    local meta = META_KINDS[kind]
    if meta then
        Browse.show_meta(self.api, meta)
    else
        Browse.show_books(self.api, kind, nil, title)
    end
end

function HomePage:_paint_stats(bb, x, y, w)
    local pad = self.pad
    local profile = self.data.profile or {}
    local stats = self.data.stats or {}
    local avatar = math.floor(Metrics.dp(44))
    local cy = y + Metrics.dp(4)
    local path = DeviceInfo.cache_dir() .. "/avatar.jpg"
    if DeviceInfo.file_exists(path) then
        UI.paint_cover(bb, path, x + pad, cy, avatar, avatar)
    else
        local cx = x + pad + math.floor(avatar / 2)
        UI.circle(bb, cx, cy + math.floor(avatar / 2), math.floor(avatar / 2) - 1, Metrics.color.line)
        local text = UI.text(first_char(profile.nickname), { face = Metrics.title_face() })
        local size = text:getSize()
        text:paintTo(bb, cx - math.floor(size.w / 2), cy + math.floor((avatar - size.h) / 2))
        text:free()
    end

    local left = x + pad + avatar + pad
    local name = UI.text(profile.nickname or I18N.T("not_logged_in"), {
        width = w - (left - x) - pad,
        bold = true,
    })
    local name_size = name:getSize()
    name:paintTo(bb, left, cy)
    name:free()

    local status = stats.book_status or {}
    local line = string.format(
        "%s · %s %d · %s %d · %s %d",
        Metrics.format_duration(stats.total_seconds or 0),
        I18N.T("reading"), status.reading or 0,
        I18N.T("finished"), status.finished or 0,
        I18N.T("to_read"), status.to_read or 0
    )
    local sub = UI.text(line, { face = Metrics.small_face(), color = Metrics.color.muted, width = w - (left - x) - pad })
    sub:paintTo(bb, left, cy + name_size.h + Metrics.dp(2))
    sub:free()

    self.hit_rows[#self.hit_rows + 1] = UI.hit_rect(x, y, math.floor(w * 0.6), Metrics.dp(56), function()
        require("mybooks_settings_page").show(self.api)
    end)
    self.hit_rows[#self.hit_rows + 1] = UI.hit_rect(left, cy + name_size.h, w - (left - x) - pad, Metrics.dp(24), function()
        local streak = stats.streak or {}
        Toast.show(string.format(
            "%s · %s",
            I18N.T("today_reading", Metrics.format_duration(stats.today_seconds or 0)),
            I18N.T("streak_days", streak.current or 0)
        ))
    end)
    return Metrics.dp(56)
end

function HomePage:reading_metrics(w)
    local pad = self.pad
    local card_w = math.floor((w - pad * 4) / 3)
    local cover_h = math.min(math.floor(card_w * 1.4), Metrics.dp(180))
    return card_w, cover_h, cover_h + Metrics.dp(40)
end

function HomePage:_paint_reading(bb, x, y, w)
    local pad = self.pad
    local books = self.data.reading_now or {}
    local header_h = Metrics.dp(30)
    local title = UI.text(I18N.T("home_reading"), { bold = true })
    local title_size = title:getSize()
    title:paintTo(bb, x + pad, y + math.floor((header_h - title_size.h) / 2))
    title:free()
    local all = UI.text(I18N.T("view_all") .. " ›", { face = Metrics.small_face(), color = Metrics.color.muted })
    local all_size = all:getSize()
    all:paintTo(bb, x + w - pad - all_size.w, y + math.floor((header_h - all_size.h) / 2))
    all:free()
    self.hit_rows[#self.hit_rows + 1] = UI.hit_rect(x + w - pad - all_size.w - pad, y, all_size.w + pad * 2, header_h, function()
        require("mybooks_browse").show_books(self.api, "reading", nil, I18N.T("reading_now"))
    end)

    if #books == 0 then
        local empty = UI.text(I18N.T("no_reading_now"), { face = Metrics.small_face(), color = Metrics.color.muted })
        empty:paintTo(bb, x + pad, y + header_h)
        empty:free()
        return header_h + Metrics.dp(32)
    end

    local card_w, cover_h, card_h = self:reading_metrics(w)
    local count = math.min(3, #books)
    for index = 1, count do
        local book = books[index]
        local cx = x + pad + (index - 1) * (card_w + pad)
        local cy = y + header_h
        UI.paint_cover(bb, Thumbnails.get(book), cx, cy, card_w, cover_h)
        local label = UI.text(book.title, {
            face = Metrics.small_face(),
            width = card_w,
            padding = 0,
        })
        label:paintTo(bb, cx, cy + cover_h + Metrics.dp(2))
        label:free()
        local percent = UI.text(Metrics.format_percent(book.progress_percent or 0), {
            face = Metrics.small_face(),
            color = Metrics.color.muted,
            padding = 0,
        })
        percent:paintTo(bb, cx, cy + cover_h + Metrics.dp(20))
        percent:free()
        local rect = UI.hit_rect(cx, cy, card_w, card_h, function()
            self:open_book(book)
        end)
        rect.on_hold = function()
            require("mybooks_browse").book_actions(self.api, book)
        end
        self.hit_rows[#self.hit_rows + 1] = rect
    end
    return header_h + card_h
end

function HomePage:paintContent(bb, x, y)
    local pad = self.pad
    local w = self.dimen.w
    local data = self.data or {}
    self.data = data

    local row_h = Metrics.dp(48)
    local rows_count = 8
    local _, _, card_h = self:reading_metrics(w)
    local content_h = Metrics.dp(56) + Metrics.dp(30) + card_h + Metrics.dp(30)
        + rows_count * row_h + pad * 2
    self._content_h = content_h
    self.offset = math.min(self.offset, math.max(0, content_h - self.list_h))

    local top = y + pad - self.offset
    top = top + self:_paint_stats(bb, x, top, w)
    top = top + self:_paint_reading(bb, x, top, w)

    local header_h = Metrics.dp(30)
    local section = UI.text(I18N.T("browse_section"), { bold = true })
    local section_size = section:getSize()
    section:paintTo(bb, x + pad, top + math.floor((header_h - section_size.h) / 2))
    section:free()
    top = top + header_h

    local section_labels = {}
    local counts = {}
    for _, item in ipairs(data.sections or {}) do
        counts[item.kind] = item.count
        section_labels[item.kind] = item.title
    end

    local rows = {
        { title = I18N.T("search"), action = function()
            require("mybooks_browse").search(self.api)
        end },
    }
    for _, kind in ipairs({ "favorites", "wants", "read_done", "categories", "tags", "authors", "recent" }) do
        rows[#rows + 1] = {
            title = section_labels[kind] or I18N.T(SECTION_LABELS[kind]),
            badge = counts[kind],
            action = function()
                self:open_section(kind, section_labels[kind] or I18N.T(SECTION_LABELS[kind]))
            end,
        }
    end

    local row_y = top
    for _, row in ipairs(rows) do
        local item = MenuUI.icon_row(nil, row.title, row.badge)
        self:_paint_row(bb, item, x, row_y, w, row_h)
        self.hit_rows[#self.hit_rows + 1] = UI.hit_rect(x, row_y, w, row_h, row.action)
        bb:paintRect(x + pad, row_y + row_h - 1, w - pad * 2, 1, Metrics.color.line)
        row_y = row_y + row_h
    end
end

function HomePage:scroll(delta)
    self.offset = math.min(
        math.max(0, (self._content_h or 0) - self.list_h),
        math.max(0, self.offset + delta * math.floor(self.list_h * 0.75))
    )
    logger.dbg("MyBooks: home scroll", self.offset)
    self:refresh()
end

function HomePage:onSwipeNorth()
    self:scroll(1)
    return true
end

function HomePage:onSwipeSouth()
    self:scroll(-1)
    return true
end

function HomePage:onLeft()
    self:scroll(-1)
    return true
end

function HomePage:onRight()
    self:scroll(1)
    return true
end

function HomePage:onUp()
    self:scroll(-1)
    return true
end

function HomePage:onDown()
    self:scroll(1)
    return true
end

function M.show(api, opts)
    opts = opts or {}
    local page = HomePage:new{
        api = api,
        on_close = opts.on_close,
    }
    UIManager:show(page)
    local cached = page.data ~= nil
    if not cached then
        Toast.loading(I18N.T("loading"))
    end
    local ok = page:load_home()
    if not cached and ok then
        Toast.dismiss()
    end
    return page
end

return M
