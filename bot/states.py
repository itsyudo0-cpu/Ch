from aiogram.fsm.state import State, StatesGroup


class ConnectChannelStates(StatesGroup):
    waiting_for_channel = State()


class NewPostStates(StatesGroup):
    choosing_channel = State()
    waiting_for_content = State()
    managing_buttons = State()
    waiting_for_buttons_input = State()
    previewing = State()


class EditPublishedPostStates(StatesGroup):
    managing_buttons = State()
    waiting_for_buttons_input = State()
