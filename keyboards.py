from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def main_menu(is_admin=False):
    rows = [
        [KeyboardButton(text="📦 Забронювати обладнання")],
        [KeyboardButton(text="📋 Мої бронювання")],
        [KeyboardButton(text="ℹ️ Інформація")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="⚙️ Адмін-панель")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Надіслати номер телефону", request_contact=True)],
            [KeyboardButton(text="✍️ Ввести номер вручну")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def info_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Мої дані", callback_data="info_my_data")],
        [InlineKeyboardButton(text="📋 Правила користування", callback_data="info_rules")],
    ])

def equipment_keyboard(equipment_rows, selected):
    buttons = []
    for e in equipment_rows:
        if e["disabled"]:
            continue
        qty = selected.get(e["id"], 0)
        label = f"{'✅ ' if qty else ''}{e['name']} ({qty})"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"eq:{e['id']}")])
    buttons.append([InlineKeyboardButton(text="➡️ Готово", callback_data="eq_done")])
    buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="booking_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def quantity_keyboard(current, maximum):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="−", callback_data="qty:minus"),
            InlineKeyboardButton(text=str(current), callback_data="qty:noop"),
            InlineKeyboardButton(text="+", callback_data="qty:plus"),
        ],
        [InlineKeyboardButton(text="💾 Додати до бронювання", callback_data="qty_save")],
    ])

def booking_edit_keyboard(booking_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Змінити бронювання", callback_data=f"edit_booking:{booking_id}")],
        [InlineKeyboardButton(text="❌ Скасувати бронювання", callback_data=f"cancel_booking:{booking_id}")],
    ])

def rules_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Відкрити правила", callback_data="show_rules")],
        [InlineKeyboardButton(text="☑️ Я погоджуюсь з правилами", callback_data="agree_rules")],
    ])

def final_booking_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Правила користування", callback_data="show_rules")],
        [InlineKeyboardButton(text="☑️ Я погоджуюсь з правилами", callback_data="agree_rules")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="booking_cancel")],
    ])

def admin_booking_keyboard(booking_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"adm:approve:{booking_id}"),
            InlineKeyboardButton(text="✏️ Змінити час", callback_data=f"adm:time:{booking_id}"),
        ],
        [InlineKeyboardButton(text="❌ Відхилити", callback_data=f"adm:reject:{booking_id}")],
        [InlineKeyboardButton(text="📦 Видати обладнання", callback_data=f"adm:issue:{booking_id}")],
        [InlineKeyboardButton(text="🔄 Прийняти повернення", callback_data=f"adm:return:{booking_id}")],
    ])

def admin_panel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Нові заявки", callback_data="admin_pending")],
        [InlineKeyboardButton(text="📅 Усі бронювання", callback_data="admin_bookings")],
        [InlineKeyboardButton(text="📦 Обладнання", callback_data="admin_equipment")],
        [InlineKeyboardButton(text="➕ Створити бронювання", callback_data="admin_create")],
    ])
