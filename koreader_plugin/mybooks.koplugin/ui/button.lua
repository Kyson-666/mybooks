--[[
 Draw a button with text.
 PoxenStudio@2026
]]

local Metrics = require("mybooks_metrics")
local UI = require("mybooks_ui")

local M = {}

function M.draw(bb, x, y, w, h, text, opts)
    opts = opts or {}
    local inset = opts.inset or Metrics.dp(2)
    UI.card(bb, x + inset, y + inset, w - inset * 2, h - inset * 2, {
        radius = opts.radius or Metrics.dp(6),
        border = opts.border or Metrics.color.edge,
        shadow = false,
    })
    local label = UI.text(text or "", {
        face = opts.face or Metrics.body_face(),
        color = opts.color,
        bold = opts.bold,
        padding = Metrics.dp(2),
        width = math.max(Metrics.dp(20), w - inset * 2 - Metrics.dp(8)),
    })
    local size = label:getSize()
    label:paintTo(bb, x + math.floor((w - size.w) / 2), y + math.floor((h - size.h) / 2))
    label:free()
end

return M
