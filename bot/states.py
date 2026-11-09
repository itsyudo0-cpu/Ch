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


class WelcomeStates(StatesGroup):
    waiting_for_image = State()


class AdminStates(StatesGroup):
    waiting_for_mongo_url = State()


class ChannelTemplateStates(StatesGroup):
    waiting_for_template = State()
