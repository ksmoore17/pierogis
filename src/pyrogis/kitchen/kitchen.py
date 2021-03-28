import math
import multiprocessing  as mp
import os
import time
from typing import Callable

import imageio

from .menu import menu
from .order import Order
from .ticket import Ticket
from .. import Pierogi, Dish


class Kitchen:
    menu = menu

    _pool: mp.Pool

    @property
    def pool(self):
        if self._pool is None:
            self._pool = mp.Pool(self.processes)

        return self._pool

    def __init__(self, chef, processes: int = None):
        self.chef = chef
        if processes is None:
            processes = os.cpu_count()
        self.processes = processes
        self._pool = None

    def __getstate__(self):
        self_dict = self.__dict__.copy()
        del self_dict['pool']
        return self_dict

    def __setstate__(self, state):
        self.__dict__.update(state)

    @staticmethod
    def cook_ticket(
            chef,
            ticket: Ticket
    ) -> None:
        """
        cook a ticket with a thread pool
        """
        dish = chef.assemble_ticket(ticket, menu)

        cooked_dish = chef.cook_dish(dish)

        cooked_dish.save(ticket.output_filename)

    def _presave_ticket(self, frame, ticket: Ticket):
        raw_dir = os.path.join('/tmp', 'raw')
        if not os.path.isdir(raw_dir):
            os.makedirs(raw_dir)

        input_filename = os.path.join(raw_dir, os.path.basename(ticket.output_filename))
        writer = imageio.get_writer(input_filename)
        writer.append_data(frame)

        pierogi_desc = ticket.pierogis[ticket.base]
        ticket.files[pierogi_desc.files_key] = input_filename
        pierogi_desc.frame_index = 0

    def _auto_pilot(self, order: Order):
        """test some frames in the animation"""
        tickets = order.tickets

        # test with 5% of the frames, within 2 and 10
        seq_pilot_frames = 2

        frame_index = 0

        next_frame_index = frame_index + seq_pilot_frames
        next_tickets = tickets[frame_index:next_frame_index]
        frame_index = next_frame_index

        # sync cooking
        start = time.perf_counter()
        for ticket in next_tickets:
            self.cook_ticket(self.chef, ticket)
        seq_rate = seq_pilot_frames / (time.perf_counter() - start)

        next_frame_index = frame_index + 2
        next_tickets = tickets[frame_index:next_frame_index]
        frame_index = next_frame_index

        if order.presave is None:
            # sync cooking with presave frames
            presave_start = time.perf_counter()

            for ticket in next_tickets:
                frame = order.reader.get_next_data()
                self._presave_ticket(frame, ticket)
                self.cook_ticket(self.chef, ticket)

            presave_rate = seq_pilot_frames / (time.perf_counter() - presave_start)

            if presave_rate > seq_rate:
                order.presave = True
                seq_rate = presave_rate
            else:
                order.presave = False

        if order.cook_async is None:
            par_pilot_frames = max(2, min(round(len(tickets) * .05), 10))

            if order.presave:
                next_frame_index = frame_index + par_pilot_frames
                next_tickets = tickets[frame_index:next_frame_index]
                frame_index = next_frame_index

                # async cooking with presave frames
                par_presave_start = time.perf_counter()

                results = []

                for ticket in next_tickets:
                    frame = order.reader.get_next_data()
                    self._presave_ticket(frame, ticket)
                    results.append(self.pool.apply_async(self.cook_ticket, (self.chef, ticket)))

                for result in results:
                    result.wait()

                par_rate = par_pilot_frames / (time.perf_counter() - par_presave_start)

            else:
                # parallel cooking

                next_frame_index = frame_index + par_pilot_frames
                next_tickets = tickets[frame_index:next_frame_index]
                frame_index = next_frame_index

                par_start = time.perf_counter()

                results = []

                for ticket in next_tickets:
                    results.append(self.pool.apply_async(self.cook_ticket, (self.chef, ticket)))

                for result in results:
                    result.wait()

                par_rate = par_pilot_frames / (time.perf_counter() - par_start)

            if par_rate > seq_rate:
                order.cook_async = True

        return next_frame_index

    def queue_order(self, order: Order, start_callback: Callable, report_status: Callable):
        frames = len(order.tickets)

        digits = math.floor(math.log(frames, 10)) + 1

        cooked_dir = 'cooked'

        if frames > 0:
            if not os.path.isdir(cooked_dir):
                os.makedirs(cooked_dir)

        frame_index = 1

        tickets_to_cook = []

        for ticket in order.tickets:
            padded_frame_index = str(frame_index).zfill(digits)

            if frames > 1:
                output_filename = os.path.join(
                    cooked_dir,
                    order.order_name + '-' + padded_frame_index + '.png'
                )

                ticket.output_filename = output_filename

                if os.path.isfile(output_filename):
                    if order.resume:
                        continue
                    else:
                        os.remove(output_filename)
            else:
                output_filename = os.path.join(cooked_dir, order.order_name + '.png')

            ticket.output_filename = output_filename
            frame_index += 1

            tickets_to_cook.append(ticket)

        order.tickets = tickets_to_cook

        start_callback()

        report_status(order, status='preprocessing')

        processed_frame_index = 0
        if len(order.tickets) > 8 and (order.presave is None or order.cook_async is None):
            processed_frame_index = self._auto_pilot(order)

        next_tickets = order.tickets[processed_frame_index:]

        report_status(order, status='cooking')

        for ticket in next_tickets:
            if order.presave:
                frame = order.reader.get_next_data()
                self._presave_ticket(frame, ticket)

            if order.cook_async:
                self.pool.apply_async(
                    func=self.cook_ticket,
                    args=(self.chef, ticket)
                )

            else:
                self.cook_ticket(self.chef, ticket)

        if self.pool is not None:
            def close_callback():
                self.pool.close()
                self.pool.join()
        else:
            def close_callback():
                pass

        return close_callback

    def plate(
            self,
            order: Order,
            report_status: Callable = None
    ) -> str:
        """"""
        input_path = order.input_path
        order_name = order.order_name

        pierogis = []

        if os.path.isdir(input_path):
            # debug here
            for filename in sorted(os.listdir(input_path)):
                if filename.startswith(order_name):
                    frame_path = os.path.join(input_path, filename)
                    pierogis.append(Pierogi.from_path(path=frame_path, frame_index=0))
        elif os.path.isfile(input_path):
            reader = imageio.get_reader(input_path)

            for i in range(reader.count_frames()):
                pierogis.append(Pierogi.from_path(path=input_path, frame_index=i))

        dish = Dish(pierogis=pierogis)

        output_filename = order.output_filename
        fps = order.fps
        optimize = order.optimize
        frame_duration = order.duration

        if output_filename is None:
            if order_name is None:
                order_name = os.path.splitext(os.path.basename(input_path))[0]
            if dish.frames == 1:
                output_filename = order_name + '.png'
            else:
                output_filename = order_name + '.gif'

        def callback():
            report_status(
                order,
                advance=1
            )

        dish.save(
            output_filename,
            optimize,
            duration=frame_duration,
            fps=fps,
            callback=callback
        )

        return output_filename
