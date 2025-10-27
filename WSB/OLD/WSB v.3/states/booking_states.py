# states/booking_states.py
from telebot.handler_backends import State, StatesGroup

class BookingStates(StatesGroup):
    # Состояния для основного процесса бронирования (если будете его тоже переводить на FSM)
    choose_category = State()
    choose_equipment = State()
    choose_date = State()
    choose_slot = State()
    choose_start_time = State()
    choose_duration = State()
    confirm_details = State() # Финальное подтверждение перед созданием

    # Состояние ожидания подтверждения СТАРТА брони (после уведомления)
    awaiting_start_confirmation = State()