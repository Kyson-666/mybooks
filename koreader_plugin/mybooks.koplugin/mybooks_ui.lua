local ImageWidget = require("ui/widget/imagewidget")
local TextWidget = require("ui/widget/textwidget")

local Metrics = require("mybooks_metrics")

local M = {}

function M.text(text, opts)
    opts = opts or {}
    return TextWidget:new{
        text = tostring(text or ""),
        face = opts.face or Metrics.body_face(),
        max_width = opts.width,
        bold = opts.bold,
        fgcolor = opts.color or Metrics.color.text,
        padding = opts.padding or Metrics.dp(2),
    }
end

function M.cover(path, width, height)
    if not path then
        return nil
    end
    return ImageWidget:new{
        file = path,
        width = width,
        height = height,
        scale_factor = 0,
        alpha = true,
    }
end

function M.paint_cover(bb, path, x, y, w, h)
    local image = M.cover(path, w, h)
    if not image then
        bb:paintRect(x, y, w, h, Metrics.color.line)
        return
    end
    local size = image:getSize()
    image:paintTo(bb, x + math.floor((w - size.w) / 2), y + math.floor((h - size.h) / 2))
    image:free()
end

function M.circle(bb, cx, cy, radius, color)
    local r2 = radius * radius
    for dy = -radius, radius do
        local dx = math.floor(math.sqrt(math.max(0, r2 - dy * dy)))
        bb:paintRect(cx - dx, cy + dy, dx * 2, 1, color or Metrics.color.line)
    end
end

function M.hit_rect(x, y, w, h, hit)
    return { x1 = x, y1 = y, x2 = x + w, y2 = y + h, hit = hit }
end

function M.contains(rect, pos)
    return pos.x >= rect.x1 and pos.x <= rect.x2 and pos.y >= rect.y1 and pos.y <= rect.y2
end

return M
