local Dispatcher = require("dispatcher")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local logger = require("logger")

local I18N = require("mybooks_i18n")
local State = require("mybooks_state")

local MyBooks = WidgetContainer:extend{
    name = "mybooks",
    is_doc_only = false,
}

function MyBooks:init()
    if self.ui and self.ui.menu then
        self.ui.menu:registerToMainMenu(self)
    end
    Dispatcher:registerAction("mybooks_open_home", {
        category = "none",
        event = "MyBooksOpenHome",
        title = I18N.T("app_title"),
        general = true,
    })
    logger.dbg("MyBooks: plugin initialized", State.device_id())
end

function MyBooks:addToMainMenu(menu_items)
    menu_items.mybooks = {
        text = I18N.T("app_title"),
        sorting_hint = "tools",
        callback = function()
            self:open_home()
        end,
    }
end

function MyBooks:open_home()
    local api = State.api()
    if not api then
        require("mybooks_signin_page").show()
        return
    end
    require("mybooks_home").show(api)
end

function MyBooks:onMyBooksOpenHome()
    self:open_home()
    return true
end

return MyBooks
