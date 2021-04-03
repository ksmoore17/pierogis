import argparse
from abc import ABC, abstractmethod

from ..ticket import Ticket, IngredientDesc


class Filling(ABC):
    type_name = None

    @classmethod
    def generate_ticket(
            cls,
            ticket: Ticket,
            path: str = None,
            frame_index: int = 0,
            target_pierogi_uuid: str = None,
            **kwargs
    ) -> Ticket:
        """
        add a description of a quantize recipe
        """

        if path is not None:
            target_pierogi_uuid = ticket.add_pierogi(path, frame_index)
            ticket.base = target_pierogi_uuid

        if cls.type_name is not None:
            ingredient_desc = IngredientDesc(
                type_name=cls.type_name,
                kwargs=kwargs
            )

            ingredient_uuid = ticket.add_ingredient_desc(ingredient_desc)

            ticket.extend_recipe([ingredient_uuid])

        return ticket

    @classmethod
    def get_parser(cls):
        """
        get a parser for this menu item
        """
        parser = argparse.ArgumentParser(add_help=False)
        parser.set_defaults(generate_ticket=cls.generate_ticket)

        parser.add_argument(
            '--presave',
            action='store_true',
            default=None,
            help="presave frames for cooking animations"
        )
        parser.add_argument(
            '--async',
            action='store_true',
            default=None,
            help="use multiple python processes to cook frames"
        )
        parser.add_argument(
            '--processes',
            type=int,
            help="number of async processes to use"
        )

        # get extra parser arguments from subclasses
        cls.add_parser_arguments(parser)

        return parser

    @classmethod
    @abstractmethod
    def add_parser_arguments(cls, parser):
        pass
