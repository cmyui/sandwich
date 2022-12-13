from __future__ import annotations

import getpass
import os
import traceback

from chatgpt import Conversation


def create_conversation() -> Conversation:
    kwargs: dict[str, object] = {"timeout": 500}

    if not os.path.exists(Conversation.DEFAULT_CONFIG_PATH):
        kwargs["email"] = input("Email Address: ")
        kwargs["password"] = getpass.getpass("Password: ")

    # TODO: handle auth failure
    try:
        conversation = Conversation(**kwargs)
    except Exception as exc:
        traceback.print_exc()
        print(" ^^ Failure while creating conversation:")
        breakpoint()
        raise

    return conversation


def send_message(conversation: Conversation, message: str) -> str:
    try:
        response = conversation.chat(message,  # type: ignore
                                     retry_on_401=False)
    except Exception as exc:
        traceback.print_exc()
        print(" ^^ Failure while sending message:")
        breakpoint()
        raise

    return response
